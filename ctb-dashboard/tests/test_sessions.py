"""Tests for sessions module."""

import subprocess
from unittest.mock import patch

from ctb_dashboard.sessions import get_all_claude_sessions, get_session_path, sort_sessions_by_activity


def test_get_all_claude_sessions_no_tmux():
    """Returns empty list when tmux is not available."""
    with patch("subprocess.run", side_effect=FileNotFoundError("tmux not found")):
        result = get_all_claude_sessions()
        assert result == []


def test_get_all_claude_sessions_no_sessions():
    """Returns empty list when no claude sessions exist."""
    mock_result = subprocess.CompletedProcess(args="", returncode=1, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        result = get_all_claude_sessions()
        assert result == []


def test_get_session_path_not_found():
    """Returns empty string when session does not exist."""
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
        result = get_session_path("nonexistent_session")
        assert result == ""


def test_sort_sessions_by_activity_fallback():
    """Returns original list on error."""
    sessions = ["claude_a", "claude_b"]
    with patch("subprocess.run", side_effect=Exception("fail")):
        result = sort_sessions_by_activity(sessions)
        assert result == sessions
