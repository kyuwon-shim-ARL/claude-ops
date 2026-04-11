"""
Web Dashboard Backend -- FastAPI + SSE

Self-contained dashboard server that polls tmux sessions directly.
Works in both hook-only mode and polling mode.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .state_detector import SessionStateAnalyzer, SessionState
from .sessions import get_all_claude_sessions, get_session_path

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between state refreshes
BIND_HOST = "0.0.0.0"  # accessible via Tailscale network
BIND_PORT = 8420
_FOCUS_SECRET = os.environ.get("CTB_FOCUS_SECRET", "")
_SESSION_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-:.]{1,64}$')


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
_WORKING_HOLD_SECONDS = 8  # hold WORKING for 8s after last working indicator
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

    return name, state.value, path, context_percent, last_prompt, work_context, workflow_phase, pending_count


def _poll_sessions() -> Dict[str, Any]:
    """Poll all tmux sessions and return state dict using SessionStateAnalyzer."""
    global _prev_session_timestamps
    sessions = get_all_claude_sessions()
    now = time.time()

    # Parallel probe: ~1-2s instead of ~30s for 26 sessions
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_probe_session, sessions))

    session_list = []
    for name, state_val, path, context_percent, last_prompt, work_context, workflow_phase, pending_count in results:
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
    task = asyncio.create_task(_background_poller())
    yield
    task.cancel()
    try:
        await task
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

# Serve static files (HTML frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Serve dashboard HTML."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        with open(index_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard not found. Place index.html in static/</h1>")


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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
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

    # 1. Activate VSCode window via xdotool (brings VSCode to foreground)
    window_ok = False
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "Visual Studio Code"],
            capture_output=True, text=True, timeout=3,
        )
        wids = result.stdout.strip().split('\n')
        if wids and wids[0]:
            subprocess.run(
                ["xdotool", "windowactivate", wids[0]],
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

    # 3. Write focus signal for VSCode extension (file-based IPC)
    # The extension watches this file and calls terminal.show() + focus to switch tabs
    _FOCUS_SIGNAL_PATH = "/tmp/ctb-focus-signal.json"
    try:
        import json as _json, time as _time
        with open(_FOCUS_SIGNAL_PATH, "w") as f:
            _json.dump({"session": req.session, "ts": _time.time()}, f)
    except Exception as e:
        logger.warning(f"Failed to write focus signal: {e}")

    return {"status": "focused", "session": req.session, "tmux_switched": tmux_ok, "window_activated": window_ok}


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
