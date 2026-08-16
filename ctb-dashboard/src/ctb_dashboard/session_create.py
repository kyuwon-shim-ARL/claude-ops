"""Create a Claude session from the dashboard: pick a project, or make one.

The machine already has a launcher -- ``~/bin/cs`` -- and everything here
mirrors its conventions rather than inventing new ones, because the sessions it
makes have to be indistinguishable from the ones already on screen:

  plain session    ``claude_<project>``     in ``<root>/<project>``
  worktree session ``claude_<project>_wt_<name>``
                   in ``<root>/<project>/.claude/worktrees/<name>``
                   on branch ``worktree-<name>``

The tmux invocation matches cs too: a login shell wrapper (so PATH and profile
are the ones a human would get), ``remain-on-exit`` so a crashed Claude leaves
a pane to read instead of vanishing, and ``--continue`` when this directory has
prior Claude history.
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .sessions import get_sessions_activity

logger = logging.getLogger(__name__)

# Same character set the rest of the dashboard accepts in a session name, minus
# the separators we compose with. Leading dot excluded: a project directory is
# never hidden, and ".." must not survive validation.
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# cs restricts worktree names to this set; '.' is left out on purpose since the
# name also becomes a branch name. A leading '-' is the one thing cs allows and
# this does not: such a name reads as a flag wherever it is passed to git.
WORKTREE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")

_GIT_TIMEOUT = 30
_TMUX_TIMEOUT = 10

_DEFAULT_ROOT = "/home/kyuwon/projects"


class CreateError(Exception):
    """A create request that cannot be satisfied. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def projects_root() -> Path:
    """Root directory holding project folders (same env var the review gate uses)."""
    return Path(os.environ.get("CTB_PROJECTS_ROOT") or _DEFAULT_ROOT).expanduser()


def _run(argv: list[str], timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _git(cwd: Path, *args: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return _run(["git", "-C", str(cwd), *args], timeout=timeout)


def _is_git_repo(path: Path) -> bool:
    try:
        r = _git(path, "rev-parse", "--is-inside-work-tree", timeout=5)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def _live_sessions() -> set:
    """Every tmux session name that exists right now (one tmux call)."""
    return set(get_sessions_activity().keys())


def session_name_for(project: str, worktree: Optional[str] = None) -> str:
    if worktree:
        return f"claude_{project}_wt_{worktree}"
    return f"claude_{project}"


def _validate_project_name(name: str) -> str:
    name = (name or "").strip()
    if not PROJECT_NAME_RE.match(name):
        raise CreateError(
            "invalid_project",
            "프로젝트 이름은 영문자/숫자로 시작하고 영문자, 숫자, '.', '_', '-'만 쓸 수 있습니다",
        )
    if name in (".", "..") or "/" in name:
        raise CreateError("invalid_project", "잘못된 프로젝트 이름입니다")
    return name


def _validate_worktree_name(name: str) -> str:
    name = (name or "").strip()
    if not WORKTREE_NAME_RE.match(name):
        raise CreateError(
            "invalid_worktree",
            "워크트리 이름은 '-'로 시작할 수 없고 영문자, 숫자, '_', '-'만 쓸 수 있습니다",
        )
    return name


def _project_dir(name: str) -> Path:
    """Resolve a validated project name under the root, refusing any escape.

    The name is already restricted to a single path segment, so this is belt
    and braces -- but a symlinked project directory would otherwise put the
    worktree we create, and the files git later deletes, outside the root.
    """
    root = projects_root()
    candidate = (root / name).resolve()
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise CreateError("invalid_project", "프로젝트 경로가 프로젝트 루트를 벗어납니다")
    return candidate


# --- listing ---------------------------------------------------------------


def list_projects() -> dict:
    """Every project directory under the root, with its session status."""
    root = projects_root()
    live = _live_sessions()
    projects = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: -p.stat().st_mtime)
    except OSError as e:
        logger.warning("projects root unreadable (%s): %s", root, e)
        return {"root": str(root), "projects": []}

    for entry in entries:
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if not PROJECT_NAME_RE.match(entry.name):
            continue
        name = session_name_for(entry.name)
        projects.append({
            "name": entry.name,
            "path": str(entry),
            "is_git": (entry / ".git").exists(),
            "session": name,
            "session_exists": name in live,
        })
    return {"root": str(root), "projects": projects}


def list_worktrees(project: str) -> dict:
    """Worktrees of one project, in the ``.claude/worktrees/<name>`` convention.

    Only that directory is reported: those are the ones this endpoint can also
    create, and a worktree parked somewhere else has no session-name mapping.
    """
    project = _validate_project_name(project)
    path = _project_dir(project)
    out: dict = {"project": project, "path": str(path), "is_git": False, "worktrees": []}
    if not path.is_dir():
        raise CreateError("no_project", f"프로젝트 '{project}'를 찾을 수 없습니다")
    if not _is_git_repo(path):
        return out
    out["is_git"] = True

    live = _live_sessions()
    wt_root = path / ".claude" / "worktrees"
    branches = _worktree_branches(path)
    for entry in sorted(wt_root.iterdir(), key=lambda p: p.name.lower()) if wt_root.is_dir() else []:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        name = session_name_for(project, entry.name)
        out["worktrees"].append({
            "name": entry.name,
            "path": str(entry),
            "branch": branches.get(str(entry.resolve())),
            "session": name,
            "session_exists": name in live,
        })
    return out


def _worktree_branches(repo: Path) -> dict:
    """{absolute worktree path: branch name} from `git worktree list`."""
    result: dict = {}
    try:
        r = _git(repo, "worktree", "list", "--porcelain", timeout=10)
    except Exception:
        return result
    if r.returncode != 0:
        return result
    current = None
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            current = os.path.realpath(line[len("worktree "):].strip())
        elif line.startswith("branch ") and current:
            result[current] = line[len("branch "):].strip().replace("refs/heads/", "")
    return result


# --- creation --------------------------------------------------------------


_GITIGNORE = """# Python
__pycache__/
*.py[cod]
.venv/
venv/
.env

# Node
node_modules/

# OS
.DS_Store

# Claude
.claude/worktrees/
.omc/
"""


def _init_project(path: Path, git_init: bool) -> None:
    """Create the project directory and, unless told not to, its git repo.

    Any failure after the directory exists takes the directory with it. The
    alternative was worse in both directions: a half-made project is left on
    disk, and because ``create_session`` refuses a name that already exists,
    every retry then answers "이미 있습니다" -- a lie that never clears itself.
    ``mkdir(exist_ok=False)`` above is what makes the cleanup safe: nothing was
    there a moment ago, so nothing of the user's can be inside it.
    """
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise CreateError("project_exists", f"'{path.name}' 프로젝트가 이미 있습니다")
    except OSError as e:
        raise CreateError("mkdir_failed", f"디렉토리 생성 실패: {e}")

    if not git_init:
        return

    try:
        r = _run(["git", "init", "-b", "main", str(path)])
        if r.returncode != 0:
            raise CreateError("git_init_failed", (r.stderr or r.stdout).strip()[:300])

        (path / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
        a = _git(path, "add", ".gitignore")
        if a.returncode != 0:
            raise CreateError("git_init_failed", (a.stderr or a.stdout).strip()[:300])

        # The initial commit is load-bearing, not decoration, and its failure
        # must not pass quietly. `git worktree add -b` on a repo with no commit
        # does not fail -- it infers --orphan and produces a branch with no
        # relationship to the project's history, which is not the worktree this
        # module promises and is not visible until someone reads git log.
        c = _git(path, "commit", "-m", "Initial commit")
        if c.returncode != 0:
            raise CreateError(
                "git_init_failed",
                "최초 커밋 실패 (git user.name/user.email 설정을 확인하세요): "
                + (c.stderr or c.stdout).strip()[:200],
            )
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise


def _ensure_worktree(project_dir: Path, worktree: str) -> tuple[Path, bool]:
    """Return (worktree path, created). Reuses an existing directory as-is."""
    wt_dir = project_dir / ".claude" / "worktrees" / worktree
    if wt_dir.is_dir():
        return wt_dir, False

    if not _is_git_repo(project_dir):
        raise CreateError(
            "not_git", f"'{project_dir.name}'는 git 저장소가 아니라 워크트리를 만들 수 없습니다"
        )

    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    branch = f"worktree-{worktree}"
    r = _git(project_dir, "worktree", "add", str(wt_dir), "-b", branch)
    if r.returncode != 0:
        # The branch may already exist from a worktree that was removed; check
        # it out instead of failing, which is what cs does.
        r2 = _git(project_dir, "worktree", "add", str(wt_dir), branch)
        if r2.returncode != 0:
            # r2's message, not r's: the fallback is the attempt that decided
            # the outcome, and r's "branch already exists" is exactly the thing
            # the fallback was trying to accommodate.
            raise CreateError(
                "worktree_failed",
                (r2.stderr or r2.stdout).strip()[:300] or "워크트리 생성에 실패했습니다",
            )
    return wt_dir, True


def _claude_history_exists(path: Path) -> bool:
    """Has Claude ever run in this directory? (its transcript dir naming)."""
    encoded = str(path).replace("/", "-")
    hist = Path.home() / ".claude" / "projects" / encoded
    try:
        return any(hist.glob("*.jsonl"))
    except OSError:
        return False


def launch_session(session: str, path: Path) -> None:
    """Start a detached tmux session running Claude, the way ``cs`` does."""
    claude_bin = os.environ.get("CTB_CLAUDE_BIN", "claude")
    flags = "--continue --dangerously-skip-permissions" if _claude_history_exists(path) \
        else "--dangerously-skip-permissions"
    window = session[len("claude_"):] if session.startswith("claude_") else session
    inner = f"{claude_bin} {flags}; exec bash --login"

    r = _run(
        ["tmux", "new-session", "-d", "-s", session, "-n", window, "-c", str(path),
         f"bash --login -c {_shquote(inner)}"],
        timeout=_TMUX_TIMEOUT,
    )
    if r.returncode != 0:
        raise CreateError("tmux_failed", (r.stderr or r.stdout).strip()[:300])

    # A Claude that exits (crash, /exit) leaves a readable dead pane rather than
    # taking the session -- and its card -- off the dashboard with it.
    _run(["tmux", "set-window-option", "-t", f"={session}", "remain-on-exit", "on"],
         timeout=_TMUX_TIMEOUT)


def _shquote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def schedule_remote_control(session: str) -> None:
    """Register /remote-control once the TUI is up, as ``cs`` does on launch.

    Best effort by design: the session is already usable without it, so an
    unavailable helper must not turn a successful create into a failure.
    """
    try:
        import sys
        ctb_home = os.environ.get("CTB_HOME", "/home/kyuwon/projects/claude-ops")
        if ctb_home not in sys.path:
            sys.path.insert(0, ctb_home)
        from claude_ctb.utils.remote_control import send_remote_control_bg
    except Exception as e:
        logger.info("remote-control helper unavailable (%s); skipping for %s", e, session)
        return
    try:
        send_remote_control_bg(session)
    except Exception as e:
        logger.warning("remote-control scheduling failed for %s: %s", session, e)


def create_session(
    project: Optional[str] = None,
    new_project: Optional[str] = None,
    worktree: Optional[str] = None,
    git_init: bool = True,
) -> dict:
    """Create (or reuse) a project/worktree and start a Claude session in it.

    Exactly one of `project` / `new_project` must be given. Returns a dict with
    `status` in {"created", "exists"}; every refusal raises CreateError.
    """
    if bool(project) == bool(new_project):
        raise CreateError(
            "bad_request", "기존 프로젝트 또는 새 프로젝트 중 하나만 지정해야 합니다"
        )

    name = _validate_project_name(project or new_project)
    wt = _validate_worktree_name(worktree) if worktree else None
    project_dir = _project_dir(name)

    project_created = False
    if new_project:
        if project_dir.exists():
            raise CreateError("project_exists", f"'{name}' 프로젝트가 이미 있습니다")
        _init_project(project_dir, git_init)
        project_created = True
    elif not project_dir.is_dir():
        raise CreateError("no_project", f"프로젝트 '{name}'를 찾을 수 없습니다")

    worktree_created = False
    work_dir = project_dir
    if wt:
        work_dir, worktree_created = _ensure_worktree(project_dir, wt)

    session = session_name_for(name, wt)
    result = {
        "status": "created",
        "session": session,
        "project": name,
        "worktree": wt,
        "path": str(work_dir),
        "project_created": project_created,
        "worktree_created": worktree_created,
    }

    if session in _live_sessions():
        # Nothing was started; say so plainly instead of reporting a create the
        # user would then look for in the log of a session that predates it.
        result["status"] = "exists"
        return result

    try:
        launch_session(session, work_dir)
    except CreateError as e:
        # Two taps on the button -- or a `cs` in a terminal -- race between the
        # check above and this launch, and tmux settles it by refusing the
        # second. Ask tmux what exists rather than reading its error text: the
        # loser's session is there, which is what was asked for, not a 502.
        if e.code == "tmux_failed" and session in _live_sessions():
            result["status"] = "exists"
            return result
        raise
    schedule_remote_control(session)
    return result
