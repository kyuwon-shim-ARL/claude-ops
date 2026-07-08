"""
Session deletion with git-safety checks for CTB Dashboard.

A "session" is a tmux session. Deleting it means:
  - regular session: kill the tmux session (files on disk are untouched)
  - worktree session: kill the tmux session AND `git worktree remove` the
    working directory (this DOES delete files on disk)

Before deleting we verify the work is safe to lose:
  - no uncommitted changes
  - no unpushed commits (has an upstream and is up to date)
  - for worktrees: the branch is merged into the default branch

`force=True` bypasses these checks (the frontend guards it behind a second
confirmation).
"""

import os
import subprocess
from typing import Optional

from .sessions import get_session_path


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
    try:
        r = _run_git(path, ["status", "--porcelain"])
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return True  # fail safe: assume dirty


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

    has_upstream, unpushed = _upstream_status(path)
    result["has_upstream"] = has_upstream
    result["unpushed_count"] = unpushed

    default_branch = _default_branch(path)
    result["default_branch"] = default_branch

    reasons: list[str] = []
    if has_uncommitted:
        reasons.append("커밋되지 않은 변경사항이 있습니다")

    if is_wt:
        # For a worktree the durable-work question is answered by merge status:
        # if HEAD is an ancestor of the default branch, every commit is already
        # preserved there, so the branch's own upstream tracking is irrelevant.
        merged = _is_merged(path, default_branch)
        result["is_merged"] = merged
        if merged is False:
            tgt = default_branch or "기본 브랜치"
            reasons.append(f"'{result['branch']}' 브랜치가 {tgt}에 병합되지 않았습니다")
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


def delete_session(session_name: str, force: bool = False) -> dict:
    """Delete a session. Blocks unsafe deletes unless force=True.

    Returns a dict with `status` in {"deleted", "blocked", "error"}.
    """
    check = check_delete_safety(session_name)

    if not force and not check["safe"]:
        return {"status": "blocked", "check": check}

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

    if check["is_worktree"] and check["path"]:
        main_repo = _main_repo_dir(check["path"])
        if main_repo:
            args = ["worktree", "remove"]
            if force or check["has_uncommitted"]:
                args.append("--force")
            args.append(check["path"])
            try:
                r = _run_git(main_repo, args, timeout=15)
                if r.returncode == 0:
                    out["removed_worktree"] = True
                else:
                    out["status"] = "error"
                    out["error"] = (r.stderr or r.stdout).strip()
            except Exception as e:
                out["status"] = "error"
                out["error"] = str(e)

            # Clean up the now-orphaned branch when it is safe to do so.
            branch = check["branch"]
            if out["removed_worktree"] and branch:
                del_flag = "-D" if force else "-d"
                try:
                    r = _run_git(main_repo, ["branch", del_flag, branch], timeout=10)
                    out["branch_deleted"] = r.returncode == 0
                except Exception:
                    pass

    return out
