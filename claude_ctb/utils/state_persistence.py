"""
State persistence utility for Claude-Ops.
Provides directory structure and path management for persisting session state
across monitoring system restarts.
"""
import os
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import time


@dataclass
class PersistedSessionState:
    """
    Persisted session state for tracking across restarts.

    Attributes:
        session_name: Name of the tmux session
        screen_hash: MD5 hash of screen content
        last_state: Last detected state (e.g., WAITING_INPUT, WORKING)
        timestamp: Timestamp of last state update
        notification_sent: Whether notification was sent for this state
    """

    session_name: str
    screen_hash: str
    last_state: str
    notification_sent: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_name": self.session_name,
            "screen_hash": self.screen_hash,
            "last_state": self.last_state,
            "notification_sent": self.notification_sent,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersistedSessionState":
        """Deserialize from dictionary."""
        return cls(
            session_name=data["session_name"],
            screen_hash=data["screen_hash"],
            last_state=data["last_state"],
            notification_sent=data["notification_sent"],
            timestamp=data.get("timestamp", time.time())
        )

    def save(self, filepath: str):
        """
        Save state to file using atomic write (temp + rename).

        Args:
            filepath: Path to save state file
        """
        data = self.to_dict()

        # Atomic write: write to temp file, then rename
        dir_path = os.path.dirname(filepath)
        os.makedirs(dir_path, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=dir_path,
            delete=False,
            suffix='.tmp'
        ) as tmp_file:
            json.dump(data, tmp_file, indent=2)
            tmp_path = tmp_file.name

        # Atomic rename
        os.rename(tmp_path, filepath)

    @classmethod
    def load(cls, filepath: str) -> Optional["PersistedSessionState"]:
        """
        Load state from file.

        Args:
            filepath: Path to state file

        Returns:
            PersistedSessionState if file exists, None otherwise
        """
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, IOError):
            return None


# Default state directory
DEFAULT_STATE_DIR = "/tmp/claude-ops/state"


def get_state_dir() -> Path:
    """
    Get the state persistence directory path.
    Creates the directory if it doesn't exist.

    Returns:
        Path: Directory path for state files
    """
    state_dir = Path(os.getenv("CLAUDE_OPS_STATE_DIR", DEFAULT_STATE_DIR))
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_state_file_path(session_name: str) -> Path:
    """
    Get the state file path for a specific session.

    Args:
        session_name: Name of the tmux session (e.g., "claude_my-project")

    Returns:
        Path: Full path to the state file for this session
    """
    state_dir = get_state_dir()
    # Sanitize session name for filename
    safe_name = session_name.replace("/", "_").replace("\\", "_")
    return state_dir / f"{safe_name}.state"


def get_session_state_file(session_name: str) -> Path:
    """
    Get the state file path for a specific session.

    Args:
        session_name: Name of the tmux session

    Returns:
        Path to session state JSON file
    """
    state_dir = get_state_dir()
    # Sanitize session name for filesystem
    safe_name = session_name.replace("/", "_").replace(":", "_")
    return state_dir / f"{safe_name}.json"


def get_reconnection_state_file(session_name: str) -> Path:
    """
    Get the reconnection state file path for a specific session.

    Args:
        session_name: Name of the tmux session

    Returns:
        Path to reconnection state JSON file
    """
    state_dir = get_state_dir()
    safe_name = session_name.replace("/", "_").replace(":", "_")
    return state_dir / f"{safe_name}_reconnect.json"


def ensure_state_dir_exists() -> bool:
    """
    Ensure the state directory exists and is writable.

    Returns:
        bool: True if directory exists and is writable, False otherwise
    """
    try:
        state_dir = get_state_dir()
        # Test write access
        test_file = state_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        return False


def clear_session_state(session_name: str) -> bool:
    """
    Clear persisted state for a specific session.

    Args:
        session_name: Name of the tmux session

    Returns:
        bool: True if state was cleared, False if file didn't exist or error
    """
    try:
        state_file = get_state_file_path(session_name)
        if state_file.exists():
            state_file.unlink()
            return True
        return False
    except (OSError, PermissionError):
        return False


def cleanup_old_state_files(max_age_days: int = 30) -> int:
    """
    Remove state files older than specified age.

    Args:
        max_age_days: Maximum age of state files to keep

    Returns:
        Number of files deleted
    """
    state_dir = get_state_dir()
    max_age_seconds = max_age_days * 24 * 60 * 60
    current_time = time.time()

    deleted_count = 0
    for filepath in state_dir.glob("*.json"):
        file_age = current_time - filepath.stat().st_mtime
        if file_age > max_age_seconds:
            filepath.unlink()
            deleted_count += 1

    return deleted_count


def list_persisted_sessions() -> list[str]:
    """
    List all sessions with persisted state.

    Returns:
        list[str]: Session names that have state files
    """
    try:
        state_dir = get_state_dir()
        sessions = []

        for filepath in state_dir.glob("*.state"):
            if filepath.is_file():
                sessions.append(filepath.stem)

        # Also check .json files
        for filepath in state_dir.glob("*.json"):
            if filepath.is_file() and not filepath.name.endswith("_reconnect.json"):
                sessions.append(filepath.stem)

        return list(set(sessions))
    except (OSError, PermissionError):
        return []
