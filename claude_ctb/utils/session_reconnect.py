"""
Session reconnection state management with exponential backoff.
Tracks disconnection, retry attempts, and timeout enforcement.
"""
from dataclasses import dataclass, field
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionReconnectionState:
    """
    Tracks session reconnection state with exponential backoff.

    Attributes:
        session_name: Name of the disconnected session
        disconnect_time: Timestamp when disconnection was detected
        retry_count: Number of reconnection attempts
        next_retry_time: Timestamp for next retry attempt
        max_duration_seconds: Maximum time to retry (default: 300s = 5min)
        initial_backoff: Initial backoff delay in seconds (default: 1s)
        max_backoff: Maximum backoff delay in seconds (default: 30s)
        status: Current state (RECONNECTING, SUCCESS, FAILED)
    """

    session_name: str
    max_duration_seconds: int = 300
    initial_backoff: int = 1
    max_backoff: int = 30

    disconnect_time: float = field(default_factory=time.time)
    retry_count: int = 0
    next_retry_time: float = field(default_factory=time.time)
    status: str = "RECONNECTING"
    current_backoff_seconds: int = 1

    def get_next_backoff(self) -> int:
        """
        Calculate next backoff delay using exponential backoff.
        Formula: min(initial * 2^retry_count, max)

        Returns:
            Next backoff delay in seconds
        """
        # Calculate backoff: 1, 2, 4, 8, 16, 30 (max), 30 (max), ...
        backoff = min(
            self.initial_backoff * (2 ** self.retry_count),
            self.max_backoff
        )

        self.current_backoff_seconds = backoff
        self.next_retry_time = time.time() + backoff
        self.retry_count += 1

        # T039: Log retry attempt with backoff delay
        logger.info(
            f"Session reconnection retry #{self.retry_count} for '{self.session_name}' "
            f"with {backoff}s backoff (elapsed: {self.get_elapsed_time():.1f}s)"
        )

        return backoff

    def is_timed_out(self) -> bool:
        """
        Check if reconnection has exceeded max_duration timeout.

        Returns:
            True if timeout exceeded, False otherwise
        """
        elapsed = time.time() - self.disconnect_time
        return elapsed > self.max_duration_seconds

    def mark_success(self):
        """Mark reconnection as successful."""
        self.status = "SUCCESS"
        # T039: Log success outcome
        logger.info(
            f"Session reconnection SUCCESS for '{self.session_name}' "
            f"after {self.retry_count} attempts ({self.get_elapsed_time():.1f}s)"
        )

    def mark_failed(self):
        """Mark reconnection as failed."""
        self.status = "FAILED"
        # T039: Log failure outcome
        logger.error(
            f"Session reconnection FAILED for '{self.session_name}' "
            f"after {self.retry_count} attempts ({self.get_elapsed_time():.1f}s total)"
        )

    def get_elapsed_time(self) -> float:
        """Get elapsed time since disconnection."""
        return time.time() - self.disconnect_time
