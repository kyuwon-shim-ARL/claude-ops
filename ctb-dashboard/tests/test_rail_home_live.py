"""A way back to the start of the session rail.

The rail holds every session -- ninety of them on this machine -- in the
grid's order, and opening one scrolls it to the middle. Getting back to the
first meant flinging the rail for as long as it took, which on a phone is a
finger and several seconds.

Driven in a real browser: the button is pinned with `position: sticky` inside
the scrolling rail, and whether that actually holds its place while the chips
pass underneath is exactly the kind of thing only a browser can answer.
"""

import pytest  # noqa: F401

import live_board
from live_board import _session, board, open_board  # noqa: F401  (board fixture)


@pytest.fixture
def crowded():
    """Enough sessions that the rail has to scroll."""
    saved = live_board.SESSIONS
    live_board.SESSIONS = [_session("claude_alpha", state="working")] + [
        _session("claude_project_number_%02d" % i) for i in range(40)
    ]
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS = saved


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector("#ctb-console", state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


BTN = "#ctb-console button[aria-label='세션 목록 맨 처음으로']"
RAIL = "#ctb-console .con-rail"


def scroll_left(page):
    return page.eval_on_selector(RAIL, "el => el.scrollLeft")


def visible(page):
    return page.eval_on_selector(
        BTN, "el => el.style.display !== 'none' && el.offsetParent !== null")


def test_the_button_takes_the_rail_back_to_the_first_chip(crowded):
    open_console(crowded)
    crowded.eval_on_selector(RAIL, "el => { el.scrollLeft = el.scrollWidth; }")
    crowded.wait_for_timeout(150)
    assert scroll_left(crowded) > 0, "the rail did not scroll; nothing to test"

    crowded.click(BTN)
    crowded.wait_for_function("() => document.querySelector('%s').scrollLeft <= 8"
                              % RAIL, timeout=3000)


def test_it_stays_pinned_at_the_rail_s_right_edge_while_chips_pass_under(crowded):
    """`position: sticky` inside a horizontally scrolling flex row is the part
    worth proving -- a plain child would scroll away with the chips."""
    open_console(crowded)
    crowded.eval_on_selector(RAIL, "el => { el.scrollLeft = 0; }")
    crowded.wait_for_timeout(120)
    before = crowded.eval_on_selector(BTN, "el => el.getBoundingClientRect().right")

    crowded.eval_on_selector(RAIL, "el => { el.scrollLeft = 400; }")
    crowded.wait_for_timeout(200)
    after = crowded.eval_on_selector(BTN, "el => el.getBoundingClientRect().right")

    assert abs(after - before) < 2, f"the button moved: {before} -> {after}"
    rail_right = crowded.eval_on_selector(RAIL, "el => el.getBoundingClientRect().right")
    # Within the rail's own 4px gap: sticky pins to the scrollport's padding
    # box, and the flex gap sits outside it.
    assert abs(after - rail_right) < 6, "the button is not at the rail's right edge"


def test_it_is_not_shown_when_every_session_already_fits(board):
    """A control that cannot do anything is worse than no control: the stock
    fixture has five sessions and the rail does not scroll."""
    open_console(board)
    board.wait_for_timeout(200)
    assert not visible(board)


def test_it_dims_itself_once_the_rail_is_back_at_the_start(crowded):
    """Dimmed rather than removed: a button that vanishes under the finger
    that is scrolling makes the rail jump."""
    open_console(crowded)
    crowded.eval_on_selector(RAIL, "el => { el.scrollLeft = el.scrollWidth; }")
    crowded.wait_for_timeout(200)
    assert crowded.eval_on_selector(BTN, "el => el.style.opacity") == "1"

    crowded.eval_on_selector(RAIL, "el => { el.scrollLeft = 0; }")
    crowded.wait_for_timeout(200)
    assert visible(crowded), "it disappeared instead of dimming"
    assert crowded.eval_on_selector(BTN, "el => el.style.opacity") != "1"
    assert crowded.eval_on_selector(BTN, "el => el.style.pointerEvents") == "none"


def test_it_survives_the_rail_being_rebuilt(crowded):
    """renderStrip empties the rail on every board update; the button is one
    of the children that gets cleared."""
    open_console(crowded)
    crowded.evaluate("() => window.ctbConsole._renderStrip && window.ctbConsole._renderStrip()")
    crowded.ctb_set_state("claude_project_number_03", "waiting")
    crowded.wait_for_timeout(300)
    assert crowded.eval_on_selector(
        RAIL, "el => el.lastElementChild.getAttribute('aria-label')"
    ) == "세션 목록 맨 처음으로", "the button is no longer the rail's last child"


def test_no_page_errors(crowded):
    open_console(crowded)
    crowded.click(BTN)
    crowded.wait_for_timeout(300)
    assert crowded.ctb_errors == []
