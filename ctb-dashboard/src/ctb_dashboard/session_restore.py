"""Closed sessions, kept so they can come back.

Every session the dashboard deletes -- from the trash or from Ctrl+Q -- is
recorded first: its name, working directory, and how it was made. Restore
pops the most recent one that is not already live and starts it again in
the same directory; Claude resumes there with ``--continue`` when the
directory has a transcript, so the conversation comes back with the pane.
One per call, newest first, the way a browser reopens closed tabs.

A worktree that a forced delete parked in the trash (session_delete) comes
back by moving that directory home, so its uncommitted and untracked files
and its branch return with the conversation. A bash-only (``_sh``) session
comes back as a shell, never with Claude started in it.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from .session_create import (
    CreateError,
    create_session,
    launch_session,
    launch_shell_session,
    projects_root,
)
from .session_delete import untrash
from .session_input import is_shell_session
from .sessions import get_session_path

HISTORY_MAX = 20
_WT_RE = re.compile(r"^claude_(?P<project>.+?)_wt_(?P<worktree>.+)$")


def history_path(state_dir: str) -> str:
    return os.path.join(state_dir, "closed-sessions.json")


def _load(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def describe(session: str, path: str | None = None) -> dict:
    """What restore needs, taken while the session is still alive."""
    cwd = path if path is not None else get_session_path(session)
    entry = {"session": session, "path": cwd, "closed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # The suffix alone is not proof (a project may end in "_sh"); the tmux
    # mark is, and it is only readable now, while the session is alive.
    shell = session.endswith("_sh") and is_shell_session(session)
    if shell:
        entry["shell"] = True
    m = _WT_RE.match(session[:-len("_sh")] if shell else session)
    if m:
        entry["project"] = m.group("project")
        entry["worktree"] = m.group("worktree")
    return entry


def record(path: str, entry: dict) -> None:
    """Newest last; a session closed twice keeps only its latest entry."""
    rows = [r for r in _load(path) if r.get("session") != entry.get("session")]
    rows.append(entry)
    _save(path, rows[-HISTORY_MAX:])


def peek(path: str) -> list[dict]:
    return _load(path)[::-1]


def restore_last(path: str, live: Callable[[], set]) -> dict | None:
    """Bring back the most recent closed session that can come back.

    Skips entries whose session is already live (made again by hand) and
    whose directory is gone (a regular session with nothing to start in).
    Returns the entry with ``status`` set, or None when nothing is left.
    """
    rows = _load(path)
    alive = live()
    while rows:
        entry = rows.pop()
        session = entry.get("session") or ""
        if session in alive:
            continue
        shell = bool(entry.get("shell"))
        launch = launch_shell_session if shell else launch_session
        trash = entry.get("trashed_to")
        try:
            # Whatever the name says: a plain-named session that had cd'd into
            # a worktree trashes it too, and has no `worktree` key to go by.
            if trash and Path(trash).is_dir():
                _untrash(trash, entry.get("trashed_from") or entry.get("path") or "")
                launch(session, Path(entry["path"]))
                out = {**entry, "status": "created"}
            elif entry.get("worktree"):
                # The worktree may have been removed with the session, or its
                # trash already purged; the create path makes it again (same
                # branch when it survived).
                kwargs = {"project": entry["project"], "worktree": entry["worktree"]}
                if shell:
                    kwargs["shell"] = True
                result = create_session(**kwargs)
                out = {**entry, "status": result["status"], "path": result["path"]}
            else:
                cwd = Path(entry.get("path") or "")
                if not cwd.is_dir():
                    continue
                launch(session, cwd)
                out = {**entry, "status": "created"}
        except CreateError:
            # Put it back: a failed restore must leave the session restorable
            # once whatever stood in the way is dealt with.
            rows.append(entry)
            _save(path, rows)
            raise
        _save(path, rows)
        return out
    _save(path, rows)
    return None


def _untrash(trash: str, original: str) -> None:
    """Move a trashed worktree back to its own path -- the path Claude's
    transcript is keyed by, so ``--continue`` finds the conversation there.

    Refuses rather than merges when something already occupies that path
    (most likely a worktree made again under the same name): which of the two
    to keep is not ours to decide.
    """
    if not original:
        raise CreateError("restore_failed", "복원할 워크트리 경로가 기록되어 있지 않습니다")
    if os.path.lexists(original):
        raise CreateError(
            "restore_conflict",
            f"원래 경로 {original} 가 이미 있어 휴지통의 워크트리({trash})를 되돌릴 수 없습니다",
        )
    err = untrash(trash, original)
    if err:
        raise CreateError("restore_failed", f"휴지통에서 되돌리지 못했습니다: {err}"[:300])


def project_of(path: str) -> str | None:
    """The project name a regular session's directory belongs to, if it is
    under the projects root; informational only."""
    try:
        return Path(path).resolve().relative_to(projects_root().resolve()).parts[0]
    except (ValueError, IndexError, OSError):
        return None
