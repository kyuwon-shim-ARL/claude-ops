"""A session sitting on a chooser is waiting for you, not idle.

Eleven live sessions were parked on a blocking prompt -- ten of them on the
"Do you trust this folder?" question a session opens with -- and the dashboard
reported every one of them IDLE. The board already draws the two apart
(입력대기 amber vs 유휴 grey) and the prompt endpoint already refuses to type
free text into a chooser; what was missing was noticing.

The wordings were guesses. The footer Claude Code draws under a chooser is
not: what identifies it is its form, a line made only of "<key> to <verb>"
segments. These tests are mostly about the lines that merely mention a key and
must NOT count -- there are far more of those on a real screen than there are
choosers.
"""

import pytest

from ctb_dashboard.state_detector import SessionState, SessionStateAnalyzer

A = SessionStateAnalyzer


def screen(*tail):
    """A plausible pane: some output, then the lines under test at the foot."""
    body = ["> ask the model something", "", "⏺ Read(src/thing.py)",
            "  ⎿  Read 40 lines (ctrl+o to expand)", ""]
    return "\n".join(body + list(tail))


# --- the footers that mean "answer me" --------------------------------------

@pytest.mark.parametrize("line", [
    "Enter to confirm · Esc to cancel",
    "Enter to select · ↑/↓ to navigate · Esc to cancel",
    "  Enter to select · ↑/↓ to navigate · Esc to cancel  ",
    "Enter to confirm · Tab to edit · Esc to cancel",
    "space to select · enter to confirm · esc to cancel",
    # Found by scanning 161,332 lines of real scrollback from every pane on
    # the machine -- a third live form, and the one that justifies accepting a
    # bare letter as a key.
    "Enter to review · d to discard · Esc to close",
])
def test_a_chooser_footer_is_a_request_for_input(line):
    assert A._is_key_hint_footer(line), line


def test_the_folder_trust_prompt_is_no_longer_idle():
    """The exact screen ten sessions were stuck on, reported idle."""
    content = screen(
        "╭──────────────────────────────────────────────╮",
        "│ Do you trust the files in this folder?       │",
        "│                                              │",
        "│  ❯ No, exit                                  │",
        "│    Yes, I trust this folder                  │",
        "╰──────────────────────────────────────────────╯",
        " Enter to confirm · Esc to cancel",
    )
    assert A()._detect_input_waiting(content)


def test_a_numbered_menu_is_a_request_for_input():
    content = screen(
        "  4. Something else",
        "  5. Explain this",
        "  6. Chat about this",
        "Enter to select · ↑/↓ to navigate · Esc to cancel",
    )
    assert A()._detect_input_waiting(content)


# --- the lines that merely mention a key ------------------------------------

@pytest.mark.parametrize("line", [
    # The permission-mode footer: on screen in EVERY working session on this
    # machine, sixty-seven panes' worth. The single most dangerous match.
    "⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents",
    "⏵⏵ bypass permissions on · 1 shell · ← 8 agents",
    "⏵⏵ bypass permissions on (shift+tab to cycle) · PR #45 · ← 8 agents",
    # Collapsed tool output, everywhere.
    "… +2 lines (ctrl+o to expand)",
    "Read 1 file (ctrl+o to expand)",
    # What Claude offers while it is generating -- the opposite of waiting.
    "esc to interrupt · ctrl+t to hide",
    # A single hint inside a sentence, including one Claude itself wrote while
    # discussing this very feature.
    "지난번에 피드백 초안 화면(Esc to close) 때문에 처리를 넣었는데",
    "Esc to close",
    "Press Enter to continue reading the manual",
    # A table quoting the footer rather than being it.
    "│ Enter to confirm · Esc to cancel │ Enter │ Esc는 종료 취소 │",
    # The one that matters: text the user typed or pasted into the input box,
    # which Claude Code draws as a bordered box. An earlier version stripped
    # the border before matching, which turned a draft's continuation line
    # into a perfect footer.
    "│   Enter to confirm · Esc to cancel                        │",
    "│ > Enter to confirm · Esc to cancel                        │",
    "┃   Enter to confirm · Esc to cancel                        ┃",
    # Another program's chooser, in Korean: not Claude Code's form.
    "↑/↓ 이동 · x 완료 · d 그만둠 · r 재판정",
    "",
    "·",
])
def test_a_line_that_merely_mentions_a_key_is_not_a_chooser(line):
    assert not A._is_key_hint_footer(line), line


def test_an_ordinary_working_pane_is_not_waiting():
    content = screen(
        "✻ Sautéing… (12s · ↓ 1.2k tokens · esc to interrupt)",
        "────────────────────────────────────────────",
        "  branch:main",
        "  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents",
    )
    assert not A()._detect_input_waiting(content)


def test_an_idle_pane_is_still_idle():
    content = screen(
        "⏺ Done.",
        "────────────────────────────────────────────",
        "  ⏵⏵ bypass permissions on · ← 8 agents",
    )
    assert not A()._detect_input_waiting(content)


def test_the_matcher_fires_on_nothing_else_in_a_screenful_of_real_output():
    """The corpus this was built from: every line that is not a chooser
    footer, including the ones that look most like one."""
    noise = [
        "⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents",
        "… +24 lines (ctrl+o to expand)",
        "⏺ Bash(git status --short)",
        "  ⎿  Running…",
        "✻ Pondering… (31s · ↑ 2.1k tokens · esc to interrupt)",
        "[OMC#5.1.0L] | Model: Opus 5 | 5h:[###-----]38%(2h38m)",
        "  branch:main | !1 ?2 ⇡2",
        "> 정리해줘",
        "Total cost:            $0.42 · Total duration: 2m 13s",
    ]
    fired = [line for line in noise if A._is_key_hint_footer(line)]
    assert fired == [], fired


# --- shape rules -------------------------------------------------------------

def test_a_footer_pasted_into_the_input_box_is_not_a_chooser():
    """Reproduced by the adversarial pass: a multiline draft whose
    continuation line happens to be the footer text. The session is not
    blocked -- and calling it blocked also makes the prompt endpoint refuse
    to type into it."""
    content = "\n".join([
        "> 이 문구 처리 좀 해줘:",
        "╭────────────────────────────────────────────────────────────╮",
        "│ > 아래 푸터를 감지해야 해                                  │",
        "│   Enter to confirm · Esc to cancel                         │",
        "╰────────────────────────────────────────────────────────────╯",
    ])
    assert not A()._detect_input_waiting(content)


def test_a_borderless_draft_quoting_a_footer_is_not_a_chooser():
    """Claude Code's input box is sometimes drawn with no side borders, so
    rejecting vertical bars is not enough on its own. Five non-blank lines
    off the bottom, and the session is blocked on nothing."""
    content = "\n".join([
        "────────────────────────────────────────────────",
        "❯ Please explain this footer:",
        "  Enter to confirm · Esc to cancel",
        "────────────────────────────────────────────────",
        "  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents",
    ])
    assert not A()._detect_input_waiting(content)


def test_a_footer_with_the_statusline_below_it_is_not_a_chooser():
    """Same shape, arrived at from the other direction: anything drawn after
    the footer means the pane has moved on from it."""
    content = "\n".join([
        "Enter to confirm · Esc to cancel",
        "────────────────────────────────────────────────",
        "  branch:main",
        "  ⏵⏵ bypass permissions on · ← 8 agents",
    ])
    assert not A()._detect_input_waiting(content)


def test_a_tab_between_the_key_and_the_verb_does_not_crash():
    """The verb used to be taken by splitting on a literal ' to ' while the
    pattern accepted any whitespace, so a tab raised IndexError out through
    get_state -- a crash in the poll, not a misread."""
    assert A._is_key_hint_footer("Enter\tto\tconfirm · Esc to cancel")
    assert not A._is_key_hint_footer("esc\tto\tinterrupt · ctrl+t to hide")


def test_one_segment_alone_is_not_enough():
    """A chooser names the accept key and the way out. One segment is how a
    sentence quoting a hint would get in."""
    assert not A._is_key_hint_footer("Enter to confirm")


def test_a_footer_buried_in_scrollback_does_not_count():
    """An answered chooser leaves its footer in the transcript. Only a footer
    on the pane's last line is a live question -- the two non-chooser matches
    found in a hundred and sixty thousand lines of real scrollback were forty
    and seventy-nine lines up, exactly like this."""
    old = ["Enter to confirm · Esc to cancel"] + ["ordinary output"] * 12
    assert not A()._detect_input_waiting("\n".join(old))


def test_working_still_outranks_a_footer():
    """If Claude is generating, a footer left on screen is not a question --
    the working guard runs first and must keep running first."""
    content = "\n".join([
        "Enter to confirm · Esc to cancel",
        "✻ Thinking… (8s · esc to interrupt)",
    ])
    assert not A()._detect_input_waiting(content)


def test_the_state_comes_out_as_waiting_not_idle():
    """End of the chain: what the board is actually handed."""
    analyzer = A()
    content = screen(
        "  ❯ No, exit",
        "    Yes, I trust this folder",
        " Enter to confirm · Esc to cancel",
    )
    analyzer.get_screen_content = lambda name, use_cache=True: content
    assert analyzer.get_state("s", None, False) == SessionState.WAITING_INPUT
