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
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.sessions import SessionMiddleware

from .state_detector import SessionStateAnalyzer, SessionState
from .sessions import get_all_claude_sessions, get_session_path

import sys as _sys
_PSTATUS_DIR = "/home/kyuwon/projects/project-status"
if _PSTATUS_DIR not in _sys.path:
    _sys.path.insert(0, _PSTATUS_DIR)
import projects_router as _pstatus_module  # noqa: E402
_pstatus_scan_loop = _pstatus_module.scan_loop
projects_router = _pstatus_module.router
pstatus_static_app = _pstatus_module.pstatus_static_app
from scanner import PROJECTS_ROOT as _SCANNER_PROJECTS_ROOT  # noqa: E402
from scanner import find_rpt_artifact as _find_rpt_artifact  # noqa: E402

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between state refreshes
BIND_HOST = "0.0.0.0"  # accessible via Tailscale network
BIND_PORT = 8420
_FOCUS_SECRET = os.environ.get("CTB_FOCUS_SECRET", "")
_SESSION_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-:.]{1,64}$')

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

# --- Session Poller (reuses SessionStateAnalyzer for accurate detection) ---

_cached_state: Dict[str, Any] = {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""}
_TS_PERSIST_PATH = "/tmp/ctb-session-timestamps.json"

def _load_timestamps() -> Dict[str, float]:
    """Load persisted session timestamps from disk (survives server restart)."""
    try:
        with open(_TS_PERSIST_PATH) as f:
            data = json.load(f)
        # Discard entries older than 24h to avoid stale data
        cutoff = time.time() - 86400
        return {k: v for k, v in data.items() if v > cutoff}
    except Exception:
        return {}

_prev_session_timestamps: Dict[str, float] = _load_timestamps()  # track per-session state change time
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
_last_working_phase: Dict[str, str] = {}


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
    workflow_phase = _state_analyzer.extract_workflow_phase(screen_content, state)

    # T3: Persist last working phase — idle cards show what they were last doing
    if workflow_phase and state == SessionState.WORKING:
        _last_working_phase[name] = workflow_phase
    elif workflow_phase is None and state == SessionState.IDLE:
        workflow_phase = _last_working_phase.get(name)

    pending_count = _state_analyzer.extract_pending_task_count(screen_content)

    # Stall detection: track when WORKING state started
    if state == SessionState.WORKING:
        if name not in _working_since:
            _working_since[name] = now
        working_since = _working_since[name]
    else:
        _working_since.pop(name, None)
        working_since = None

    return name, state.value, path, context_percent, last_prompt, work_context, workflow_phase, pending_count, working_since


def _poll_sessions() -> Dict[str, Any]:
    """Poll all tmux sessions and return state dict using SessionStateAnalyzer."""
    global _prev_session_timestamps
    sessions = get_all_claude_sessions()
    now = time.time()

    # Parallel probe: ~1-2s instead of ~30s for 26 sessions
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_probe_session, sessions))

    session_list = []
    for name, state_val, path, context_percent, last_prompt, work_context, workflow_phase, pending_count, working_since in results:
        # Only update timestamp when state actually changes
        prev_ts = _prev_session_timestamps.get(name, 0)
        prev_state = None
        for s in _cached_state.get("sessions", []):
            if s["name"] == name:
                prev_state = s.get("state")
                break
        if prev_state != state_val or prev_ts == 0:
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
            "workflow_phase": workflow_phase,     # null or phase string (frontend shows badge)
            "pending_count": pending_count,       # null=no TodoWrite, 0=all done, N=pending tasks
            "working_since": working_since,       # epoch float when WORKING started, null otherwise
        }
        session_list.append(entry)

    # Content hash for SSE change detection (includes dynamic fields for real-time updates)
    content_key = json.dumps([
        (s["name"], s["state"], bool(s.get("completed_at")),
         s.get("context_percent"), s.get("last_prompt", ""), s.get("work_context", ""),
         s.get("workflow_phase"))
        for s in session_list
    ], sort_keys=True)
    content_hash = hashlib.md5(content_key.encode()).hexdigest()[:8]

    # Clean up timestamps and prompt cache for removed sessions
    active_names = {s["name"] for s in session_list}
    _prev_session_timestamps = {k: v for k, v in _prev_session_timestamps.items() if k in active_names}
    for gone in set(_last_known_prompt) - active_names:
        del _last_known_prompt[gone]
    for gone in set(_last_working_phase) - active_names:
        del _last_working_phase[gone]

    # Persist timestamps to disk so they survive server restarts
    try:
        with open(_TS_PERSIST_PATH, "w") as f:
            json.dump(_prev_session_timestamps, f)
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
    if not _FOCUS_SECRET:
        logger.warning("CTB_FOCUS_SECRET not set, focus endpoint is unauthenticated")

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
    pstatus_task = asyncio.create_task(_pstatus_scan_loop())
    purge_task = asyncio.create_task(_purge_consumed_loop())
    app.state.purge_consumed_task = purge_task
    yield
    task.cancel()
    pstatus_task.cancel()
    purge_task.cancel()
    for t in (task, pstatus_task, purge_task):
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

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)

# Project-status integration (Phase C)
app.mount("/pstatus-static", pstatus_static_app, name="pstatus-static")
app.include_router(projects_router, prefix="/projects")


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
        {"csp_nonce": nonce},
    )
    response.headers["Content-Security-Policy"] = csp
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


@app.get("/api/sessions/{name}/log")
async def get_session_log(name: str, lines: int = 50):
    """Return recent tmux pane output for a session."""
    if not _SESSION_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid session name")
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", name, "-p", f"-S-{lines}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": name, "log": result.stdout}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="tmux timeout")


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


@app.post("/api/focus-session")
async def focus_session(
    req: FocusRequest,
    x_ctb_secret: str | None = Header(None),
):
    """Switch the host's tmux client to the requested session."""
    # Auth check (optional — only when CTB_FOCUS_SECRET is set)
    if _FOCUS_SECRET and x_ctb_secret != _FOCUS_SECRET:
        raise HTTPException(status_code=403, detail="Invalid or missing X-CTB-Secret")

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

    # 2. Try tmux switch-client for direct terminal focus.
    # Enumerate all currently attached clients so that a freshly reconnected
    # VSCode SSH terminal (which gets a new client name like /dev/pts/7) is
    # also switched correctly.  Without -c the command targets the "most recent
    # client" which may no longer match after a reconnect.
    tmux_ok = False
    try:
        clients_result = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_name}"],
            capture_output=True, text=True, timeout=3,
        )
        clients = [c.strip() for c in clients_result.stdout.split('\n') if c.strip()]
        if clients:
            for client in clients:
                r = subprocess.run(
                    ["tmux", "switch-client", "-c", client, "-t", req.session],
                    capture_output=True, timeout=3,
                )
                if r.returncode == 0:
                    tmux_ok = True
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
    _FOCUS_SIGNAL_PATH = "/tmp/ctb-focus-signal.json"
    try:
        import json as _json
        import time as _time
        with open(_FOCUS_SIGNAL_PATH, "w") as f:
            _json.dump({"session": req.session, "ts": _time.time()}, f)
    except Exception as e:
        logger.warning(f"Failed to write focus signal: {e}")

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


def run_server(host: str = BIND_HOST, port: int = BIND_PORT):
    """Run the dashboard server (blocking). Auto-kills previous instance."""
    import uvicorn

    # Check tmux is available
    if not shutil.which("tmux"):
        print("ERROR: tmux is required but not found in PATH.")
        print("Install tmux first: apt install tmux / brew install tmux")
        raise SystemExit(1)

    _kill_previous_on_port(port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
