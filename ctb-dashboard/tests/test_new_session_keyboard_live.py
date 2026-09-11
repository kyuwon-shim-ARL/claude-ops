"""The new-session sheet is driveable from the keyboard alone.

Opening it with Ctrl+N was already possible (test_new_session_shortcut_live),
but once open the project list only answered the mouse: no cursor, no Enter.
These drive the shipped sheet in a real browser with nothing but keys, the
same way the console's session palette is driven.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

SHEET = "#new-session-modal"
ROWS = "#new-session-projects [data-project]"


def open_sheet(page):
    page.keyboard.press("n")
    page.wait_for_selector(SHEET, state="visible")
    # The list arrives over fetch; the cursor means nothing until it is there.
    page.wait_for_selector(ROWS)


def cursor(page):
    """The project the arrow keys are on, read off the DOM the user sees."""
    return page.eval_on_selector(
        "#new-session-projects", """el => {
            const at = el.ownerDocument.querySelector('#new-session-projects')
                .parentElement.querySelector('input[role=combobox]')
                .getAttribute('aria-activedescendant');
            const row = at && el.ownerDocument.getElementById(at);
            return row ? row.getAttribute('data-project') : null;
        }""")


def chosen(page):
    return page.eval_on_selector_all(
        ROWS, "els => els.filter(e => e.getAttribute('aria-selected') === 'true')"
              "        .map(e => e.getAttribute('data-project'))")


def preview(page):
    return page.eval_on_selector("#new-session-modal", "el => el.innerText")


def test_the_cursor_starts_on_the_first_project(board):
    open_sheet(board)
    assert cursor(board) == "atlas"


def test_arrows_move_the_cursor_without_leaving_the_search_box(board):
    open_sheet(board)
    board.keyboard.press("ArrowDown")
    assert cursor(board) == "borealis"
    board.keyboard.press("ArrowUp")
    assert cursor(board) == "atlas"
    # Typing must keep filtering: the caret never left.
    board.keyboard.type("bor")
    assert cursor(board) == "borealis"


def test_arrow_up_from_the_top_wraps_to_the_bottom(board):
    open_sheet(board)
    board.keyboard.press("ArrowUp")
    assert cursor(board) == "borealis"


def test_enter_selects_the_project_under_the_cursor(board):
    open_sheet(board)
    board.keyboard.press("ArrowDown")
    board.keyboard.press("Enter")
    assert chosen(board) == ["borealis"]
    assert "claude_borealis" in preview(board)


def test_typing_then_enter_picks_the_match(board):
    open_sheet(board)
    board.keyboard.type("bor")
    board.keyboard.press("Enter")
    assert chosen(board) == ["borealis"]


def test_enter_on_the_already_chosen_project_starts_the_session(board):
    """Pick, then go -- two presses, no reach for the mouse."""
    open_sheet(board)
    board.keyboard.press("Enter")          # choose atlas
    assert chosen(board) == ["atlas"]
    board.keyboard.press("Enter")          # and start it
    board.wait_for_selector(SHEET, state="hidden")
    assert "/api/sessions/create" in board.ctb_requests


def test_enter_with_nothing_chosen_does_not_create(board):
    """An empty filter has no match to take; the sheet says so and stays up."""
    open_sheet(board)
    board.keyboard.type("zzzz")
    board.keyboard.press("Enter")
    assert "/api/sessions/create" not in board.ctb_requests
    assert board.is_visible(SHEET)


def test_ctrl_enter_starts_from_anywhere_in_the_sheet(board):
    open_sheet(board)
    board.keyboard.press("Enter")          # choose atlas
    board.click("#new-session-modal button:has-text('새로 만들기')")
    board.keyboard.type("refactor")        # caret now in the worktree box
    board.keyboard.press("Control+Enter")
    board.wait_for_selector(SHEET, state="hidden")
    assert "/api/sessions/create" in board.ctb_requests


def test_enter_in_the_worktree_box_starts_the_session(board):
    open_sheet(board)
    board.keyboard.press("Enter")
    board.click("#new-session-modal button:has-text('새로 만들기')")
    board.keyboard.type("refactor")
    board.keyboard.press("Enter")
    board.wait_for_selector(SHEET, state="hidden")
    assert "/api/sessions/create" in board.ctb_requests


def test_enter_in_the_new_project_name_starts_the_session(board):
    open_sheet(board)
    board.click("#new-session-modal button:has-text('새 프로젝트')")
    board.keyboard.type("fresh-thing")
    board.keyboard.press("Enter")
    board.wait_for_selector(SHEET, state="hidden")
    assert "/api/sessions/create" in board.ctb_requests
