"""Typing in the board's search box filters without rebuilding the board.

The filter used to run inside render(): every keystroke tore down every card
and re-parsed the whole grid, which on a phone with dozens of sessions made
the box stop taking characters. The board is built once per data update now,
and the filter toggles `display` over the cards already on screen.

Both halves are asserted against the shipped page in a real browser -- that
the right cards hide, and that the cards left showing are the same DOM nodes
they were before the keystroke, which is the part that makes it fast.
"""

import pytest  # noqa: F401

from live_board import SESSIONS, board  # noqa: F401  (fixture)


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


def _type(page, text):
    page.fill("#filter-search", text)
    page.wait_for_timeout(50)


def test_search_hides_the_rest(board):
    _type(board, "gamma")
    assert _shown(board) == ["claude_gamma"]


def test_search_reads_work_context_too(board):
    _type(board, "alpha")
    assert sorted(_shown(board)) == [
        "claude_alpha", "claude_alpha_wt_topic", "claude_delta"]


def test_hidden_cards_stay_in_the_dom(board):
    """The point of the change: hiding is not removal."""
    _type(board, "gamma")
    count = board.eval_on_selector_all("#grid [data-session-name]", "c => c.length")
    assert count == len(SESSIONS)


def test_matching_cards_are_not_rebuilt(board):
    """A keystroke must not tear down and re-parse the grid.

    A property set on a live node cannot survive innerHTML replacement, so it
    answers the only question that matters here: is this the same card?
    """
    board.eval_on_selector('[data-session-name="claude_gamma"]',
                           "c => { c.__probe = 'kept'; }")
    _type(board, "gamma")
    assert board.eval_on_selector('[data-session-name="claude_gamma"]',
                                  "c => c.__probe") == "kept"


def test_count_label_and_clearing(board):
    _type(board, "gamma")
    assert board.inner_text("#filter-count").startswith("1 / 5")
    _type(board, "")
    assert board.inner_text("#filter-count") == ""
    assert sorted(_shown(board)) == sorted(s["name"] for s in SESSIONS)


def test_no_match_says_so(board):
    _type(board, "zzzz")
    assert _shown(board) == []
    assert board.is_visible("#empty-state")
    assert "필터와 일치하는" in board.inner_text("#empty-state")
    # Nothing of the board's structure may be left standing over it.
    assert not board.is_visible('[data-section="pinned"]')


def test_emptied_quadrant_shows_its_placeholder(board):
    """Q1 holds only alpha; filtering alpha away must not leave an empty box."""
    _type(board, "beta")   # beta is pinned in Q2, so the pinned block stays up
    assert board.is_visible('[data-section="pinned"]')
    assert board.is_visible('.quadrant[data-quadrant="Q1"] [data-quad-empty]')
    assert not board.is_visible('.quadrant[data-quadrant="Q1"] .quadrant-cards')
    # ...and the quadrant that still has a card shows the card, not the prompt.
    assert not board.is_visible('.quadrant[data-quadrant="Q2"] [data-quad-empty]')


def test_keyboard_skips_hidden_cards(board):
    """Enter jumps to the first *visible* card, not the first in the DOM."""
    _type(board, "gamma")
    board.press("#filter-search", "Enter")
    assert board.evaluate(
        "document.activeElement && document.activeElement.dataset.sessionName"
    ) == "claude_gamma"


def test_group_count_follows_the_filter(board):
    """A repo group's header counts what it is showing, not what it holds."""
    assert board.inner_text("[data-group-count]").startswith("2")
    _type(board, "_wt_")
    assert board.inner_text("[data-group-count]").startswith("1")


def test_the_others_header_keeps_its_layout(board):
    """Toggling display must not erase the inline `display:flex` it ships with."""
    _type(board, "a")           # matches both pinned and unpinned sessions
    assert board.eval_on_selector(
        '[data-section="others"]', "el => getComputedStyle(el).display") == "flex"
