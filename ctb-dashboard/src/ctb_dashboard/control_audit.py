"""Audit trail and rate limiting for the control endpoints.

Two separate concerns, kept together because they guard the same surface: the
routes that can type into a live session.

What the audit log deliberately does NOT contain is the prompt text. The log
sits in a plain file on disk; if it leaked, the interesting content would be
what was said to Claude, not that something was said. Recording who touched
which session and when is enough to answer "did I do that?" without turning the
log into the most sensitive file in the deployment.
"""

import json
import logging
import os
import time
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)

AUDIT_PATH = os.path.expanduser(
    os.environ.get("CTB_CONTROL_AUDIT_LOG", "~/.claude-ops/control-audit.log")
)

# A phone in a pocket, a stuck retry loop, or a script gone wrong should not be
# able to hammer tmux. Generous for a human, obviously wrong for a loop.
RATE_LIMIT_MAX = int(os.environ.get("CTB_CONTROL_RATE_MAX", "30"))
RATE_LIMIT_WINDOW = float(os.environ.get("CTB_CONTROL_RATE_WINDOW", "60"))


def record(
    endpoint: str,
    session: str,
    client: str | None,
    ok: bool,
    reason: str | None = None,
) -> None:
    """Append one line describing a control action. Never raises.

    Auditing must not be able to break the thing it audits, so every failure
    here degrades to a log warning.
    """
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoint": endpoint,
        "session": session,
        "client": client or "unknown",
        "ok": bool(ok),
    }
    if reason:
        entry["reason"] = reason
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("control audit write failed: %s", e)


class RateLimiter:
    """Sliding-window limiter shared across the control endpoints.

    Deliberately global rather than per-session: the thing being protected is
    tmux and the host, and spreading a flood over many sessions would not make
    it cheaper. Single-user deployment, so there is no per-caller fairness to
    preserve.
    """

    def __init__(self, max_events: int = RATE_LIMIT_MAX, window: float = RATE_LIMIT_WINDOW):
        self.max_events = max_events
        self.window = window
        self._events: deque[float] = deque()
        self._lock = Lock()

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            cutoff = now - self.window
            while self._events and self._events[0] <= cutoff:
                self._events.popleft()
            if len(self._events) >= self.max_events:
                return False
            self._events.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    @property
    def in_window(self) -> int:
        with self._lock:
            return len(self._events)


limiter = RateLimiter()
