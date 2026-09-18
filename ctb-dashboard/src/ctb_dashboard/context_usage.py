"""Context-window usage per tmux session, read from Claude Code's own files.

Claude Code writes `<config_dir>/sessions/*.json`, one per running session,
each carrying the tmux target it is attached to (`name:@win.%pane`) plus its
`sessionId`, `pid` and `procStart`. OMC's statusline wrapper separately
writes `<config_dir>/hud/cache/stdin.<sessionId>.json` on every statusline
render, which carries `context_window.used_percentage`.

This module joins the two: tmux session name -> live sessions file entry
(liveness checked via /proc, PID-reuse guarded by comparing `procStart`
against the process's actual start time) -> that session's hud cache ->
`used_percentage`.

Known limitation: the hud cache is written by the OMC statusline wrapper, so
a session whose statusline has never rendered has no cache file at all --
this function will simply omit that session, and the caller is expected to
fall back to another source (e.g. screen-scraping) for it.

A freshness gate rejects a cache file whose mtime predates the live process's
own `startedAt` (a cache older than the process it is reporting on belongs to
a previous process that reused the same session id). This only catches that
one case, though: a wrapper that dies *mid-process* -- the session keeps
running, but its statusline stops updating -- leaves a cache file that is
stale yet still newer than `startedAt`, and that goes undetected. There is no
staleness check against "now", only against the process start time.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional


def _default_config_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude"


def _pid_matches(pid: int, proc_start: str, proc_root: str = "/proc") -> bool:
    """True iff /proc/<pid> is alive, is a `claude` process, and its start
    time (field 22 of /proc/<pid>/stat) matches `proc_start` -- guards
    against a recycled pid now belonging to an unrelated process."""
    try:
        comm_path = os.path.join(proc_root, str(pid), "comm")
        with open(comm_path, "r") as f:
            comm = f.read().strip()
        if comm != "claude":
            return False

        stat_path = os.path.join(proc_root, str(pid), "stat")
        with open(stat_path, "r") as f:
            stat = f.read()
        # Fields after the process name (which may itself contain spaces/
        # parens) start right after the last ')'.
        rest = stat.rsplit(")", 1)[1].split()
        # rest[0] is field 3 (state); field 22 is therefore rest[22 - 3].
        starttime = rest[22 - 3]
        return starttime == str(proc_start)
    except (OSError, IndexError, ValueError):
        return False


def get_active_panes() -> Dict[str, str]:
    """tmux session name -> active pane id, for sessions whose active window
    and active pane both agree (flags == '11')."""
    try:
        out = subprocess.run(
            ["tmux", "list-panes", "-a", "-F",
             "#{session_name} #{pane_id} #{window_active}#{pane_active}"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    panes: Dict[str, str] = {}
    for line in out.stdout.splitlines():
        parts = line.rsplit(" ", 2)
        if len(parts) != 3:
            continue
        name, pane_id, flags = parts
        if flags == "11":
            panes[name] = pane_id
    return panes


def _parse_tmux_field(tmux: str):
    """`name:@win.%pane` -> (name, pane_id). No '.' -> (name, None)."""
    name = tmux.split(":", 1)[0]
    if "." in tmux:
        pane_id = tmux.rsplit(".", 1)[1]
    else:
        pane_id = None
    return name, pane_id


def _cache_is_fresh(cache_path: Path, started_at) -> bool:
    """False iff the cache file's mtime predates `started_at` (ms epoch) --
    a cache older than the process it is reporting on is left over from an
    earlier process that reused the same session id. A missing/invalid
    `started_at` skips the gate (nothing to compare against, so accept)."""
    if started_at is None:
        return True
    try:
        started_s = float(started_at) / 1000.0
    except (TypeError, ValueError):
        return True
    try:
        mtime = cache_path.stat().st_mtime
    except OSError:
        return True  # missing file: _read_context_percentage handles it
    return mtime >= started_s


def _read_context_percentage(cache_path: Path) -> Optional[int]:
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        used = data["context_window"]["used_percentage"]
    except (KeyError, TypeError):
        return None
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    return int(max(0, min(100, used)))


def load_context_by_tmux_session(
    config_dir: Optional[str] = None,
    active_panes: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    """tmux session name -> context-window used percentage (0..100)."""
    base = Path(config_dir) if config_dir else _default_config_dir()
    sessions_dir = base / "sessions"
    cache_dir = base / "hud" / "cache"

    if active_panes is None:
        active_panes = get_active_panes()

    # name -> list of (pane_id, sessionId, startedAt)
    by_name: Dict[str, list] = {}

    try:
        entries = sorted(sessions_dir.glob("*.json"))
    except OSError:
        entries = []

    for entry_path in entries:
        try:
            with open(entry_path, "r") as f:
                data = json.load(f)

            tmux = data.get("tmux")
            session_id = data.get("sessionId")
            pid = data.get("pid")
            proc_start = data.get("procStart")
            started_at = data.get("startedAt")

            if not isinstance(tmux, str) or not tmux:
                continue
            if not isinstance(session_id, str) or not session_id:
                continue
            if isinstance(pid, bool) or not isinstance(pid, int):
                continue
            if not isinstance(proc_start, (str, int)):
                continue

            if not _pid_matches(pid, str(proc_start)):
                continue

            name, pane_id = _parse_tmux_field(tmux)
            by_name.setdefault(name, []).append((pane_id, session_id, started_at))
        except Exception:
            continue

    result: Dict[str, int] = {}
    for name, live in by_name.items():
        if name in active_panes:
            # Every candidate is validated against the session's active
            # pane -- a single live entry gets no exemption here, since a
            # stale/background entry for this name is as plausible as a
            # second one.
            active_pane = active_panes[name]
            match = [(sid, sa) for (pid_, sid, sa) in live
                     if pid_ is not None and pid_ == active_pane]
            if len(match) != 1:
                continue
            session_id, started_at = match[0]
        else:
            # tmux failed, or returned no window/pane-agreeing row for this
            # name: fall back to accepting a lone live entry and rejecting
            # duplicates outright (no way to disambiguate them).
            if len(live) != 1:
                continue
            _, session_id, started_at = live[0]

        cache_path = cache_dir / f"stdin.{session_id}.json"
        try:
            if not _cache_is_fresh(cache_path, started_at):
                continue
            pct = _read_context_percentage(cache_path)
            if pct is not None:
                result[name] = pct
        except Exception:
            continue

    return result
