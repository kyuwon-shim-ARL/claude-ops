"""The new-session sheet opens from the keyboard.

Same shape as the board's search shortcut: Ctrl/Cmd+N, or a bare "n" when
nothing is being typed into. The bare letter is what actually lands on a
desktop -- browsers keep Ctrl+N for "new window" and a page never sees it, so
the chord only reaches the page in an installed PWA window and the VSCode
webview, and this suite is the only place both can be exercised.

The sheet itself is untouched; what is asserted is when the key opens it and
when it must keep its hands off.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

SHEET = "#new-session-modal"


def opened(page):
    return page.eval_on_selector_all(
        SHEET, "els => els.some(e => e.style.display !== 'none')")


def test_bare_n_opens_the_sheet(board):
    board.keyboard.press("n")
    board.wait_for_selector(SHEET, state="visible")


def test_the_chord_opens_the_sheet(board):
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")


def test_typing_n_into_the_filter_box_does_not_open_it(board):
    """The board's search box is the one place "n" is just a letter."""
    board.click("#filter-search")
    board.keyboard.press("n")
    assert board.input_value("#filter-search") == "n"
    assert not opened(board)


def test_the_chord_still_works_from_a_text_field(board):
    """A chord is never a character, so the filter box does not own it."""
    board.click("#filter-search")
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    assert board.input_value("#filter-search") == ""


def test_ctrl_shift_n_is_left_to_the_browser(board):
    board.keyboard.press("Control+Shift+n")
    assert not opened(board)


def test_an_open_console_keeps_the_key(board):
    """The console is a full-bleed sheet; a modal over it is not wanted."""
    board.evaluate("window.ctbConsole.open('claude_alpha')")
    board.wait_for_selector("#ctb-console", state="visible")
    board.keyboard.press("n")
    assert not opened(board)


def test_a_second_press_does_not_reopen_the_sheet(board):
    """show() refetches the project list and resets the form.

    Asserted by the fetch it would make: the field's own text survives a
    reopen, so the visible state cannot tell the two apart.
    """
    board.keyboard.press("n")
    board.wait_for_selector(SHEET, state="visible")
    board.wait_for_function(
        "() => document.querySelectorAll('#new-session-modal button').length > 0")
    before = board.ctb_requests.count("/api/projects")
    assert before > 0
    # The chord, not the bare letter: the caret sits in the sheet's search
    # field, where a bare "n" is just a character.
    board.keyboard.press("Control+n")
    board.wait_for_timeout(200)
    assert board.ctb_requests.count("/api/projects") == before


def test_the_cmd_chord_works_too(board):
    """Cmd+N on a Mac is the same request as Ctrl+N.

    Pressed from inside the filter box: over the board a bare "n" would open
    the sheet anyway, so only a text field can tell a recognised chord from an
    unrecognised modifier.
    """
    board.click("#filter-search")
    board.keyboard.press("Meta+n")
    board.wait_for_selector(SHEET, state="visible")
    assert board.input_value("#filter-search") == ""


def test_a_dragged_card_keeps_the_key(board):
    """A sheet over the drop target loses the move that was in flight."""
    card = board.query_selector('[data-session-name="claude_alpha"]')
    box = card.bounding_box()
    board.mouse.move(box["x"] + 40, box["y"] + 20)
    board.mouse.down()
    board.mouse.move(box["x"] + 120, box["y"] + 90, steps=8)
    assert board.evaluate("window.ctbBoardBusy()")
    board.keyboard.press("n")
    assert not opened(board)
    board.mouse.up()


def test_an_open_delete_dialog_keeps_the_key(board):
    # Dispatched, not moved-to: Tailwind's grid is blocked in this fixture, so
    # the cards stack and a real pointer lands on whichever is on top.
    board.eval_on_selector('[data-delete-session="claude_gamma"]', "el => el.click()")
    board.wait_for_selector("#delete-modal", state="visible")
    board.keyboard.press("n")
    assert not opened(board)


def test_a_composing_ime_keeps_the_key(board):
    """Mid-Hangul, the keystroke belongs to the IME, not to a shortcut."""
    board.evaluate(
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key:'n', isComposing:true, bubbles:true}))")
    assert not opened(board)
