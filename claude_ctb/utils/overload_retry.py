"""
API 529 Overloaded retry state management with exponential backoff.

Backoff schedule: 30s → 60s → 120s → 240s → 480s → 960s → 1200s (20min cap)
Retries indefinitely at 20min intervals until the session recovers.
"""
from dataclasses import dataclass, field
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF = 30       # seconds
_MAX_BACKOFF = 1200         # 20 minutes
_FALLBACK_PROMPT = "재시도해줘"  # sent when no saved prompt available


@dataclass
class OverloadRetryState:
    """
    Tracks 529 overloaded retry state with exponential backoff.

    Saves the last user prompt so it can be re-sent after the API recovers.
    Retries indefinitely (no hard timeout) — gives up only when the session
    disappears or the caller explicitly clears the state.
    """

    session_name: str
    saved_prompt: str = _FALLBACK_PROMPT

    first_seen: float = field(default_factory=time.time)
    retry_count: int = 0
    next_retry_time: float = field(default_factory=time.time)
    current_backoff: int = _INITIAL_BACKOFF
    status: str = "WAITING"  # WAITING | RETRYING | RECOVERED

    def schedule_next(self) -> int:
        """Compute next backoff, schedule retry, return delay in seconds."""
        backoff = min(_INITIAL_BACKOFF * (2 ** self.retry_count), _MAX_BACKOFF)
        self.current_backoff = backoff
        self.next_retry_time = time.time() + backoff
        self.retry_count += 1
        logger.info(
            f"🔁 Overload retry #{self.retry_count} for '{self.session_name}' "
            f"in {backoff}s (elapsed {self.elapsed:.0f}s)"
        )
        return backoff

    def is_ready(self) -> bool:
        """True when the backoff period has elapsed."""
        return time.time() >= self.next_retry_time

    def mark_retrying(self):
        self.status = "RETRYING"

    def mark_recovered(self):
        self.status = "RECOVERED"
        logger.info(
            f"✅ Overload recovered for '{self.session_name}' "
            f"after {self.retry_count} retries ({self.elapsed:.0f}s total)"
        )

    @property
    def elapsed(self) -> float:
        return time.time() - self.first_seen

    @property
    def next_in(self) -> float:
        """Seconds until next retry (negative = already due)."""
        return self.next_retry_time - time.time()
