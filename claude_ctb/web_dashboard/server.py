"""
Web Dashboard Backend — FastAPI + SSE

Self-contained dashboard server that polls tmux sessions directly.
Works in both hook-only mode and polling mode — no dependency on multi_monitor.py.

e003: Web Dashboard backend experiment
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between state refreshes
BIND_HOST = "127.0.0.1"
BIND_PORT = 8420

# --- Session Poller (self-contained, no multi_monitor dependency) ---

_cached_state: Dict[str, Any] = {"version": 1, "updated_at": 0, "sessions": []}


def _discover_claude_sessions() -> List[str]:
    """Discover active Claude tmux sessions."""
    try:
        result = subprocess.run(
            "tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1",
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
            exclude = {'claude-multi-monitor', 'claude-monitor', 'claude-telegram-bridge'}
            return [s for s in sessions if s not in exclude]
    except Exception as e:
        logger.warning(f"Failed to discover sessions: {e}")
    return []


def _detect_session_state(session_name: str) -> str:
    """Detect session state from tmux screen content (lightweight)."""
    try:
        result = subprocess.run(
            f"tmux capture-pane -t {session_name} -p",
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return "unknown"

        content = result.stdout
        lines = content.split('\n')
        recent = '\n'.join(lines[-25:])

        # Priority order: working > waiting > idle
        working_indicators = [
            "esc to interrupt", "ctrl+c to interrupt",
            "Running…", "Thinking…", "ctrl+b to run in background",
            "Building", "Testing", "Installing", "Processing", "Analyzing",
        ]
        for pattern in working_indicators:
            if pattern in recent:
                return "working"

        # Context limit
        limit_patterns = ["Context limit reached", "Conversation is too long", "context window exceeded"]
        for pattern in limit_patterns:
            if pattern.lower() in recent.lower():
                return "context_limit"

        # Waiting for input
        input_patterns = [
            "Do you want to proceed?", "Choose an option:", "Question ",
            "❯ 1.", "❯ 2.", "┌────────┬",
        ]
        for pattern in input_patterns:
            if pattern in '\n'.join(lines[-10:]):
                return "waiting"

        # Check for prompt (idle)
        for line in reversed(lines[-6:]):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ['>', '│ >'] or line.endswith(('$ ', '> ', '❯ ')):
                return "idle"

        return "idle"

    except Exception as e:
        logger.warning(f"Failed to detect state for {session_name}: {e}")
        return "unknown"


def _get_session_path(session_name: str) -> str:
    """Get working directory of a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", session_name, "-p", "#{pane_current_path}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _poll_sessions() -> Dict[str, Any]:
    """Poll all tmux sessions and return state dict."""
    sessions = _discover_claude_sessions()
    now = time.time()

    session_list = []
    for name in sessions:
        state = _detect_session_state(name)
        path = _get_session_path(name)
        session_list.append({
            "name": name,
            "state": state,
            "path": path,
            "updated_at": now,
        })

    return {
        "version": 1,
        "updated_at": now,
        "sessions": session_list,
    }


async def _background_poller():
    """Background task that polls sessions every POLL_INTERVAL seconds."""
    global _cached_state
    while True:
        try:
            _cached_state = await asyncio.get_event_loop().run_in_executor(None, _poll_sessions)
        except Exception as e:
            logger.warning(f"Poller error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


# --- FastAPI App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background poller on startup, cancel on shutdown."""
    logger.info(f"Dashboard server starting on {BIND_HOST}:{BIND_PORT}")
    task = asyncio.create_task(_background_poller())
    yield
    task.cancel()
    try:
        await task
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
    allow_origins=["http://127.0.0.1:8420"],
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
    """Yield session state as SSE events when data changes."""
    last_updated_at = 0.0
    while True:
        current_updated = _cached_state.get("updated_at", 0)
        if current_updated != last_updated_at:
            last_updated_at = current_updated
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


def run_server(host: str = BIND_HOST, port: int = BIND_PORT):
    """Run the dashboard server (blocking)."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
