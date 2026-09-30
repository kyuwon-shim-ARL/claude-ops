"""A left-edge mirror of the Ctrl/Cmd+Backslash shortcut (see
test_rail_skip_working_key_live.py): a button pinned to the rail's LEFT
edge that jumps to the next session that is not `working`, for a finger
that has no keyboard to press Ctrl+\\ on.

It shares the shortcut's walk (jumpToNextIdle(dir)) rather than duplicating
it, and mirrors railHome (test_rail_home_live.py) visually: same size,
sticky to its own edge, opaque ground with a fade on the side the chips
pass under, first child of the rail rather than last, and dimmed instead of
removed when there is nothing to jump to.

Driven in a real browser: the button's sticky positioning and its
first-child survival across a rail rebuild are exactly what only a browser
can answer.
"""

import pytest  # noqa: F401

import live_board
from live_board import _session, board, open_board  # noqa: F401  (board fixture)

CONSOLE = "#ctb-console"
BTN = "#ctb-console button[aria-label='작업중이 아닌 다음 세션으로 이동']"
RAIL = "#ctb-console .con-rail"


def open_console(page, name="claude_alpha"):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector(CONSOLE, state="visible")


def current(page):
    return page.evaluate("window.ctbConsole._state.session")


def state_of(page, name):
    return page.evaluate(
        "n => (window.ctbSessionAll.find(s => s.name === n) || {}).state", name)


def visible(page):
    return page.eval_on_selector(
        BTN, "el => el.style.display !== 'none' && el.offsetParent !== null")


def enabled(page):
    return page.eval_on_selector(BTN, "el => el.style.pointerEvents !== 'none'")


@pytest.fixture
def five():
    """Five sessions, one of them working, so the walk has real work to skip."""
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
            yield page
    finally:
        live_board.SESSIONS = saved


def test_it_is_the_rail_s_first_child(five):
    open_console(five, "claude_alpha")
    assert five.eval_on_selector(
        RAIL, "el => el.firstElementChild.getAttribute('aria-label')"
    ) == "작업중이 아닌 다음 세션으로 이동"


def test_it_has_no_switch_session_attribute(five):
    open_console(five, "claude_alpha")
    assert five.eval_on_selector(BTN, "el => el.hasAttribute('data-switch-session')") is False


def test_clicking_it_skips_a_working_session(five):
    open_console(five, "claude_alpha")
    five.click(BTN)
    five.wait_for_timeout(100)
    landed = current(five)
    assert landed != "claude_alpha"
    assert state_of(five, landed) != "working"


def test_it_survives_a_rail_rebuild(five):
    open_console(five, "claude_alpha")
    five.evaluate("() => window.ctbConsole._renderStrip && window.ctbConsole._renderStrip()")
    five.ctb_set_state("claude_gamma", "waiting")
    five.wait_for_timeout(300)
    assert five.eval_on_selector(
        RAIL, "el => el.firstElementChild.getAttribute('aria-label')"
    ) == "작업중이 아닌 다음 세션으로 이동", "the button is no longer the rail's first child"


def test_it_is_dimmed_when_no_candidate_exists(five):
    for name in ("claude_alpha_wt_topic", "claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    open_console(five, "claude_alpha_wt_topic")
    five.wait_for_timeout(300)
    assert visible(five), "it disappeared instead of dimming"
    assert not enabled(five)


def test_it_re_enables_once_a_candidate_appears(five):
    for name in ("claude_alpha_wt_topic", "claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    open_console(five, "claude_alpha_wt_topic")
    five.wait_for_timeout(300)
    assert not enabled(five)
    five.ctb_set_state("claude_gamma", "idle")
    five.wait_for_timeout(300)
    assert enabled(five)


def test_numbering_is_unaffected(five):
    """The button carries no data-switch-session, so it must not shift the
    digit hints off the chips (see number shortcuts, HINT_MAX)."""
    open_console(five, "claude_alpha")
    five.keyboard.down("Control")
    five.wait_for_timeout(80)
    first_numbered = five.eval_on_selector(
        RAIL,
        "el => { var c = el.querySelector('[data-switch-session]'); "
        "var n = c && c.querySelector('[data-numhint]'); return n && n.textContent; }")
    five.keyboard.up("Control")
    assert first_numbered == "1"


def test_no_page_errors(five):
    open_console(five, "claude_alpha")
    five.click(BTN)
    five.wait_for_timeout(300)
    assert five.ctb_errors == []
