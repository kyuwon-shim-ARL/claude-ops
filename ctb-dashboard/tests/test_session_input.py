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
    monkeypatch.setattr(session_input.time, "sleep", lambda s: None)
    # Default box: the text shows up after the paste and is gone after the
    # first Enter -- a session that behaves. Tests that need a stubborn box
    # replace this.
    def box(name):
        pasted = any(a[:2] == ["tmux", "paste-buffer"] for a in fake.calls)
        entered = any(a[-1:] == ["Enter"] and "send-keys" in a for a in fake.calls)
        return "" if (entered or not pasted) else fake.last_body_needle
    fake.last_body_needle = ""
    monkeypatch.setattr(session_input, "_box_text", box)
    real_load = session_input._tmux
    def spy(argv, stdin_text=None):
        if argv[:2] == ["tmux", "load-buffer"] and stdin_text:
            fake.last_body_needle = "".join(c for c in stdin_text if not c.isspace())
        return real_load(argv, stdin_text=stdin_text)
    monkeypatch.setattr(session_input, "_tmux", spy)
    return fake


def test_text_is_pasted_and_the_enter_sent_on_its_own(run):
    """Text and Enter in one send-keys arrive as one burst, which Claude Code
    reads as a paste -- and a paste's Enter does not submit. Measured on fresh
    sessions: 43 characters went through, 163 and up stayed in the box.

    This test used to require the single call, on the theory that splitting
    would submit a prompt in two pieces. A bracketed paste cannot be split by
    a later Enter; the single call is what was losing prompts.
    """
    assert session_input.send_prompt("claude_demo", "테스트 돌려줘") is True
    load, paste, enter = run.argvs[-3:]
    assert load[:2] == ["tmux", "load-buffer"]
    assert paste[:2] == ["tmux", "paste-buffer"] and "-p" in paste
    assert enter == ["tmux", "send-keys", "-t", "claude_demo", "Enter"]


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


def test_trailing_newline_is_still_one_prompt(run):
    """A stray trailing newline is noise, not intent to write multiple lines."""
    session_input.send_prompt("claude_demo", "한 줄입니다\n")
    enters = [a for a in run.argvs if a[-1:] == ["Enter"]]
    assert len(enters) == 1, "a trailing newline became a second submit"


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


def test_over_size_prompt_is_rejected(run):
    with pytest.raises(ValueError):
        session_input.send_prompt("claude_demo", "a" * (session_input.MAX_PROMPT_BYTES + 1))
    assert run.argvs == []


def test_over_size_prompt_is_rejected_by_bytes_not_chars(run):
    """A Korean string can be under the byte limit in char-count but over it
    in bytes (3 bytes/char) -- this is what would slip through a char-based
    cap."""
    char_count = session_input.MAX_PROMPT_BYTES // 2 + 100
    text = "가" * char_count
    assert char_count < session_input.MAX_PROMPT_BYTES
    assert len(text.encode("utf-8")) > session_input.MAX_PROMPT_BYTES
    with pytest.raises(ValueError):
        session_input.send_prompt("claude_demo", text)
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

    assert run.argvs[0] == ["tmux", "send-keys", "-t", "claude_demo", "-l", "!"]
    assert run.argvs[-1] == ["tmux", "send-keys", "-t", "claude_demo", "Enter"]
    assert all("!" not in " ".join(a) for a in run.argvs[1:]), \
        "the mode char went in twice"


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

    assert ["tmux", "send-keys", "-t", "claude_demo", "-l", "!"] not in run.argvs


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
        # the lead char and the recovery Escape succeed; the body paste does not
        r.returncode = 1 if argv[:2] == ["tmux", "paste-buffer"] else 0
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


# --- getting the text out of the box --------------------------------------

@pytest.fixture
def stubborn(monkeypatch):
    """A session whose box is scripted: a list of what each look returns."""
    calls = []

    def fake_tmux(argv, stdin_text=None):
        calls.append(argv)

    monkeypatch.setattr(session_input, "_tmux", fake_tmux)
    monkeypatch.setattr(session_input.time, "sleep", lambda s: None)

    def script(looks):
        seq = iter(looks)
        last = [looks[-1]]
        def box(name):
            try:
                last[0] = next(seq)
            except StopIteration:
                pass
            return last[0]
        monkeypatch.setattr(session_input, "_box_text", box)
        return calls
    return script


def enters(calls):
    return sum(1 for a in calls if a[-1:] == ["Enter"])


def test_enter_is_resent_while_our_text_is_still_in_the_box(stubborn):
    body = "긴 프롬프트의 끝부분입니다"
    ours = "".join(body.split())
    calls = stubborn([ours, ours, ""])    # landed; still there after Enter 1; gone after Enter 2
    assert session_input.send_prompt("claude_demo", body) is True
    assert enters(calls) == 2


def test_enter_is_not_resent_for_somebody_elses_text(stubborn):
    """After a submit Claude Code can put a dim suggestion in the box. The
    box is non-empty, but it is not ours, and an Enter on it is not ours to
    send."""
    body = "보낸 문장"
    calls = stubborn(["".join(body.split()), "결과나오면알려줘"])
    assert session_input.send_prompt("claude_demo", body) is True
    assert enters(calls) == 1


def test_a_collapsed_paste_counts_as_ours(stubborn):
    """A long paste is shown as '[Pasted text #1 +3 lines]' -- the words are
    not on screen, and that is exactly the case that was getting stuck."""
    calls = stubborn(["[Pastedtext#1+3lines]", "[Pastedtext#1+3lines]", ""])
    assert session_input.send_prompt("claude_demo", "x" * 2000) is True
    assert enters(calls) == 2


def test_it_gives_up_and_says_so(stubborn):
    body = "끝내 안 나가는 글"
    ours = "".join(body.split())
    calls = stubborn([ours])
    assert session_input.send_prompt("claude_demo", body) is False
    assert enters(calls) == session_input._ENTER_TRIES


def test_the_enter_waits_for_the_text_to_land(stubborn):
    """An Enter that arrives before the paste has been drawn is the same burst
    as before."""
    body = "도착을 기다리는 글"
    ours = "".join(body.split())
    order = []
    calls = stubborn(["", "", ours, ""])
    real = session_input._box_text
    def watching(name):
        order.append(("look", enters(calls)))
        return real(name)
    session_input._box_text = watching
    session_input.send_prompt("claude_demo", body)
    first_enter_at = next(i for i, (_, e) in enumerate(order) if e >= 1)
    assert first_enter_at >= 3, "Enter went before the text was seen in the box"
