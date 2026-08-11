"""The suite must not be able to drive the machine it runs on.

This runs on the host it monitors, against ~75 live Claude sessions. Twice a
test reached them: one made tmux switch the user's terminal, creating and
removing a session called some-session; another posted an empty pin set that
overwrote the user's real pins on every run. Neither left a trace.

The guard lives in conftest as an autouse fixture. It needs tests of its own —
removing it silently left the whole suite green, which is precisely how this
went unnoticed.
"""

import os
import subprocess

import pytest

from ctb_dashboard import server


def test_live_tmux_is_refused():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.run(["tmux", "list-sessions"], capture_output=True)


def test_an_absolute_path_to_tmux_is_refused_too():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.run(["/usr/bin/tmux", "kill-session", "-t", "x"], capture_output=True)


def test_popen_is_refused_as_well():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.Popen(["tmux", "ls"])


def test_other_programs_still_run():
    """Tests legitimately use node and git; a blanket ban would be worse."""
    assert subprocess.run(["true"]).returncode == 0


def test_state_files_point_somewhere_disposable():
    """A test writing these would land on the user's pins and idle timers."""
    for path in (server._PINNED_PERSIST_PATH, server._TS_PERSIST_PATH):
        assert "/.claude-ops/" not in path, f"{path} is the real user state"


# --- the ways it was actually escaping ---------------------------------------
#
# argv[0] alone missed two: sessions.py and state_detector.py run their tmux
# commands with shell=True, so the whole command arrives as one string, and
# session_manager.py uses os.system.

def test_shell_string_escape():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.run("tmux list-sessions", shell=True, capture_output=True)

def test_check_output_escape():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.check_output(["tmux", "ls"])

def test_call_escape():
    with pytest.raises(AssertionError, match="live tmux"):
        subprocess.call(["tmux", "ls"])

def test_os_system_escape():
    with pytest.raises(AssertionError, match="live tmux"):
        os.system("tmux list-sessions > /dev/null 2>&1")


def test_the_audit_log_is_not_the_users():
    """Runs were adding hundreds of entries to the record of who drove real
    sessions, which is the first place anyone looks when something moved."""
    from ctb_dashboard import control_audit
    assert "/.claude-ops/" not in control_audit.AUDIT_PATH, control_audit.AUDIT_PATH
