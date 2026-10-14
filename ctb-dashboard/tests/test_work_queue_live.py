"""처리 순서: the numbered work queue above the matrix.

One list of session names, "do these in this order", stored as `queue` in the
pin set. The panel is shut until the user opens it, and remembers which way it
was left. Cards are dragged into it at a position; rows are dragged within it
to reorder and out of it to remove. A queued card wears its number.

Driven in a real browser against the shipped page (live_board): drops are
read from real row geometry, and the assertion that matters is what the page
POSTs to /api/pinned.
"""

import time

import pytest

import live_board
from live_board import _session, open_board

QUADS = {"Q1": ["claude_alpha", "claude_one", "claude_two"],
         "Q2": ["claude_beta"], "Q3": [], "Q4": []}


@pytest.fixture
def board():
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_one", state="idle", age=300),
        _session("claude_two", state="waiting", age=200),
        _session("claude_beta", state="idle"),
        _session("claude_loose", state="idle"),
    ]
    live_board.QUADS = QUADS
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.SESSIONS, live_board.QUADS = saved


@pytest.fixture
def queued():
    """A queue already stored: two, plus a session that no longer exists."""
    saved = live_board.SESSIONS, live_board.QUADS
    live_board.SESSIONS = [
        _session("claude_alpha", state="working"),
        _session("claude_one", state="idle", age=300),
        _session("claude_two", state="idle", age=200),
        _session("claude_beta", state="idle"),
    ]
    live_board.QUADS = dict(QUADS, queue=["claude_two", "claude_gone", "claude_beta"])
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


def no_write(page, wait_ms=600):
    page.wait_for_timeout(wait_ms)
    return not page.ctb_posted


def panel_shown(page):
    return page.evaluate(
        "() => getComputedStyle(document.getElementById('queue-panel')).display !== 'none'")


def open_panel(page):
    if not panel_shown(page):
        page.click("#btn-queue")
    assert panel_shown(page)


def rows(page):
    return page.eval_on_selector_all(
        "#queue-list [data-queue-row]",
        "els => els.map(e => e.querySelector('.queue-num').textContent + ':' + e.dataset.queueRow)")


def badge(page, name):
    return page.evaluate(
        "n => { const b = document.querySelector(`#grid [data-session-name=\"${n}\"] [data-queue-badge]`);"
        " return b ? b.textContent : null; }", name)


def box(page, selector):
    return page.locator(selector).bounding_box()


def card(name):
    return f'#grid [data-session-name="{name}"]'


def row(name):
    return f'#queue-list [data-queue-row="{name}"]'


def marker_visible(page):
    return page.evaluate(
        "() => { const m = document.querySelector('[data-drop-marker]');"
        " return !!m && m.style.display !== 'none'; }")


def mouse_drag(page, selector, to_x, to_y, check=None):
    b = box(page, selector)
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.mouse.down()
    page.mouse.move(to_x, to_y, steps=12)
    seen = check() if check else None
    page.mouse.up()
    return seen


# --- the panel itself ------------------------------------------------------------

def test_the_panel_is_shut_by_default(board):
    assert not panel_shown(board)
    assert board.get_attribute("#btn-queue", "aria-expanded") == "false"


def test_the_toggle_opens_it_and_the_choice_survives_a_reload(board):
    board.click("#btn-queue")
    assert panel_shown(board)
    assert board.get_attribute("#btn-queue", "aria-expanded") == "true"
    board.reload()
    board.wait_for_selector(card("claude_alpha"))
    assert panel_shown(board)
    board.click("#btn-queue")
    board.reload()
    board.wait_for_selector(card("claude_alpha"))
    assert not panel_shown(board)


def test_an_empty_queue_offers_a_place_to_drop(board):
    open_panel(board)
    assert rows(board) == []
    assert "여기로 끌어놓기" in board.inner_text("#queue-list [data-queue-end]")


def test_rows_number_only_sessions_that_exist_and_cards_wear_the_number(queued):
    open_panel(queued)
    assert rows(queued) == ["1:claude_two", "2:claude_beta"]
    assert badge(queued, "claude_two") == "#1"
    assert badge(queued, "claude_beta") == "#2"
    assert badge(queued, "claude_one") is None


def test_a_row_shows_quadrant_and_state(queued):
    open_panel(queued)
    r = queued.locator(row("claude_beta"))
    assert "🟡" in r.inner_text()          # Q2
    assert r.locator("[data-queue-state]").get_attribute("data-queue-state") == "idle"


def test_the_shut_button_still_says_how_many(queued):
    assert not panel_shown(queued)
    assert queued.inner_text("#queue-count") == "2"
    assert "처리 순서" in queued.inner_text("#btn-queue")


def test_quadrant_order_puts_the_queue_after_the_working_ones(queued):
    order = queued.eval_on_selector_all(
        '[data-quadrant="Q1"] [data-session-name]', "els => els.map(e => e.dataset.sessionName)")
    # alpha works; two is queued #1; one is not queued.
    assert order == ["claude_alpha", "claude_two", "claude_one"]


# --- adding, reordering, removing ----------------------------------------------

def test_dragging_a_card_into_the_panel_at_slot_one(queued):
    open_panel(queued)
    first = box(queued, row("claude_two"))
    seen = mouse_drag(queued, card("claude_one"), first["x"] + 6, first["y"] + 4,
                      check=lambda: marker_visible(queued))
    assert seen, "no insertion line while over the panel"
    w = last_write(queued)
    # Stored with the dead entry kept in its place.
    assert w["queue"] == ["claude_one", "claude_two", "claude_gone", "claude_beta"]
    # The quadrants are untouched by a queue drop.
    assert w["Q1"] == QUADS["Q1"]
    queued.wait_for_timeout(150)
    assert rows(queued)[0] == "1:claude_one"
    assert badge(queued, "claude_one") == "#1"
    assert not marker_visible(queued)


def test_dropping_on_the_end_slot_appends(board):
    open_panel(board)
    end = box(board, "#queue-list [data-queue-end]")
    mouse_drag(board, card("claude_two"), end["x"] + end["width"] / 2, end["y"] + end["height"] / 2)
    assert last_write(board)["queue"] == ["claude_two"]


def test_an_unpinned_card_can_go_into_the_queue(board):
    # Tall enough that the unpinned card, below the matrix, is on screen.
    board.set_viewport_size({"width": 1280, "height": 1600})
    open_panel(board)
    end = box(board, "#queue-list [data-queue-end]")
    mouse_drag(board, card("claude_loose"), end["x"] + 10, end["y"] + end["height"] / 2)
    w = last_write(board)
    assert w["queue"] == ["claude_loose"]
    # Queued is not pinned: it did not land in a quadrant.
    assert all("claude_loose" not in w[q] for q in ("Q1", "Q2", "Q3", "Q4"))


def test_reordering_within_the_panel(queued):
    queued.set_viewport_size({"width": 500, "height": 900})   # one column
    open_panel(queued)
    first = box(queued, row("claude_two"))
    mouse_drag(queued, row("claude_beta"), first["x"] + 20, first["y"] + 3)
    assert last_write(queued)["queue"] == ["claude_beta", "claude_two", "claude_gone"]
    queued.wait_for_timeout(150)
    assert rows(queued) == ["1:claude_beta", "2:claude_two"]


def test_a_row_dropped_back_on_itself_writes_nothing(queued):
    open_panel(queued)
    b = box(queued, row("claude_two"))
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    queued.mouse.move(cx, cy)
    queued.mouse.down()
    queued.mouse.move(cx + 8, cy + 30, steps=4)
    queued.mouse.move(cx, cy + 2, steps=4)
    queued.mouse.up()
    assert no_write(queued), queued.ctb_posted


def test_the_cross_removes(queued):
    open_panel(queued)
    queued.click(row("claude_two") + " [data-queue-remove]")
    assert last_write(queued)["queue"] == ["claude_gone", "claude_beta"]
    queued.wait_for_timeout(150)
    assert rows(queued) == ["1:claude_beta"]
    assert badge(queued, "claude_two") is None


def test_dropping_a_row_outside_the_list_does_nothing(queued):
    """A long press released a few pixels off the list is a slip, not a
    decision; the cross is the one way out of the queue."""
    open_panel(queued)
    q4 = box(queued, '[data-quadrant="Q4"]')
    mouse_drag(queued, row("claude_beta"), q4["x"] + 20, q4["y"] + 20)
    assert no_write(queued), queued.ctb_posted
    assert rows(queued) == ["1:claude_two", "2:claude_beta"]


def test_dropping_a_row_on_the_panels_own_padding_does_nothing(queued):
    open_panel(queued)
    lst = box(queued, "#queue-list")
    # The section pads the list by 12px above it.
    mouse_drag(queued, row("claude_beta"), lst["x"] + 30, lst["y"] - 5)
    assert no_write(queued), queued.ctb_posted


def test_an_unpinned_card_dropped_on_a_quadrant_is_pinned_there(board):
    """With the panel open an unpinned card lifts; putting it in a quadrant
    pins it there, the way a quadrant means on the board."""
    board.set_viewport_size({"width": 1280, "height": 1600})
    open_panel(board)
    q3 = box(board, '[data-quadrant="Q3"]')
    mouse_drag(board, card("claude_loose"), q3["x"] + q3["width"] / 2, q3["y"] + q3["height"] - 10)
    w = last_write(board)
    assert w["Q3"] == ["claude_loose"]
    assert w["queue"] == []


# --- closed sessions -------------------------------------------------------------

def prune_text(page):
    return page.evaluate(
        "() => { const b = document.querySelector('#queue-panel [data-queue-prune]');"
        " return b && getComputedStyle(b).display !== 'none' ? b.textContent.trim() : null; }")


def refetch(page):
    """A fresh /api/sessions snapshot, through the board's own refetch path."""
    page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(150)


def test_closed_sessions_can_be_cleared_from_the_queue(queued):
    open_panel(queued)
    refetch(queued)
    refetch(queued)
    assert prune_text(queued) == "종료된 세션 1개 정리"
    queued.click("#queue-panel [data-queue-prune]")
    assert last_write(queued)["queue"] == ["claude_two", "claude_beta"]
    queued.wait_for_timeout(150)
    assert prune_text(queued) is None
    assert rows(queued) == ["1:claude_two", "2:claude_beta"]


def test_no_clear_control_when_nothing_is_closed(board):
    open_panel(board)
    assert prune_text(board) is None


def test_a_session_ending_is_offered_only_after_two_snapshots(queued):
    open_panel(queued)
    refetch(queued)
    refetch(queued)
    queued.ctb_drop_session("claude_two")      # first snapshot without it
    assert prune_text(queued) == "종료된 세션 1개 정리"
    refetch(queued)                            # second
    assert prune_text(queued) == "종료된 세션 2개 정리"


def test_one_missing_snapshot_is_not_a_closed_session(queued):
    open_panel(queued)
    refetch(queued)
    refetch(queued)
    queued.ctb_drop_session("claude_two")
    # It comes back on the next poll (restored, or the poll just missed it).
    queued.ctb_sessions.append(live_board._session("claude_two", state="idle"))
    queued.ctb_gone.discard("claude_two")
    refetch(queued)
    refetch(queued)
    assert prune_text(queued) == "종료된 세션 1개 정리"   # only claude_gone


def test_an_empty_snapshot_hides_the_clear_control(queued):
    """A poll that comes back with no sessions at all is a missed poll; it must
    not make every queued name look closed."""
    open_panel(queued)
    refetch(queued)
    refetch(queued)
    assert prune_text(queued) == "종료된 세션 1개 정리"
    queued.ctb_sessions[:] = []
    refetch(queued)
    assert prune_text(queued) is None
    refetch(queued)
    assert prune_text(queued) is None
    assert no_write(queued), queued.ctb_posted


def test_tapping_a_row_opens_that_session(queued):
    open_panel(queued)
    # Desktop: the card's own action focuses the terminal -- stub that out so
    # the fallback (the console) is what a missing terminal gets.
    queued.evaluate("() => { window.ctbFocusSession = () => false; }")
    queued.click(row("claude_beta") + " .queue-name")
    queued.wait_for_selector("#ctb-console", state="visible")
    assert queued.evaluate("() => window.ctbConsole._state.session") == "claude_beta"


def test_touch_long_press_drags_a_card_into_the_panel(queued):
    """Real touch input through CDP: the browser turns it into pointer
    events of type 'touch', which is what the long-press path keys on."""
    open_panel(queued)
    cdp = queued.context.new_cdp_session(queued)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})
    src = box(queued, card("claude_one"))
    dst = box(queued, row("claude_two"))
    sx, sy = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    tx, ty = dst["x"] + 6, dst["y"] + 4

    def touch(kind, x=None, y=None):
        pts = [] if x is None else [{"x": x, "y": y, "id": 1}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})

    touch("touchStart", sx, sy)
    queued.wait_for_timeout(700)  # past the 500ms long press
    for i in range(1, 13):
        touch("touchMove", sx + (tx - sx) * i / 12, sy + (ty - sy) * i / 12)
    assert marker_visible(queued), "no insertion line during a touch drag"
    touch("touchEnd")
    assert last_write(queued)["queue"] == ["claude_one", "claude_two", "claude_gone", "claude_beta"]


# --- the queue survives everything else ----------------------------------------

def test_a_pin_change_after_queueing_keeps_the_queue(queued):
    queued.locator(f'{card("claude_one")} [data-pin-session]').dispatch_event("click")  # unpin
    w = last_write(queued)
    assert "claude_one" not in w["Q1"]
    assert w["queue"] == ["claude_two", "claude_gone", "claude_beta"]


def test_unpinning_a_queued_session_keeps_its_place(queued):
    queued.locator(f'{card("claude_two")} [data-pin-session]').dispatch_event("click")
    assert last_write(queued)["queue"] == ["claude_two", "claude_gone", "claude_beta"]


def test_moving_a_session_to_another_quadrant_keeps_the_queue(queued):
    q3 = box(queued, '[data-quadrant="Q3"]')
    mouse_drag(queued, card("claude_one"), q3["x"] + q3["width"] / 2, q3["y"] + q3["height"] - 10)
    w = last_write(queued)
    assert w["Q3"] == ["claude_one"]
    assert w["queue"] == ["claude_two", "claude_gone", "claude_beta"]


def test_the_console_quadrant_menu_keeps_the_queue(queued):
    queued.evaluate("() => window.ctbSetQuadrant('claude_two', 'Q4')")
    w = last_write(queued)
    assert w["Q4"] == ["claude_two"]
    assert w["queue"] == ["claude_two", "claude_gone", "claude_beta"]


def test_a_session_ending_does_not_rewrite_the_queue(queued):
    queued.ctb_drop_session("claude_two")
    queued.wait_for_timeout(200)
    assert queued.inner_text("#queue-count") == "1"
    assert badge(queued, "claude_beta") == "#1"
    assert no_write(queued), queued.ctb_posted


# --- carried over from the in-quadrant reorder it replaces -----------------------

def test_dropping_a_card_on_its_own_quadrant_writes_nothing(board):
    q1 = box(board, '[data-quadrant="Q1"]')
    two = box(board, card("claude_two"))
    mouse_drag(board, card("claude_one"), two["x"] + two["width"] / 2, two["y"] + two["height"] / 2)
    assert q1, "Q1 is on screen"
    assert no_write(board), board.ctb_posted


def test_choosing_the_current_quadrant_from_the_console_writes_nothing(board):
    board.evaluate("() => window.ctbSetQuadrant('claude_one', 'Q1')")
    assert no_write(board), board.ctb_posted


def test_dropping_on_another_quadrant_appends(board):
    beta = box(board, card("claude_beta"))
    mouse_drag(board, card("claude_two"), beta["x"] + 10, beta["y"] + 10)
    w = last_write(board)
    assert w["Q2"] == ["claude_beta", "claude_two"]
    assert "claude_two" not in w["Q1"]
    assert not marker_visible(board), "no insertion line inside a quadrant any more"


@pytest.mark.parametrize("cancel", [
    "() => document.dispatchEvent(new PointerEvent('pointercancel'))",
    "() => window.dispatchEvent(new Event('blur'))",
])
def test_the_insertion_line_goes_away_when_the_drag_is_cancelled(queued, cancel):
    open_panel(queued)
    src = box(queued, card("claude_one"))
    dst = box(queued, row("claude_two"))
    queued.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    queued.mouse.down()
    queued.mouse.move(dst["x"] + 6, dst["y"] + 4, steps=8)
    assert marker_visible(queued)
    queued.evaluate(cancel)
    assert not marker_visible(queued)
    queued.mouse.up()
    assert no_write(queued), queued.ctb_posted
