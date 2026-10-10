"""Marking a tmux session as 'bash only' and typing a raw line into it.

send_shell_line is deliberately not send_prompt: there is no readiness gate,
no bracketed paste, no mode-character handling -- the point is to type
exactly what was given, the way a terminal would. load-buffer/paste-buffer is
avoided on purpose: a tmux buffer outlives the call, and this path exists for
secrets.
"""

import subprocess

import pytest

from ctb_dashboard import session_input


class FakeRun:
    def __init__(self, returncode=0, stdout=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)

        class R:
            pass

        r = R()
        r.returncode = self.returncode
        r.stdout = self.stdout
        r.stderr = ""
        return r


@pytest.fixture
def run(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(session_input.subprocess, "run", fake)
    return fake


# --- is_shell_session / shell_sessions -------------------------------------


def test_is_shell_session_true_when_option_is_1(run):
    run.stdout = "1\n"
    assert session_input.is_shell_session("claude_demo_sh") is True
    assert run.calls == [
        ["tmux", "show-options", "-t", "claude_demo_sh", "-qv", "@ctb_shell"]
    ]


def test_is_shell_session_false_when_option_is_unset(run):
    run.stdout = "\n"
    assert session_input.is_shell_session("claude_demo") is False


def test_is_shell_session_false_on_tmux_failure(run):
    run.returncode = 1
    assert session_input.is_shell_session("nope") is False


def test_is_shell_session_false_on_timeout(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="tmux", timeout=5)
    monkeypatch.setattr(session_input.subprocess, "run", boom)
    assert session_input.is_shell_session("claude_demo") is False


def test_shell_sessions_reads_every_session_in_one_call(run):
    run.stdout = "claude_a\t\nclaude_b_sh\t1\nclaude_c\t0\n"
    assert session_input.shell_sessions() == {"claude_b_sh"}
    assert run.calls == [
        ["tmux", "list-sessions", "-F", "#{session_name}\t#{@ctb_shell}"]
    ]


def test_shell_sessions_empty_on_failure_with_no_history_or_candidates(run):
    """First call ever, tmux refuses: nothing sticky to fall back to yet,
    and no candidate list was given to apply the name-suffix heuristic to."""
    session_input._shell_sessions_cache.clear()
    run.returncode = 1
    assert session_input.shell_sessions() == set()


def test_shell_sessions_sticky_on_failure_after_a_success(run):
    """A scan that fails after a prior success must not suddenly say
    'nothing is a shell session' -- the last known-good set is kept."""
    run.stdout = "claude_a\t\nclaude_b_sh\t1\n"
    assert session_input.shell_sessions() == {"claude_b_sh"}
    run.returncode = 1
    assert session_input.shell_sessions() == {"claude_b_sh"}


def test_shell_sessions_timeout_falls_back_to_sticky_plus_sh_suffix(run, monkeypatch):
    run.stdout = "claude_a\t\nclaude_old_sh\t1\n"
    assert session_input.shell_sessions() == {"claude_old_sh"}

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="tmux", timeout=5)
    monkeypatch.setattr(session_input.subprocess, "run", boom)
    # A session created during the outage can't be in the sticky set (it
    # didn't exist on the last successful scan) -- the name-suffix
    # heuristic is what still catches it.
    result = session_input.shell_sessions(candidates=["claude_old_sh", "claude_new_sh", "claude_plain"])
    assert result == {"claude_old_sh", "claude_new_sh"}


def test_shell_sessions_os_error_is_caught(run, monkeypatch):
    session_input._shell_sessions_cache.clear()

    def boom(*a, **k):
        raise OSError("tmux binary not found")
    monkeypatch.setattr(session_input.subprocess, "run", boom)
    assert session_input.shell_sessions() == set()


# --- send_shell_line --------------------------------------------------------


def test_send_shell_line_types_literal_then_enter(run):
    session_input.send_shell_line("claude_demo_sh", "echo hi")
    assert run.calls == [
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-l", "--", "echo hi"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "Enter"],
    ]


def test_send_shell_line_never_touches_a_tmux_buffer(run):
    session_input.send_shell_line("claude_demo_sh", "export SECRET=abc123")
    for argv in run.calls:
        assert "load-buffer" not in argv
        assert "paste-buffer" not in argv


def test_send_shell_line_raises_on_tmux_failure(run):
    run.returncode = 1
    with pytest.raises(RuntimeError):
        session_input.send_shell_line("claude_demo_sh", "echo hi")


# --- trailing ';' --------------------------------------------------------
#
# Verified against a live tmux 3.6a: `send-keys -l -- 'abc;'` reaches the
# pane as 'abc' -- the trailing ';' is silently eaten, apparently by the
# same command-splitting tmux applies to its own command line, even inside
# a literal, double-dashed argument. 'p;;' arrives as 'p;': only the LAST
# semicolon of a trailing run goes missing, not every one of them. A
# semicolon anywhere but at the end ('x;y') is unaffected.
#
# The fix sends everything up to the trailing run of ';' as literal text,
# then each stripped ';' as its own keystroke via `-H 3b` (hex 0x3b is the
# ';' character) -- a key event rather than a line tmux's parser can see as
# chainable.


def test_a_single_trailing_semicolon_is_sent_as_a_hex_key(run):
    session_input.send_shell_line("claude_demo_sh", "abc;")
    assert run.calls == [
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-l", "--", "abc"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-H", "3b"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "Enter"],
    ]


def test_a_run_of_trailing_semicolons_sends_one_hex_key_each(run):
    session_input.send_shell_line("claude_demo_sh", "p;;")
    assert run.calls == [
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-l", "--", "p"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-H", "3b"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-H", "3b"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "Enter"],
    ]


def test_an_all_semicolon_line_sends_only_hex_keys(run):
    """No literal call at all when there is nothing left after the trailing
    run -- an empty -l argument would be a no-op, but a confusing one."""
    session_input.send_shell_line("claude_demo_sh", ";")
    assert run.calls == [
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-H", "3b"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "Enter"],
    ]


def test_a_mid_line_semicolon_is_sent_literally(run):
    session_input.send_shell_line("claude_demo_sh", "x;y")
    assert run.calls == [
        ["tmux", "send-keys", "-t", "claude_demo_sh", "-l", "--", "x;y"],
        ["tmux", "send-keys", "-t", "claude_demo_sh", "Enter"],
    ]


@pytest.mark.parametrize("text", ["-n", "#{session_name}", "echo hi"])
def test_flag_and_format_shaped_text_is_unaffected(run, text):
    session_input.send_shell_line("claude_demo_sh", text)
    assert run.calls[0] == ["tmux", "send-keys", "-t", "claude_demo_sh", "-l", "--", text]


# --- failure must not leak the text into the error ------------------------


def test_timeout_raises_runtime_error_without_the_text(monkeypatch):
    def boom(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=5)

    monkeypatch.setattr(session_input.subprocess, "run", boom)
    with pytest.raises(RuntimeError) as exc:
        session_input.send_shell_line("claude_demo_sh", "export SECRET=topsecret123")
    assert "topsecret123" not in str(exc.value)
    assert "SECRET" not in str(exc.value)


def test_os_error_raises_runtime_error_without_the_text(monkeypatch):
    def boom(argv, **kwargs):
        raise OSError("no such file or directory: tmux")

    monkeypatch.setattr(session_input.subprocess, "run", boom)
    with pytest.raises(RuntimeError) as exc:
        session_input.send_shell_line("claude_demo_sh", "export SECRET=topsecret123")
    assert "topsecret123" not in str(exc.value)


def test_a_logged_warning_on_timeout_does_not_contain_the_text(monkeypatch, caplog):
    def boom(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=5)

    monkeypatch.setattr(session_input.subprocess, "run", boom)
    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError):
            session_input.send_shell_line("claude_demo_sh", "export SECRET=topsecret123")
    assert "topsecret123" not in caplog.text
