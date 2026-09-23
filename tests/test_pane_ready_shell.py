"""Is a Claude pane ready to be typed into?

`~/bin/claude-session-helpers.sh:claude_pane_ready()` is the gate everything
`cf` and `cr` do runs through, and it had been answering "no" for every
session on the machine since 2026-09-17. The empty input box is drawn as `❯`
followed by U+00A0, a NO-BREAK SPACE; the parser stripped ASCII space and tab
only, so an empty box always read as one with text in it. `cf` then spent
twenty seconds failing to find idle, and the "three consecutive ready"
gate before delivering a handoff could never pass at all -- 29 consecutive
`ABORT ready-timeout(30s)` entries in /tmp/cf-inject.log.

Driven against real tmux panes holding captured screens, because that is what
the function reads. Half of these are the other direction: a detector that
says "ready" too easily types into a chooser, and that is worse than one that
waits.
"""

import os
import subprocess
import time
import uuid

import pytest

HELPERS = os.path.expanduser("~/bin/claude-session-helpers.sh")
NBSP = " "
RULE = "─" * 80

pytestmark = pytest.mark.skipif(
    not os.path.exists(HELPERS) or not subprocess.run(
        ["which", "tmux"], capture_output=True).returncode == 0,
    reason="needs tmux and ~/bin/claude-session-helpers.sh")


def pane_showing(text, tmp_path):
    """A real tmux pane whose capture-pane returns `text`.

    The screen is printed from a file and the pane then parked, rather than
    typed in with send-keys: send-keys goes through the terminal's own input
    handling, which rewraps, re-echoes and can drop the pad character that is
    the whole point of these fixtures.
    """
    name = "ready_test_%s" % uuid.uuid4().hex[:8]
    fixture = tmp_path / (name + ".txt")
    fixture.write_text(text, encoding="utf-8")
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-x", "100", "-y", "24",
         "sh", "-c", "cat %s; sleep 600" % fixture], check=True)
    for _ in range(50):
        shown = subprocess.run(["tmux", "capture-pane", "-t", name, "-p"],
                               capture_output=True, text=True).stdout
        if text.split("\n")[0][:20] in shown:
            break
        time.sleep(0.05)
    return name


def kill(name):
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


def ready(pane):
    r = subprocess.run(
        ["bash", "-c", 'source "$1" && claude_pane_ready "$2"', "_", HELPERS, pane],
        capture_output=True, text=True)
    return r.returncode == 0


def screen(*body):
    return "\n".join(body)


IDLE = screen("⏺ Done.", "", RULE, "❯" + NBSP, RULE,
              "  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents")


@pytest.fixture
def pane(tmp_path):
    made = []

    def make(text):
        name = pane_showing(text, tmp_path)
        made.append(name)
        return name

    yield make
    for name in made:
        kill(name)


# --- the pane that must read as ready ---------------------------------------

def test_an_idle_pane_is_ready(pane):
    """`❯` + U+00A0. Every session on the machine looked like this and every
    one of them was reported not-ready."""
    assert ready(pane(IDLE))


# --- and everything that must not --------------------------------------------

def test_a_queued_prompt_is_not_ready(pane):
    assert not ready(pane(screen(RULE, "❯ 각 검정을 파이썬 코드로 보여줘", RULE)))


def test_text_after_the_pad_character_is_not_ready(pane):
    """Stripping U+00A0 must not swallow what follows it."""
    assert not ready(pane(screen(RULE, "❯" + NBSP + "hello", RULE)))


def test_a_pane_mid_turn_is_not_ready(pane):
    assert not ready(pane(screen(
        "✽ Pondering… (12s · ↑ 2.1k tokens · esc to interrupt)",
        RULE, "❯" + NBSP, RULE)))


@pytest.mark.parametrize("footer", [
    "Enter to confirm · Esc to cancel",
    "Enter to select · ↑/↓ to navigate · Esc to cancel",
    "Enter to review · d to discard · Esc to close",
])
def test_a_chooser_is_not_ready_even_with_an_empty_box_above_it(pane, footer):
    """The shape the chooser guard is the only defence against.

    On today's screens a chooser is refused for a different reason -- it
    replaces the composer, so the box parse finds nothing and gives up. Take
    the guard out and not one live session changes answer. It is kept for
    what happens when the two are on screen together: the box reads empty,
    everything else says ready, and /exit goes in as a menu selection rather
    than a command. That is not a stall, it is a wrong answer chosen on the
    user's behalf, which is why this one is guarded without a live case.

    The busy patterns cannot cover it: they are case-sensitive and look for
    `esc to cancel`, and every dialog says `Esc to cancel`.
    """
    assert not ready(pane(screen(
        "  ❯ No, exit", "    Yes, I trust this folder",
        RULE, "❯" + NBSP, RULE, footer)))


@pytest.mark.parametrize("line", [
    # The start-up banner: "…Now defaults to high effort · …". Eighteen of
    # these in the corpus, and a looser rule matched every one.
    "Welcome back ARLrocks! Opus 4.8 is here! Now defaults to high effort · try it",
    # Prose quoting a footer, which is most of what a transcript about this
    # feature contains.
    "그 화면은 Enter to review · d to discard · Esc to close 입니다. 그런데",
    # A table row, not a footer.
    "│ Enter to confirm · Esc to cancel │ Enter │ Esc는 종료 취소 │",
])
def test_a_line_that_merely_mentions_keys_does_not_block(pane, line):
    """Every segment has to be a key hint. A rule that only wants a middle dot
    and the word `to` matched eleven distinct lines in 161,332 of real
    scrollback, six of them not choosers at all.

    The line goes LAST, where the guard actually looks -- put above the box it
    is never examined and the test passes whatever the rule says.
    """
    assert ready(pane(screen(RULE, "❯" + NBSP, RULE, line)))


def test_a_chooser_that_replaced_the_composer_is_not_ready(pane):
    """What the ten folder-trust sessions actually look like."""
    assert not ready(pane(screen(
        "  ❯ No, exit", "    Yes, I trust this folder", "",
        "Enter to confirm · Esc to cancel")))


def test_a_pane_with_no_input_box_is_not_ready(pane):
    assert not ready(pane(screen("just some output", "and more")))


def test_a_pane_that_cannot_be_captured_is_not_ready():
    assert not ready("no_such_pane_%s" % uuid.uuid4().hex[:8])


def test_a_shell_prompt_is_not_ready(pane):
    """No Claude, nothing to be ready."""
    assert not ready(pane("[kyuwon@arl project]$ "))


def test_a_multiline_draft_is_not_ready(pane):
    assert not ready(pane(screen(
        RULE, "❯ first line of a draft", "  second line still being typed", RULE)))


def test_an_old_chooser_footer_in_the_scrollback_does_not_block(pane):
    """Only the last line counts: an answered chooser leaves its footer in the
    transcript, and a permanent veto there is the same bug in the mirror."""
    assert ready(pane(screen(
        "Enter to confirm · Esc to cancel",
        "  ⎿  Yes, I trust this folder",
        "⏺ Done.", "", RULE, "❯" + NBSP, RULE)))


def test_a_queued_character_made_of_the_same_bytes_is_not_erased(pane):
    """The pad character cannot be added to the same bracket class as `❯`.

    Under LC_ALL=C awk's brackets are a set of BYTES, so `[❯ \\t\\302\\240]`
    is the set {E2,9D,AF,C2,A0}, and any other character built from those
    bytes is taken apart and deleted. `¯` is C2 AF -- one byte from the pad,
    one from the prompt marker -- so a composer holding it read as empty and
    /exit would have gone in on top of it. Whole sequences, removed one at a
    time.
    """
    name = pane(screen(RULE, "❯" + NBSP + "¯", RULE))
    r = subprocess.run(
        ["bash", "-c",
         'export LC_ALL=C; source "$1" && claude_pane_ready "$2"', "_", HELPERS, name],
        capture_output=True, text=True)
    assert r.returncode != 0, "a queued ¯ was erased and the box read as empty"


@pytest.mark.parametrize("line", [
    "Ready to ship · all checks passed",
    "Welcome to project · main",
    "shift+tab to cycle · model opus",
])
def test_ordinary_text_with_a_middle_dot_does_not_read_as_a_chooser(pane, line):
    """A `[a-z]` with no left boundary matches the last letter of any word,
    which turned these three ordinary bottom lines into blocking choosers."""
    assert ready(pane(screen(RULE, "❯" + NBSP, RULE, line)))
