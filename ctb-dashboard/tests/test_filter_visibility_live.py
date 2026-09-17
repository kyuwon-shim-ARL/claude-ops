"""The board hides sessions for one reason only: the age filter.

Searching used to hide them too -- a box on the board that filtered the grid
down to what matched. It is gone. Finding a session is not why the board is
on screen; typing at the session is, and the filter made that two moves
through a grid that had just rearranged itself. F / Ctrl+F now opens the
console's own palette, which reaches every session and hands over its prompt.

What is left here is the age filter (for clearing out old sessions, not for
reaching one) and the property that made the old filtering fast: the board is
built once per data update, and filtering toggles `display` over the cards
already on screen rather than rebuilding the grid.
"""

import pytest  # noqa: F401

from live_board import SESSIONS, board  # noqa: F401  (fixture)

PALETTE = "[role='dialog'][aria-label='세션 검색']"
# claude_gamma is the one session older than an hour (see live_board).
OLD = "claude_gamma"


def _shown(page):
    return page.eval_on_selector_all(
        "#grid [data-session-name]",
        """cards => cards.filter(c => {
             for (let el = c; el; el = el.parentElement) {
               if (el.style && el.style.display === 'none') return false;
             }
             return true;
           }).map(c => c.dataset.sessionName)""",
    )


def _age(page, window):
    page.click(f'#filter-age [data-age="{window}"]')
    page.wait_for_timeout(50)


def _flip_direction(page):
    """'최근 N' <-> '오래된 N' -- the first button in the age bar."""
    page.click("#filter-age button:first-child")
    page.wait_for_timeout(50)


def test_the_search_box_is_gone(board):
    assert board.query_selector("#filter-search") is None


def test_recent_window_hides_the_old_session(board):
    _age(board, "1h")
    assert OLD not in _shown(board)
    assert sorted(_shown(board)) == sorted(
        s["name"] for s in SESSIONS if s["name"] != OLD)


def test_older_direction_keeps_only_the_old_session(board):
    _age(board, "1h")
    _flip_direction(board)
    assert _shown(board) == [OLD]


def test_hidden_cards_stay_in_the_dom(board):
    """The point of the change: hiding is not removal."""
    _age(board, "1h")
    count = board.eval_on_selector_all("#grid [data-session-name]", "c => c.length")
    assert count == len(SESSIONS)


def test_shown_cards_are_not_rebuilt(board):
    """Applying the filter must not tear down and re-parse the grid.

    A property set on a live node cannot survive innerHTML replacement, so it
    answers the only question that matters here: is this the same card?
    """
    board.eval_on_selector('[data-session-name="claude_alpha"]',
                           "c => { c.__probe = 'kept'; }")
    _age(board, "1h")
    assert board.eval_on_selector('[data-session-name="claude_alpha"]',
                                  "c => c.__probe") == "kept"


def test_count_label_and_clearing(board):
    _age(board, "1h")
    assert board.inner_text("#filter-count").startswith("4 / 5")
    _age(board, "all")
    assert board.inner_text("#filter-count") == ""
    assert sorted(_shown(board)) == sorted(s["name"] for s in SESSIONS)


def test_no_match_says_so(board):
    _age(board, "30d")
    _flip_direction(board)          # older than a month: nothing is
    assert _shown(board) == []
    assert board.is_visible("#empty-state")
    assert "필터와 일치하는" in board.inner_text("#empty-state")
    # Nothing of the board's structure may be left standing over it.
    assert not board.is_visible('[data-section="pinned"]')


def test_emptied_quadrant_shows_its_placeholder(board):
    """A quadrant the filter empties must not be left as a blank box.

    Gamma is pinned into Q3 first so that filtering it away empties exactly
    one quadrant, with the pinned block itself still on screen -- which is
    the case the placeholder exists for.
    """
    board.evaluate("() => window.ctbSetQuadrant('claude_gamma', 'Q3')")
    board.wait_for_selector('.quadrant[data-quadrant="Q3"] [data-session-name]')
    _age(board, "1h")
    assert board.is_visible('[data-section="pinned"]')
    assert board.is_visible('.quadrant[data-quadrant="Q3"] [data-quad-empty]')
    assert not board.is_visible('.quadrant[data-quadrant="Q3"] .quadrant-cards')
    # ...and a quadrant that still has a card shows the card, not the prompt.
    assert not board.is_visible('.quadrant[data-quadrant="Q1"] [data-quad-empty]')


def test_group_count_follows_the_filter(board):
    """A repo group's header counts what it is showing, not what it holds."""
    assert board.inner_text("[data-group-count]").startswith("2")
    _age(board, "1h")
    _flip_direction(board)          # alpha and its worktree both go
    assert not board.is_visible("[data-group-count]")


def test_the_others_header_keeps_its_layout(board):
    """Toggling display must not erase the inline `display:flex` it ships with."""
    _age(board, "1h")               # leaves cards in both blocks
    assert board.eval_on_selector(
        '[data-section="others"]', "el => getComputedStyle(el).display") == "flex"


# --- the search that replaced the filter -------------------------------------

def test_bare_f_opens_the_palette(board):
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")


def test_the_chord_opens_the_palette(board):
    board.keyboard.press("Control+f")
    board.wait_for_selector(PALETTE, state="visible")


def test_the_button_opens_the_palette(board):
    board.click("#btn-find-session")
    board.wait_for_selector(PALETTE, state="visible")


def test_the_palette_reaches_a_filtered_away_session(board):
    """The age filter hides cards; it must not hide sessions from the search."""
    _age(board, "1h")
    assert OLD not in _shown(board)
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.type("gamma")
    board.wait_for_timeout(50)
    assert board.query_selector(f'[data-search-session="{OLD}"]') is not None


def test_picking_opens_that_session_console(board):
    """Find it, press Enter, and the caret is in its prompt -- one move."""
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.type("gamma")
    board.wait_for_timeout(50)
    board.keyboard.press("Enter")
    board.wait_for_function(
        "() => window.ctbConsole._state.session === 'claude_gamma'")
    board.wait_for_selector(PALETTE, state="hidden")
    assert board.evaluate(
        "() => document.activeElement === document.querySelector('#ctb-console textarea')")


def test_the_board_is_not_filtered_by_the_search(board):
    """Nothing disappears while the palette is up, or after it closes."""
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.type("gamma")
    board.wait_for_timeout(50)
    assert sorted(_shown(board)) == sorted(s["name"] for s in SESSIONS)
