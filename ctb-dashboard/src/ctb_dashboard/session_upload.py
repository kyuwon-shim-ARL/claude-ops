"""Files from a phone or a desktop into the session's project.

The dashboard can already type into a session; this lets it hand that session
something to work on. Where the file lands is deliberately boring -- one
``.ctb-uploads`` directory at the project root, the same place whatever
subdirectory the pane happens to sit in -- because the user says what to do
with it in words afterwards ("move the csv in .ctb-uploads into data/").

Everything here is written against a hostile caller, because the token is a
single shared secret in localStorage and a write primitive is worth more to an
attacker than the prompt endpoint next to it:

  * the destination is never taken on trust from tmux. An empty answer (tmux
    failed) or a path outside the projects root is a refusal, not a write.
  * the directory is opened once, with O_NOFOLLOW, and every file is created
    through that descriptor with O_EXCL|O_NOFOLLOW. A swapped symlink between
    the check and the write therefore cannot redirect the bytes -- there is no
    second path lookup to poison.
  * the size ceiling is on bytes actually received, not on Content-Length,
    which a caller writes and can lie about.
  * no path below the projects root is ever resolved twice. The destination is
    reached by opening one component at a time with O_NOFOLLOW, from a root
    taken from configuration -- so a directory swapped for a symlink between
    the check and the write has nothing to capture. Resolving once and reusing
    the string was not enough: O_NOFOLLOW on the last component still let a
    swapped *ancestor* redirect the whole thing.
  * the quota is reserved, not merely observed. Two requests that both read
    "there is room" would both write.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import threading
import unicodedata
from pathlib import Path

from .session_create import projects_root

logger = logging.getLogger(__name__)

UPLOAD_DIRNAME = ".ctb-uploads"

# A phone photo is 2-5 MB, a screenshot 200 KB, a csv anything. 25 MB takes the
# useful cases and leaves "stream a video into the repo" out.
MAX_FILE_BYTES = int(os.environ.get("CTB_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024)))
# What the directory may hold in total. Without this the rate limit alone
# permits gigabytes a minute into someone's project.
MAX_DIR_BYTES = int(os.environ.get("CTB_UPLOAD_DIR_MAX_BYTES", str(300 * 1024 * 1024)))

# How long a single upload may take to arrive. Without a deadline a caller
# that opens a request and then sends one byte a minute holds two descriptors
# for as long as it likes, and the rate limiter -- which counts starts, not
# outstanding requests -- hands out a fresh batch every window.
RECEIVE_TIMEOUT = float(os.environ.get("CTB_UPLOAD_TIMEOUT", "120"))
# And how many may be in flight at once, which is what actually bounds the
# descriptors held.
MAX_CONCURRENT = int(os.environ.get("CTB_UPLOAD_CONCURRENCY", "4"))

_MAX_NAME_BYTES = 100
_COLLISION_TRIES = 50

# Control characters, path separators and the Windows-reserved set. NUL would
# truncate the name at the syscall boundary; the rest are how a name becomes a
# path.
_BAD_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


class UploadError(Exception):
    """A refusal with a machine-readable code and an HTTP status."""

    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


def safe_name(raw: str) -> str:
    """A filename that cannot be a path, a traversal, or an empty string.

    NFC first: iOS sends decomposed Hangul and Latin accents, so the same name
    typed on a Mac and picked on a phone would otherwise be two different files
    that look identical in a listing.
    """
    name = unicodedata.normalize("NFC", raw or "")
    # basename on both conventions -- a browser on Windows sends backslashes.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _BAD_CHARS.sub("_", name).strip().strip(".")
    if not name:
        return "upload"
    encoded = name.encode("utf-8")
    if len(encoded) > _MAX_NAME_BYTES:
        stem, dot, ext = name.rpartition(".")
        # A "suffix" longer than the budget is not a suffix, it is the name.
        if dot and len(ext.encode("utf-8")) <= 16:
            keep = _MAX_NAME_BYTES - len(ext.encode("utf-8")) - 1
            name = _truncate_bytes(stem, keep) + "." + ext
        else:
            name = _truncate_bytes(name, _MAX_NAME_BYTES)
        name = name.strip().strip(".") or "upload"
    return name


def _truncate_bytes(text: str, limit: int) -> str:
    """Cut to `limit` bytes without splitting a character."""
    encoded = text.encode("utf-8")[: max(limit, 1)]
    return encoded.decode("utf-8", "ignore")


def project_for(session_path: str) -> tuple[Path, str]:
    """-> (projects root, project directory name) for a session's pane.

    `session_path` is whatever tmux reported, including "" when the lookup
    failed -- which is why this refuses rather than defaulting to anything.
    Anchoring at the project root instead of the pane's own cwd means a session
    that has cd'd into `src/` still uploads to the one place the user knows.

    Only the *name* comes back, never a path to walk again: the caller opens it
    from the root with O_NOFOLLOW, so nothing that happens to the directory
    between here and there can redirect the write. A project directory that is
    itself a symlink out of the root therefore cannot be uploaded to -- it
    resolves outside and is refused below, which is the safe answer.
    """
    raw = (session_path or "").strip()
    if not raw or not raw.startswith("/"):
        raise UploadError("no_path", 409, "세션의 작업 디렉토리를 알 수 없습니다")
    try:
        pane = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError):
        raise UploadError("no_path", 409, "세션의 작업 디렉토리를 열 수 없습니다")
    if not pane.is_dir():
        raise UploadError("no_path", 409, "세션의 작업 디렉토리가 디렉토리가 아닙니다")

    root = projects_root()
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise UploadError("no_root", 409, "프로젝트 루트를 찾을 수 없습니다")

    if root not in pane.parents:
        raise UploadError(
            "outside_root",
            409,
            f"세션이 프로젝트 루트({root}) 밖에 있어 업로드할 수 없습니다",
        )
    # The first component under the root is the project; deeper components are
    # the session's own wandering.
    return root, pane.relative_to(root).parts[0]


def open_upload_dir(root: Path, project: str) -> int:
    """Descriptor for the project's upload directory, opened a step at a time.

    Every component below the root is opened with O_NOFOLLOW relative to the
    one above it, so a symlink swapped in anywhere along the way is refused
    rather than followed -- including the project directory itself, which an
    earlier version resolved once and then re-opened by path.

    Synchronous, and called synchronously: an earlier version ran this in an
    executor and handed the descriptor back through an await. Cancelling an
    executor call does not stop the thread, so the worker could still be
    opening descriptors after the caller had given up and "cleaned up" -- or
    return one into a coroutine that was never resumed to receive it. There is
    nothing here worth a thread: these are local-filesystem syscalls.
    """
    try:
        # The root is configuration, not attacker input; if it can be swapped
        # the account is already lost, and refusing a symlinked root would
        # break a perfectly ordinary ~/projects -> /data/projects setup.
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as e:
        raise UploadError("no_root", 409, f"프로젝트 루트를 열 수 없습니다: {e}")

    project_fd = None
    try:
        project_fd = _open_child(root_fd, project, "프로젝트 디렉토리")
        try:
            os.mkdir(UPLOAD_DIRNAME, 0o700, dir_fd=project_fd)
            created = True
        except FileExistsError:
            created = False
        except OSError as e:
            raise UploadError("mkdir_failed", 500, f"업로드 폴더를 만들 수 없습니다: {e}")

        fd = _open_child(project_fd, UPLOAD_DIRNAME, UPLOAD_DIRNAME)
        if created:
            _write_self_ignore(fd)
        return fd
    finally:
        # The intermediates have done their job the moment the next one is
        # open; only the caller's descriptor outlives this call.
        for intermediate in (project_fd, root_fd):
            if intermediate is not None:
                try:
                    os.close(intermediate)
                except OSError:
                    pass


def _open_child(parent_fd: int, name: str, label: str) -> int:
    """One component down, refusing a symlink."""
    try:
        return os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UploadError(
                "unsafe_dir", 409,
                f"{label} 가 심볼릭 링크입니다 — 업로드를 거부합니다",
            )
        if e.errno == errno.ENOENT:
            raise UploadError("no_path", 409, f"{label} 를 찾을 수 없습니다")
        raise UploadError("mkdir_failed", 500, f"{label} 를 열 수 없습니다: {e}")


def _write_self_ignore(dir_fd: int) -> None:
    """`.gitignore` holding `*`, so the directory hides itself.

    Dropping files into a repo would otherwise show them in `git status` and
    invite a stray `git add .`. Ignoring itself keeps the project's own
    .gitignore untouched.
    """
    try:
        fd = os.open(
            ".gitignore",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=dir_fd,
        )
    except OSError:
        return
    try:
        os.write(fd, b"*\n")
    except OSError:
        pass
    finally:
        os.close(fd)


# --- the quota, reserved rather than observed -------------------------------
#
# In-process state, which is sound because the dashboard runs as a single
# uvicorn worker (deploy/ctb-dashboard.service). A second worker would each
# keep their own book and the ceiling would double; that is the assumption to
# revisit if the deployment ever grows one.
_reservations: dict[tuple, int] = {}
_reservation_lock = threading.Lock()


def reserve(dir_fd: int, want: int) -> tuple[int, tuple]:
    """-> (bytes this upload may write, key to release it with).

    Raises UploadError when the directory is already full. The space is booked
    under the lock, so two requests arriving together cannot both be told there
    is room for the last megabyte.
    """
    st = os.fstat(dir_fd)
    key = (st.st_dev, st.st_ino)
    with _reservation_lock:
        used = dir_bytes(dir_fd) + _reservations.get(key, 0)
        room = MAX_DIR_BYTES - used
        if room <= 0:
            raise UploadError(
                "dir_full", 507,
                f"{UPLOAD_DIRNAME} 가 가득 찼습니다 "
                f"({used // (1024 * 1024)}MB). 정리한 뒤 다시 시도하세요.",
            )
        budget = min(want, room)
        _reservations[key] = _reservations.get(key, 0) + budget
        return budget, key


def release(key: tuple, budget: int) -> None:
    """Give back a reservation once the bytes are on disk (or gone)."""
    with _reservation_lock:
        left = _reservations.get(key, 0) - budget
        if left > 0:
            _reservations[key] = left
        else:
            _reservations.pop(key, None)


def unlink_if_same(dir_fd: int, name: str, fd: int) -> None:
    """Remove `name`, but only while it is still the file `fd` refers to.

    There is no unlink-by-descriptor on Linux, so a cleanup by name can delete
    whatever took the name in the meantime. Comparing the inode first narrows
    that to an interleaving: a replacement that arrives between the stat and
    the unlink is still removed. It is not a guarantee, and saying so would be
    worse than the gap -- what closes it is that this directory is 0700, only
    this process creates names in it, and creation is O_EXCL.
    """
    try:
        here = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        mine = os.fstat(fd)
    except OSError:
        return
    if (here.st_dev, here.st_ino) != (mine.st_dev, mine.st_ino):
        logger.warning("upload cleanup skipped: %s is no longer our file", name)
        return
    try:
        os.unlink(name, dir_fd=dir_fd)
    except OSError:
        pass


def dir_bytes(dir_fd: int) -> int:
    """What the upload directory already holds (one level; no recursion)."""
    total = 0
    try:
        for entry in os.listdir(dir_fd):
            try:
                total += os.stat(entry, dir_fd=dir_fd, follow_symlinks=False).st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def write_all(fd: int, data: bytes) -> None:
    """os.write may write less than it was given; the remainder is not optional.

    A short write left the file quietly truncated -- and a truncated file is
    the one failure mode this whole module is built to avoid, because the user
    hands its path to Claude and gets a confident answer about half a file.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise UploadError("write_failed", 500, "파일을 쓰지 못했습니다")
        view = view[written:]


def _create_exclusive(dir_fd: int, name: str) -> tuple[int, str]:
    """Create `name` in the directory, stepping aside for a name in use.

    O_EXCL is what makes the collision check and the create one operation: two
    uploads racing on the same name cannot both win, so neither is silently
    overwritten.
    """
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    for n in range(1, _COLLISION_TRIES + 1):
        candidate = name if n == 1 else f"{stem}-{n}{('.' + ext) if ext else ''}"
        try:
            fd = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=dir_fd,
            )
            return fd, candidate
        except FileExistsError:
            continue
        except OSError as e:
            raise UploadError("write_failed", 500, f"파일을 만들 수 없습니다: {e}")
    raise UploadError("too_many_collisions", 409, "같은 이름의 파일이 너무 많습니다")
