"""
Web Dashboard Backend — FastAPI + SSE

Self-contained dashboard server that polls tmux sessions directly.
Works in both hook-only mode and polling mode — no dependency on multi_monitor.py.

e003: Web Dashboard backend experiment
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..utils.session_state import SessionStateAnalyzer
from ..session_manager import session_manager

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between state refreshes
BIND_HOST = "0.0.0.0"  # accessible via Tailscale network
BIND_PORT = 8420

# --- Session Poller (reuses SessionStateAnalyzer for accurate detection) ---

_cached_state: Dict[str, Any] = {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""}
_prev_session_timestamps: Dict[str, float] = {}  # track per-session state change time
_completion_times: Dict[str, float] = {}  # track working→idle/waiting transitions
_state_analyzer = SessionStateAnalyzer()

# Hold timer: keep WORKING state for a few seconds after indicators disappear
# This prevents flickering during tool transitions (e.g., between Read → Edit)
_working_hold: Dict[str, float] = {}  # session_name → last_seen_working_time
_WORKING_HOLD_SECONDS = 8  # hold WORKING for 8s after last working indicator
_FRESH_TTL = 300  # seconds to keep completed_at visible (5 minutes)

_work_cache: Dict[str, Any] = {}  # repo_slug → {total, completed, repo, cached_at}
_work_cache_lock = threading.Lock()
_WORK_POLL_INTERVAL = 60  # seconds


def _get_repo_for_path(path: str) -> "str | None":
    """Map session path to GitHub repo slug via .omc-config.sh (grep, NOT source)."""
    if not path:
        return None
    # Find git root first
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        git_root = result.stdout.strip() if result.returncode == 0 else path
    except Exception:
        git_root = path

    config_path = os.path.join(git_root, ".omc-config.sh")
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        match = re.search(r'OMC_GH_REPO="([^"]+)"', content)
        return match.group(1) if match else None
    except Exception:
        return None


def _query_work_info(repo_slug: str) -> "Dict[str, Any] | None":
    """Query GitHub issues for task completion data. Runs in executor thread."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", repo_slug, "--state", "open",
             "--json", "number,title,body", "--limit", "100"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None

        import json as _json
        issues = _json.loads(result.stdout)
        total = 0
        completed = 0
        for issue in issues:
            body = issue.get("body", "") or ""
            # Count task checkboxes
            checks = re.findall(r'- \[([ xX])\]', body)
            total += len(checks)
            completed += sum(1 for c in checks if c in ('x', 'X'))

        if total == 0:
            return None

        return {
            "total": total,
            "completed": completed,
            "repo": repo_slug,
            "open_issues": len(issues),
            "cached_at": time.time(),
        }
    except Exception as e:
        logger.warning(f"Work info query failed for {repo_slug}: {e}")
        return None


async def _background_work_poller():
    """Background task that polls GitHub for work info every 60 seconds.
    Uses run_in_executor to avoid blocking the event loop (H2 fix)."""
    global _work_cache
    logger.info("Work info poller started")
    # Initial delay to stagger with session poller (M2 fix: cold start)
    await asyncio.sleep(10)
    while True:
        try:
            loop = asyncio.get_running_loop()
            # Collect unique repos from current sessions
            sessions = _cached_state.get("sessions", [])
            path_repo_map: Dict[str, str] = {}
            for s in sessions:
                path = s.get("path")
                if path and path not in path_repo_map:
                    repo = await loop.run_in_executor(None, _get_repo_for_path, path)
                    if repo:
                        path_repo_map[path] = repo

            # Query each unique repo (deduplicated)
            unique_repos = set(path_repo_map.values())
            new_cache: Dict[str, Any] = {}
            for repo in unique_repos:
                info = await loop.run_in_executor(None, _query_work_info, repo)
                if info:
                    new_cache[repo] = info
                else:
                    # Keep previous cache on failure (M2/S3 fix)
                    with _work_cache_lock:
                        prev = _work_cache.get(repo)
                    if prev:
                        new_cache[repo] = prev

            with _work_cache_lock:
                _work_cache = new_cache

            # Store path→repo mapping for session enrichment
            _work_cache["__path_map__"] = path_repo_map

            logger.debug(f"Work info: {len(unique_repos)} repos, {sum(1 for v in new_cache.values() if isinstance(v, dict) and 'total' in v)} with data")
        except Exception as e:
            logger.warning(f"Work poller error: {e}", exc_info=True)
        await asyncio.sleep(_WORK_POLL_INTERVAL)


def _probe_session(name: str) -> tuple:
    """Probe a single session's state and path (called in thread pool)."""
    from ..utils.session_state import SessionState
    raw_state = _state_analyzer.get_state(name)
    state = raw_state
    now = time.time()

    # Hold timer: if state was recently WORKING, keep it WORKING through brief gaps
    if raw_state == SessionState.WORKING:
        _working_hold[name] = now
    elif raw_state == SessionState.IDLE and name in _working_hold:
        elapsed = now - _working_hold[name]
        # Raw state is IDLE but was recently WORKING → work just completed
        # Record completion time immediately (before hold timer hides the transition)
        if name not in _completion_times:
            _completion_times[name] = now
            logger.info(f"✅ Fresh completion: {name}")
        if elapsed < _WORKING_HOLD_SECONDS:
            logger.debug(f"⏳ Hold WORKING for {name} ({elapsed:.1f}s < {_WORKING_HOLD_SECONDS}s)")
            state = SessionState.WORKING
        else:
            del _working_hold[name]

    # Expire stale completion times
    completed_at = _completion_times.get(name)
    if completed_at and (now - completed_at) >= _FRESH_TTL:
        del _completion_times[name]

    path = session_manager.get_session_path(name)
    return name, state.value, path


def _poll_sessions() -> Dict[str, Any]:
    """Poll all tmux sessions and return state dict using SessionStateAnalyzer."""
    global _prev_session_timestamps
    sessions = session_manager.get_all_claude_sessions()
    now = time.time()

    # Parallel probe: ~1-2s instead of ~30s for 26 sessions
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_probe_session, sessions))

    session_list = []
    for name, state_val, path in results:
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

        # Enrich with work_info from cache
        work_info = None
        with _work_cache_lock:
            path_map = _work_cache.get("__path_map__", {})
            repo = path_map.get(path)
            if repo:
                info = _work_cache.get(repo)
                if info and isinstance(info, dict) and "total" in info:
                    work_info = {"total": info["total"], "completed": info["completed"], "repo": info["repo"]}

        session_list.append({
            "name": name,
            "state": state_val,
            "path": path,
            "updated_at": prev_ts,
            "completed_at": _completion_times.get(name),
            "work_info": work_info,
        })

    # Content hash for SSE change detection (includes completed_at and work_info for fresh notifications)
    content_key = json.dumps([(s["name"], s["state"], bool(s.get("completed_at")), s.get("work_info")) for s in session_list], sort_keys=True)
    content_hash = hashlib.md5(content_key.encode()).hexdigest()[:8]

    # Clean up timestamps for removed sessions
    active_names = {s["name"] for s in session_list}
    _prev_session_timestamps = {k: v for k, v in _prev_session_timestamps.items() if k in active_names}

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
    task = asyncio.create_task(_background_poller())
    work_task = asyncio.create_task(_background_work_poller())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    work_task.cancel()
    try:
        await work_task
    except asyncio.CancelledError:
        pass
    logger.info("Dashboard server shutting down")


app = FastAPI(
    title="Claude-CTB Dashboard",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # safe: server only binds to loopback (127.0.0.1)
    allow_methods=["GET"],
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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "sessions_count": len(_cached_state.get("sessions", [])),
        "last_updated": _cached_state.get("updated_at", 0),
    }


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
        pass  # lsof not found or no process — fine


def run_server(host: str = BIND_HOST, port: int = BIND_PORT):
    """Run the dashboard server (blocking). Auto-kills previous instance."""
    import uvicorn
    _kill_previous_on_port(port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
