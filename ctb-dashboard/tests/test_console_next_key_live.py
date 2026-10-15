"""다음: the input row's own copy of Ctrl/Cmd+Backslash, beside 전송.

On a phone the gesture is type, 전송, move on -- with the thumb already on
the input row, not up at the rail's left edge where railSkip sits. The new
key shares railSkip's jump (jumpToFirstIdle), icon and dimming, and adds the
one thing the rail never needed: a session just sent to still reads idle
until the next poll, so a local "just sent" mark keeps the jump from landing
straight back on it.

Driven in a real browser against the shipped dashboard fixture (live_board):
the mark lives across a click, a fetch in flight and a board refresh, and
the row's fit at 390px is a layout question only a browser answers.
"""

import json

import pytest  # noqa: F401

import live_board
from live_board import _session, open_board

CONSOLE = "#ctb-console"
NEXT = "#ctb-console .con-next"
SKIP = "#ctb-console .con-rail-skip"
SEND = "#ctb-console .con-send"
BOX = "#ctb-console textarea"
BUSY = ("working", "overloaded", "scheduled")
VSCODE = "window.acquireVsCodeApi = function () { return { postMessage: function () {} }; };"


def open_console(page, name):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector(CONSOLE, state="visible")


def current(page):
    return page.evaluate("window.ctbConsole._state.session")


def status_text(page):
    return page.evaluate("window.ctbConsole._el().status.textContent")


def idle_in_rail_order(page):
    """The non-busy chips, leftmost first: what the jump walks."""
    return page.evaluate(
        "busy => Array.from(document.querySelectorAll('#ctb-console [data-switch-session]'))"
        ".map(c => c.getAttribute('data-switch-session'))"
        ".filter(n => !busy.includes((window.ctbSessionAll.find(s => s.name === n) || {}).state))",
        list(BUSY))


def enabled(page, sel=NEXT):
    return page.eval_on_selector(sel, "el => el.style.pointerEvents !== 'none'")


def shown(page, sel=NEXT):
    return page.eval_on_selector(
        sel, "el => getComputedStyle(el).display !== 'none' && el.offsetParent !== null")


def send(page, text):
    page.fill(BOX, text)
    page.click(SEND)


@pytest.fixture
def five():
    """Five sessions, one working: three idle ones to walk through."""
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


def test_both_buttons_draw_the_same_icon(five):
    open_console(five, "claude_alpha")
    d_skip = five.eval_on_selector(SKIP, "el => el.querySelector('svg path').getAttribute('d')")
    d_next = five.eval_on_selector(NEXT, "el => el.querySelector('svg path').getAttribute('d')")
    assert d_skip == d_next
    # Not the old arrow: the tray's arrow keys have shafts, this must not.
    assert d_next != "M5 12h14M12 5l7 7-7 7"


def test_it_sits_right_of_send_and_says_what_it_does(five):
    open_console(five, "claude_alpha")
    assert five.eval_on_selector(SEND, "el => el.nextElementSibling.classList.contains('con-next')")
    assert five.eval_on_selector(NEXT, "el => el.querySelector('.con-key-label').textContent") == "다음"
    same = five.evaluate(
        "() => { const a = document.querySelector('#ctb-console .con-rail-skip'),"
        "              b = document.querySelector('#ctb-console .con-next');"
        "  return a.title === b.title && a.getAttribute('aria-label') === b.getAttribute('aria-label'); }")
    assert same


def test_tapping_it_lands_on_the_leftmost_idle_session(five):
    open_console(five, "claude_alpha")
    first = idle_in_rail_order(five)[0]
    five.click(NEXT)
    five.wait_for_timeout(100)
    assert current(five) == first


def test_send_then_next_moves_past_the_session_just_sent_to(five):
    """The harness never reports the sent session busy: only the mark can
    tell the jump to look past it."""
    open_console(five, "claude_alpha")
    first, second = idle_in_rail_order(five)[:2]
    open_console(five, first)
    send(five, "do the thing")
    # Unmarked, the session just sent to is still the leftmost idle one, so
    # the key is dimmed as "already there" and a click would only time out.
    assert enabled(five), "the key still reads the session just sent to as idle"
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == second


def test_a_tap_while_the_send_is_still_in_flight_moves_on(five):
    held = []
    five.route("**/prompt", lambda r: held.append(r))
    open_console(five, "claude_alpha")
    first, second = idle_in_rail_order(five)[:2]
    open_console(five, first)
    send(five, "do the thing")
    five.wait_for_timeout(100)
    assert held, "the send never left"
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == second
    held[0].fulfill(status=200, content_type="application/json", body="{}")
    five.wait_for_timeout(100)


def test_send_next_send_next_reaches_the_third(five):
    open_console(five, "claude_alpha")
    first, second, third = idle_in_rail_order(five)[:3]
    open_console(five, first)
    send(five, "one")
    assert enabled(five), "the key still reads the session just sent to as idle"
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == second
    send(five, "two")
    assert enabled(five), "the key still reads the session just sent to as idle"
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == third


@pytest.mark.parametrize("answer", [409, 500, "abort"])
def test_a_refused_send_clears_the_mark(five, answer):
    def refuse(r):
        if answer == "abort":
            return r.abort()
        body = {"reason": "awaiting"} if answer == 409 else {}
        return r.fulfill(status=answer, content_type="application/json", body=json.dumps(body))

    five.route("**/prompt", refuse)
    open_console(five, "claude_alpha")
    first = idle_in_rail_order(five)[0]
    open_console(five, first)
    send(five, "will be refused")
    five.wait_for_timeout(200)
    # From a session that is not a candidate, the jump must find the
    # refused one again: nothing was sent there.
    open_console(five, "claude_alpha")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == first


def test_the_mark_expires_when_the_session_never_turns_busy(five):
    """A slash command can come back without the session ever reading
    working; the mark must not hide it for good."""
    five.evaluate("() => window.ctbConsole._setJustSentMs(300)")
    open_console(five, "claude_alpha")
    first, second = idle_in_rail_order(five)[:2]
    open_console(five, first)
    send(five, "/clear")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == second
    five.wait_for_timeout(400)
    open_console(five, "claude_alpha")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == first


def test_the_mark_goes_once_the_board_reports_it_busy(five):
    """Busy then idle again means the work really finished: it is a
    candidate again at once, not after the timeout."""
    open_console(five, "claude_alpha")
    first = idle_in_rail_order(five)[0]
    open_console(five, first)
    send(five, "quick one")
    five.wait_for_timeout(150)
    five.ctb_set_state(first, "working")
    five.ctb_set_state(first, "idle")
    five.wait_for_timeout(150)
    open_console(five, "claude_alpha")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == first


def test_answering_from_the_key_tray_then_next_moves_on(five):
    open_console(five, "claude_alpha")
    first, second = idle_in_rail_order(five)[:2]
    open_console(five, first)
    five.click("#ctb-console button[aria-label='1번 키 전송']")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == second


@pytest.mark.parametrize("label", ["아래 키 전송", "한 글자 지우기 키 전송", "Tab 키 전송",
                                   "Escape — 진행 중인 작업 중단 · 메뉴 닫기 키 전송"])
def test_a_key_that_does_not_answer_leaves_the_session_where_it_is(five, label):
    """Moving through a menu, deleting, or stopping the session is still
    working on it -- none of that makes Claude go, so the mark must not push
    Ctrl+\\ and 다음 off a session the user is in the middle of."""
    open_console(five, "claude_alpha")
    five.click(NEXT)                       # onto the leftmost idle: dimmed
    five.wait_for_timeout(200)
    here = current(five)
    five.click(f"#ctb-console button[aria-label='{label}']")
    five.wait_for_timeout(150)
    assert current(five) == here
    assert not enabled(five), "the key moved the session out of 다음's way"


def test_escape_clears_a_mark_left_by_a_send(five):
    """Escape stops the work a send started: the session is waiting on the
    user again, so it is a candidate again at once, not 8 s later."""
    open_console(five, "claude_alpha")
    first = idle_in_rail_order(five)[0]
    open_console(five, first)
    send(five, "go")
    five.wait_for_timeout(100)
    assert enabled(five)                   # marked: 다음 offers the next one
    five.click("#ctb-console button[aria-label='Escape — 진행 중인 작업 중단 · 메뉴 닫기 키 전송']")
    five.wait_for_timeout(150)
    assert not enabled(five), "the interrupted session still reads as just sent"


def test_it_is_dimmed_when_no_candidate_exists(five):
    for name in ("claude_alpha_wt_topic", "claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    open_console(five, "claude_alpha_wt_topic")
    five.wait_for_timeout(300)
    assert shown(five), "it disappeared instead of dimming"
    assert not enabled(five)


def test_it_is_dimmed_when_already_on_the_leftmost_idle_session(five):
    open_console(five, "claude_alpha")
    five.click(NEXT)
    five.wait_for_timeout(300)
    assert current(five) != "claude_alpha"
    assert shown(five)
    assert not enabled(five)


def test_it_is_dimmed_while_the_only_other_candidate_was_just_sent_to(five):
    """The mark repaints the key itself; no board event fires for it."""
    for name in ("claude_beta", "claude_gamma", "claude_delta"):
        five.ctb_set_state(name, "working")
    open_console(five, "claude_alpha_wt_topic")
    five.wait_for_timeout(200)
    send(five, "only one idle")
    five.wait_for_timeout(100)
    assert not enabled(five)


def test_next_with_a_draft_parks_it_and_says_so(five):
    open_console(five, "claude_alpha")
    first = idle_in_rail_order(five)[0]
    five.fill(BOX, "half typed")
    five.click(NEXT)
    five.wait_for_timeout(150)
    assert current(five) == first
    assert five.evaluate("n => window.ctbConsole._state.drafts[n]", "claude_alpha") == "half typed"
    assert not any(u.endswith("/prompt") for u in five.ctb_requests)
    text = status_text(five)
    assert "보관됨 · alpha" in text, text
    assert "wt_topic" not in text, "the notice names the session left, not the destination"


def test_hidden_in_the_vscode_webview_where_the_rail_button_stays():
    saved = live_board.SESSIONS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_beta", state="idle"),
    ]
    try:
        with open_board(init=VSCODE) as page:
            open_console(page, "claude_alpha")
            page.wait_for_timeout(200)
            assert not shown(page)
            assert shown(page, SKIP)
    finally:
        live_board.SESSIONS = saved


def test_the_row_fits_a_phone_with_every_key_showing(five):
    five.set_viewport_size({"width": 390, "height": 844})
    five.route("**/api/stt/config", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"enabled": true}'))
    # Not a secure context, so the browser hides mediaDevices; the mic only
    # asks whether it exists.
    five.evaluate(
        "() => Object.defineProperty(navigator, 'mediaDevices',"
        " { value: { getUserMedia: () => Promise.reject(new Error('stub')) }, configurable: true })")
    open_console(five, "claude_alpha")
    five.wait_for_function(
        "() => getComputedStyle(document.querySelector('#ctb-console .con-mic')).display !== 'none'")
    boxes = five.evaluate(
        "() => ['.con-clip', '.con-mic', '.con-send', '.con-next'].map(s => {"
        "  const r = document.querySelector('#ctb-console ' + s).getBoundingClientRect();"
        "  return { s, left: r.left, right: r.right, top: r.top, w: r.width }; })")
    for b in boxes:
        assert b["w"] > 0, b
        assert b["left"] >= 0 and b["right"] <= 390, b
    tops = {round(b["top"]) for b in boxes}
    assert len(tops) == 1, "the keys wrapped onto more than one line: %r" % boxes
    width = five.eval_on_selector(BOX, "el => el.getBoundingClientRect().width")
    assert width >= 160, width


def test_no_page_errors(five):
    open_console(five, "claude_alpha")
    send(five, "hello")
    five.click(NEXT)
    five.wait_for_timeout(300)
    assert five.ctb_errors == []
