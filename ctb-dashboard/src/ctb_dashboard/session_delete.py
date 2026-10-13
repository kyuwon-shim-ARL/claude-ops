"""
Session deletion with git-safety checks for CTB Dashboard.

A "session" is a tmux session. Deleting it means:
  - regular session: kill the tmux session (files on disk are untouched)
  - worktree session, safe (clean and merged): kill the tmux session, then
    `git worktree remove` the directory and `git branch -d` its branch --
    nothing is lost that the default branch does not already hold
  - worktree session, forced: kill the tmux session and `git worktree move`
    the directory into ``<main repo>/.claude/trash/<name>-<stamp>``. Nothing
    is deleted: uncommitted, untracked and ignored files and the branch (still
    checked out there) all survive, and restore moves it back. The trash is
    time-limited retention, not a second home: entries older than
    CTB_TRASH_DAYS (default 7) are removed for real, branch included, the
    next time a worktree of that repo is deleted.
  - a worktree another live session is also working in (the Claude session
    and its ``_sh`` shell share one): only this session's tmux goes, the
    worktree stays where it is.

Before deleting we verify the work is safe to lose:
  - no uncommitted changes
  - no unpushed commits (has an upstream and is up to date)
  - for worktrees: the branch is merged into the default branch

`force=True` bypasses these checks (the frontend guards it behind a second
confirmation).
"""

import logging
import os
import re
import subprocess
import time
from typing import Optional

from .sessions import get_session_path, get_sessions_activity

logger = logging.getLogger(__name__)

TRASH_DIR = os.path.join(".claude", "trash")
_STAMP_FMT = "%Y%m%dT%H%M%S"
_STAMP_RE = re.compile(r"-(\d{8}T\d{6})$")


def _run_git(cwd: str, args: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _is_git_repo(path: str) -> bool:
    try:
        r = _run_git(path, ["rev-parse", "--is-inside-work-tree"])
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def _is_worktree(path: str) -> bool:
    """A linked worktree has git-dir != git-common-dir."""
    try:
        gd = _run_git(path, ["rev-parse", "--absolute-git-dir"])
        cd = _run_git(path, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
        if gd.returncode != 0 or cd.returncode != 0:
            return False
        git_dir = os.path.realpath(gd.stdout.strip())
        common_dir = os.path.realpath(cd.stdout.strip())
        return git_dir != common_dir
    except Exception:
        return False


def _main_repo_dir(path: str) -> Optional[str]:
    """Parent of the shared .git dir — the main worktree, where `git worktree
    remove` must run from (git refuses to remove the current worktree)."""
    try:
        cd = _run_git(path, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
        if cd.returncode != 0:
            return None
        common_dir = os.path.realpath(cd.stdout.strip())
        return os.path.dirname(common_dir)
    except Exception:
        return None


def _current_branch(path: str) -> Optional[str]:
    try:
        r = _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
        if r.returncode == 0:
            b = r.stdout.strip()
            return b if b and b != "HEAD" else None
    except Exception:
        pass
    return None


def _default_branch(path: str) -> Optional[str]:
    """Short name of the repo's default branch (e.g. 'main')."""
    try:
        r = _run_git(path, ["rev-parse", "--abbrev-ref", "origin/HEAD"])
        if r.returncode == 0:
            ref = r.stdout.strip()  # e.g. "origin/main"
            if "/" in ref:
                return ref.split("/", 1)[1]
    except Exception:
        pass
    # Fallback: probe common names
    for cand in ("main", "master"):
        try:
            r = _run_git(path, ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}"])
            if r.returncode == 0:
                return cand
            r = _run_git(path, ["rev-parse", "--verify", "--quiet", f"refs/heads/{cand}"])
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    return None


def _has_uncommitted(path: str) -> bool:
    """Tracked changes only.

    Plain `status --porcelain` lists untracked files as well, so a repo with
    everything committed and one stray directory was reported as having
    uncommitted changes -- which is what people read, and it was not true.
    """
    try:
        r = _run_git(path, ["status", "--porcelain", "--untracked-files=no"])
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return True  # fail safe: assume dirty


def _has_untracked(path: str) -> bool:
    """Files git is not following.

    Harmless for a regular session, which leaves the disk alone; a worktree
    removal takes them with it, so only that case treats them as a risk.
    """
    try:
        r = _run_git(path, ["ls-files", "--others", "--exclude-standard"])
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return True


def _upstream_status(path: str) -> tuple[bool, int]:
    """Return (has_upstream, unpushed_count). unpushed_count is -1 when unknown."""
    try:
        r = _run_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        if r.returncode != 0:
            return False, -1
        c = _run_git(path, ["rev-list", "--count", "@{u}..HEAD"])
        if c.returncode != 0:
            return True, -1
        return True, int(c.stdout.strip() or "0")
    except Exception:
        return False, -1


def _is_merged(path: str, default_branch: Optional[str]) -> Optional[bool]:
    """Whether HEAD is fully contained in the default branch (local or remote)."""
    if not default_branch:
        return None
    for target in (f"origin/{default_branch}", default_branch):
        try:
            r = _run_git(path, ["merge-base", "--is-ancestor", "HEAD", target])
            if r.returncode == 0:
                return True
            if r.returncode == 1:
                # valid ref, not an ancestor
                continue
        except Exception:
            continue
    return False


def check_delete_safety(session_name: str) -> dict:
    """Inspect a session's working tree and report whether it is safe to delete."""
    path = get_session_path(session_name)
    result: dict = {
        "session": session_name,
        "path": path,
        "is_git": False,
        "is_worktree": False,
        "branch": None,
        "has_uncommitted": False,
        "has_untracked": False,
        "has_upstream": False,
        "unpushed_count": 0,
        "is_merged": None,
        "default_branch": None,
        "safe": True,
        "reasons": [],
    }

    if not path or not _is_git_repo(path):
        # Not a git repo — killing the tmux session loses nothing on disk.
        return result

    result["is_git"] = True
    is_wt = _is_worktree(path)
    result["is_worktree"] = is_wt
    result["branch"] = _current_branch(path)

    has_uncommitted = _has_uncommitted(path)
    result["has_uncommitted"] = has_uncommitted
    has_untracked = _has_untracked(path)
    result["has_untracked"] = has_untracked

    has_upstream, unpushed = _upstream_status(path)
    result["has_upstream"] = has_upstream
    result["unpushed_count"] = unpushed

    default_branch = _default_branch(path)
    result["default_branch"] = default_branch

    reasons: list[str] = []
    if has_uncommitted:
        reasons.append("커밋되지 않은 변경사항이 있습니다")

    if is_wt and has_untracked:
        # Only here are they at stake: the safe path's `git worktree remove`
        # would refuse them, and a force parks them in the trash, which is
        # purged after CTB_TRASH_DAYS. A regular session leaves every file
        # where it is.
        reasons.append("git이 추적하지 않는 파일이 있습니다 (강제 삭제 시 휴지통으로 옮겨지고 7일 뒤 사라집니다)")

    if is_wt:
        # For a worktree the durable-work question is answered by merge status:
        # if HEAD is an ancestor of the default branch, every commit is already
        # preserved there, so the branch's own upstream tracking is irrelevant.
        merged = _is_merged(path, default_branch)
        result["is_merged"] = merged
        if merged is False:
            tgt = default_branch or "기본 브랜치"
            branch_label = result["branch"] or "현재 브랜치"
            reasons.append(f"'{branch_label}' 브랜치가 {tgt}에 병합되지 않았습니다")
        elif merged is None:
            reasons.append("병합 여부를 확인할 수 없습니다")
    else:
        # Regular checkout: killing the session leaves files on disk, but we
        # still warn if work isn't pushed so it isn't silently forgotten.
        if not has_upstream:
            reasons.append("업스트림(원격 추적 브랜치)이 없어 푸시 여부를 확인할 수 없습니다")
        elif unpushed > 0:
            reasons.append(f"푸시되지 않은 커밋 {unpushed}개가 있습니다")
        elif unpushed < 0:
            reasons.append("푸시 여부를 확인할 수 없습니다")

    result["reasons"] = reasons
    result["safe"] = len(reasons) == 0
    return result


def _kill_tmux(session_name: str) -> bool:
    try:
        r = subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _worktree_top(path: str) -> str:
    """The worktree's top level. A pane's cwd may be any subdirectory of it,
    and both the move and the sharing question are about the whole worktree."""
    try:
        r = _run_git(path, ["rev-parse", "--show-toplevel"])
        if r.returncode == 0 and r.stdout.strip():
            return os.path.realpath(r.stdout.strip())
    except Exception:
        pass
    return os.path.realpath(path)


def _sharing_session(session_name: str, root: str) -> Optional[str]:
    """Another live tmux session working in the worktree at ``root``, if any.

    Inside it counts as well as at its root: a shell that has cd'd into a
    subdirectory is just as much in the worktree that would vanish under it.
    """
    for other in get_sessions_activity():
        if other == session_name:
            continue
        p = get_session_path(other)
        if not p:
            continue
        rp = os.path.realpath(p)
        if rp == root or rp.startswith(root + os.sep):
            return other
    return None


def _ensure_trash_dir(main_repo: str) -> str:
    """``<main repo>/.claude/trash``, ignored by git.

    New projects list it in their .gitignore (session_create._GITIGNORE); a
    repo made any other way gets a ``.gitignore`` of ``*`` inside the trash
    itself, which hides the directory without touching the project's own.
    """
    trash = os.path.join(main_repo, TRASH_DIR)
    os.makedirs(trash, exist_ok=True)
    ignore = os.path.join(trash, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as f:
            f.write("*\n")
    return trash


def _trash_days() -> float:
    try:
        return float(os.environ.get("CTB_TRASH_DAYS", "7"))
    except ValueError:
        return 7.0


def _trashed_at(entry: str) -> float:
    """When an entry went into the trash: the stamp in its name, or -- for a
    directory that does not carry one -- its mtime."""
    m = _STAMP_RE.search(os.path.basename(entry))
    if m:
        try:
            return time.mktime(time.strptime(m.group(1), _STAMP_FMT))
        except ValueError:
            pass
    return os.path.getmtime(entry)


def gc_trash(main_repo: str) -> None:
    """Remove trash entries older than CTB_TRASH_DAYS, branch and all.

    Opportunistic and best-effort: a failure is logged and the entry left for
    the next pass, never raised -- it runs at the end of a delete that has
    already succeeded.
    """
    trash = os.path.join(main_repo, TRASH_DIR)
    cutoff = time.time() - _trash_days() * 86400
    try:
        entries = [os.path.join(trash, n) for n in os.listdir(trash)]
    except OSError:
        return
    for entry in entries:
        try:
            # Only directories `worktree move` put here are ours to purge; a
            # symlink points at something that is not.
            if os.path.islink(entry) or not os.path.isdir(entry) or _trashed_at(entry) >= cutoff:
                continue
            branch = _current_branch(entry)
            r = _run_git(main_repo, ["worktree", "remove", "--force", entry], timeout=30)
            if r.returncode != 0:
                logger.warning("trash gc: %s not removed: %s", entry, (r.stderr or r.stdout).strip())
                continue
            if branch:
                b = _run_git(main_repo, ["branch", "-D", branch], timeout=10)
                if b.returncode != 0:
                    logger.warning("trash gc: branch %s not deleted: %s", branch,
                                   (b.stderr or b.stdout).strip())
        except Exception as e:  # noqa: BLE001 -- gc must never fail the delete
            logger.warning("trash gc: %s: %s", entry, e)


def untrash(trash_path: str, original: str) -> Optional[str]:
    """Move a trashed worktree back to where it was. Returns git's error, or
    None on success."""
    main_repo = _main_repo_dir(trash_path)
    if not main_repo:
        return f"{trash_path} 의 저장소를 찾을 수 없습니다"
    os.makedirs(os.path.dirname(original), exist_ok=True)
    r = _run_git(main_repo, ["worktree", "move", trash_path, original], timeout=30)
    if r.returncode != 0:
        return (r.stderr or r.stdout).strip()
    return None


def delete_session(session_name: str, force: bool = False, allow_worktree: bool = True) -> dict:
    """Delete a session. Blocks unsafe deletes unless force=True.

    `allow_worktree=False` narrows the force to plain sessions: a caller that
    forces on the strength of an earlier check saying "not a worktree" must
    not delete one if this check finds that it is.

    Returns a dict with `status` in {"deleted", "blocked", "error"}.
    """
    check = check_delete_safety(session_name)

    if check["is_worktree"] and not allow_worktree:
        force = False
    # Blocked comes first, even when another session shares the worktree: an
    # unforced close of an unsafe worktree has to answer "blocked" so Ctrl+Q
    # arms, rather than kill a busy Claude because its `_sh` sibling is open.
    if not force and not check["safe"]:
        return {"status": "blocked", "check": check}

    wt_root = _worktree_top(check["path"]) if check["is_worktree"] and check["path"] else None
    if wt_root:
        # With another session still in the worktree only this tmux session
        # goes, forced or not; nothing on disk moves.
        other = _sharing_session(session_name, wt_root)
        if other:
            return {
                "status": "deleted",
                "session": session_name,
                "killed": _kill_tmux(session_name),
                "removed_worktree": False,
                "branch_deleted": False,
                "kept_worktree_shared_with": other,
                "check": check,
            }

    out: dict = {
        "status": "deleted",
        "session": session_name,
        "killed": False,
        "removed_worktree": False,
        "branch_deleted": False,
        "check": check,
    }

    # Kill tmux first so no process holds the worktree directory.
    out["killed"] = _kill_tmux(session_name)

    if wt_root:
        main_repo = _main_repo_dir(wt_root)
        if main_repo and force:
            # A forced delete parks the worktree instead of destroying it; the
            # branch stays, checked out there, so restore can move it all
            # back. If git will not move it (locked, submodules) the delete
            # fails right here with the directory untouched -- falling back to
            # `remove --force` would destroy exactly what the trash is for.
            dest = os.path.join(
                _ensure_trash_dir(main_repo),
                f"{os.path.basename(wt_root)}-{time.strftime(_STAMP_FMT)}",
            )
            try:
                r = _run_git(main_repo, ["worktree", "move", wt_root, dest], timeout=30)
                if r.returncode == 0:
                    out["trashed_to"] = dest
                    # Where it came from, which is not the session's path
                    # when the pane was in a subdirectory: restore moves it
                    # back here.
                    out["trashed_from"] = wt_root
                else:
                    out["status"] = "error"
                    out["error"] = (r.stderr or r.stdout).strip()
            except Exception as e:
                out["status"] = "error"
                out["error"] = str(e)
        elif main_repo:
            try:
                r = _run_git(main_repo, ["worktree", "remove", wt_root], timeout=15)
                if r.returncode == 0:
                    out["removed_worktree"] = True
                else:
                    out["status"] = "error"
                    out["error"] = (r.stderr or r.stdout).strip()
            except Exception as e:
                out["status"] = "error"
                out["error"] = str(e)

            # Clean up the now-orphaned branch: merged, so `-d` accepts it.
            branch = check["branch"]
            if out["removed_worktree"] and branch:
                try:
                    r = _run_git(main_repo, ["branch", "-d", branch], timeout=10)
                    out["branch_deleted"] = r.returncode == 0
                except Exception:
                    pass

        if main_repo:
            gc_trash(main_repo)

    return out
