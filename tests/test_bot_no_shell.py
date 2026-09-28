"""A Telegram message must never reach a shell.

Every tmux call in the bot was os.system(f"tmux ..."): a shell command line
with the session name -- and in one place the message itself -- pasted into
it. Three ways in were reproduced creating a file on the host:

  * the message text, inside '...': a single quote closes it;
  * repr() used as if it were shell quoting: a quote in the text makes repr
    switch to "...", inside which $(...) runs;
  * a session name lifted from the replied-to message with a `[^`]+` pattern.

The bot now runs tmux with an argument list. These tests push the same
strings through the real handler, against a real tmux session, and look for
the file.
"""

import asyncio
import os
import subprocess
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from claude_ctb.telegram import bot as bot_mod

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "tmux"], capture_output=True).returncode != 0,
    reason="needs tmux")


@pytest.fixture
def canary(tmp_path):
    return tmp_path / ("PWNED_" + uuid.uuid4().hex[:6])


@pytest.fixture
def session():
    name = "botshell_" + uuid.uuid4().hex[:6]
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "20",
                    "cat"], check=True)
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


@pytest.fixture
def bot(session, monkeypatch):
    cls = next(v for k, v in vars(bot_mod).items()
               if isinstance(v, type) and hasattr(v, "forward_to_claude"))
    b = cls.__new__(cls)
    b.config = SimpleNamespace(session_name=session, working_directory="/tmp")
    monkeypatch.setattr(b, "check_user_authorization", lambda uid: True, raising=False)
    monkeypatch.setattr(b, "validate_input", lambda text: (True, ""), raising=False)
    return b


def update_with(text, reply_to=None):
    msg = MagicMock()
    msg.text = text
    msg.reply_text = AsyncMock()
    if reply_to is None:
        msg.reply_to_message = None
    else:
        msg.reply_to_message = SimpleNamespace(
            text=reply_to, from_user=SimpleNamespace(is_bot=True))
    return SimpleNamespace(effective_user=SimpleNamespace(id=1), message=msg)


def pane(session):
    return subprocess.run(["tmux", "capture-pane", "-p", "-t", session],
                          capture_output=True, text=True).stdout


def test_a_quote_in_the_message_is_just_a_quote(bot, session, canary):
    text = "안녕'; touch %s; echo '" % canary
    asyncio.run(bot.forward_to_claude(update_with(text), None))
    assert not canary.exists(), "the message ran as a shell command"
    assert "touch" in pane(session), "the message never reached the session"


def test_command_substitution_in_the_message_does_not_run(bot, session, canary):
    # The quotes have to balance once the old code wrapped the text in '...':
    # an unbalanced line is a syntax error and runs nothing, which is how an
    # earlier version of this test passed against the vulnerable code.
    text = "it's $(touch %s) ok'" % canary
    asyncio.run(bot.forward_to_claude(update_with(text), None))
    assert not canary.exists()


def test_a_session_name_from_a_replied_message_is_not_a_command(bot, canary):
    """The name is pulled out of the replied-to bot message, which can echo
    whatever the user typed earlier."""
    evil = "claude_x;touch %s" % canary
    asyncio.run(bot.forward_to_claude(
        update_with("hello", reply_to="세션: `%s`" % evil), None))
    assert not canary.exists(), "a session name ran as a shell command"


def test_the_bot_has_no_shell_line_with_a_variable_in_it():
    """The property itself, over the whole file: no os.system, and no
    shell=True call built from an f-string. Checked on the source because a
    new call site added next month is exactly how this comes back."""
    import re
    src = open(bot_mod.__file__).read()
    assert "os.system(" not in src.replace("os.system(f\"tmux ...\")", "")
    for m in re.finditer(r"subprocess\.run\(", src):
        j, depth = m.end(), 1
        while depth:
            depth += {"(": 1, ")": -1}.get(src[j], 0)
            j += 1
        call = src[m.start():j]
        assert not ("shell=True" in call and re.search(r'f"[^"]*\{', call)), call[:120]
