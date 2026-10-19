"""⏭ 다음 on the board: Ctrl/Cmd+Backslash as a button, beside 세션 검색.

The chord already worked from the board, but a phone has no Ctrl. The
button runs the same jump (jumpToFirstIdle) the console's 다음 key and the
rail's skip key run: it opens the console on the leftmost session that is
not working, and it dims rather than disappears when there is none.
"""

import pytest

import live_board
from live_board import _session, open_board

BTN = "#btn-next-idle"
BUSY = ("working", "overloaded", "scheduled")


@pytest.fixture
def five():
    saved = live_board.SESSIONS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_alpha_wt_topic", state="idle"),
        _session("claude_beta", state="waiting"),
        _session("claude_gamma", state="idle"),
        _session("claude_delta", state="idle"),
    ]
    try:
        with open_board() as page:
            page.wait_for_function("Array.isArray(window.ctbSessionOrder) && window.ctbSessionOrder.length")
            yield page
    finally:
        live_board.SESSIONS = saved


def first_not_busy(page):
    return page.evaluate(
        "busy => (window.ctbSessionOrder.find(s => !busy.includes(s.state)) || {}).name",
        list(BUSY))


def enabled(page):
    return page.eval_on_selector(BTN, "el => el.style.pointerEvents !== 'none'")


@pytest.mark.parametrize("width", [390, 1200])
def test_tapping_it_opens_the_console_on_the_leftmost_idle_session(five, width):
    five.set_viewport_size({"width": width, "height": 844})
    assert five.is_visible(BTN)
    want = first_not_busy(five)
    assert want and want != "claude_alpha"
    assert enabled(five)
    five.click(BTN)
    five.wait_for_selector("#ctb-console", state="visible")
    assert five.evaluate("window.ctbConsole._state.session") == want


def test_it_dims_when_every_session_is_working(five):
    for name in ("claude_alpha_wt_topic", "claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    five.wait_for_function(
        "!window.ctbSessionOrder.some(s => s.state !== 'working')")
    five.wait_for_timeout(200)
    assert five.is_visible(BTN), "it disappeared instead of dimming"
    assert not enabled(five)


def test_no_page_errors(five):
    errors = []
    five.on("pageerror", lambda e: errors.append(str(e)))
    five.click(BTN)
    five.wait_for_timeout(300)
    assert errors == []
