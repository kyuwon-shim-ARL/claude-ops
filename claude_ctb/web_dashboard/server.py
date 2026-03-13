"""
Web Dashboard Backend — FastAPI + SSE

Serves session state from /tmp/ctb-sessions.json written by SharedSessionState.
Provides both REST and SSE endpoints for the HTML frontend.

e003: Web Dashboard backend experiment
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .shared_state import SharedSessionState, DEFAULT_STATE_PATH

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds between SSE pushes
BIND_HOST = "127.0.0.1"
BIND_PORT = 8420


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — log startup/shutdown."""
    logger.info(f"Dashboard server starting on {BIND_HOST}:{BIND_PORT}")
    yield
    logger.info("Dashboard server shutting down")


app = FastAPI(
    title="Claude-CTB Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow local dev access
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


def _read_state() -> dict:
    """Read the shared state JSON, returning empty structure on failure."""
    data = SharedSessionState.read(DEFAULT_STATE_PATH)
    if data is None:
        return {"version": 1, "updated_at": 0, "sessions": []}
    return data


@app.get("/")
async def root():
    """Redirect to dashboard HTML."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        with open(index_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard not found. Place index.html in static/</h1>")


@app.get("/api/sessions")
async def get_sessions():
    """REST endpoint: current session state snapshot."""
    return _read_state()


async def _session_event_generator() -> AsyncGenerator[dict, None]:
    """Yield session state as SSE events every POLL_INTERVAL seconds."""
    last_updated_at = 0.0
    while True:
        data = _read_state()
        current_updated = data.get("updated_at", 0)
        # Only send if data changed
        if current_updated != last_updated_at:
            last_updated_at = current_updated
            yield {"event": "sessions", "data": json.dumps(data, ensure_ascii=False)}
        await asyncio.sleep(POLL_INTERVAL)


@app.get("/api/sessions/stream")
async def session_stream():
    """SSE endpoint: real-time session state updates."""
    return EventSourceResponse(_session_event_generator())


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    state = _read_state()
    return {
        "status": "ok",
        "sessions_count": len(state.get("sessions", [])),
        "last_updated": state.get("updated_at", 0),
    }


def run_server(host: str = BIND_HOST, port: int = BIND_PORT):
    """Run the dashboard server (blocking)."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
