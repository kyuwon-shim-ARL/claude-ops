"""Is Claude actually running in this pane?

tmux's pane_current_command names the foreground process *group leader*. When
claude shares a process group with the bash that launched it, that leader is
bash, and the send guard refused the session as a shell while Claude sat there
drawing its UI. The process tree does not have that ambiguity: either a claude
process is running under the pane or it is not.

The subprocess calls are stubbed here; a live check against real tmux sessions
is in the verification run, not in this suite, because it needs real sessions.
"""

from unittest.mock import MagicMock, patch

import pytest

from ctb_dashboard.session_input import pane_has_claude


def _tmux_pid(pid="1070512", rc=0):
    return MagicMock(returncode=rc, stdout=pid + "\n", stderr="")


PANE = "1070512"


def _ps(rows, rc=0):
    """`ps -eo pid=,ppid=,comm=` output: (pid, ppid, comm) triples."""
    body = "".join(f"{pid} {ppid} {comm}\n" for pid, ppid, comm in rows)
    return MagicMock(returncode=rc, stdout=body, stderr="")


def test_claude_under_the_pane_is_found():
    rows = [(PANE, "1", "bash"), ("1071644", PANE, "claude")]
    with patch("subprocess.run", side_effect=[_tmux_pid(), _ps(rows)]):
        assert pane_has_claude("claude_demo") is True


def test_a_pane_running_only_a_shell_has_no_claude():
    rows = [(PANE, "1", "bash")]
    with patch("subprocess.run", side_effect=[_tmux_pid(), _ps(rows)]):
        assert pane_has_claude("claude_demo") is False


def test_claude_is_found_further_down_the_tree():
    """Started through a wrapper, claude is a grandchild rather than a child."""
    rows = [(PANE, "1", "bash"), ("2000", PANE, "uv"), ("2001", "2000", "claude")]
    with patch("subprocess.run", side_effect=[_tmux_pid(), _ps(rows)]):
        assert pane_has_claude("claude_demo") is True


def test_claude_in_a_different_pane_is_not_counted():
    """Every process is in the table; only this pane's subtree may answer."""
    rows = [(PANE, "1", "bash"), ("3000", "1", "bash"), ("3001", "3000", "claude")]
    with patch("subprocess.run", side_effect=[_tmux_pid(), _ps(rows)]):
        assert pane_has_claude("claude_demo") is False


def test_an_unrelated_process_is_not_mistaken_for_claude():
    """Substring matching would call 'claude-wrapper-logs' a running Claude."""
    rows = [(PANE, "1", "bash"), ("2000", PANE, "claude-log-tail"), ("2001", PANE, "vim")]
    with patch("subprocess.run", side_effect=[_tmux_pid(), _ps(rows)]):
        assert pane_has_claude("claude_demo") is False


def test_a_failed_tmux_query_reports_no_claude():
    """Unknown is not evidence. The caller keeps refusing on the pane command,
    which is what it did before this check existed."""
    with patch("subprocess.run", side_effect=[_tmux_pid(rc=1)]):
        assert pane_has_claude("claude_demo") is False


def test_a_timeout_does_not_propagate():
    """This runs inside the poll path; it must fail quietly, not raise."""
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("tmux", 5)):
        assert pane_has_claude("claude_demo") is False


def test_a_nonsense_pane_pid_is_not_queried_for_children():
    with patch("subprocess.run", side_effect=[_tmux_pid(pid="not-a-pid")]) as run:
        assert pane_has_claude("claude_demo") is False
    assert run.call_count == 1, "should not shell out with a bad pid"
