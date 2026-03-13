"""
SharedSessionState — Atomic JSON writer for session state sharing.

Writes session state to /tmp/ctb-sessions.json using atomic rename
so that external consumers (FastAPI backend, etc.) always read
consistent data without file locks.

e006: SharedSessionState experiment
"""

import json
import os
import time
import logging
import tempfile
import threading
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Default output path
DEFAULT_STATE_PATH = "/tmp/ctb-sessions.json"


class SharedSessionState:
    """Writes aggregated session state to a JSON file atomically.

    Usage:
        shared = SharedSessionState()
        shared.update_session("claude_my-app", {
            "state": "working",
            "last_activity": 1710000000.0,
        })
        shared.flush()  # atomic write to disk
    """

    def __init__(self, path: str = DEFAULT_STATE_PATH):
        self.path = path
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._last_flush: float = 0.0
        self._lock = threading.Lock()

    def update_session(self, session_name: str, data: Dict[str, Any]) -> None:
        """Update in-memory state for a single session (thread-safe).

        Args:
            session_name: tmux session name
            data: Dict with state fields (state, last_activity, screen_hash, etc.)
        """
        with self._lock:
            entry = self._sessions.get(session_name, {})
            entry.update(data)
            entry["name"] = session_name
            entry["updated_at"] = time.time()
            self._sessions[session_name] = entry

    def remove_session(self, session_name: str) -> None:
        """Remove a session from the shared state (thread-safe)."""
        with self._lock:
            self._sessions.pop(session_name, None)

    def flush(self) -> bool:
        """Atomically write current state to disk (thread-safe).

        Uses write-to-temp + os.replace for crash-safe atomic update.

        Returns:
            True if write succeeded, False otherwise.
        """
        with self._lock:
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "sessions": list(self._sessions.values()),
            }

        try:
            dir_name = os.path.dirname(self.path) or tempfile.gettempdir()
            fd, tmp_path = tempfile.mkstemp(
                prefix=".ctb-sessions-", suffix=".tmp", dir=dir_name
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp_path, self.path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            with self._lock:
                self._last_flush = time.time()
            return True

        except Exception as e:
            logger.error(f"Failed to flush shared state: {e}")
            return False

    def flush_if_due(self, interval: float = 3.0) -> bool:
        """Flush only if *interval* seconds have elapsed since the last flush (thread-safe).

        Args:
            interval: Minimum seconds between flushes (default 3s).

        Returns:
            True if flushed, False if skipped or failed.
        """
        with self._lock:
            if time.time() - self._last_flush < interval:
                return False
        return self.flush()

    def get_snapshot(self) -> Dict[str, Any]:
        """Return the current in-memory state (for testing/debugging)."""
        return {
            "version": 1,
            "updated_at": time.time(),
            "sessions": list(self._sessions.values()),
        }

    @staticmethod
    def read(path: str = DEFAULT_STATE_PATH) -> Optional[Dict[str, Any]]:
        """Read the shared state file (consumer side).

        Returns:
            Parsed JSON dict, or None if file missing/corrupt.
        """
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        except Exception as e:
            logger.warning(f"Failed to read shared state: {e}")
            return None
