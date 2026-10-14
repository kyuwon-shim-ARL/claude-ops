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


def test_rail_starts_with_the_queue_and_chips_wear_the_number(board):
    open_console(board)
    order = board.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.map(e => e.dataset.switchSession)")
    assert order[:2] == ["claude_two", "claude_beta"]
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
    # The rail is rebuilt with the queue first.
    first3 = board.eval_on_selector_all(
        "#ctb-console [data-switch-session]", "els => els.slice(0, 3).map(e => e.dataset.switchSession)")
    assert first3 == ["claude_two", "claude_beta", "claude_one"]


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
    src = board.locator("#ctb-console-queue [data-queue-open='claude_beta']").bounding_box()
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
    board.keyboard.press("Control+]")
    board.wait_for_function("() => window.ctbConsole._state.session !== 'claude_one'")
