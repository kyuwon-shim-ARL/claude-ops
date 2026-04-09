#!/usr/bin/env python3
"""
Hook Notification Handler
Called by notify_telegram.sh when idle_prompt hook fires.
Uses the same notification format as primary scraping.
"""

import sys
import json
import os
import fcntl
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from claude_ctb.config import ClaudeOpsConfig
from claude_ctb.telegram.notifier import SmartNotifier
from claude_ctb.session_manager import session_manager
import logging

# Wait time tracking
try:
    from claude_ctb.utils.wait_time_tracker_v2 import migrate_to_v2
    wait_tracker = migrate_to_v2()
except ImportError:
    wait_tracker = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log file for hook events
LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "hooks_events.jsonl"
)

def log_event(project: str, event_type: str, skipped: bool = False, reason: str = "") -> None:
    """Log hook event to JSONL file."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "project": project,
        "event_type": event_type,
        "source": "hooks",
        "skipped": skipped,
        "reason": reason
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + "\n")


def _state_dir() -> str:
    """Get the notifications state directory (cached)."""
    d = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".state", "notifications"
    )
    os.makedirs(d, exist_ok=True)
    return d


def get_notification_state_file(session_name: str) -> str:
    """Get path to notification state file for a session"""
    return os.path.join(_state_dir(), f"{session_name}.json")


def get_session_cooldown_file(session_name: str) -> str:
    """Per-session cooldown file. NOT cleared by UserPromptSubmit.
    Prevents autonomous sessions (ralph/autopilot) from re-notifying
    every time they cycle between working and idle states."""
    return os.path.join(_state_dir(), f"{session_name}.cooldown.json")


def get_global_cooldown_file() -> str:
    """Get path to global cooldown file (shared across all sessions)"""
    return os.path.join(_state_dir(), "_global_cooldown.json")


def was_notification_already_sent(session_name: str) -> bool:
    """Check if notification was already sent for this session.

    Returns True if state file exists (notification was sent).
    State file is deleted by UserPromptSubmit hook when user sends input.
    This ensures: notification sent once → no more notifications until user responds.
    """
    state_file = get_notification_state_file(session_name)
    try:
        return os.path.exists(state_file)
    except Exception as e:
        logger.debug(f"Error checking notification state: {e}")
    return False


def is_session_cooldown_active(session_name: str, cooldown_seconds: int = 600) -> bool:
    """Per-session time-based cooldown. NOT cleared by UserPromptSubmit.
    Prevents autonomous sessions from re-notifying on every work cycle."""
    cooldown_file = get_session_cooldown_file(session_name)
    try:
        if os.path.exists(cooldown_file):
            with open(cooldown_file, 'r') as f:
                state = json.load(f)
            last_sent = datetime.fromisoformat(state.get('last_sent', ''))
            elapsed = (datetime.now() - last_sent).total_seconds()
            return elapsed < cooldown_seconds
    except Exception as e:
        logger.debug(f"Error reading session cooldown: {e}")
    return False


def is_global_cooldown_active(cooldown_seconds: int = 30) -> bool:
    """Check if global cooldown is active (any notification sent recently)"""
    cooldown_file = get_global_cooldown_file()
    try:
        if os.path.exists(cooldown_file):
            with open(cooldown_file, 'r') as f:
                state = json.load(f)
            last_sent = datetime.fromisoformat(state.get('last_sent', ''))
            elapsed = (datetime.now() - last_sent).total_seconds()
            return elapsed < cooldown_seconds
    except Exception as e:
        logger.debug(f"Error reading global cooldown: {e}")
    return False


def mark_notification_sent(session_name: str) -> None:
    """Mark notification as sent for a session (state file + cooldown file)"""
    now = datetime.now().isoformat()
    # State file (cleared by UserPromptSubmit)
    state_file = get_notification_state_file(session_name)
    with open(state_file, 'w') as f:
        json.dump({'last_sent': now, 'session': session_name}, f)
    # Cooldown file (NOT cleared by UserPromptSubmit — time-based expiry only)
    cooldown_file = get_session_cooldown_file(session_name)
    with open(cooldown_file, 'w') as f:
        json.dump({'last_sent': now, 'session': session_name}, f)


def mark_global_cooldown(session_name: str) -> None:
    """Mark global cooldown after sending any notification"""
    cooldown_file = get_global_cooldown_file()
    state = {
        'last_sent': datetime.now().isoformat(),
        'last_session': session_name
    }
    with open(cooldown_file, 'w') as f:
        json.dump(state, f)


def clear_notification_state(session_name: str) -> None:
    """Clear notification state when user sends input"""
    state_file = get_notification_state_file(session_name)
    try:
        if os.path.exists(state_file):
            os.remove(state_file)
    except Exception:
        pass


def main() -> None:
    # Read stdin first for better error logging
    try:
        stdin_content = sys.stdin.read()
        if not stdin_content.strip():
            logger.error("No input received from stdin")
            sys.exit(1)
        input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"Input received: {stdin_content[:500]}")
        sys.exit(1)

    # Parse input
    session_id = input_data.get('session_id', 'unknown')
    project_dir = input_data.get('cwd', input_data.get('project_dir', 'unknown'))
    hook_event = input_data.get('hook_event_name', 'unknown')
    notification_type = input_data.get('notification_type', '')

    # Extract project name
    project_name = os.path.basename(project_dir)

    # Skip Stop hook entirely (unreliable with bypass permission)
    if hook_event == 'Stop':
        logger.info(f"Skipping Stop hook for {project_name}: unreliable with bypass permission")
        log_event(project_name, "stop_skipped", skipped=True, reason="unreliable_with_bypass")
        sys.exit(0)

    # Only process idle_prompt and permission_prompt
    if notification_type not in ('idle_prompt', 'permission_prompt'):
        logger.info(f"Skipping notification type: {notification_type}")
        sys.exit(0)

    # Find the session name (claude_<project>)
    session_name = f"claude_{project_name}"

    # Check if session exists
    if not session_manager.session_exists(session_name):
        # Try without prefix
        if session_manager.session_exists(project_name):
            session_name = project_name
        else:
            logger.error(f"Session not found: {session_name}")
            sys.exit(1)

    # Acquire exclusive lock to prevent race conditions from concurrent async hooks.
    # All cooldown/dedup checks and state writes happen atomically under this lock.
    lock_file_path = os.path.join(
        os.path.dirname(get_global_cooldown_file()), "_notify.lock"
    )
    lock_fd = open(lock_file_path, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Another hook instance holds the lock - skip to avoid pile-up
        logger.info(f"⏭️ Skipping notification for {session_name} (another hook running)")
        log_event(project_name, f"hook_{notification_type}", skipped=True, reason="lock_contention")
        lock_fd.close()
        sys.exit(0)

    try:
        # Check global cooldown first (prevent notification flood from multiple sessions)
        # 600s = 10 minutes — with 20+ idle sessions, shorter values cause round-robin spam
        if is_global_cooldown_active(cooldown_seconds=600):
            logger.info(f"⏭️ Skipping notification for {session_name} (global cooldown active)")
            log_event(project_name, f"hook_{notification_type}", skipped=True, reason="global_cooldown")
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            sys.exit(0)

        # Per-session time-based cooldown (survives UserPromptSubmit clearing)
        # Prevents autonomous sessions (ralph/autopilot) from re-notifying on every work cycle
        if is_session_cooldown_active(session_name, cooldown_seconds=600):
            logger.info(f"⏭️ Skipping notification for {session_name} (session cooldown active)")
            log_event(project_name, f"hook_{notification_type}", skipped=True, reason="session_cooldown")
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            sys.exit(0)

        # Check if notification was already sent (wait for user input to clear)
        if was_notification_already_sent(session_name):
            logger.info(f"⏭️ Skipping notification for {session_name} (already notified, waiting for user input)")
            log_event(project_name, f"hook_{notification_type}", skipped=True, reason="already_notified")
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            sys.exit(0)

        # Write state files BEFORE sending (lock ensures no race)
        mark_notification_sent(session_name)
        mark_global_cooldown(session_name)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

    # Switch to the session and send notification using SmartNotifier (outside lock to avoid holding it during I/O)
    try:

        original_session = session_manager.get_active_session()
        session_manager.switch_session(session_name)

        config = ClaudeOpsConfig()
        notifier = SmartNotifier(config)

        # Mark state transition for wait time tracking
        if wait_tracker:
            wait_tracker.mark_state_transition(session_name, 'waiting')

        # Send notification using the same format as primary scraping
        success = notifier.send_work_completion_notification()

        # If send failed, remove state file so next invocation can retry
        if not success:
            clear_notification_state(session_name)

        # Switch back
        session_manager.switch_session(original_session)

        if success:
            logger.info(f"✅ Hook notification sent for {session_name}")
            log_event(project_name, f"hook_{notification_type}", skipped=False)
        else:
            logger.warning(f"⏭️ Notification skipped for {session_name} (duplicate)")
            log_event(project_name, f"hook_{notification_type}", skipped=True, reason="duplicate")

    except Exception as e:
        logger.error(f"Error sending hook notification: {e}")
        log_event(project_name, "error", skipped=True, reason=str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
