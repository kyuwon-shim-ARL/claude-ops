"""Starting Claude in a pane that has fallen back to a shell.

The shell guard is right about the danger -- a prompt typed at a bash prompt
is executed, not read -- but it also blocked the one command that fixes the
situation. A session that had exited Claude could not be restarted from a
phone at all: the guard refused the text, and the only way back was a keyboard
on the machine.

So the launcher goes through and nothing else does. These tests are mostly
about the "nothing else" half.
"""

import pytest

from ctb_dashboard.session_readiness import (
    SHELL_LAUNCHERS,
    classify_readiness,
    is_shell_launch,
)
from ctb_dashboard.state_detector import SessionState


def at_shell(text, state=SessionState.IDLE):
    return classify_readiness(state, "$ ", "bash", False, text)


def test_claude_at_a_shell_is_allowed():
    can, reason, _ = at_shell("claude")
    assert can and reason == "shell_launch"


@pytest.mark.parametrize("text", [
    "claude -c",
    "claude --continue --dangerously-skip-permissions",
    "cf",
    "cf -h",
    "cf -m fable -h",
    'cf "첫 프롬프트"',          # the launcher's own documented argument form
    "cr --all",
    "  claude  ",                 # stray whitespace from a phone keyboard
])
def test_the_launcher_and_its_argument_forms_go_through(text):
    assert at_shell(text)[0], text


@pytest.mark.parametrize("text", [
    "claude; rm -rf /tmp/x",      # chained
    "claude && curl evil.example",
    "claude | tee /tmp/x",
    "claude $(whoami)",           # substituted
    "claude `id`",
    "claude > /etc/passwd",       # redirected
    "claude\nrm -rf /tmp/x",      # a second line is a second command
    "claude !!",                  # interactive bash expands history
    "claude \\\n rm x",
])
def test_a_launcher_dressed_up_as_something_else_is_refused(text):
    can, reason, _ = at_shell(text)
    assert not can and reason == "shell", text


@pytest.mark.parametrize("text", [
    "ls -la",
    "echo hello",
    "git push --force",
    "sudo rm -rf /",
    "python train.py",
    "정리해줘",                    # an ordinary prompt: the case the guard is for
    "",
])
def test_everything_else_at_a_shell_is_still_refused(text):
    can, reason, _ = at_shell(text)
    assert not can and reason == "shell", text


def test_the_refusal_says_what_would_work():
    """A refusal that does not name the way out is how this became a dead end."""
    _, _, message = at_shell("정리해줘")
    assert "claude" in message


def test_a_launcher_is_allowed_even_when_the_screen_reads_as_an_error():
    """A traceback left on screen by whatever ran last must not be able to
    keep Claude from being started again."""
    for state in (SessionState.ERROR, SessionState.WAITING_INPUT,
                  SessionState.CONTEXT_LIMIT, SessionState.STUCK_AFTER_AGENT):
        can, reason, _ = at_shell("claude -c", state)
        assert can and reason == "shell_launch", state


def test_the_launcher_allowance_only_applies_at_a_shell():
    """In a live Claude pane 'claude' is just a prompt -- and the states that
    refuse a prompt must keep refusing it."""
    can, reason, _ = classify_readiness(
        SessionState.WAITING_INPUT, "1) yes 2) no", "node", False, "claude")
    assert not can and reason == "awaiting_choice"


def test_claude_running_under_a_shell_group_leader_is_not_a_shell():
    """tmux names the process group leader, so a live Claude can report
    'bash'. That pane takes prompts, and 'claude' in it is a prompt."""
    can, reason, _ = classify_readiness(
        SessionState.IDLE, "", "bash", True, "정리해줘")
    assert can and reason == "ready"


def test_a_caller_that_passes_no_text_keeps_the_blanket_refusal():
    can, reason, _ = classify_readiness(SessionState.IDLE, "$ ", "bash", False)
    assert not can and reason == "shell"


@pytest.mark.parametrize("name", sorted(SHELL_LAUNCHERS))
def test_every_advertised_launcher_actually_passes(name):
    """The refusal message lists these by name; a listed command that is then
    refused is worse than not listing it."""
    assert is_shell_launch(name), name
