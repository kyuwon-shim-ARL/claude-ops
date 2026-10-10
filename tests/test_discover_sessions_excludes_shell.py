"""discover_sessions() must never hand back a bash-only session.

The exclusion itself now lives in session_manager.get_all_claude_sessions()
(see test_session_manager_shell_exclusion.py) so that every caller -- this
monitor, the bot's /summary, /board -- inherits it from one place.
discover_sessions() is a thin wrapper, so this just pins that it still
delegates there and does not re-filter (or un-filter) on its own.
"""

from unittest.mock import patch

from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor


def _monitor():
    # __init__ touches tempfile/os only -- no tmux, safe to construct directly.
    return MultiSessionMonitor()


@patch("claude_ctb.monitoring.multi_monitor.session_manager")
def test_discover_sessions_is_exactly_what_session_manager_returns(mock_sm):
    """session_manager.get_all_claude_sessions() already excludes shell
    sessions; this asserts discover_sessions() does not duplicate, bypass,
    or otherwise second-guess that filtering."""
    mock_sm.get_all_claude_sessions.return_value = ["claude_a"]
    assert _monitor().discover_sessions() == {"claude_a"}
    mock_sm.get_all_claude_sessions.assert_called_once_with()
