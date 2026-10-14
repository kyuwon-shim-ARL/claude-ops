"""Dragging a card inside its quadrant puts it where it was dropped.

The quadrant's stored pin array is the order its non-working sessions are
shown in, so a drop has to land in that array: the assertion that matters is
what the page POSTs to /api/pinned, and then that the board drew it. A drop
between cards shows an insertion line first, so the user can see where it
will go before letting go.

Driven in a real browser against the shipped page (live_board): the drop
position is read from real card geometry, which a fake DOM would not have.
"""

import time

import pytest

import live_board
from live_board import _session, open_board

QUADS = {"Q1": ["claude_alpha", "claude_one", "claude_two", "claude_three"],
         "Q2": ["claude_beta"], "Q3": [], "Q4": []}


@pytest.fixture
def board():
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        # Newest last: if recency still ordered the idle ones, `three`
        # would be drawn first and these tests would be asserting on the
        # wrong starting order.
        _session("claude_one", state="idle", age=300),
        _session("claude_two", state="waiting", age=200),
        _session("claude_three", state="idle", age=100),
        _session("claude_beta", state="idle"),
    ]
    live_board.QUADS = QUADS
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


def quad_order(page, qid):
    return page.eval_on_selector_all(
        f'[data-quadrant="{qid}"] [data-session-name]',
        "els => els.map(e => e.dataset.sessionName)")


def box(page, name):
    return page.locator(f'[data-session-name="{name}"]').bounding_box()


def last_write(page, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.ctb_posted:
            return page.ctb_posted[-1]
        page.wait_for_timeout(50)
    raise AssertionError("the page never wrote a pin set")


def marker_visible(page):
    return page.evaluate(
        "() => { const m = document.querySelector('[data-drop-marker]');"
        " return !!m && m.style.display !== 'none'; }")


def mouse_drag(page, name, to_x, to_y, check=None):
    b = box(page, name)
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.mouse.down()
    page.mouse.move(to_x, to_y, steps=12)
    seen = check() if check else None
    page.mouse.up()
    return seen


def test_the_board_starts_in_stored_order(board):
    assert quad_order(board, "Q1") == [
        "claude_alpha", "claude_one", "claude_two", "claude_three"]


def test_dragging_above_a_card_in_the_same_quadrant_reorders_it(board):
    one = box(board, "claude_one")
    seen = mouse_drag(board, "claude_three", one["x"] + 10, one["y"] + one["height"] * 0.25,
                      check=lambda: marker_visible(board))
    assert seen, "no insertion line while dragging inside the quadrant"
    assert last_write(board)["Q1"] == [
        "claude_alpha", "claude_three", "claude_one", "claude_two"]
    board.wait_for_timeout(150)
    assert quad_order(board, "Q1") == [
        "claude_alpha", "claude_three", "claude_one", "claude_two"]
    assert not marker_visible(board)


def test_dropping_into_another_quadrant_at_a_position(board):
    beta = box(board, "claude_beta")
    mouse_drag(board, "claude_two", beta["x"] + 10, beta["y"] + beta["height"] * 0.25)
    w = last_write(board)
    assert w["Q2"] == ["claude_two", "claude_beta"]
    assert "claude_two" not in w["Q1"]


def test_dropping_on_an_empty_quadrant_appends(board):
    q3 = board.locator('[data-quadrant="Q3"]').bounding_box()
    mouse_drag(board, "claude_one", q3["x"] + q3["width"] / 2, q3["y"] + q3["height"] - 10)
    assert last_write(board)["Q3"] == ["claude_one"]


def test_a_working_session_keeps_its_place_on_top_but_stores_the_drop(board):
    three = box(board, "claude_three")
    mouse_drag(board, "claude_alpha", three["x"] + 10, three["y"] + three["height"] * 0.25)
    assert last_write(board)["Q1"] == [
        "claude_one", "claude_two", "claude_alpha", "claude_three"]
    board.wait_for_timeout(150)
    assert quad_order(board, "Q1")[0] == "claude_alpha"
    # Once it stops working it takes the slot it was dropped into.
    board.ctb_set_state("claude_alpha", "idle")
    board.wait_for_timeout(200)
    assert quad_order(board, "Q1") == [
        "claude_one", "claude_two", "claude_alpha", "claude_three"]


def test_touch_long_press_drag_reorders_the_same_way(board):
    """Real touch input through CDP: the browser turns it into pointer
    events of type 'touch', which is what the long-press path keys on."""
    cdp = board.context.new_cdp_session(board)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    src = box(board, "claude_three")
    dst = box(board, "claude_one")
    sx, sy = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    tx, ty = dst["x"] + 10, dst["y"] + dst["height"] * 0.25

    def touch(kind, x=None, y=None):
        pts = [] if x is None else [{"x": x, "y": y, "id": 1}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})

    touch("touchStart", sx, sy)
    board.wait_for_timeout(700)  # past the 500ms long press
    for i in range(1, 13):
        touch("touchMove", sx + (tx - sx) * i / 12, sy + (ty - sy) * i / 12)
    assert marker_visible(board), "no insertion line during a touch drag"
    touch("touchEnd")
    assert last_write(board)["Q1"] == [
        "claude_alpha", "claude_three", "claude_one", "claude_two"]


def no_write(page, wait_ms=600):
    page.wait_for_timeout(wait_ms)
    return not page.ctb_posted


def test_a_lower_right_drop_goes_before_the_next_card(board):
    two = box(board, "claude_two")
    mouse_drag(board, "claude_one", two["x"] + two["width"] * 0.75,
               two["y"] + two["height"] * 0.75)
    assert last_write(board)["Q1"] == [
        "claude_alpha", "claude_two", "claude_one", "claude_three"]


def test_a_lower_right_drop_on_the_last_card_appends(board):
    three = box(board, "claude_three")
    mouse_drag(board, "claude_one", three["x"] + three["width"] * 0.75,
               three["y"] + three["height"] * 0.75)
    assert last_write(board)["Q1"] == [
        "claude_alpha", "claude_two", "claude_three", "claude_one"]


def test_dropping_a_card_back_in_place_writes_nothing(board):
    two = box(board, "claude_two")
    cx, cy = two["x"] + two["width"] / 2, two["y"] + two["height"] / 2
    board.mouse.move(cx, cy)
    board.mouse.down()
    # Out and back: a press that never moves is a click, not a drag, and
    # would pass this without dropping anything.
    board.mouse.move(cx + 60, cy + 60, steps=6)
    assert marker_visible(board), "the drag never started"
    board.mouse.move(cx, cy, steps=6)
    board.mouse.up()
    assert no_write(board), board.ctb_posted


def test_choosing_the_current_quadrant_from_the_console_keeps_the_order(board):
    """The console's importance menu re-selecting the quadrant a session is
    already in must not send it to the end of that quadrant."""
    board.evaluate("() => window.ctbSetQuadrant('claude_one', 'Q1')")
    assert no_write(board), board.ctb_posted


def test_the_anchor_is_the_card_as_drawn_not_as_reported_mid_drag(board):
    """A card that turns working while a drag is in flight is still drawn
    where it was -- render() holds still during a drag -- so a drop on it
    has to anchor to it, not to whatever the newer data says."""
    src = box(board, "claude_three")
    one = box(board, "claude_one")
    board.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    board.mouse.down()
    board.mouse.move(src["x"] + 40, src["y"] + 40, steps=4)
    board.ctb_set_state("claude_one", "working")
    board.mouse.move(one["x"] + 10, one["y"] + one["height"] * 0.25, steps=8)
    board.mouse.up()
    assert last_write(board)["Q1"] == [
        "claude_alpha", "claude_three", "claude_one", "claude_two"]


@pytest.mark.parametrize("cancel", [
    "() => document.dispatchEvent(new PointerEvent('pointercancel'))",
    "() => window.dispatchEvent(new Event('blur'))",
])
def test_the_insertion_line_goes_away_when_the_drag_is_cancelled(board, cancel):
    src = box(board, "claude_three")
    one = box(board, "claude_one")
    board.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    board.mouse.down()
    board.mouse.move(one["x"] + 10, one["y"] + one["height"] * 0.25, steps=8)
    assert marker_visible(board)
    board.evaluate(cancel)
    assert not marker_visible(board)
    board.mouse.up()


@pytest.fixture
def grouped():
    """A repo group in Q1 between two loose cards, and a Q4 holding only a
    working session."""
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_one", state="idle"),
        _session("claude_proj", state="idle"),
        _session("claude_proj_wt_x", state="idle"),
        _session("claude_two", state="idle"),
        _session("claude_busy", state="working"),
    ]
    live_board.QUADS = {
        "Q1": ["claude_alpha", "claude_one", "claude_proj", "claude_proj_wt_x", "claude_two"],
        "Q2": [], "Q3": [], "Q4": ["claude_busy"]}
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


def test_a_non_member_dropped_inside_a_group_lands_before_the_group(grouped):
    """Anchoring to the second member would store it between them while the
    group still draws as one box; the drop has to mean the group's slot."""
    wt = box(grouped, "claude_proj_wt_x")
    mouse_drag(grouped, "claude_two", wt["x"] + 10, wt["y"] + 10)
    assert last_write(grouped)["Q1"] == [
        "claude_alpha", "claude_one", "claude_two", "claude_proj", "claude_proj_wt_x"]


def test_a_member_can_still_be_reordered_inside_its_group(grouped):
    main = box(grouped, "claude_proj")
    mouse_drag(grouped, "claude_proj_wt_x", main["x"] + 10, main["y"] + main["height"] * 0.25)
    assert last_write(grouped)["Q1"] == [
        "claude_alpha", "claude_one", "claude_proj_wt_x", "claude_proj", "claude_two"]


def test_a_quadrant_of_only_working_cards_shows_the_line_at_its_end(grouped):
    # Tall enough that Q4 sits inside the viewport: elementFromPoint finds
    # nothing below the fold, and the drop would miss for the test's reasons.
    grouped.set_viewport_size({"width": 1280, "height": 1400})
    grouped.wait_for_timeout(100)
    q4 = grouped.locator('[data-quadrant="Q4"]').bounding_box()
    seen = mouse_drag(grouped, "claude_one", q4["x"] + q4["width"] / 2,
                      q4["y"] + q4["height"] - 6, check=lambda: marker_visible(grouped))
    assert seen, "no insertion line over a quadrant of working cards"
    assert last_write(grouped)["Q4"] == ["claude_busy", "claude_one"]
