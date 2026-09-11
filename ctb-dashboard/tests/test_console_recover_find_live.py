"""Getting back to live, finding a way to the end, and searching the output.

Three things a reader on a phone kept losing: a pane frozen by a half-made
selection with no obvious way out, a console reopened hundreds of lines up,
and no way to find anything in what is on screen. Driven against the shipped
page in a real browser, because all three are DOM behaviour.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"
PILL = "#ctb-console button[aria-label='맨 아래로 가기']"
FIND = "#con-find"
FIND_INPUT = "#con-find-input"


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def frozen(page):
    """The amber "갱신 정지됨" badge — the console's own word for paused."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#ctb-console div')]"
        "  .some(e => e.textContent.includes('갱신 정지됨')"
        "          && e.style.display !== 'none' && e.style.position === 'absolute')")


def scroll_up(page, to=0):
    page.eval_on_selector("#ctb-console pre", "(el, to) => { el.scrollTop = to; }", to)
    page.wait_for_timeout(120)


def logs(page):
    """How many times the pane has been asked for. One recovery, one ask."""
    return len([u for u in page.ctb_requests if u.endswith("/log")])


def at_bottom(page):
    return page.eval_on_selector(
        "#ctb-console pre",
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 8")


# --- Enter gets you back to work -------------------------------------------

def test_enter_thaws_a_frozen_pane_and_returns_the_caret(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")      # starts a selection
    assert frozen(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_function("() => !document.querySelector('#ctb-console pre')"
                            ".style.boxShadow.includes('245,158,11')")
    assert not frozen(board)
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_enter_brings_the_view_back_to_the_bottom(board):
    open_console(board)
    scroll_up(board)
    assert not at_bottom(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_function(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        return el.scrollHeight - el.scrollTop - el.clientHeight < 8; }")


def test_enter_in_the_prompt_box_still_sends_a_bare_newline(board):
    """The one Enter that must not be stolen.

    An empty Enter sent to tmux is how a Claude Code prompt gets confirmed.
    Freezing the pane says nothing about whether the session is waiting for
    that key.
    """
    open_console(board)
    board.click("#ctb-console [data-line='3']")      # freeze it, to be sure
    board.click("#ctb-console textarea")
    board.keyboard.press("Enter")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Enter"]
    # And it stayed a send: the pane is still frozen, not quietly thawed.
    assert frozen(board)


def test_enter_on_a_button_is_the_press_not_a_recovery(board):
    open_console(board)
    scroll_up(board)
    board.focus("#ctb-console button[aria-label='콘솔 닫기']")
    board.keyboard.press("Enter")
    board.wait_for_selector(CONSOLE, state="hidden")


# --- the jump-to-end pill ---------------------------------------------------

def test_the_pill_is_hidden_at_the_bottom(board):
    open_console(board)
    assert board.eval_on_selector_all(PILL, "els => els.length") == 1
    assert board.is_hidden(PILL)


def test_the_pill_appears_far_from_the_end_and_takes_you_there(board):
    open_console(board)
    scroll_up(board)
    board.wait_for_selector(PILL, state="visible")
    board.click(PILL)
    board.wait_for_function(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        return el.scrollHeight - el.scrollTop - el.clientHeight < 8; }")
    board.wait_for_selector(PILL, state="hidden")


def test_the_pill_thaws_a_frozen_pane_too(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")
    scroll_up(board)
    board.wait_for_selector(PILL, state="visible")
    board.click(PILL)
    assert not frozen(board)


# --- find in the output -----------------------------------------------------

def open_find(board):
    board.keyboard.press("Control+Shift+f")
    board.wait_for_selector(FIND, state="visible")


def count(board):
    return board.eval_on_selector(FIND + " [aria-live]", "e => e.textContent")


def test_the_chord_opens_the_find_bar_and_freezes_the_pane(board):
    open_console(board)
    open_find(board)
    assert frozen(board)
    assert board.evaluate("document.activeElement.id") == "con-find-input"


def test_the_session_palette_keeps_plain_ctrl_f(board):
    open_console(board)
    board.keyboard.press("Control+f")
    board.wait_for_selector("#con-find", state="hidden")
    assert board.evaluate(
        "() => [...document.querySelectorAll('[role=option],[data-search-session]')]"
        ".length > 0")


def test_typing_highlights_every_match_and_counts_them(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 3
    assert count(board) == "1/3"


def test_enter_steps_through_the_matches_and_shift_enter_goes_back(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.keyboard.press("Enter")
    assert count(board) == "2/3"
    board.keyboard.press("Enter")
    assert count(board) == "3/3"
    board.keyboard.press("Enter")          # wraps
    assert count(board) == "1/3"
    board.keyboard.press("Shift+Enter")
    assert count(board) == "3/3"


def test_the_current_match_is_scrolled_into_view(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")          # first hit is on line 7, far up
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    assert board.evaluate(
        "() => { const m = document.querySelector('#ctb-console mark[data-find-hit]');"
        "        const p = document.querySelector('#ctb-console pre');"
        "        const a = m.getBoundingClientRect(), b = p.getBoundingClientRect();"
        "        return a.top >= b.top - 2 && a.bottom <= b.bottom + 2; }")


def test_a_word_that_is_not_there_says_so(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("zzzzz")
    assert count(board) == "없음"
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0


def test_matches_survive_a_link_in_the_line(board):
    """A match that crosses a linkified URL must still highlight.

    Range.surroundContents refuses a range that only half-contains an
    element, and the naive version silently dropped those hits.
    """
    open_console(board)
    board.evaluate(
        "() => window.ctbConsole._renderTail('see http://x.test/a now')")
    # "a now" starts inside the <a> and ends outside it.
    assert board.eval_on_selector_all("#ctb-console [data-line='0'] a",
                                      "els => els.length") == 1
    open_find(board)
    board.keyboard.type("a now")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 1
    assert board.eval_on_selector("#ctb-console [data-line='0']",
                                  "e => e.textContent") == "see http://x.test/a now"


def test_escape_closes_find_and_leaves_the_console_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Escape")
    board.wait_for_selector(FIND, state="hidden")
    assert board.is_visible(CONSOLE)
    assert not frozen(board)
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_closing_find_leaves_no_highlights_behind(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    board.keyboard.press("Escape")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0
    assert board.eval_on_selector("#ctb-console [data-line='7']",
                                  "e => e.textContent") == "line 007 needle here"


def test_terminal_keys_stand_down_while_the_find_bar_is_open(board):
    """Ctrl+U over the console is a kill-line for tmux. Not while searching.

    Guarded twice on purpose: the bar swallows its own keys, and keysTaken()
    stands the console's shortcuts down for anything that starts elsewhere in
    the sheet while the bar is up.
    """
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.keyboard.press("Control+u")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Control+u")
    board.wait_for_timeout(300)
    assert not any("/key" in u for u in board.ctb_requests)


def test_enter_recovery_stands_down_while_the_find_bar_is_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Enter")
    assert board.is_visible(FIND)


def test_switching_session_closes_the_find_bar(board):
    open_console(board)
    open_find(board)
    board.evaluate("() => window.ctbConsole.open('claude_beta')")
    board.wait_for_selector(FIND, state="hidden")
    assert not frozen(board)


# --- Shift+Escape sends Escape to the session -------------------------------

def test_shift_escape_sends_escape_to_the_session(board):
    open_console(board)
    board.keyboard.press("Shift+Escape")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]
    assert board.is_visible(CONSOLE)


def test_holding_shift_escape_sends_one_escape(board):
    """Every repeat would be another interrupt aimed at a live session."""
    open_console(board)
    board.keyboard.down("Shift")
    board.keyboard.down("Escape")
    for _ in range(5):
        board.evaluate(
            "() => document.dispatchEvent(new KeyboardEvent('keydown',"
            "  {key:'Escape', shiftKey:true, repeat:true, bubbles:true}))")
    board.keyboard.up("Escape")
    board.keyboard.up("Shift")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]


def test_plain_escape_still_closes_the_console(board):
    open_console(board)
    board.keyboard.press("Escape")
    board.wait_for_selector(CONSOLE, state="hidden")


# --- what recovery costs and what it restores -------------------------------

def test_recovery_asks_for_the_pane_exactly_once(board):
    """Not zero (the console sits on a stale pane), not twice."""
    open_console(board)
    board.evaluate("() => window.ctbConsole._state.timer && clearInterval(0)")
    before = logs(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_timeout(500)
    assert logs(board) - before == 1


def test_recovery_from_a_frozen_pane_asks_exactly_once(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")      # freezes; stops the poll
    board.wait_for_timeout(300)
    before = logs(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_timeout(500)
    assert logs(board) - before == 1


def test_recovery_restarts_the_poll_that_the_freeze_stopped(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")
    board.wait_for_timeout(300)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    before = logs(board)
    board.wait_for_timeout(2600)                     # POLL_MS is 2000
    assert logs(board) > before


def test_recovery_does_not_leave_history_loading_stuck(board):
    """The queued repaint it drops is what used to clear `growing`."""
    open_console(board)
    board.evaluate("() => { window.ctbConsole._state.growing = true; }")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    assert board.evaluate("() => window.ctbConsole._state.growing") is False


def test_holding_enter_does_not_send_the_draft(board):
    """The press that recovered the console lands in the prompt box.

    Held down, the repeats arrive there -- and the box may be holding a draft
    written hours ago. The physical press has to end before the box counts as
    typed into.
    """
    open_console(board)
    board.fill("#ctb-console textarea", "rm -rf something")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.down("Enter")
    for _ in range(4):
        board.evaluate(
            "() => document.querySelector('#ctb-console textarea')"
            "  .dispatchEvent(new KeyboardEvent('keydown',"
            "    {key:'Enter', repeat:true, bubbles:true}))")
    board.keyboard.up("Enter")
    board.wait_for_timeout(300)
    assert board.input_value("#ctb-console textarea") == "rm -rf something"
    assert not any("prompt" in u for u in board.ctb_requests)
    # And the press after the release is a normal send again.
    board.click("#ctb-console textarea")
    board.keyboard.press("Enter")
    board.wait_for_timeout(300)
    assert any("prompt" in u for u in board.ctb_requests)


def test_find_leaves_the_palette_chord_alone(board):
    """Ctrl+F from inside the find box still opens the session palette."""
    open_console(board)
    open_find(board)
    board.keyboard.press("Control+f")
    assert board.evaluate(
        "() => [...document.querySelectorAll('[data-search-session]')].length > 0")


def test_a_dead_session_closes_the_find_bar(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.evaluate("() => window.ctbConsole._sessionGone()")
    assert board.is_hidden(FIND)
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0


# --- one-shot key send ------------------------------------------------------

def arm(board):
    board.keyboard.press("Control+Period")
    board.wait_for_function(
        "() => window.ctbConsole._sendArmed()")


def status(board):
    return board.eval_on_selector("#ctb-console [role=status]", "e => e.textContent")


def test_arming_says_so_on_the_status_line(board):
    """An armed console that looks idle is a trap: the next key leaves."""
    open_console(board)
    arm(board)
    assert "다음 한 키를 세션으로" in status(board)


def test_the_armed_key_goes_to_the_session_not_into_the_prompt_box(board):
    """The caret is in the box; Enter there normally sends the draft."""
    open_console(board)
    board.fill("#ctb-console textarea", "draft that must not be sent")
    arm(board)
    board.keyboard.press("Enter")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Enter"]
    assert board.input_value("#ctb-console textarea") == "draft that must not be sent"
    assert not any("prompt" in u for u in board.ctb_requests)


def test_a_digit_is_sent_instead_of_switching_session(board):
    open_console(board)
    arm(board)
    board.keyboard.press("3")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["3"]
    assert board.evaluate("() => window.ctbConsole._state.session") == "claude_alpha"


def test_dom_key_names_are_translated_for_the_server(board):
    """The allowlist speaks tmux: Up, not ArrowUp; BSpace, not Backspace."""
    open_console(board)
    arm(board)
    board.keyboard.press("ArrowUp")
    board.wait_for_timeout(200)
    arm(board)
    board.keyboard.press("Backspace")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Up", "BSpace"]


def test_escape_is_sent_rather_than_closing_the_console(board):
    open_console(board)
    arm(board)
    board.keyboard.press("Escape")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]
    assert board.is_visible(CONSOLE)


def test_tab_is_sent_rather_than_moving_the_focus(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("Tab")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Tab"]
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_it_disarms_after_exactly_one_key(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("y")
    board.wait_for_timeout(200)
    board.keyboard.press("y")              # a letter again, this time typed
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["y"]
    assert board.input_value("#ctb-console textarea") == "y"


def test_the_chord_again_changes_your_mind(board):
    open_console(board)
    arm(board)
    board.keyboard.press("Control+Period")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False
    board.keyboard.press("Escape")         # and Escape is the console's again
    board.wait_for_selector(CONSOLE, state="hidden")
    assert board.ctb_keys == []


def test_a_key_that_cannot_be_sent_cancels_and_says_so(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("q")
    board.wait_for_timeout(300)
    assert board.ctb_keys == []
    assert "보낼 수 없는 키" in status(board)
    assert board.input_value("#ctb-console textarea") == ""


def test_a_chord_stands_the_mode_down_and_passes_through(board):
    """Changing your mind by reaching for another shortcut."""
    open_console(board)
    arm(board)
    board.keyboard.press("Control+Shift+f")
    board.wait_for_selector(FIND, state="visible")
    assert board.ctb_keys == []
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False


def test_it_does_not_arm_while_the_find_bar_is_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Control+Period")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False


def test_switching_session_disarms(board):
    open_console(board)
    arm(board)
    board.evaluate("() => window.ctbConsole.open('claude_beta')")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False
