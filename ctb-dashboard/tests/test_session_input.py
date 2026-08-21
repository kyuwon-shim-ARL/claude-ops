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


def test_bash_mode_char_is_sent_as_its_own_keystroke(run):
    """'!cf' in one send-keys arrives as one 4-byte read, which a chunk-reading
    TUI treats as a paste: the '!' lands as literal text and the bash box never
    opens. Alone it is a keypress, and the mode switches."""
    session_input.send_prompt("claude_demo", "!cf")

    assert run.argvs == [
        ["tmux", "send-keys", "-t", "claude_demo", "-l", "!"],
        ["tmux", "send-keys", "-t", "claude_demo", "cf", "Enter"],
    ]


def test_memory_mode_char_too(run):
    session_input.send_prompt("claude_demo", "#기억해둘 것")

    assert run.argvs[0] == ["tmux", "send-keys", "-t", "claude_demo", "-l", "#"]


def test_mode_char_before_a_multiline_body(run):
    session_input.send_prompt("claude_demo", "!ls\nsecond")

    assert run.argvs[0] == ["tmux", "send-keys", "-t", "claude_demo", "-l", "!"]
    assert run.argvs[1][:3] == ["tmux", "load-buffer", "-b"]
    assert run.argvs[-1] == ["tmux", "send-keys", "-t", "claude_demo", "Enter"]


def test_a_bare_mode_char_is_refused(run):
    """Nothing to run: it would leave the session sitting in an empty bash box."""
    with pytest.raises(ValueError):
        session_input.send_prompt("claude_demo", "!")
    assert run.argvs == []


def test_a_mode_char_mid_prompt_is_ordinary_text(run):
    session_input.send_prompt("claude_demo", "run a!b")

    assert run.argvs == [
        ["tmux", "send-keys", "-t", "claude_demo", "run a!b", "Enter"]
    ]


def test_a_failed_body_send_closes_the_box_it_opened(monkeypatch):
    """The mode char lands first. If the body send then fails, the session is
    left in an empty shell box -- and the NEXT prompt, ordinary prose with no
    '!', would be typed into it and executed as a shell command."""
    calls = []

    def flaky(argv, **kwargs):
        calls.append(argv)

        class R:
            pass

        r = R()
        # the lead char and the recovery Escape succeed; the body send does not
        r.returncode = 1 if argv[3:5] == ["claude_demo", "cf"] else 0
        r.stdout = r.stderr = ""
        return r

    monkeypatch.setattr(session_input.subprocess, "run", flaky)

    with pytest.raises(RuntimeError):
        session_input.send_prompt("claude_demo", "!cf")

    assert calls[0] == ["tmux", "send-keys", "-t", "claude_demo", "-l", "!"]
    assert calls[-1] == ["tmux", "send-keys", "-t", "claude_demo", "Escape"], \
        "the shell box the send opened must not be left open"


def test_no_box_no_escape(run):
    """A plain prompt that fails opened nothing, so nothing needs closing."""
    run.returncode = 1
    with pytest.raises(RuntimeError):
        session_input.send_prompt("claude_demo", "테스트 돌려줘")
    assert not any(a[-1] == "Escape" for a in run.argvs)


def test_a_prompt_starting_with_a_dash_goes_through_the_buffer(run):
    """tmux reads a leading '-' as a flag and refuses the send outright
    ("command send-keys: invalid flag --"), and send-keys has no '--'
    terminator. The paste path carries the text as data instead."""
    session_input.send_prompt("claude_demo", "--force 옵션 붙여서 다시")

    assert run.argvs[0][:3] == ["tmux", "load-buffer", "-b"]
    assert run.argvs[-1] == ["tmux", "send-keys", "-t", "claude_demo", "Enter"]
    assert not any(a[4:5] == ["--force 옵션 붙여서 다시"] for a in run.argvs), \
        "the text must never reach tmux as an argv position that parses flags"
