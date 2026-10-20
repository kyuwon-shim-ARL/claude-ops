"""Dragging a 처리 순서 row past the rows in view scrolls the panel.

On an iPhone 12 the console's queue panel is 84px tall: two or three rows of
chips, the rest scrolled out of sight. A row being dragged could only be
dropped among the rows already showing -- one up or one down. Held at the
panel's top or bottom edge, or past it, the drag now scrolls the panel that
way, so any slot can be reached in one drag.

Driven with real touch events in a browser at 390px: the panel's height
comes from a media query and the scroll from the page's own frames.
"""

import time

import pytest

import live_board
from live_board import _session, open_board

NAMES = ["claude_q%02d" % i for i in range(16)]
PANEL = "#ctb-console-queue"
TOGGLE = "#ctb-console .con-qtoggle"


@pytest.fixture
def long_queue():
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [_session("claude_alpha", state="working")] + [
        _session(n, state="idle", age=100 + i) for i, n in enumerate(NAMES)]
    live_board.QUADS = {"Q1": ["claude_alpha"] + NAMES, "Q2": [], "Q3": [], "Q4": [],
                        "queue": list(NAMES)}
    try:
        with open_board() as page:
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
            page.wait_for_selector("#ctb-console", state="visible")
            page.click(TOGGLE)
            page.wait_for_timeout(200)
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


def scroll_top(page):
    return page.eval_on_selector(PANEL, "p => p.scrollTop")


def toucher(page):
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})

    def touch(kind, x=None, y=None):
        pts = [] if x is None else [{"x": x, "y": y, "id": 1}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})
    return touch


def lift(page, touch, name):
    g = page.locator(f"{PANEL} [data-queue-open='{name}'] [data-queue-grip]").bounding_box()
    x, y = g["x"] + g["width"] / 2, g["y"] + g["height"] / 2
    touch("touchStart", x, y)
    page.wait_for_timeout(650)            # the long press that lifts a row
    return x, y


def test_the_panel_is_short_and_scrollable_on_a_phone(long_queue):
    h = long_queue.eval_on_selector(PANEL, "p => [p.clientHeight, p.scrollHeight]")
    assert h[0] <= 100 and h[1] > h[0] * 2


def test_holding_a_row_at_the_bottom_edge_scrolls_down_and_reaches_the_end(long_queue):
    page = long_queue
    touch = toucher(page)
    lift(page, touch, NAMES[0])
    box = page.locator(PANEL).bounding_box()
    x = box["x"] + 30
    # Down to just inside the bottom edge, then rest there.
    touch("touchMove", x, box["y"] + box["height"] - 4)
    page.wait_for_timeout(1500)
    assert page.eval_on_selector(PANEL, "p => p.scrollTop + p.clientHeight >= p.scrollHeight - 1"), \
        "resting at the bottom edge did not scroll the panel to its end"
    # Drop on the last row, which was out of sight when the drag began.
    last = page.locator(f"{PANEL} [data-queue-open='{NAMES[-1]}']").bounding_box()
    touch("touchMove", last["x"] + last["width"] - 3, last["y"] + last["height"] / 2)
    page.wait_for_timeout(100)
    touch("touchEnd")
    q = last_write(page)["queue"]
    assert q.index(NAMES[0]) > q.index(NAMES[-2]), q
    # The rebuilt panel stays where the row landed, not back at the top.
    page.wait_for_timeout(300)
    assert scroll_top(page) > 0


def test_dragging_above_the_panel_scrolls_up(long_queue):
    page = long_queue
    page.eval_on_selector(PANEL, "p => { p.scrollTop = p.scrollHeight; }")
    page.wait_for_timeout(100)
    start = scroll_top(page)
    assert start > 0
    touch = toucher(page)
    # A row near the bottom, in view now.
    name = page.evaluate(f"""() => {{
      const p = document.querySelector('{PANEL}'), b = p.getBoundingClientRect();
      const r = [...p.querySelectorAll('[data-queue-open]')].reverse()
        .find(e => {{ const q = e.getBoundingClientRect(); return q.top >= b.top && q.bottom <= b.bottom; }});
      return r.dataset.queueOpen; }}""")
    lift(page, touch, name)
    box = page.locator(PANEL).bounding_box()
    touch("touchMove", box["x"] + 30, box["y"] - 15)   # past the top edge
    page.wait_for_timeout(1500)
    assert scroll_top(page) == 0
    touch("touchEnd")
    page.wait_for_timeout(300)
    assert not page.ctb_posted, "a drop outside the panel wrote the queue"


def test_a_drag_resting_mid_panel_does_not_scroll(long_queue):
    page = long_queue
    touch = toucher(page)
    lift(page, touch, NAMES[0])
    box = page.locator(PANEL).bounding_box()
    touch("touchMove", box["x"] + 30, box["y"] + box["height"] / 2)
    page.wait_for_timeout(800)
    assert scroll_top(page) == 0
    touch("touchEnd")


def test_letting_go_stops_the_scroll(long_queue):
    page = long_queue
    touch = toucher(page)
    lift(page, touch, NAMES[0])
    box = page.locator(PANEL).bounding_box()
    touch("touchMove", box["x"] + 30, box["y"] + box["height"] - 4)
    page.wait_for_timeout(150)
    touch("touchEnd")
    page.wait_for_timeout(100)
    a = scroll_top(page)
    page.wait_for_timeout(500)
    assert scroll_top(page) == a


def test_resting_on_the_lower_line_of_chips_does_not_scroll(long_queue):
    """Aiming at the bottom visible line must not slide it away."""
    page = long_queue
    touch = toucher(page)
    lift(page, touch, NAMES[0])
    rows = page.evaluate(f"""() => {{
      const p = document.querySelector('{PANEL}'), b = p.getBoundingClientRect();
      return [...p.querySelectorAll('[data-queue-open]')].map(e => e.getBoundingClientRect())
        .filter(q => q.bottom <= b.bottom).map(q => [q.top, q.bottom]); }}""")
    top, bottom = max(rows)                       # the lowest fully visible line
    box = page.locator(PANEL).bounding_box()
    # Its lower part, where a wide scroll band used to reach.
    touch("touchMove", box["x"] + 30, bottom - 3)
    page.wait_for_timeout(800)
    assert scroll_top(page) == 0
    touch("touchEnd")


def test_a_finger_far_below_the_panel_stops_scrolling(long_queue):
    page = long_queue
    touch = toucher(page)
    lift(page, touch, NAMES[0])
    box = page.locator(PANEL).bounding_box()
    touch("touchMove", box["x"] + 30, box["y"] + box["height"] + 120)
    page.wait_for_timeout(600)
    assert scroll_top(page) == 0
    touch("touchEnd")
