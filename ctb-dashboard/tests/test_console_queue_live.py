"""처리 순서 inside the console.

A toggle at the end of the session rail shows or hides a compact copy of the
board's work queue under it. Rows switch the console to that session, reorder
by drag and leave with their cross; "+ 현재 세션" puts the open session at the
end. Every change goes through the board's own pin write, so what is asserted
is what the page POSTs to /api/pinned.
"""

import time

import pytest

import live_board
from live_board import _session, open_board


@pytest.fixture
def board():
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_one", state="idle", age=300),
        _session("claude_two", state="waiting", age=200),
        _session("claude_beta", state="idle"),
    ]
    live_board.QUADS = {"Q1": ["claude_alpha", "claude_one", "claude_two"],
                        "Q2": ["claude_beta"], "Q3": [], "Q4": [],
                        "queue": ["claude_two", "claude_gone", "claude_beta"]}
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


def last_write(page, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.ctb_posted:
            return page.ctb_posted[-1]
        page.wait_for_timeout(50)
    raise AssertionError("the page never wrote a pin set")


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector("#ctb-console", state="visible")


def panel_shown(page):
    return page.evaluate(
        "() => { const p = document.getElementById('ctb-console-queue');"
        " return !!p && getComputedStyle(p).display !== 'none'; }")


def rows(page):
    return page.eval_on_selector_all(
        "#ctb-console-queue [data-queue-open]",
        "els => els.map(e => e.querySelector('.con-qnum').textContent + ':' + e.dataset.queueOpen)")


TOGGLE = "#ctb-console .con-qtoggle"


def test_hidden_by_default_and_the_toggle_shows_and_hides_it(board):
    open_console(board)
    assert not panel_shown(board)
    assert board.get_attribute(TOGGLE, "aria-expanded") == "false"
    board.click(TOGGLE)
    assert panel_shown(board)
    assert rows(board) == ["1:claude_two", "2:claude_beta"]
    board.click(TOGGLE)
    assert not panel_shown(board)


def test_the_choice_is_remembered(board):
    open_console(board)
    board.click(TOGGLE)
    board.reload()
    board.wait_for_selector('[data-session-name="claude_alpha"]')
    open_console(board)
    assert panel_shown(board)


def test_the_toggle_counts_the_queue_while_shut(board):
    open_console(board)
    assert board.inner_text(TOGGLE).strip() == "2"


def test_rail_puts_working_then_the_queue_and_chips_wear_the_number(board):
    open_console(board)
    order = board.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.map(e => e.dataset.switchSession)")
    # alpha is working, so it leads; then the queue.
    assert order[:3] == ["claude_alpha", "claude_two", "claude_beta"]
    nums = board.eval_on_selector_all(
        "#ctb-console [data-switch-session]",
        "els => Object.fromEntries(els.map(e => [e.dataset.switchSession,"
        " e.querySelector('[data-queue-num]').textContent]))")
    assert nums == {"claude_two": "#1", "claude_beta": "#2",
                    "claude_alpha": "", "claude_one": ""}


def test_tapping_a_row_opens_that_session(board):
    open_console(board)
    board.click(TOGGLE)
    board.click("#ctb-console-queue [data-queue-open='claude_beta'] .con-qname")
    board.wait_for_function("() => window.ctbConsole._state.session === 'claude_beta'")
    assert board.get_attribute(
        "#ctb-console-queue [data-queue-open='claude_beta']", "aria-current") == "true"


def test_add_current_session_appends_it(board):
    open_console(board, "claude_one")
    board.click(TOGGLE)
    board.click("#ctb-console-queue [data-queue-add]")
    assert last_write(board)["queue"] == ["claude_two", "claude_gone", "claude_beta", "claude_one"]
    board.wait_for_function(
        "() => document.querySelectorAll('#ctb-console-queue [data-queue-open]').length === 3")
    assert rows(board)[-1] == "3:claude_one"
    assert board.is_disabled("#ctb-console-queue [data-queue-add]")
    # The rail is rebuilt: the working one, then the queue with one at its end.
    first4 = board.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.slice(0, 4).map(e => e.dataset.switchSession)")
    assert first4 == ["claude_alpha", "claude_two", "claude_beta", "claude_one"]


def test_add_is_disabled_for_a_session_already_queued(board):
    open_console(board, "claude_two")
    board.click(TOGGLE)
    assert board.is_disabled("#ctb-console-queue [data-queue-add]")


def test_the_cross_removes(board):
    open_console(board)
    board.click(TOGGLE)
    board.click("#ctb-console-queue [data-queue-x='claude_two']")
    assert last_write(board)["queue"] == ["claude_gone", "claude_beta"]
    board.wait_for_function(
        "() => document.querySelectorAll('#ctb-console-queue [data-queue-open]').length === 1")
    assert rows(board) == ["1:claude_beta"]


def test_dragging_a_row_reorders(board):
    open_console(board)
    board.click(TOGGLE)
    src = board.locator("#ctb-console-queue [data-queue-open='claude_beta']").bounding_box()
    dst = board.locator("#ctb-console-queue [data-queue-open='claude_two']").bounding_box()
    board.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    board.mouse.down()
    board.mouse.move(dst["x"] + 4, dst["y"] + dst["height"] / 2, steps=10)
    assert board.evaluate(
        "() => { const m = document.querySelector('[data-con-queue-marker]');"
        " return !!m && m.style.display !== 'none'; }"), "no insertion line"
    board.mouse.up()
    assert last_write(board)["queue"] == ["claude_beta", "claude_two", "claude_gone"]
    # The drag's click did not also switch session.
    assert board.evaluate("() => window.ctbConsole._state.session") == "claude_alpha"


def test_touch_long_press_drag_reorders(board):
    open_console(board)
    board.click(TOGGLE)
    cdp = board.context.new_cdp_session(board)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    # By its grip: a finger lifts a row from there only.
    src = board.locator("#ctb-console-queue [data-queue-open='claude_beta'] [data-queue-grip]").bounding_box()
    dst = board.locator("#ctb-console-queue [data-queue-open='claude_two']").bounding_box()
    sx, sy = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    tx, ty = dst["x"] + 4, dst["y"] + dst["height"] / 2

    def touch(kind, x=None, y=None):
        pts = [] if x is None else [{"x": x, "y": y, "id": 1}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})

    touch("touchStart", sx, sy)
    board.wait_for_timeout(650)
    for i in range(1, 11):
        touch("touchMove", sx + (tx - sx) * i / 10, sy + (ty - sy) * i / 10)
    touch("touchEnd")
    assert last_write(board)["queue"] == ["claude_beta", "claude_two", "claude_gone"]


def test_opening_the_panel_on_a_phone_keeps_the_pane_and_keys_on_screen(board):
    board.set_viewport_size({"width": 390, "height": 700})
    open_console(board)
    board.click(TOGGLE)
    boxes = board.evaluate("""() => {
      const q = document.getElementById('ctb-console-queue').getBoundingClientRect();
      const tail = document.querySelector('#ctb-console pre').getBoundingClientRect();
      const input = document.querySelector('#ctb-console textarea').getBoundingClientRect();
      return { q, tail, input, vh: innerHeight, sw: document.documentElement.scrollWidth };
    }""")
    assert boxes["q"]["bottom"] <= boxes["tail"]["top"]
    assert boxes["tail"]["height"] >= 120
    assert boxes["input"]["bottom"] <= boxes["vh"]
    assert boxes["sw"] <= 390


def test_the_panel_does_not_take_the_rail_shortcuts(board):
    open_console(board, "claude_one")
    board.click(TOGGLE)
    board.focus("#ctb-console-queue [data-queue-open='claude_two']")
    board.keyboard.press("Control+[")
    board.wait_for_function("() => window.ctbConsole._state.session !== 'claude_one'")


def test_closed_sessions_can_be_cleared_from_the_console(board):
    open_console(board)
    board.click(TOGGLE)
    btn = "#ctb-console-queue [data-queue-prune]"
    for _ in range(2):   # closed means missing from two snapshots running
        board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        board.wait_for_timeout(150)
    board.wait_for_selector(btn)
    assert board.inner_text(btn).strip() == "종료된 세션 1개 정리"
    board.click(btn)
    assert last_write(board)["queue"] == ["claude_two", "claude_beta"]
    board.wait_for_function(f"() => !document.querySelector('{btn}')")


def test_rows_scroll_vertically_on_touch_and_the_grip_holds_still(board):
    open_console(board)
    board.click(TOGGLE)
    ta = board.evaluate(
        "() => [getComputedStyle(document.querySelector('#ctb-console-queue [data-queue-open]')).touchAction,"
        " getComputedStyle(document.querySelector('#ctb-console-queue [data-queue-grip]')).touchAction]")
    assert ta == ["pan-y", "none"]


def test_a_long_press_off_the_grip_does_not_drag(board):
    open_console(board)
    board.click(TOGGLE)
    cdp = board.context.new_cdp_session(board)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    src = board.locator("#ctb-console-queue [data-queue-open='claude_beta'] .con-qname").bounding_box()
    sx, sy = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": sx, "y": sy, "id": 1}]})
    board.wait_for_timeout(650)
    assert board.evaluate("() => document.querySelectorAll('#ctb-console > .con-qrow').length") == 0
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def test_a_press_that_never_moves_lets_the_panel_repaint(board):
    """A mouse held down on a row without moving holds the repaint off; the
    idle timer is armed from the press so it cannot hold it off forever."""
    open_console(board)
    board.click(TOGGLE)
    board.evaluate("""() => { const real = window.setTimeout;
      window.setTimeout = (fn, ms, ...a) => real(fn, ms === 10000 ? 50 : ms, ...a); }""")
    b = board.locator("#ctb-console-queue [data-queue-open='claude_beta']").bounding_box()
    board.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    board.mouse.down()
    board.wait_for_timeout(200)
    board.evaluate("() => window.ctbQueueRemove('claude_two')")
    board.wait_for_function(
        "() => !document.querySelector(\"#ctb-console-queue [data-queue-open='claude_two']\")")
    board.mouse.up()


def _marker_shown(page):
    return page.evaluate(
        "() => { const m = document.querySelector('[data-con-queue-marker]');"
        " return !!m && m.style.display !== 'none'; }")


def _ghosts(page):
    return page.evaluate("() => document.querySelectorAll('#ctb-console > .con-qrow').length")


@pytest.mark.parametrize("cancel", [
    "() => window.dispatchEvent(new Event('blur'))",
    "() => document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))",
])
def test_a_drag_can_be_cancelled(board, cancel):
    open_console(board)
    board.click(TOGGLE)
    src = board.locator("#ctb-console-queue [data-queue-open='claude_beta']").bounding_box()
    dst = board.locator("#ctb-console-queue [data-queue-open='claude_two']").bounding_box()
    board.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    board.mouse.down()
    board.mouse.move(dst["x"] + 4, dst["y"] + dst["height"] / 2, steps=10)
    assert _marker_shown(board) and _ghosts(board) == 1
    board.evaluate(cancel)
    assert not _marker_shown(board)
    assert _ghosts(board) == 0
    board.mouse.up()
    board.wait_for_timeout(500)
    assert not board.ctb_posted
    # The console is still open (Escape cancelled the drag, not the sheet)
    # and the panel repaints again.
    assert board.evaluate("() => window.ctbConsole._state.session") == "claude_alpha"
    board.click("#ctb-console-queue [data-queue-x='claude_two']")
    assert last_write(board)["queue"] == ["claude_gone", "claude_beta"]


@pytest.fixture
def busy_queue():
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_q2nd", state="working"),
        _session("claude_q1st", state="idle"),
        _session("claude_q3rd", state="idle"),
        _session("claude_other", state="idle"),
    ]
    live_board.QUADS = {"Q1": ["claude_other"], "Q2": [], "Q3": [], "Q4": [],
                        "queue": ["claude_q1st", "claude_q2nd", "claude_q3rd"]}
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


def test_rail_has_working_first_and_ctrl_backslash_lands_on_queue_one(busy_queue):
    open_console(busy_queue, "claude_other")
    order = busy_queue.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.map(e => e.dataset.switchSession)")
    assert order[:2] == ["claude_q2nd", "claude_alpha"]
    assert order[2:4] == ["claude_q1st", "claude_q3rd"]
    # One busy/idle boundary, right after the working chips.
    dividers = busy_queue.evaluate("""() => {
      const kids = Array.from(document.querySelector('#ctb-console .con-rail').children);
      return kids.map(k => k.hasAttribute('data-ctb-divider') ? '|' : (k.dataset.switchSession || ''))
                 .filter(Boolean); }""")
    assert dividers.index("|") == 2 and dividers.count("|") == 1
    busy_queue.keyboard.press("Control+Backslash")
    busy_queue.wait_for_function("() => window.ctbConsole._state.session === 'claude_q1st'")


# --- working sessions sit in front, out of Ctrl+\\'s way ---------------------------------------------

@pytest.fixture
def walk():
    """Two working sessions -- one unpinned, which the queue-first order of
    the previous commit put last and the working-first order puts in front --
    a queue of two idle ones, and an idle Q1 session after them."""
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),        # Q1, working
        _session("claude_free", state="working"),         # unpinned, working
        _session("claude_first", state="idle", age=500),  # queue #1
        _session("claude_second", state="waiting", age=400),  # queue #2
        _session("claude_later", state="idle", age=300),  # Q1, not queued
    ]
    live_board.QUADS = {"Q1": ["claude_alpha", "claude_second", "claude_later"],
                        "Q2": ["claude_first"], "Q3": [], "Q4": [],
                        "queue": ["claude_first", "claude_second"]}
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


def rail(page):
    return page.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.map(e => e.dataset.switchSession)")


def current(page):
    return page.evaluate("() => window.ctbConsole._state.session")


def test_the_unpinned_working_session_sits_in_front_of_the_queue(walk):
    open_console(walk, "claude_later")
    assert rail(walk) == ["claude_alpha", "claude_free",
                          "claude_first", "claude_second", "claude_later"]
    walk.keyboard.press("Control+Backslash")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_first'")


def test_after_answering_number_one_ctrl_backslash_goes_to_number_two(walk):
    open_console(walk, "claude_first")
    walk.ctb_set_state("claude_first", "working")    # answered: it is off again
    walk.keyboard.press("Control+Backslash")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_second'")


# --- but working sessions can still be looked into -------------------------------
# A session read as working may be stuck or misread, and only a look tells; so
# the digits and the brackets keep every chip. Skipping the busy ones is
# Ctrl+\'s job alone.

def test_left_bracket_from_number_one_reaches_the_working_block(walk):
    open_console(walk, "claude_first")
    walk.keyboard.press("Control+[")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_free'")


def test_right_bracket_steps_chip_by_chip_from_a_working_session(walk):
    open_console(walk, "claude_alpha")
    walk.keyboard.press("Control+]")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_free'")


def test_left_bracket_goes_to_the_previous_chip(walk):
    open_console(walk, "claude_second")
    walk.keyboard.press("Control+[")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_first'")


def test_the_urgent_walk_keeps_working_q1_sessions(walk):
    # Q1 = alpha (working), second, later, in rail order alpha, second, later.
    open_console(walk, "claude_second")
    walk.keyboard.press("Control+Shift+]")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_later'")
    walk.keyboard.press("Control+Shift+]")         # wraps, onto the working one
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_alpha'")


def test_digits_count_from_the_front_of_the_rail(walk):
    open_console(walk, "claude_later")
    walk.keyboard.down("Control")
    walk.wait_for_timeout(100)
    hints = walk.eval_on_selector_all(
        "#ctb-console [data-switch-session]",
        "els => Object.fromEntries(els.map(e => { const b = e.querySelector('[data-numhint]');"
        " return [e.dataset.switchSession, b && b.style.display !== 'none' ? b.textContent : null]; }))")
    assert hints == {"claude_alpha": "1", "claude_free": "2",
                     "claude_first": "3", "claude_second": "4", "claude_later": "5"}
    walk.keyboard.press("1")
    walk.keyboard.up("Control")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_alpha'")


def test_digits_on_the_board_number_the_same_way(walk):
    walk.keyboard.down("Control")
    walk.wait_for_timeout(100)
    hints = walk.evaluate(
        "() => Object.fromEntries(['claude_alpha', 'claude_first'].map(n => {"
        " const c = document.querySelector(`#grid [data-session-name=\"${n}\"] [data-ctb-gridhint]`);"
        " return [n, c && c.textContent]; }))")
    walk.keyboard.up("Control")
    assert hints == {"claude_alpha": "1", "claude_first": "3"}


def test_ctrl_backslash_with_the_numbers_up_judges_the_frozen_states(walk):
    # Ctrl held freezes the rail; alpha (frozen as working, at the front) going
    # idle mid-hold must not win over queue #1.
    open_console(walk, "claude_later")
    walk.keyboard.down("Control")
    walk.wait_for_timeout(100)
    walk.ctb_set_state("claude_alpha", "idle")
    walk.keyboard.press("Backslash")
    walk.keyboard.up("Control")
    walk.wait_for_function("() => window.ctbConsole._state.session === 'claude_first'")


def test_a_session_going_idle_moves_behind_the_working_block(walk):
    open_console(walk, "claude_later")
    walk.eval_on_selector("#ctb-console [data-switch-session='claude_alpha']",
                          "c => { c.__probe = 'kept'; }")
    walk.ctb_set_state("claude_alpha", "idle")
    walk.wait_for_function(
        "() => document.querySelector('#ctb-console [data-switch-session]').dataset.switchSession === 'claude_free'")
    order = rail(walk)
    assert order[0] == "claude_free" and order.index("claude_alpha") > 0
    assert walk.eval_on_selector("#ctb-console [data-switch-session='claude_alpha']",
                                 "c => c.__probe") == "kept", "moved, not rebuilt"
    dividers = walk.evaluate(
        "() => document.querySelectorAll('#ctb-console .con-rail [data-ctb-divider]').length")
    assert dividers == 1


def test_the_rail_holds_still_while_the_numbers_are_up(walk):
    open_console(walk, "claude_later")
    walk.keyboard.down("Control")
    walk.wait_for_timeout(100)
    before = rail(walk)
    walk.ctb_set_state("claude_alpha", "idle")
    assert rail(walk) == before
    walk.keyboard.up("Control")
