"""
Web Dashboard Backend -- FastAPI + SSE

Self-contained dashboard server that polls tmux sessions directly.
Works in both hook-only mode and polling mode.
"""

import asyncio
import hashlib
import hmac as _hmac_mod
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, Any
from pathlib import Path
import markdown as _markdown
import bleach as _bleach

import filelock as _filelock
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.sessions import SessionMiddleware

from .state_detector import SessionStateAnalyzer, SessionState
from . import push
from .sessions import get_all_claude_sessions, get_session_path, get_sessions_activity
from .session_delete import check_delete_safety, delete_session
from .session_create import (
    CreateError,
    create_session,
    list_projects,
    list_worktrees,
)
from .session_input import (
    ALLOWED_KEYS,
    pane_command,
    pane_has_claude,
    send_interrupt,
    send_key,
    send_prompt,
    session_exists,
)
from .dangerous_commands import is_dangerous_command
from .session_readiness import classify_readiness, is_shell
from . import stt as _stt
from .control_audit import RateLimiter as _RateLimiter
from .control_audit import limiter as _rate_limiter, record as _audit

import sys as _sys
_PSTATUS_DIR = "/home/kyuwon/projects/project-status"
if _PSTATUS_DIR not in _sys.path:
    _sys.path.insert(0, _PSTATUS_DIR)
# Only scanner is needed now: the PI review gate reads plans and reports from
# the projects tree. The Projects tab that used to mount this package's router,
# static files and scan loop is gone.
from scanner import PROJECTS_ROOT as _SCANNER_PROJECTS_ROOT  # noqa: E402
from scanner import find_rpt_artifact as _find_rpt_artifact  # noqa: E402

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between state refreshes
# Default stays 0.0.0.0 (reachable over Tailscale). Narrowing the listener is
# opt-in via CTB_BIND_HOST because this runs under systemd Restart=always:
# hard-binding to an interface that is not up yet at boot would loop forever.
# LAN exposure is closed by the firewall rules in deploy/firewall-8420.sh.
BIND_HOST = os.environ.get("CTB_BIND_HOST") or "0.0.0.0"
BIND_PORT = 8420


def _resolve_control_secret() -> str:
    """Shared secret guarding every mutating endpoint.

    CTB_FOCUS_SECRET is the former name and is still accepted so an existing
    deployment that only set the old variable does not silently lose writes.
    """
    return os.environ.get("CTB_CONTROL_SECRET") or os.environ.get("CTB_FOCUS_SECRET", "")


_CONTROL_SECRET = _resolve_control_secret()
_SESSION_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-:.]{1,64}$')

# How long to wait before re-reading the pane to confirm a prompt landed.
# Long enough for the TUI to redraw, short enough not to stall the request.
_SEND_CONFIRM_DELAY = 0.4


def require_control_token(x_ctb_secret: str | None = Header(None)) -> None:
    """Fail-closed gate for endpoints that change state or drive a session.

    Read endpoints stay open: the dashboard is a monitor first, and the VSCode
    webview's portMapping proxy only forwards GET, so gating reads would break
    it. Writes are a different matter -- they reach live tmux sessions.

    With no secret configured we refuse writes (503) instead of allowing them.
    The previous behaviour was the opposite, and since the secret was never
    actually injected into the service environment, that meant wide-open
    control endpoints in production.
    """
    if not _CONTROL_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Control endpoints are disabled: CTB_CONTROL_SECRET is not set",
        )
    if not x_ctb_secret or not secrets.compare_digest(x_ctb_secret, _CONTROL_SECRET):
        raise HTTPException(status_code=403, detail="Invalid or missing X-CTB-Secret")

# PI Review Gate
_REVIEW_SECRET = os.environ.get("CTB_REVIEW_SECRET", "")
_REVIEW_OVERLAY_DIR = os.path.expanduser(
    os.environ.get("CTB_REVIEW_OVERLAY_DIR", "~/.claude-ops")
)
_REVIEW_LOCK_TIMEOUT = int(os.environ.get("CTB_REVIEW_OVERLAY_LOCK_TIMEOUT", "10"))
_CTB_PROJECTS_ROOT = os.environ.get("CTB_PROJECTS_ROOT", _SCANNER_PROJECTS_ROOT)
_CTB_DEFAULT_REVIEWER_ID = os.environ.get("CTB_DEFAULT_REVIEWER_ID", "")

_REVIEW_ALLOWED_TAGS = frozenset({
    "p", "h1", "h2", "h3", "h4", "ul", "ol", "li",
    "strong", "em", "code", "pre", "blockquote", "br", "a",
})
_REVIEW_ALLOWED_ATTRS: dict = {"a": ["href", "title"]}


def _render_plan_html(md: str) -> str:
    html = _markdown.markdown(md, extensions=["fenced_code", "tables"])
    return _bleach.clean(html, tags=_REVIEW_ALLOWED_TAGS,
                         attributes=_REVIEW_ALLOWED_ATTRS, strip_comments=True)


def _extract_pi_summary_section(content: str) -> str | None:
    m = re.search(
        r'(^## PI Review Summary\s*\n.*?)(?=^##[^#]|\Z)',
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        return None
    section = m.group(1).strip()
    if not section:
        return None
    # Require at least one content line beyond the heading itself
    body = re.sub(r'^## PI Review Summary\s*', '', section, flags=re.MULTILINE).strip()
    return section if body else None


def _load_latest_plan(project: str) -> dict[str, str | None]:
    try:
        root = Path(_CTB_PROJECTS_ROOT).resolve()
        project_path = (root / project).resolve()
        if not str(project_path).startswith(str(root) + "/"):
            return {"summary": None, "full": None}
        plans = list(project_path.glob(".omc/plans/*.md"))
        if not plans:
            return {"summary": None, "full": None}
        latest = sorted(plans, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        content = latest.read_text()
        summary_md = _extract_pi_summary_section(content)
        return {
            "summary": _render_plan_html(summary_md) if summary_md else None,
            "full": _render_plan_html(content),
        }
    except Exception as e:
        logger.warning("plan load failed for %s: %s", project, e)
        return {"summary": None, "full": None}


def _load_rpt(project: str) -> str | None:
    try:
        root = Path(_CTB_PROJECTS_ROOT).resolve()
        project_path = (root / project).resolve()
        if not str(project_path).startswith(str(root) + "/"):
            return None
        rpt_path = _find_rpt_artifact(project_path)
        if not rpt_path:
            return None
        content = rpt_path.read_text()
        html = _markdown.markdown(content, extensions=["fenced_code", "tables"])
        return _bleach.clean(html, tags=_REVIEW_ALLOWED_TAGS, attributes=_REVIEW_ALLOWED_ATTRS, strip_comments=True)
    except Exception as e:
        logger.warning("rpt load failed for %s: %s", project, e)
        return None

if not _REVIEW_SECRET:
    logger.warning("CTB_REVIEW_SECRET not set — /review route will return 403")


class FocusRequest(BaseModel):
    session: str


class PinnedRequest(BaseModel):
    Q1: list[str] = []
    Q2: list[str] = []
    Q3: list[str] = []
    Q4: list[str] = []


# --- Session Poller (reuses SessionStateAnalyzer for accurate detection) ---

_cached_state: Dict[str, Any] = {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""}
# Not /tmp. This host sweeps it (`q /tmp ... 10d`), and pins are configuration,
# not scratch: they gate every completion alert, so losing them turns alerts off
# silently and permanently. That is exactly how "notifications used to come and
# then stopped" happened. Timestamps live here too, for the same reason —
# losing them resets every idle badge.
_STATE_DIR = os.path.expanduser(os.environ.get("CTB_STATE_DIR", "~/.claude-ops"))
_TS_PERSIST_PATH = os.path.join(_STATE_DIR, "session-timestamps.json")
_PINNED_PERSIST_PATH = os.path.join(_STATE_DIR, "pinned-sessions.json")
# Where both used to live. Read once so an upgrade does not drop live pins.
# Watched by the VSCode extension, which calls terminal.show() when it changes.
# Module level so a test can redirect it: as a local it could not be, and test
# runs really did move the user's editor by writing a session name into it --
# a file write, so nothing about the tmux guard could catch it.
_FOCUS_SIGNAL_PATH = "/tmp/ctb-focus-signal.json"
_LEGACY_PINNED_PATH = "/tmp/ctb-pinned-sessions.json"
_LEGACY_TS_PATH = "/tmp/ctb-session-timestamps.json"


def _read_pinned_file(path: str) -> Dict[str, Any] | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return None
    return data if all(k in data for k in ("Q1", "Q2", "Q3", "Q4")) else None


def _load_pinned() -> Dict[str, Any]:
    return (_read_pinned_file(_PINNED_PERSIST_PATH)
            or _read_pinned_file(_LEGACY_PINNED_PATH)
            or {"Q1": [], "Q2": [], "Q3": [], "Q4": []})


_pinned_state: Dict[str, Any] = _load_pinned()

def _load_timestamps() -> Dict[str, float]:
    """Load persisted session timestamps from disk (survives server restart)."""
    try:
        try:
            f = open(_TS_PERSIST_PATH)
        except FileNotFoundError:
            f = open(_LEGACY_TS_PATH)
        with f:
            data = json.load(f)
        # Discard entries older than 24h to avoid stale data
        cutoff = time.time() - 86400
        return {k: v for k, v in data.items() if v > cutoff}
    except Exception:
        return {}

_prev_session_timestamps: Dict[str, float] = _load_timestamps()  # track per-session state change time
# Anything a pane printed before this moment happened while we were not
# watching; anything after it we saw happen. Used to tell a transition during
# an outage apart from a pane that simply keeps printing.
_PROCESS_START = time.time()
_completion_times: Dict[str, float] = {}  # track working->idle/waiting transitions
_state_analyzer = SessionStateAnalyzer()

# Hold timer: keep WORKING state for a few seconds after indicators disappear
_working_hold: Dict[str, float] = {}  # session_name -> last_seen_working_time
_working_since: Dict[str, float] = {}  # session_name -> time when WORKING state started (stall detection)
_WORKING_HOLD_SECONDS = 8  # hold WORKING for 8s after last working indicator

# Hold timer: keep STUCK_AFTER_AGENT state stable — prevents sort position from
# dropping to idle(5) when detection misses a single poll cycle
_stuck_hold: Dict[str, float] = {}  # session_name -> last_seen_stuck_time
_STUCK_HOLD_SECONDS = 30  # hold STUCK_AFTER_AGENT for 30s after last detection
_FRESH_TTL = 300  # seconds to keep completed_at visible (5 minutes)

# T2: Persist last known prompt per session to avoid flickering
# Structure: {session_name: {"text": str, "timestamp": float}}
_last_known_prompt: Dict[str, Dict] = {}
_PROMPT_TTL = 60  # seconds to keep stale prompt visible

# T3: Persist last known working phase — show on idle cards after work completes


def _probe_session(name: str) -> tuple:
    """Probe a single session's state and path (called in thread pool)."""
    path = get_session_path(name)
    raw_state = _state_analyzer.get_state(name, session_path=path)
    state = raw_state
    now = time.time()

    # Hold timer: if state was recently WORKING, keep it WORKING through brief gaps
    if raw_state == SessionState.WORKING:
        _working_hold[name] = now
        # Clear previous completion so next completion can be detected
        _completion_times.pop(name, None)
    elif raw_state in (SessionState.IDLE, SessionState.WAITING_INPUT) and name in _working_hold:
        elapsed = now - _working_hold[name]
        # Was recently WORKING -> work just completed (IDLE or WAITING)
        if name not in _completion_times:
            _completion_times[name] = now
            logger.info(f"Fresh completion: {name}")
        if raw_state == SessionState.IDLE and elapsed < _WORKING_HOLD_SECONDS:
            logger.debug(f"Hold WORKING for {name} ({elapsed:.1f}s < {_WORKING_HOLD_SECONDS}s)")
            state = SessionState.WORKING
        else:
            del _working_hold[name]

    # Hold timer: keep STUCK_AFTER_AGENT stable through brief detection gaps
    if raw_state == SessionState.STUCK_AFTER_AGENT:
        _stuck_hold[name] = now
    elif state == SessionState.IDLE and name in _stuck_hold:
        elapsed = now - _stuck_hold[name]
        if elapsed < _STUCK_HOLD_SECONDS:
            logger.debug(f"Hold STUCK_AFTER_AGENT for {name} ({elapsed:.1f}s < {_STUCK_HOLD_SECONDS}s)")
            state = SessionState.STUCK_AFTER_AGENT
        else:
            _stuck_hold.pop(name, None)

    # Expire stale completion times
    completed_at = _completion_times.get(name)
    if completed_at and (now - completed_at) >= _FRESH_TTL:
        del _completion_times[name]

    # Extract context percentage and last prompt from cached screen content
    screen_content = _state_analyzer.get_screen_content(name, use_cache=True)
    context_percent = _state_analyzer.extract_context_percent(screen_content)
    raw_prompt = _state_analyzer.extract_last_prompt(screen_content)

    # T2: Persist last known prompt — update on new detection, keep stale on miss
    now_ts = time.time()
    if raw_prompt:
        _last_known_prompt[name] = {"text": raw_prompt, "timestamp": now_ts}
        last_prompt = raw_prompt
    elif name in _last_known_prompt:
        # TTL 60s — after expiry, still show stale value (avoid flickering)
        last_prompt = _last_known_prompt[name]["text"]
    else:
        last_prompt = None

    work_context = _state_analyzer.extract_work_context(path)

    pending_count = _state_analyzer.extract_pending_task_count(screen_content)
    progress = _state_analyzer.extract_screen_progress(screen_content)
    last_reply = _state_analyzer.extract_last_reply(screen_content)
    recap = _state_analyzer.extract_recap(screen_content)

    # Stall detection: track when WORKING state started
    if state == SessionState.WORKING:
        if name not in _working_since:
            _working_since[name] = now
        working_since = _working_since[name]
    else:
        _working_since.pop(name, None)
        working_since = None

    return (name, state.value, path, context_percent, last_prompt, work_context,
            pending_count, working_since, progress, last_reply, recap)


# A completion notification arrives on a lock screen, where the reader has a
# couple of lines and no context. "wte 세션이 작업을 마쳤습니다" tells them which
# of fifteen pinned sessions rang and nothing about what happened. Everything
# worth saying is already computed for the card.
_TOOL_CALL_RE = re.compile(
    r"^(Bash|Read|Edit|Write|Grep|Glob|Task|WebFetch|WebSearch|TodoWrite|"
    r"NotebookEdit|MultiEdit)\s*\(")


def _one_line(text: str, limit: int) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def _completion_body(entry: Dict[str, Any]) -> str:
    """The ask, the outcome, and how much is left -- in a few lines."""
    lines = []

    prompt = _one_line(entry.get("last_prompt") or "", 70)
    if prompt:
        lines.append(f"❯ {prompt}")

    # Claude's own recap says what the session is about far better than the
    # first line of the last reply; fall back to the reply when absent.
    recap = _one_line(entry.get("recap") or "", 200)
    if recap:
        lines.append(f"※ {recap}")
    else:
        reply = _one_line(entry.get("last_reply") or "", 110)
        # A tool invocation is not an outcome; it is what the outcome was made of.
        if reply and not _TOOL_CALL_RE.match(reply):
            lines.append(f"● {reply}")

    extras = []
    progress = entry.get("progress")
    if isinstance(progress, (list, tuple)) and len(progress) == 2:
        extras.append(f"{progress[0]}/{progress[1]} 단계")
    pending = entry.get("pending_count")
    if pending:
        extras.append(f"할 일 {pending}개")
    context = entry.get("context_percent")
    # Only when it is close enough to matter for what to do next.
    if isinstance(context, int) and context >= 80:
        extras.append(f"ctx {context}%")
    if extras:
        lines.append(" · ".join(extras))

    return "\n".join(lines) or "작업을 마쳤습니다"


# Which completion we have already pushed for, per session. Keyed by the
# completion timestamp so the next completion of the same session pushes again.
#
# On disk, because this used to live only in memory and the process restarts --
# for a deploy, for a crash, for a config change. Empty after a restart, the
# next poll saw completions it had already pushed for and pushed again, so a
# quiet afternoon of restarts arrived on the phone as a burst of duplicates for
# work that finished hours ago. Persisted, a restart is invisible here.
_PUSHED_PATH = os.path.join(_STATE_DIR, "pushed-completions.json")


def _load_pushed_completions() -> Dict[str, float]:
    try:
        with open(_PUSHED_PATH) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Written by us, but read defensively: a truncated write must not take the
    # whole poll loop down on the next start.
    return {k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, (int, float))}


def _save_pushed_completions() -> None:
    """Best effort: a completion pushed twice is a nuisance, a crash is not."""
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        tmp = _PUSHED_PATH + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(_pushed_completions, fh)
        os.replace(tmp, _PUSHED_PATH)
    except OSError as e:
        logger.warning("Could not persist pushed completions: %s", e)


_pushed_completions: Dict[str, float] = _load_pushed_completions()


def _push_completions(session_list: list) -> None:
    """Push a finished session to every subscribed phone.

    Pinned sessions only, matching the in-page alerts: with 71 sessions, pushing
    all of them would make the lock screen useless. Nothing here may raise --
    polling drives the whole UI, and a push service having a bad day must not
    take it down with it.
    """
    try:
        pinned = pinned_session_names()
        if not pinned:
            return
        for entry in session_list:
            name = entry.get("name")
            completed_at = entry.get("completed_at")
            if not completed_at or name not in pinned:
                continue
            if _pushed_completions.get(name) == completed_at:
                continue
            _pushed_completions[name] = completed_at
            _save_pushed_completions()
            short = name.replace("claude_", "", 1)
            # Logged either way: this path has failed silently in several
            # different ways, and "did a push go out" should not need a phone
            # to answer.
            delivered = push.notify(name, _completion_body(entry),
                                    title=f"✅ {short}")
            logger.info("Completion push for %s: delivered to %d subscriber(s)",
                        name, delivered)
    except Exception as e:
        logger.warning("Completion push failed: %s", e)


def _poll_sessions() -> Dict[str, Any]:
    """Poll all tmux sessions and return state dict using SessionStateAnalyzer."""
    global _prev_session_timestamps
    sessions = get_all_claude_sessions()
    now = time.time()
    activity_map = get_sessions_activity()

    # Parallel probe: ~1-2s instead of ~30s for 26 sessions
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_probe_session, sessions))

    session_list = []
    for (name, state_val, path, context_percent, last_prompt, work_context,
         pending_count, working_since, progress, last_reply, recap) in results:
        # Only update timestamp when state actually changes
        prev_ts = _prev_session_timestamps.get(name, 0)
        prev_state = None
        for s in _cached_state.get("sessions", []):
            if s["name"] == name:
                prev_state = s.get("state")
                break
        if prev_ts == 0:
            # Never seen this session. It predates us, so the poll time would
            # claim it just changed state; the pane's last activity is the
            # closest thing we have to when the current state began.
            prev_ts = activity_map.get(name) or now
            _prev_session_timestamps[name] = prev_ts
        elif prev_state is None:
            # First poll of a fresh process: _cached_state is in-memory only, so
            # there is nothing to compare against. Treating that as a state
            # change is what reset every idle badge to zero on each restart, so
            # the persisted timestamp stands by default.
            # It can still be out of date — the session may have moved on while
            # we were down. Output after the moment we recorded means something
            # happened since, and it is the only record of when.
            # Two limits on trusting it, because output is not proof of a state
            # change: a WORKING pane prints continuously, so its activity is
            # always ~now and would erase how long it has been running; and a
            # settled pane can still print (a repainting footer, a stray
            # `tail -f`), so only output from before we started counts —
            # anything since is chatter we watched happen without the state
            # moving, and adopting it would put the badge back at zero.
            activity = activity_map.get(name) or 0
            if (state_val != SessionState.WORKING.value
                    and prev_ts < activity <= _PROCESS_START):
                prev_ts = activity
                _prev_session_timestamps[name] = prev_ts
        elif prev_state != state_val:
            _prev_session_timestamps[name] = now
            prev_ts = now

        entry = {
            "name": name,
            "state": state_val,
            "path": path,
            "updated_at": prev_ts,
            "completed_at": _completion_times.get(name),
            "context_percent": context_percent,  # null when unavailable (frontend hides gauge)
            "last_prompt": last_prompt or "",     # always string (frontend shows placeholder)
            "work_context": work_context or "",   # always string (frontend shows placeholder)
            "progress": list(progress) if progress else None,  # [n, m] from [Stage n/m]
            "last_reply": last_reply or "",
            "recap": recap or "",                 # Claude Code's own session recap (preferred summary)
            "pending_count": pending_count,       # null=no TodoWrite, 0=all done, N=pending tasks
            "working_since": working_since,       # epoch float when WORKING started, null otherwise
            "last_activity": activity_map.get(name, 0),  # tmux session_activity epoch (staleness filter)
        }
        session_list.append(entry)

    _push_completions(session_list)

    # Content hash for SSE change detection (includes dynamic fields for real-time updates)
    content_key = json.dumps([
        (s["name"], s["state"], bool(s.get("completed_at")),
         s.get("context_percent"), s.get("last_prompt", ""), s.get("work_context", ""),
         s.get("recap", ""))
        for s in session_list
    ], sort_keys=True)
    content_hash = hashlib.md5(content_key.encode()).hexdigest()[:8]

    # Clean up timestamps and prompt cache for removed sessions
    active_names = {s["name"] for s in session_list}
    _prev_session_timestamps = {k: v for k, v in _prev_session_timestamps.items() if k in active_names}
    for gone in set(_pushed_completions) - active_names:
        del _pushed_completions[gone]
    for gone in set(_last_known_prompt) - active_names:
        del _last_known_prompt[gone]

    # Persist timestamps to disk so they survive server restarts.
    # Written to a temporary file and renamed: a crash partway through a plain
    # write leaves truncated JSON, _load_timestamps() swallows the parse error
    # and returns {}, and every badge resets to zero — the failure this whole
    # mechanism exists to prevent.
    try:
        tmp_dir = os.path.dirname(_TS_PERSIST_PATH) or "."
        os.makedirs(tmp_dir, mode=0o700, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(_prev_session_timestamps, f)
            os.replace(tmp_path, _TS_PERSIST_PATH)
        except Exception:
            os.unlink(tmp_path)
            raise
    except Exception:
        pass

    return {
        "version": 1,
        "updated_at": now,
        "sessions": session_list,
        "_hash": content_hash,
    }


# --- PI Review Gate helpers ---

def _atomic_json_write(path: str, data: dict) -> bool:
    """Write JSON to path atomically via write-then-rename. Returns False on error."""
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _verify_review_sig(card: str, focus: str, rv: str, exp: str, project: str, sig: str) -> bool:
    msg = "|".join([card, focus, rv, str(exp), project]).encode()
    expected = _hmac_mod.new(_REVIEW_SECRET.encode(), msg, hashlib.sha256).hexdigest()
    return secrets.compare_digest(expected, sig)


def _read_consumed_links(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"links": {}}


def _write_consumed_links(path: str, data: dict) -> bool:
    return _atomic_json_write(path, data)


def _write_overlay_link_access(card: str, rv: str, overlay_path: str) -> bool:
    """Append link_accessed entry to ticket review_history. Returns False if write fails."""
    try:
        with open(overlay_path) as f:
            data = json.load(f)
    except Exception:
        return True  # no overlay to update — not a write failure

    tickets = data.get("tickets", {})
    ticket = tickets.get(card)
    if ticket is None:
        return True  # unknown ticket — not a write failure

    history = ticket.setdefault("review_history", [])
    history.append({"action": "link_accessed", "reviewer": rv, "ts": datetime.now(timezone.utc).isoformat()})
    ticket["review_history"] = history[-50:]
    tickets[card] = ticket
    data["tickets"] = tickets

    return _atomic_json_write(overlay_path, data)


def _get_review_tickets() -> list:
    overlay_path = os.path.join(_REVIEW_OVERLAY_DIR, "ticket-overlay.json")
    try:
        with open(overlay_path) as f:
            data = json.load(f)
    except Exception:
        return []
    return [
        {"id": tid, "review_state": t.get("review_state", ""), "updated_at": t.get("updated_at", "")}
        for tid, t in data.get("tickets", {}).items()
        if t.get("review_state") == "needs_pi_review"
    ]


async def _purge_consumed_loop() -> None:
    """Hourly purge of consumed-links.json entries older than 7 days."""
    while True:
        await asyncio.sleep(3600)
        try:
            consumed_path = os.path.join(_REVIEW_OVERLAY_DIR, "consumed-links.json")
            lock_path = os.path.join(_REVIEW_OVERLAY_DIR, "overlay.lock")
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            with _filelock.FileLock(lock_path, timeout=_REVIEW_LOCK_TIMEOUT):
                data = _read_consumed_links(consumed_path)
                links = data.get("links", {})
                pruned = {}
                for k, entry in links.items():
                    try:
                        ts = datetime.fromisoformat(entry.get("consumed_at", ""))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts >= cutoff:
                            pruned[k] = entry
                    except Exception:
                        pass
                if len(pruned) < len(links):
                    data["links"] = pruned
                    _write_consumed_links(consumed_path, data)
        except Exception as e:
            logger.warning("purge_consumed_loop error: %s", e)


async def _background_poller():
    """Background task that polls sessions every POLL_INTERVAL seconds."""
    global _cached_state
    logger.info("Background poller started")
    while True:
        try:
            loop = asyncio.get_running_loop()
            _cached_state = await loop.run_in_executor(None, _poll_sessions)
            logger.debug(f"Polled {len(_cached_state.get('sessions', []))} sessions")
        except Exception as e:
            logger.warning(f"Poller error: {e}", exc_info=True)
        await asyncio.sleep(POLL_INTERVAL)


# --- FastAPI App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background poller on startup, cancel on shutdown."""
    logger.info(f"Dashboard server starting on {BIND_HOST}:{BIND_PORT}")
    if not _CONTROL_SECRET:
        logger.warning(
            "CTB_CONTROL_SECRET not set -- mutating endpoints are DISABLED (503). "
            "Set it in .env; the systemd unit injects it via EnvironmentFile."
        )

    # Haiku rate-limiting semaphore: max 5 concurrent calls
    app.state.haiku_semaphore = asyncio.Semaphore(5)
    app.state.startup_ready = asyncio.Event()
    app.state.degraded = False

    # OAuth2 startup check (graceful)
    try:
        import google.auth.transport.requests as _gtr  # noqa: PLC0415
        import google.oauth2.credentials as _gcreds  # noqa: PLC0415
        _token_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
        if os.path.exists(_token_path):
            with open(_token_path) as _f:
                _cred_data = json.load(_f)
            _creds = _gcreds.Credentials(token=None, **{k: _cred_data[k] for k in ("client_id","client_secret","refresh_token","token_uri") if k in _cred_data})
            _creds.refresh(_gtr.Request())
            logger.info("OAuth2 startup check PASSED")
        else:
            logger.info("OAuth2 credentials not found, skipping startup check")
    except Exception as _e:
        logger.warning("OAuth2 startup check FAILED: %s — dashboard continues in degraded mode", _e)
        app.state.degraded = True

    app.state.startup_ready.set()

    task = asyncio.create_task(_background_poller())
    purge_task = asyncio.create_task(_purge_consumed_loop())
    app.state.purge_consumed_task = purge_task
    yield
    task.cancel()
    purge_task.cancel()
    for t in (task, purge_task):
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("Dashboard server shutting down")


app = FastAPI(
    title="CTB Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
_SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY") or secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET_KEY, max_age=72 * 3600)

# Serve static files (HTML frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def _revalidate_static(request: Request, call_next):
    """Make the browser check /static with us before reusing its copy.

    StaticFiles sends an ETag and Last-Modified but no Cache-Control, and a
    response with neither Cache-Control nor Expires is heuristically cached:
    the browser invents a freshness lifetime and serves the old file without
    asking. The dashboard's JS is the app itself, so a phone can keep running
    a previous deploy indefinitely -- which is exactly what a stale console
    looks like. 'no-cache' does not mean 'do not store': the copy is kept and
    revalidated, so an unchanged file still costs one 304.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _asset_version() -> str:
    """Newest mtime across the served JS, as a cache-busting query value.

    Belt and braces with the header above: a URL that changes on deploy cannot
    be answered from any cache, including a service worker's, whatever the
    headers say.
    """
    newest = 0.0
    js_dir = os.path.join(static_dir, "js")
    if os.path.isdir(js_dir):
        for entry in os.scandir(js_dir):
            if entry.name.endswith(".js"):
                newest = max(newest, entry.stat().st_mtime)
    return str(int(newest))

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)

# Project-status integration (Phase C)


@app.get("/dev/cards")
async def dev_cards(request: Request):
    return templates.TemplateResponse(request, "dev_cards.html", {"csp_nonce": secrets.token_hex(16)})


@app.get("/")
async def root(request: Request):
    """Serve dashboard HTML via Jinja2 template with CSP nonce."""
    nonce = secrets.token_hex(16)
    # Allow existing inline scripts (tailwind config, main app JS) via 'unsafe-inline'.
    # Alpine uses @alpinejs/csp (eval-free build) so no 'unsafe-eval' needed.
    csp = (
        f"script-src 'self' 'unsafe-inline' 'nonce-{nonce}' "
        "https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
        "https://fonts.googleapis.com; object-src 'none'"
    )
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "csp_nonce": nonce,
            "dashboard_url": os.environ.get("CTB_DASHBOARD_URL", ""),
            "asset_v": _asset_version(),
        },
    )
    response.headers["Content-Security-Policy"] = csp
    # Dashboard HTML embeds its JS inline; never let a browser serve a stale
    # copy after a deploy (otherwise new client code silently 404s new routes).
    response.headers["Cache-Control"] = "no-store"
    return response


async def get_haiku_semaphore(request: Request) -> asyncio.Semaphore:
    return request.app.state.haiku_semaphore


@app.get("/api/sessions")
async def get_sessions():
    """REST endpoint: current session state snapshot."""
    return _cached_state


async def _session_event_generator() -> AsyncGenerator[dict, None]:
    """Yield session state as SSE events only when session data actually changes."""
    last_hash = ""
    while True:
        current_hash = _cached_state.get("_hash", "")
        if current_hash and current_hash != last_hash:
            last_hash = current_hash
            yield {"event": "sessions", "data": json.dumps(_cached_state, ensure_ascii=False)}
        await asyncio.sleep(POLL_INTERVAL)


@app.get("/api/sessions/stream")
async def session_stream():
    """SSE endpoint: real-time session state updates."""
    return EventSourceResponse(_session_event_generator())


# The console deepens this on demand as the reader scrolls back. Bounded so a
# crafted request cannot ask tmux for an unbounded capture and ship it back.
_MAX_LOG_LINES = 5000


# tmux keeps a pane at the width of whatever client last attached, and a
# session nobody ever attached to sits at the 80-column default. That width --
# not the browser's -- is what breaks the console's lines, and it is why they
# come out ragged: the sessions here are anywhere between 80 and 159 columns.
# capture-pane -J rejoins tmux's own soft wraps, but Claude's TUI hard-wraps its
# output at the pane width itself, and those breaks are real newlines that
# nothing downstream can undo.
#
# So widen the pane instead, and only when nobody is watching it in a terminal.
# resize-window flips the window to a manual size, which would leave a later
# attach mis-fitted, so the option is handed straight back: the new width holds
# while the session is detached, and the next client to attach re-fits it.
#
# Only what tmux draws from here on is wide -- scrollback keeps the wrapping it
# was written with.
_MIN_FIT_COLS = 80
_MAX_FIT_COLS = 400


def _fit_pane(name: str, cols: int) -> None:
    cols = max(_MIN_FIT_COLS, min(_MAX_FIT_COLS, cols))
    try:
        probe = subprocess.run(
            ["tmux", "display", "-p", "-t", name,
             "#{session_attached} #{window_width} #{window_height}"],
            capture_output=True, text=True, timeout=5,
        )
        if probe.returncode != 0:
            return
        attached, width, height = probe.stdout.split()
        if attached != "0" or int(width) >= cols:
            return
        subprocess.run(
            ["tmux", "resize-window", "-t", name, "-x", str(cols), "-y", height],
            capture_output=True, text=True, timeout=5,
        )
        _PANE_COLS.pop(name, None)
        subprocess.run(
            ["tmux", "set", "-w", "-t", name, "-u", "window-size"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, ValueError):
        return


# The width changes only when something resizes the pane, and the console polls
# every 2 seconds -- so ask tmux once and reuse the answer for a while. The
# probe is cheap (~4ms) but it is a blocking subprocess inside an async handler,
# and it was doubling the per-poll cost of the endpoint for a number that
# rarely moves.
#
# Rarely, not never, and not only through us: a terminal attaching or a
# resize-window from a shell never passes through _fit_pane, so an entry kept
# for the life of the process would be permanently wrong. The direction that
# matters is cached < actual -- every row that happens to be exactly the
# remembered width then reads as cut at the margin, and its links are dropped
# or joined to the row below. A short life keeps nearly all of the saved
# probes and lets a stale width heal on its own, the way it did before there
# was a cache at all.
_PANE_COLS_TTL = 10.0
_PANE_COLS: dict[str, tuple[int, float]] = {}


_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
_DIM_RE = re.compile(r"\x1b\[(?:[0-9;]*;)?2(?:;[0-9;]*)?m")
_BOX_RE = re.compile(r"^[\s\u00a0]*\u276f[\s\u00a0]*(.*)$")


def box_is_ghost(raw_lines: list[str]) -> bool | None:
    """Whether the text in Claude Code's input box is a ghost suggestion.

    Claude Code draws a suggested prompt in the box as dim text (SGR 2); a
    Tab makes it real, and typed text is never dim. Plain capture-pane drops
    the attribute, so the two look identical to the client -- this reads the
    escape-coded capture and answers for the last box line. None when there
    is no box with text in it.
    """
    for raw in reversed(raw_lines):
        plain = _SGR_RE.sub("", raw)
        m = _BOX_RE.match(plain)
        if not m:
            continue
        text = m.group(1).rstrip()
        if not text:
            return None
        # Dim opened before the first character of the text, and not reset
        # in between: the escapes after the ❯ and before that character.
        head = raw[: raw.index(text[0], raw.index("\u276f"))]
        after_prompt = head[head.index("\u276f"):]
        return bool(_DIM_RE.search(after_prompt))
    return None


def _box_ghost(name: str) -> bool | None:
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-t", name, "-p", "-e", "-S-15"],
            capture_output=True, text=True, timeout=5,
        )
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    return box_is_ghost(r.stdout.split("\n"))


def _pane_cols(name: str) -> int:
    """The pane's width, so the console can tell a wrapped line from a whole one.

    -J rejoins tmux's own wrapping and trims the trailing padding with it, so
    from the text alone every line looks deliberately ended -- a log line that
    happens to finish with a URL is indistinguishable from the first half of a
    wrapped one. The width is the difference: only a row filled to the last
    column can have been cut there.

    pane_width, not window_width: capture-pane captures a pane, and a window
    split vertically holds panes half its width. Asking for the window's width
    there reports roughly double the columns the text was wrapped at, so no
    line ever matches and the console silently stops rejoining anything.

    0 when tmux will not say, which the console reads as "do not guess".
    """
    cached = _PANE_COLS.get(name)
    if cached is not None and time.monotonic() - cached[1] < _PANE_COLS_TTL:
        return cached[0]
    try:
        probe = subprocess.run(
            ["tmux", "display", "-p", "-t", name, "#{pane_width}"],
            capture_output=True, text=True, timeout=5,
        )
        if probe.returncode != 0:
            return 0
        cols = int(probe.stdout.strip() or 0)
    except (subprocess.TimeoutExpired, ValueError):
        return 0
    _PANE_COLS[name] = (cols, time.monotonic())
    return cols


@app.get("/api/sessions/{name}/log")
async def get_session_log(name: str, lines: int = 50, fit: int = 0, since: str = ""):
    """Return recent tmux pane output for a session.

    fit: columns the console can show. Sent when a session is opened, not on
    every poll -- a resize is a repaint for the program in the pane.
    """
    if not _SESSION_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid session name")
    lines = max(1, min(_MAX_LOG_LINES, lines))
    if fit:
        _fit_pane(name, fit)
    try:
        result = subprocess.run(
            # -J joins pane-width-wrapped lines back into their original form.
            # Without it, a copied block inherits artificial line breaks at
            # whatever width the tmux pane happened to be.
            ["tmux", "capture-pane", "-t", name, "-p", "-J", f"-S-{lines}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=404, detail="Session not found")
        ghost = _box_ghost(name)
        # A fingerprint of what the client would paint. The console polls
        # every two seconds and most polls find the pane unchanged; with
        # `since` set to the last fingerprint it gets a short answer and
        # skips the repaint instead of rebuilding forty lines for nothing.
        digest = hashlib.sha1(
            f"{ghost}\n{result.stdout}".encode("utf-8", "surrogateescape")
        ).hexdigest()[:16]
        if since and since == digest:
            return {"session": name, "unchanged": True, "hash": digest}
        return {
            "session": name, "log": result.stdout, "cols": _pane_cols(name),
            # Ghost or typed: the client cannot tell from the plain capture.
            "ghost": ghost, "hash": digest,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="tmux timeout")


class PromptRequest(BaseModel):
    text: str


@app.post("/api/sessions/{name}/prompt", dependencies=[Depends(require_control_token)])
async def session_prompt(name: str, req: PromptRequest, request: Request):
    """Type a prompt into a session and submit it.

    Screening happens before anything reaches tmux: the same destructive-command
    list the Telegram bot uses, since this endpoint is reachable from a phone
    where the screen is not visible.
    """
    client = request.client.host if request.client else None
    if not _SESSION_NAME_RE.match(name):
        _audit("prompt", name, client, False, "invalid_name")
        raise HTTPException(status_code=422, detail="Invalid session name")

    if not _rate_limiter.allow():
        _audit("prompt", name, client, False, "rate_limited")
        raise HTTPException(status_code=429, detail="Too many control requests")

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, session_exists, name):
        _audit("prompt", name, client, False, "no_session")
        raise HTTPException(status_code=404, detail="Session not found")

    if is_dangerous_command(req.text):
        _audit("prompt", name, client, False, "dangerous_pattern")
        raise HTTPException(
            status_code=400,
            detail="Blocked: text matches a destructive-command pattern",
        )

    # Refuse rather than send blind: on a phone the screen is not visible, and
    # tmux send-keys succeeds even when a shell or a permission prompt would
    # swallow the text.
    analyzer = _state_analyzer
    state = await loop.run_in_executor(
        None, lambda: analyzer.get_state(name, None, False)
    )
    before = await loop.run_in_executor(
        None, lambda: analyzer.get_screen_content(name, use_cache=False)
    )
    cmd = await loop.run_in_executor(None, pane_command, name)
    # Only worth the process walk when the reported command looks like a shell,
    # which is the only case where it changes the answer.
    claude_running = False
    if is_shell(cmd):
        claude_running = await loop.run_in_executor(None, pane_has_claude, name)
    can_send, reason, message = classify_readiness(state, before, cmd, claude_running)
    if not can_send:
        _audit("prompt", name, client, False, reason)
        return Response(
            content=json.dumps(
                {
                    "session": name,
                    "status": "refused",
                    "reason": reason,
                    "state": state.value,
                    "message": message,
                },
                ensure_ascii=False,
            ),
            status_code=409,
            media_type="application/json",
        )

    try:
        await loop.run_in_executor(None, send_prompt, name, req.text)
    except ValueError as e:
        _audit("prompt", name, client, False, "invalid_text")
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        _audit("prompt", name, client, False, "tmux_failed")
        raise HTTPException(status_code=502, detail=str(e))

    # Confirm something actually changed on screen. tmux reports success for a
    # send that landed nowhere, so this is the only evidence we have.
    await asyncio.sleep(_SEND_CONFIRM_DELAY)
    after = await loop.run_in_executor(
        None, lambda: analyzer.get_screen_content(name, use_cache=False)
    )
    confirmed = bool(after) and after != before
    if not confirmed:
        logger.warning("prompt to %s produced no screen change", name)
    _audit("prompt", name, client, True, None if confirmed else "unconfirmed")
    return {
        "session": name,
        "status": "sent",
        "state": state.value,
        "confirmed": confirmed,
    }


class KeyRequest(BaseModel):
    key: str


@app.post("/api/sessions/{name}/key", dependencies=[Depends(require_control_token)])
async def session_key(name: str, req: KeyRequest, request: Request):
    """Send one allowlisted key -- how a phone answers Claude's prompts.

    No readiness gate here on purpose: the state this is most needed in is
    exactly the one send_prompt refuses (WAITING_INPUT). Safety comes from the
    allowlist instead, which also keeps this from becoming a way to type
    commands around the destructive-command screening.
    """
    client = request.client.host if request.client else None
    if not _SESSION_NAME_RE.match(name):
        _audit("key", name, client, False, "invalid_name")
        raise HTTPException(status_code=422, detail="Invalid session name")

    # Checked at the boundary, before dispatching anywhere. send_key repeats the
    # check as defence in depth, but the endpoint must not depend on it.
    if req.key not in ALLOWED_KEYS:
        _audit("key", name, client, False, "key_not_allowed")
        raise HTTPException(
            status_code=422,
            detail=f"Key not allowed. Allowed: {sorted(ALLOWED_KEYS)}",
        )

    if not _rate_limiter.allow():
        _audit("key", name, client, False, "rate_limited")
        raise HTTPException(status_code=429, detail="Too many control requests")

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, session_exists, name):
        _audit("key", name, client, False, "no_session")
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await loop.run_in_executor(None, send_key, name, req.key)
    except ValueError:
        _audit("key", name, client, False, "key_not_allowed")
        raise HTTPException(
            status_code=422,
            detail=f"Key not allowed. Allowed: {sorted(ALLOWED_KEYS)}",
        )
    except RuntimeError as e:
        _audit("key", name, client, False, "tmux_failed")
        raise HTTPException(status_code=502, detail=str(e))
    _audit("key", name, client, True, req.key)
    return {"session": name, "status": "sent", "key": req.key}


@app.post("/api/sessions/{name}/interrupt", dependencies=[Depends(require_control_token)])
async def session_interrupt(name: str, request: Request):
    """Send ESC to stop whatever the session is doing (the bot's /stop)."""
    client = request.client.host if request.client else None
    if not _SESSION_NAME_RE.match(name):
        _audit("interrupt", name, client, False, "invalid_name")
        raise HTTPException(status_code=422, detail="Invalid session name")

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, session_exists, name):
        _audit("interrupt", name, client, False, "no_session")
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await loop.run_in_executor(None, send_interrupt, name)
    except RuntimeError as e:
        _audit("interrupt", name, client, False, "tmux_failed")
        raise HTTPException(status_code=502, detail=str(e))
    _audit("interrupt", name, client, True)
    return {"session": name, "status": "interrupted"}


class DeleteRequest(BaseModel):
    force: bool = False


@app.get("/api/sessions/{name}/delete-check")
async def session_delete_check(name: str):
    """Report whether a session is safe to delete (git commit/push/merge state)."""
    if not _SESSION_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid session name")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, check_delete_safety, name)


@app.post("/api/sessions/{name}/delete", dependencies=[Depends(require_control_token)])
async def session_delete(name: str, req: DeleteRequest, request: Request):
    """Delete a session. Blocks unsafe deletes unless force=True."""
    if not _SESSION_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid session name")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, delete_session, name, req.force)
    _audit(
        "delete", name, request.client.host if request.client else None,
        result.get("status") == "deleted",
        result.get("status"),
    )
    if result.get("status") == "blocked":
        return Response(
            content=json.dumps(result, ensure_ascii=False),
            status_code=409,
            media_type="application/json",
        )
    return result


# The project/worktree reads run git, and unlike every write they are not
# behind the control token (the VSCode webview proxy only forwards GET). Their
# own budget, not the control one: a read flood must not be able to starve the
# ability to stop a session that is doing damage.
_project_read_limiter = _RateLimiter(
    max_events=int(os.environ.get("CTB_PROJECT_READ_RATE_MAX", "120")),
    window=float(os.environ.get("CTB_PROJECT_READ_RATE_WINDOW", "60")),
)


class CreateSessionRequest(BaseModel):
    project: str | None = None
    new_project: str | None = None
    worktree: str | None = None
    git_init: bool = True


@app.get("/api/projects")
async def api_projects():
    """Project folders available to start a session in."""
    if not _project_read_limiter.allow():
        raise HTTPException(status_code=429, detail="Too many requests")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, list_projects)


@app.get("/api/projects/{name}/worktrees")
async def api_project_worktrees(name: str):
    """Worktrees of one project (the .claude/worktrees convention)."""
    if not _project_read_limiter.allow():
        raise HTTPException(status_code=429, detail="Too many requests")
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, list_worktrees, name)
    except CreateError as e:
        raise HTTPException(status_code=404 if e.code == "no_project" else 422,
                            detail=e.message)


@app.post("/api/sessions/create", dependencies=[Depends(require_control_token)])
async def api_create_session(req: CreateSessionRequest, request: Request):
    """Start a Claude session: existing project, new project, or a worktree.

    Behind the control token like every other write -- this one creates
    directories and git branches on the host, so it is the furthest-reaching
    write the dashboard has.
    """
    client = request.client.host if request.client else None
    if not _rate_limiter.allow():
        _audit("create", req.project or req.new_project or "?", client, False, "rate_limited")
        raise HTTPException(status_code=429, detail="Too many control requests")

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: create_session(
                project=req.project,
                new_project=req.new_project,
                worktree=req.worktree,
                git_init=req.git_init,
            ),
        )
    except CreateError as e:
        _audit("create", req.project or req.new_project or "?", client, False, e.code)
        status = {
            "no_project": 404,
            "project_exists": 409,
            "bad_request": 400,
            "invalid_project": 422,
            "invalid_worktree": 422,
            "not_git": 409,
        }.get(e.code, 502)
        raise HTTPException(status_code=status, detail=e.message)
    except Exception as e:
        logger.exception("session create failed")
        _audit("create", req.project or req.new_project or "?", client, False, "error")
        raise HTTPException(status_code=500, detail=str(e))

    _audit("create", result["session"], client, True, result["status"])
    return result


_TICKET_LINKS_PATH = os.path.expanduser("~/.claude-ops/session-ticket-links.json")
_BADGE_TTL = 30  # seconds


@app.get("/api/session-ticket-links")
async def session_ticket_links(response: Response):
    """Return session→ticket mapping for badge overlay on session grid."""
    try:
        with open(_TICKET_LINKS_PATH) as f:
            links = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        links = {}
    response.headers["X-Server-Time"] = str(int(time.time()))
    response.headers["X-Badge-TTL"] = str(_BADGE_TTL)
    return {"links": links, "ttl": _BADGE_TTL}


def pinned_session_names() -> set:
    """Every pinned session, flattened out of the quadrants."""
    names = set()
    for value in (_pinned_state or {}).values():
        if isinstance(value, list):
            names.update(v for v in value if isinstance(v, str))
    return names


@app.get("/sw.js")
async def service_worker():
    """The worker must be served from the root.

    A worker's scope defaults to the directory it is served from, so at
    /static/sw.js it governed /static/ and nothing controlled the app at /.
    navigator.serviceWorker.ready waits for an active worker in the page's own
    scope, so it never settled: push registration timed out at its first step
    and the app-shell caching never took effect either.
    """
    path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    with open(path) as f:
        body = f.read()
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/push/public-key")
async def push_public_key():
    """The applicationServerKey. Public by definition — a browser needs it
    before it has anything to authenticate with."""
    return {"key": push.public_key()}


@app.post("/api/push/subscribe", dependencies=[Depends(require_control_token)])
async def push_subscribe(sub: dict, request: Request):
    # The endpoint is a URL this server POSTs to on every completion, so it is
    # checked here, at the boundary, rather than deeper in. Every real push
    # service is https; anything else is someone pointing our outbound requests
    # at a target of their choosing.
    # Audited: without this a phone that never manages to subscribe is
    # indistinguishable from one that never tried, which is a diagnosis by
    # guesswork every time notifications are quiet.
    client = request.client.host if request.client else None
    endpoint = (sub or {}).get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        _audit("push_subscribe", "-", client, False, "bad_endpoint")
        raise HTTPException(status_code=422, detail="endpoint must be an https URL")
    try:
        push.add_subscription(sub)
    except ValueError as e:
        _audit("push_subscribe", "-", client, False, "invalid")
        raise HTTPException(status_code=422, detail=str(e))
    _audit("push_subscribe", "-", client, True)
    logger.info("Push subscription registered (%d total)", len(push.subscriptions()))
    return {"status": "subscribed"}


@app.post("/api/push/report", dependencies=[Depends(require_control_token)])
async def push_report(body: dict, request: Request):
    """Where a phone's push registration stopped.

    Registration fails inside the browser, before anything reaches this server,
    so without this the only channel is asking the user to read a label back —
    which took four rounds and still did not name the step.
    """
    client = request.client.host if request.client else None
    stage = str((body or {}).get("stage", ""))[:80]
    error = str((body or {}).get("error", ""))[:300]
    _audit("push_report", stage or "-", client, False, error or "unknown")
    logger.warning("Push registration failed on a client: stage=%r error=%r", stage, error)
    return {"status": "recorded"}


@app.post("/api/push/unsubscribe", dependencies=[Depends(require_control_token)])
async def push_unsubscribe(body: dict):
    endpoint = (body or {}).get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=422, detail="endpoint is required")
    push.remove_subscription(endpoint)
    return {"status": "unsubscribed"}


# --- speech to text ----------------------------------------------------------

# Twenty seconds of Opus is well under a megabyte; ten is a clip that was
# never meant for this.
_STT_MAX_BYTES = 10 * 1024 * 1024
_STT_SCREEN_LINES = 40


def _screen_lines_for_stt(name: str) -> list[str]:
    """The last screen of the session, for the terms the model should hear."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", name, "-p", "-J", f"-S-{_STT_SCREEN_LINES}"],
            capture_output=True, text=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


@app.get("/api/stt/config")
async def stt_config():
    """Whether the mic button has anything to talk to. Open, like every read."""
    return {"enabled": _stt.enabled(), "model": _stt.MODEL}


@app.post("/api/stt", dependencies=[Depends(require_control_token)])
async def stt_transcribe(request: Request, session: str = ""):
    """One recorded clip in, its words out. Nothing is typed anywhere: the
    console puts the text into its input box as a draft and the user's Enter
    is what sends it. The clip goes to OpenAI with a prompt naming the
    session, its branch, the identifiers on its screen and the user's
    glossary, which is what makes mixed Korean/English come out right."""
    client = request.client.host if request.client else None
    if session and not _SESSION_NAME_RE.match(session):
        _audit("stt", session, client, False, "invalid_name")
        raise HTTPException(status_code=422, detail="Invalid session name")
    if not _stt.enabled():
        raise HTTPException(status_code=503, detail="STT disabled: OPENAI_API_KEY is not set")
    if not _rate_limiter.allow():
        _audit("stt", session, client, False, "rate_limited")
        raise HTTPException(status_code=429, detail="Too many control requests")
    audio = await request.body()
    if len(audio) > _STT_MAX_BYTES:
        _audit("stt", session, client, False, "too_large")
        raise HTTPException(status_code=413, detail="Clip too large")
    if not audio:
        raise HTTPException(status_code=400, detail="Empty clip")
    mime = request.headers.get("content-type", "") or "audio/webm"

    loop = asyncio.get_running_loop()
    lines = await loop.run_in_executor(None, _screen_lines_for_stt, session) if session else []
    prompt = _stt.build_prompt(session, lines, _stt.read_glossary())
    try:
        result = await loop.run_in_executor(None, _stt.transcribe, audio, mime, prompt)
    except _stt.TranscribeError as e:
        _audit("stt", session, client, False, f"upstream_{e.status}")
        raise HTTPException(status_code=502, detail=f"transcription failed ({e.status}): {e}")
    _audit("stt", session, client, True, f"{result.get('seconds')}s")
    return result


@app.get("/api/pinned")
async def get_pinned():
    return _pinned_state


@app.post("/api/pinned", dependencies=[Depends(require_control_token)])
async def post_pinned(req: PinnedRequest):
    global _pinned_state
    _pinned_state = req.model_dump()
    _atomic_json_write(_PINNED_PERSIST_PATH, _pinned_state)
    return _pinned_state


@app.get("/api/health")
async def health(request: Request):
    """Health check endpoint."""
    degraded = getattr(request.app.state, "degraded", False)
    return {
        "status": "degraded" if degraded else "ok",
        "degraded": degraded,
        "sessions_count": len(_cached_state.get("sessions", [])),
        "last_updated": _cached_state.get("updated_at", 0),
    }


# Which tmux client to move -- and, far more importantly, which ones to leave
# alone.
#
# This used to switch EVERY attached client to the requested session. The
# comment defending it was about reconnects: a VSCode SSH terminal comes back
# with a new client name, so "the most recent client" could be a stale one.
# The cure was worse than the disease. Every VSCode terminal is its own tmux
# client on its own session, so one tap on a card in the browser dragged all of
# them onto that session at once -- and a terminal's VSCode tab keeps the name
# it was created with, so the tab still labelled 'omc-research-skills' now
# showed 'ops'. Observed with five clients sitting on the same session, each
# with the same client_last_session, having started on five different ones.
#
# So: if a client is already on that session, there is nothing to switch -- the
# terminal exists, and step 1 has already raised the window. Otherwise move the
# single most recently used client, which is by definition a live one, so the
# reconnect case the old loop was worried about still works.
_ALREADY_THERE = object()


def _pick_client(list_clients_output: str, session: str):
    """Return _ALREADY_THERE, a client name to switch, or None if no clients."""
    best = None
    best_activity = -1
    for line in list_clients_output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        name, current = parts[0].strip(), parts[1].strip()
        if current == session:
            return _ALREADY_THERE
        try:
            activity = int(parts[2]) if len(parts) > 2 else 0
        except ValueError:
            activity = 0
        if activity > best_activity:
            best, best_activity = name, activity
    return best


@app.post("/api/focus-session", dependencies=[Depends(require_control_token)])
async def focus_session(req: FocusRequest, request: Request):
    """Switch the host's tmux client to the requested session.

    Auth is handled by require_control_token; the old inline check only fired
    when the secret happened to be set, which is exactly the fail-open bug.
    """
    # Validate session name
    if not _SESSION_NAME_RE.match(req.session):
        raise HTTPException(status_code=422, detail="Invalid session name")

    # 1. Activate VSCode window via xdotool (brings VSCode to foreground + keyboard focus)
    window_ok = False
    try:
        result = subprocess.run(
            # --classname "code" filters out extension host / helper windows
            # so wids[0] is the actual editor window, not a background process window
            ["xdotool", "search", "--classname", "code", "--name", "Visual Studio Code"],
            capture_output=True, text=True, timeout=3,
        )
        wids = [w for w in result.stdout.strip().split('\n') if w.strip()]
        if not wids:
            # Fallback: name-only search (older xdotool or different WM)
            result = subprocess.run(
                ["xdotool", "search", "--name", "Visual Studio Code"],
                capture_output=True, text=True, timeout=3,
            )
            wids = [w for w in result.stdout.strip().split('\n') if w.strip()]
        if wids:
            wid = wids[0]
            # --sync waits for WM to process activate before returning,
            # preventing the race where keyboard focus transfer is incomplete
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", wid],
                capture_output=True, timeout=3,
            )
            # windowactivate raises the window; windowfocus explicitly moves
            # X11 keyboard focus to it. Without this step, some WM configurations
            # raise the window visually but leave keyboard input routed elsewhere,
            # causing Ctrl+C / Esc / arrow keys to stop working after focus switch.
            subprocess.run(
                ["xdotool", "windowfocus", "--sync", wid],
                capture_output=True, timeout=3,
            )
            window_ok = True
    except Exception:
        pass  # xdotool not available or no X11 display — non-fatal

    # 2. Try tmux switch-client for direct terminal focus -- for ONE client.
    tmux_ok = False
    try:
        clients_result = subprocess.run(
            ["tmux", "list-clients", "-F",
             "#{client_name}\t#{client_session}\t#{client_activity}"],
            capture_output=True, text=True, timeout=3,
        )
        rows = clients_result.stdout
        target = _pick_client(rows, req.session)
        if target is _ALREADY_THERE:
            tmux_ok = True
        elif target:
            r = subprocess.run(
                ["tmux", "switch-client", "-c", target, "-t", req.session],
                capture_output=True, timeout=3,
            )
            tmux_ok = r.returncode == 0
        else:
            # Fallback: no explicit client list (e.g. running headless), try default
            result = subprocess.run(
                ["tmux", "switch-client", "-t", req.session],
                capture_output=True, timeout=3,
            )
            tmux_ok = result.returncode == 0
    except Exception:
        pass  # No attached client or tmux not available

    # 3. If Claude Code is not running in the session pane, start it
    _SHELL_CMDS = {"bash", "zsh", "sh", "fish", "dash", "ksh", "tcsh"}
    _CLAUDE_CMD = "claude --continue --dangerously-skip-permissions"
    _WRAPPER = f"bash --login -c '{_CLAUDE_CMD}; exec bash --login'"
    claude_started = False
    try:
        pane_info_result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", req.session,
             "#{pane_dead} #{pane_current_command} #{pane_pid}"],
            capture_output=True, text=True, timeout=3,
        )
        parts = pane_info_result.stdout.strip().split(None, 2)
        pane_dead = parts[0] if parts else "0"
        pane_cmd = parts[1] if len(parts) > 1 else ""
        pane_pid = parts[2] if len(parts) > 2 else ""

        if pane_dead == "1":
            # remain-on-exit으로 pane이 죽어있는 경우 → respawn with claude wrapper
            subprocess.run(
                ["tmux", "respawn-pane", "-k", "-t", req.session, _WRAPPER],
                capture_output=True, timeout=5,
            )
            claude_started = True
        elif pane_cmd in _SHELL_CMDS:
            # bash-wrapper 세션은 pane_cmd가 "bash"여도 claude가 자식으로 실행 중일 수 있음.
            # ps --ppid로 실제 claude 자식 프로세스 존재 여부 확인.
            claude_running = False
            if pane_pid:
                ps_result = subprocess.run(
                    ["ps", "--ppid", pane_pid, "-o", "comm", "--no-headers"],
                    capture_output=True, text=True, timeout=3,
                )
                claude_running = any(
                    "claude" in line for line in ps_result.stdout.splitlines()
                )

            if not claude_running:
                subprocess.run(
                    ["tmux", "send-keys", "-t", req.session,
                     "claude --continue --dangerously-skip-permissions", "Enter"],
                    capture_output=True, timeout=3,
                )
                claude_started = True
    except Exception:
        pass

    # 4. Write focus signal for VSCode extension (file-based IPC)
    # The extension watches this file and calls terminal.show() + focus to switch tabs
    try:
        import json as _json
        import time as _time
        with open(_FOCUS_SIGNAL_PATH, "w") as f:
            _json.dump({"session": req.session, "ts": _time.time()}, f)
    except Exception as e:
        logger.warning(f"Failed to write focus signal: {e}")

    # Audited at the end, with the outcome: switch-client moves the terminal out
    # from under whoever is at it, and there was no record of who asked or
    # whether it landed.
    _audit("focus_session", req.session,
           request.client.host if request.client else None, tmux_ok,
           None if tmux_ok else "no_switch")
    return {"status": "focused", "session": req.session, "tmux_switched": tmux_ok, "window_activated": window_ok, "claude_started": claude_started}


@app.get("/api/project/{name}/review-link")
async def review_link(
    name: str,
    request: Request,
    rv: str = "",
    ttl: int = 72 * 3600,
):
    """Generate a HMAC-signed /review deep-link for a project."""
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        raise HTTPException(status_code=403, detail="XHR only")
    if not _REVIEW_SECRET:
        raise HTTPException(status_code=503, detail="Review gate not configured")
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise HTTPException(status_code=400, detail="Invalid project name")
    root = Path(_CTB_PROJECTS_ROOT).resolve()
    project_path = (root / name).resolve()
    if not str(project_path).startswith(str(root) + "/") or not project_path.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    reviewer = rv or _CTB_DEFAULT_REVIEWER_ID
    if not reviewer:
        raise HTTPException(status_code=400, detail="Reviewer ID required")
    exp = int(time.time()) + min(ttl, 7 * 24 * 3600)
    sig = _hmac_mod.new(
        _REVIEW_SECRET.encode(),
        "|".join(["", "", reviewer, str(exp), name]).encode(),
        hashlib.sha256,
    ).hexdigest()
    url = f"/review?card=&focus=&rv={reviewer}&exp={exp}&project={name}&sig={sig}"
    return {"url": url, "expires_at": exp, "project": name}


@app.get("/review")
async def review_gate(
    request: Request,
    card: str = "",
    focus: str = "",
    rv: str = "",
    exp: str = "",
    project: str = "",
    sig: str = "",
):
    """PI Review Gate — HMAC deep-link or session-cookie auth."""
    if not _REVIEW_SECRET:
        raise HTTPException(status_code=403, detail="Review gate not configured")

    # Session bypass: already authenticated reviewer
    if not sig and request.session.get("reviewer_id"):
        tickets = _get_review_tickets()
        return templates.TemplateResponse(
            request,
            "review.html",
            {"tickets": tickets, "reviewer_id": request.session["reviewer_id"],
             "plan_summary_html": "", "plan_full_html": "", "rpt_html": "", "project_name": ""},
        )

    if not (rv and exp and sig):
        raise HTTPException(status_code=403, detail="Missing required parameters")

    try:
        exp_int = int(exp)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid expiry")

    if not _verify_review_sig(card, focus, rv, exp, project, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    if time.time() > exp_int:
        raise HTTPException(status_code=403, detail="Link expired")

    consumed_path = os.path.join(_REVIEW_OVERLAY_DIR, "consumed-links.json")
    overlay_path = os.path.join(_REVIEW_OVERLAY_DIR, "ticket-overlay.json")
    lock_path = os.path.join(_REVIEW_OVERLAY_DIR, "overlay.lock")

    with _filelock.FileLock(lock_path, timeout=_REVIEW_LOCK_TIMEOUT):
        cl_data = _read_consumed_links(consumed_path)
        links = cl_data.setdefault("links", {})
        link_status = links.get(sig, {}).get("status")

        if link_status == "consumed":
            raise HTTPException(status_code=403, detail="Link already used")
        # "write-failed" → allow one retry (fall through)

        links[sig] = {"status": "consumed", "consumed_at": datetime.now(timezone.utc).isoformat()}
        if not _write_consumed_links(consumed_path, cl_data):
            raise HTTPException(status_code=503, detail="Service unavailable")

        # M14: reject links issued before the current review cycle started
        if card:
            try:
                with open(overlay_path) as _f:
                    _ov = json.load(_f)
                _since = _ov.get("tickets", {}).get(card, {}).get("needs_review_since")
                if _since:
                    _since_ts = datetime.fromisoformat(_since)
                    if _since_ts.tzinfo is None:
                        _since_ts = _since_ts.replace(tzinfo=timezone.utc)
                    _link_iat = datetime.fromtimestamp(exp_int - 72 * 3600, tz=timezone.utc)
                    if _link_iat < _since_ts:
                        raise HTTPException(status_code=403, detail="Link predates current review cycle")
            except HTTPException:
                raise
            except Exception:
                pass  # overlay unreadable — allow through

        if card and not _write_overlay_link_access(card, rv, overlay_path):
            # Rollback: mark as write-failed so next attempt can retry
            links[sig]["status"] = "write-failed"
            if not _write_consumed_links(consumed_path, cl_data):
                logger.error("Rollback write failed for sig %s — link permanently consumed", sig[:8])
            raise HTTPException(status_code=503, detail="Overlay write failed")

    request.session["reviewer_id"] = rv
    tickets = _get_review_tickets()
    plan = _load_latest_plan(project)
    plan_summary_html = plan["summary"] or ""
    plan_full_html = plan["full"] or ""
    rpt_html = _load_rpt(project) or ""
    response = templates.TemplateResponse(
        request,
        "review.html",
        {"tickets": tickets, "reviewer_id": rv,
         "plan_summary_html": plan_summary_html, "plan_full_html": plan_full_html,
         "rpt_html": rpt_html, "project_name": project},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _kill_previous_on_port(port: int):
    """Kill any previous process occupying the port to avoid EADDRINUSE."""
    import subprocess
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split('\n')
        my_pid = os.getpid()
        for pid_str in pids:
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if pid != my_pid:
                    os.kill(pid, 9)
                    logger.info(f"Killed previous dashboard process (PID {pid}) on port {port}")
    except Exception:
        pass  # lsof not found or no process


def _address_assignable(host: str) -> bool:
    """Is `host` an address we can actually bind to on this machine?

    Probes with port 0 so a busy 8420 never masquerades as a bad address.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def resolve_bind_host(requested: str | None, probe=_address_assignable) -> str:
    """Resolve the listen address, degrading to 0.0.0.0 rather than failing.

    Under systemd Restart=always a bind failure is not a crash, it is an
    infinite restart loop with the dashboard permanently down. A tailscale IP
    that is not up yet at boot (or changed after a re-login) must therefore
    fall back to the wildcard, loudly, instead of taking the service with it.
    """
    if not requested or requested == "0.0.0.0":
        return "0.0.0.0"
    if probe(requested):
        return requested
    logger.warning(
        "CTB_BIND_HOST=%s is not assignable on this host; falling back to "
        "0.0.0.0. LAN exposure is then only closed by the firewall rules "
        "(deploy/firewall-8420.sh) -- verify they are active.",
        requested,
    )
    return "0.0.0.0"


def run_server(host: str = BIND_HOST, port: int = BIND_PORT):
    """Run the dashboard server (blocking). Auto-kills previous instance."""
    import uvicorn

    # Check tmux is available
    if not shutil.which("tmux"):
        print("ERROR: tmux is required but not found in PATH.")
        print("Install tmux first: apt install tmux / brew install tmux")
        raise SystemExit(1)

    _kill_previous_on_port(port)
    uvicorn.run(app, host=resolve_bind_host(host), port=port, log_level="info")


if __name__ == "__main__":
    run_server()
