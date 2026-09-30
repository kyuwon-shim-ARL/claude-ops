"""Ctrl/Cmd+Backslash jumps the console to the LEFTMOST session on the rail
that is not `working` -- the state the rail dims, and the one state the user
does not have to act on. It does not walk: stepping on through the idle ones
is what Ctrl+] already does, so pressing it again stays put. Filtered against
the *live* catalogue so a session that goes busy drops out immediately rather
than a poll later.

Driven in a real browser against the shipped dashboard fixture (live_board),
because the behaviour under test is a document-level keydown listener wired
up at load time, not a pure function.
"""

import pytest  # noqa: F401

import live_board
from live_board import _session, board, open_board  # noqa: F401  (board fixture)

CONSOLE = "#ctb-console"


def open_console(page, name="claude_alpha"):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector(CONSOLE, state="visible")


def current(page):
    return page.evaluate("window.ctbConsole._state.session")


def state_of(page, name):
    return page.evaluate(
        "n => (window.ctbSessionAll.find(s => s.name === n) || {}).state", name)


def status_text(page):
    return page.evaluate("window.ctbConsole._el().status.textContent")


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


def rail_order(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll("
        "'#ctb-console [data-switch-session]')).map(c => c.getAttribute('data-switch-session'))")


def leftmost_idle(page):
    return next(n for n in rail_order(page) if state_of(page, n) != "working")


def test_it_goes_to_the_leftmost_idle_session(five):
    open_console(five, "claude_alpha")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    assert current(five) == leftmost_idle(five)


def test_pressing_again_does_not_walk_on(five):
    """Walking on through the idle ones is Ctrl+]'s job, not this key's."""
    open_console(five, "claude_alpha")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    first = current(five)
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    assert current(five) == first


def test_from_further_right_it_comes_back_to_the_leftmost(five):
    open_console(five, "claude_alpha")
    target = leftmost_idle(five)
    # The second idle one, not the last: from the last, a forward walk wraps
    # round to the leftmost anyway and would pass this by accident.
    second_idle = [n for n in rail_order(five) if state_of(five, n) != "working"][1]
    open_console(five, second_idle)
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    assert current(five) == target


def test_the_korean_layout_key_works_too(five):
    """Korean keyboards print ₩ on the physical Backslash key; `code`
    is what this binds on, with `key` only as a fallback."""
    open_console(five, "claude_alpha")
    five.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown', "
        "{code:'Backslash', key:'\\u20a9', ctrlKey:true, bubbles:true, cancelable:true}))")
    five.wait_for_timeout(100)
    assert current(five) == leftmost_idle(five)


def test_a_leftmost_session_that_goes_busy_is_passed_over(five):
    """The rail's own order can be a beat stale; the filter has to read the
    live catalogue, not the snapshot the walk list carries."""
    open_console(five, "claude_alpha")
    first = leftmost_idle(five)
    five.ctb_set_state(first, "working")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    landed = current(five)
    assert landed != first
    assert state_of(five, landed) != "working"


def test_no_other_idle_session_leaves_the_console_and_says_so(five):
    for name in ("claude_alpha_wt_topic", "claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    open_console(five, "claude_alpha_wt_topic")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    assert current(five) == "claude_alpha_wt_topic"
    assert "유휴" in status_text(five)


def test_urgent_only_walk_is_unaffected(five):
    """Ctrl+Shift+[ / ] still means Q1-only -- this key does not touch it."""
    open_console(five, "claude_alpha")
    five.evaluate("() => { window.ctbQuadOf = {claude_gamma: 'Q1'}; }")
    five.keyboard.press("Control+Shift+]")
    five.wait_for_timeout(100)
    assert current(five) == "claude_gamma"
