"""
Session discovery utilities for CTB Dashboard.

Provides standalone functions to list and inspect Claude Code tmux sessions.
Extracted from claude_ctb.session_manager (stateless subset).
"""

import subprocess
from typing import List


def get_all_claude_sessions(sort_by_mtime: bool = True) -> List[str]:
    """Get list of all Claude sessions (excluding monitoring sessions).

    Args:
        sort_by_mtime: If True, sort sessions by most recently modified (newest first)
    """
    try:
        result = subprocess.run(
            "tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
            # Exclude monitoring sessions and telegram bridge
            sessions = [s for s in sessions if s not in [
                'claude-multi-monitor', 'claude-monitor', 'claude-telegram-bridge',
            ]]

            if sort_by_mtime and sessions:
                sessions = sort_sessions_by_activity(sessions)

            return sessions
        else:
            return []
    except Exception:
        return []


def sort_sessions_by_activity(sessions: List[str]) -> List[str]:
    """Sort sessions by last activity time (most recent first).

    Uses single tmux call to fetch all session activity times at once.
    """
    try:
        result = subprocess.run(
            "tmux list-sessions -F '#{session_name} #{session_activity}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return sessions

        # Parse into lookup dict
        activity_map = {}
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split(' ', 1)
            if len(parts) == 2:
                try:
                    activity_map[parts[0]] = int(parts[1])
                except ValueError:
                    activity_map[parts[0]] = 0

        # Sort requested sessions by activity time
        session_times = [(s, activity_map.get(s, 0)) for s in sessions]
        session_times.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in session_times]

    except Exception:
        return sessions


def get_session_path(session_name: str) -> str:
    """Get working directory of a tmux session."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", session_name, "-p", "#{pane_current_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""
