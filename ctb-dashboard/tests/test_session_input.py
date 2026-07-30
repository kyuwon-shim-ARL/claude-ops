"""Sending text into a live Claude session via tmux.

The tmux invocations are the whole contract here, so they are asserted
argv-by-argv rather than mocked loosely: getting them subtly wrong (splitting
the Enter, dropping bracketed paste) is exactly the failure mode that silently
submits half a prompt into someone's session.
"""

import pytest

from ctb_dashboard import session_input


class FakeRun:
    """Records tmux argv and replays canned return codes."""

    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)

        class R:
            pass

        r = R()
        r.returncode = self.returncode
        r.stdout = ""
        r.stderr = ""
        return r

    @property
    def argvs(self):
        return self.calls


@pytest.fixture
def run(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(session_input.subprocess, "run", fake)
    return fake


def test_single_line_matches_the_bot_convention(run):
    """claude_ctb/session_manager.py:354 sends the text and Enter in ONE call.

    Splitting them lets the session process the text before Enter arrives,
    which is how prompts end up submitted in two pieces.
    """
    session_input.send_prompt("claude_demo", "테스트 돌려줘")

    assert run.argvs == [
        ["tmux", "send-keys", "-t", "claude_demo", "테스트 돌려줘", "Enter"]
    ]


def test_multiline_uses_bracketed_paste_then_a_separate_enter(run):
    """A raw newline in send-keys is an Enter keystroke -- it would submit early.

    load-buffer + paste-buffer -p wraps the text in bracketed paste so the TUI
    inserts it as multi-line text, and only then do we submit.
    """
    session_input.send_prompt("claude_demo", "첫 줄\n둘째 줄")

    assert len(run.argvs) == 3
    load, paste, enter = run.argvs
    assert load[:2] == ["tmux", "load-buffer"]
    assert load[-1] == "-", "text must arrive on stdin, not as an argv"
    assert paste[:2] == ["tmux", "paste-buffer"]
    assert "-p" in paste, "bracketed paste flag missing -- TUI will submit early"
    assert "-d" in paste, "buffer should be deleted after pasting"
    assert "-t" in paste and "claude_demo" in paste
    assert enter == ["tmux", "send-keys", "-t", "claude_demo", "Enter"]


def test_crlf_is_treated_as_multiline(run):
    session_input.send_prompt("claude_demo", "a\r\nb")
    assert run.argvs[0][:2] == ["tmux", "load-buffer"]


def test_trailing_newline_alone_does_not_trigger_paste(run):
    """A stray trailing newline is noise, not intent to write multiple lines."""
    session_input.send_prompt("claude_demo", "한 줄입니다\n")
    assert run.argvs == [
        ["tmux", "send-keys", "-t", "claude_demo", "한 줄입니다", "Enter"]
    ]


def test_interrupt_sends_escape(run):
    session_input.send_interrupt("claude_demo")
    assert run.argvs == [["tmux", "send-keys", "-t", "claude_demo", "Escape"]]


def test_session_exists_uses_has_session(run):
    assert session_input.session_exists("claude_demo") is True
    assert run.argvs == [["tmux", "has-session", "-t", "claude_demo"]]


def test_session_exists_false_on_nonzero(monkeypatch):
    monkeypatch.setattr(session_input.subprocess, "run", FakeRun(returncode=1))
    assert session_input.session_exists("nope") is False


def test_empty_prompt_is_rejected(run):
    with pytest.raises(ValueError):
        session_input.send_prompt("claude_demo", "   ")
    assert run.argvs == [], "nothing should reach tmux"


def test_over_long_prompt_is_rejected(run):
    with pytest.raises(ValueError):
        session_input.send_prompt("claude_demo", "a" * (session_input.MAX_PROMPT_LENGTH + 1))
    assert run.argvs == []


def test_tmux_failure_raises(monkeypatch):
    monkeypatch.setattr(session_input.subprocess, "run", FakeRun(returncode=1))
    with pytest.raises(RuntimeError):
        session_input.send_prompt("claude_demo", "hello")
