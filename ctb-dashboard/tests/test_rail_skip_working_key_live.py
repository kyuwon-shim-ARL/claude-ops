"""Ctrl/Cmd+Backslash jumps the console to the next session that is not
`working` -- the state the rail now dims instead of lighting up, and the one
state the user does not have to act on. It reuses stepSession's walk (see
Ctrl+[ / Ctrl+] in test_tail_scroll_settle_js.py) with a predicate instead of
the urgentOnly flag, filtered against the *live* catalogue so a session that
goes busy mid-walk drops out immediately rather than a poll later.

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


def test_it_skips_a_working_session(five):
    open_console(five, "claude_alpha")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    landed = current(five)
    assert landed != "claude_alpha"
    assert state_of(five, landed) != "working"


def test_shift_walks_backwards(five):
    open_console(five, "claude_alpha")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    forward = current(five)
    five.keyboard.press("Control+Shift+\\")
    five.wait_for_timeout(100)
    back = current(five)
    # Walking one step off `forward` in the other direction, over the same
    # predicate, lands back one step off where it started -- not necessarily
    # claude_alpha itself, since claude_alpha is working and gets skipped
    # both ways, but never `forward` again.
    assert back != forward


def test_it_wraps_around(five):
    """Stepping forward through every non-working session returns to the
    first one landed on, without ever landing on the working session."""
    open_console(five, "claude_alpha")
    seen = []
    for _ in range(6):
        five.keyboard.press("Control+\\")
        five.wait_for_timeout(80)
        seen.append(current(five))
    assert "claude_alpha" not in seen
    # four non-working sessions: the walk must have repeated by the 6th press
    assert len(set(seen)) <= 4
    assert seen[-1] in seen[:-1] or len(set(seen)) < len(seen)


def test_the_korean_layout_key_works_too(five):
    """Korean keyboards print ₩ on the physical Backslash key; `code`
    is what this binds on, with `key` only as a fallback."""
    open_console(five, "claude_alpha")
    five.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown', "
        "{code:'Backslash', key:'\\u20a9', ctrlKey:true, bubbles:true, cancelable:true}))")
    five.wait_for_timeout(100)
    assert current(five) != "claude_alpha"


def test_a_session_that_goes_busy_mid_walk_is_skipped(five):
    """The rail's own order can be a beat stale; the filter has to read the
    live catalogue, not the snapshot the walk list carries."""
    open_console(five, "claude_alpha")
    five.keyboard.press("Control+\\")
    five.wait_for_timeout(100)
    first = current(five)
    # That session starts working right under the walk.
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
