"""get_all_claude_sessions() must never hand back a bash-only session.

This is the one place the Telegram bot's /summary, /board and every log
path (which all build their session lists from here, directly or through
SessionManager) ultimately reads from, so excluding @ctb_shell-marked
sessions here -- rather than separately in each caller -- is what keeps a
typed password out of every one of them at once.
"""

import subprocess
from unittest.mock import patch

from claude_ctb.session_manager import SessionManager


def _manager():
    return SessionManager()


@patch("claude_ctb.session_manager.subprocess.run")
def test_shell_marked_sessions_are_excluded(mock_run):
    def fake_run(cmd, shell=None, capture_output=True, text=True, **kwargs):
        if isinstance(cmd, str) and "grep '^claude'" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="claude_a\nclaude_b_sh\n", stderr="")
        if isinstance(cmd, list) and cmd[:2] == ["tmux", "list-sessions"]:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout="claude_a\t\nclaude_b_sh\t1\n", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    mock_run.side_effect = fake_run
    result = _manager().get_all_claude_sessions(sort_by_mtime=False)
    assert result == ["claude_a"]


@patch("claude_ctb.session_manager.subprocess.run")
def test_marker_scan_failure_does_not_hide_every_session(mock_run):
    """Unable to check the marker must fail open -- the ordinary listing
    still comes back, nothing extra hidden -- for everything except names
    ending in `_sh`, which are excluded on the name alone (see item 5)."""
    def fake_run(cmd, shell=None, capture_output=True, text=True, **kwargs):
        if isinstance(cmd, str) and "grep '^claude'" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="claude_a\nclaude_b\n", stderr="")
        if isinstance(cmd, list) and cmd[:2] == ["tmux", "list-sessions"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    mock_run.side_effect = fake_run
    result = _manager().get_all_claude_sessions(sort_by_mtime=False)
    assert result == ["claude_a", "claude_b"]


@patch("claude_ctb.session_manager.subprocess.run")
def test_marker_scan_failure_still_excludes_sh_suffixed_names(mock_run):
    def fake_run(cmd, shell=None, capture_output=True, text=True, **kwargs):
        if isinstance(cmd, str) and "grep '^claude'" in cmd:
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="claude_a\nclaude_b_sh\n", stderr="")
        if isinstance(cmd, list) and cmd[:2] == ["tmux", "list-sessions"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    mock_run.side_effect = fake_run
    result = _manager().get_all_claude_sessions(sort_by_mtime=False)
    assert result == ["claude_a"]


@patch("claude_ctb.session_manager.subprocess.run")
def test_is_shell_session_true_for_marked(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="1\n", stderr="")
    assert _manager().is_shell_session("claude_b_sh") is True


@patch("claude_ctb.session_manager.subprocess.run")
def test_is_shell_session_false_on_failure(mock_run):
    mock_run.side_effect = OSError("no tmux")
    assert _manager().is_shell_session("claude_a") is False
