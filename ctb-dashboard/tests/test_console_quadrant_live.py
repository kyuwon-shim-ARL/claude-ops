"""Setting importance and notifications from inside the console.

A session's quadrant is set by dragging its card, and a completion push only
goes out for a pinned session -- both of which live on the board, underneath
the full-bleed console sheet. The header carries a control for them now, so
the decision can be made where the session is being watched.

Driven against the shipped page in a real browser; the pin write is asserted
by what the page actually POSTs.
"""

import time

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)


def last_write(page, timeout=5.0):
    """The pin set the page last POSTed.

    The menu closes before the write goes out -- the tap is painted first and
    reconciled behind it -- so waiting on the menu is not waiting on the
    write.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.ctb_posted:
            return page.ctb_posted[-1]
        page.wait_for_timeout(50)
    raise AssertionError("the page never wrote a pin set")


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector("#ctb-console", state="visible")


def menu_items(page):
    return page.eval_on_selector_all(
        "[data-quad-menu] [data-quad-set]",
        "els => els.map(e => e.dataset.quadSet + ':' + e.getAttribute('aria-checked'))",
    )


def test_button_reports_the_current_quadrant(board):
    open_console(board)  # claude_alpha is pinned in Q1
    title = board.get_attribute("#ctb-console button[aria-haspopup='menu']", "title")
    assert "긴급+중요" in title


def test_button_reports_an_unpinned_session_as_silent(board):
    open_console(board, "claude_gamma")  # in no quadrant
    title = board.get_attribute("#ctb-console button[aria-haspopup='menu']", "title")
    assert "알림 없음" in title


def test_menu_offers_four_quadrants_and_an_off_switch(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    assert menu_items(board) == [
        "Q1:true", "Q2:false", "Q3:false", "Q4:false", "none:false",
    ]


def test_choosing_a_quadrant_writes_it(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='Q3']")
    board.wait_for_function("() => !document.querySelector('[data-quad-menu]')")
    posted = last_write(board)
    assert posted["Q3"] == ["claude_alpha"]
    assert "claude_alpha" not in posted["Q1"]


def test_turning_notifications_off_unpins(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='none']")
    board.wait_for_function("() => !document.querySelector('[data-quad-menu]')")
    posted = last_write(board)
    assert all("claude_alpha" not in names for names in posted.values())


def test_menu_does_not_survive_a_session_switch(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    assert board.query_selector("[data-quad-menu]") is not None
    open_console(board, "claude_beta")
    assert board.query_selector("[data-quad-menu]") is None


def test_menu_does_not_survive_closing_the_console(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.evaluate("window.ctbConsole.close()")
    assert board.query_selector("[data-quad-menu]") is None


def test_a_refused_write_is_not_reported_as_success(board):
    """The server rejects the write; the console must not say it landed.

    The pin machinery paints optimistically and rolls back on failure, and its
    queue swallows the error -- so "the promise resolved" is not the same as
    "the change stuck".
    """
    open_console(board)
    board.ctb_refuse_writes = True
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='Q3']")
    last_write(board)
    board.wait_for_function(
        "() => document.querySelector('#ctb-console [role=status]')"
        ".textContent.includes('바꾸지 못했습니다')")


def test_pinning_clears_the_silent_badge(board):
    """Pinning is what turns completion alerts on; the badge must follow."""
    open_console(board, "claude_gamma")   # unpinned: the badge is showing
    board.wait_for_selector("#ctb-console [aria-label*='알림 없음']", state="visible")
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='Q4']")
    last_write(board)
    # Short deadline on purpose: the console's own poll repaints the strip
    # every couple of seconds, so a generous wait would pass even if the
    # change itself repainted nothing.
    board.wait_for_selector("#ctb-console [aria-label*='알림 없음']",
                            state="hidden", timeout=1000)


def test_clicking_the_icon_closes_the_menu(board):
    """The button holds an SVG; a click lands on the path, not the button.

    Dismissal runs in the capture phase, so a target the dismissal check does
    not recognise as the button closes the menu and the button's own handler
    then reopens it -- a toggle that never toggles off.
    """
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    assert board.query_selector("[data-quad-menu]") is not None
    board.click("#ctb-console button[aria-haspopup='menu'] svg")
    assert board.query_selector("[data-quad-menu]") is None


def test_the_menu_takes_the_keyboard(board):
    """Enter with a menu open must not send the prompt draft to the session."""
    open_console(board)
    board.fill("#ctb-console textarea", "not a command")
    board.click("#ctb-console button[aria-haspopup='menu']")
    assert board.evaluate(
        "document.activeElement.closest('[data-quad-menu]') !== null")
    board.keyboard.press("ArrowDown")
    board.keyboard.press("Enter")
    posted = last_write(board)
    assert posted["Q2"] == ["claude_beta", "claude_alpha"]


def test_escape_closes_the_menu_and_not_the_console(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.keyboard.press("Escape")
    assert board.query_selector("[data-quad-menu]") is None
    assert board.is_visible("#ctb-console")


def test_opening_the_search_palette_closes_the_menu(board):
    """The palette hands focus to the prompt box when it closes.

    With the menu still up underneath, Enter would send the draft to the
    session instead of choosing a quadrant.
    """
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    # The chord, not the button: a click anywhere outside the menu already
    # dismisses it, so the button path proves nothing about this.
    board.keyboard.press("Control+f")
    board.wait_for_selector("[role='dialog'][aria-label='세션 검색']",
                            state="visible", timeout=2000)
    assert board.query_selector("[data-quad-menu]") is None


def test_a_refused_write_leaves_the_server_set_alone(board):
    open_console(board)
    board.ctb_refuse_writes = True
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='Q3']")
    last_write(board)
    assert board.ctb_accepted == []


QUAD_HUE = {
    "Q1": "rgb(251, 113, 133)",
    "Q2": "rgb(240, 165, 0)",
    "Q3": "rgb(96, 165, 250)",
    "Q4": "rgb(168, 162, 189)",
}


def button_colour(page):
    return page.eval_on_selector(
        "#ctb-console button[aria-haspopup='menu']",
        "el => getComputedStyle(el).color")


def test_the_button_wears_its_quadrant_before_it_is_pressed(board):
    """The whole point: which quadrant, without opening the menu."""
    open_console(board)                      # alpha is Q1
    assert button_colour(board) == QUAD_HUE["Q1"]
    open_console(board, "claude_beta")       # Q2
    assert button_colour(board) == QUAD_HUE["Q2"]


def test_an_unpinned_session_gets_no_hue(board):
    open_console(board, "claude_gamma")
    assert button_colour(board) not in QUAD_HUE.values()


def test_the_colour_follows_a_change(board):
    open_console(board)
    assert button_colour(board) == QUAD_HUE["Q1"]
    board.click("#ctb-console button[aria-haspopup='menu']")
    board.click("[data-quad-menu] [data-quad-set='Q3']")
    last_write(board)
    board.wait_for_function(
        "() => getComputedStyle(document.querySelector("
        "  \'#ctb-console button[aria-haspopup=\\\'menu\\\']\')).color"
        " === 'rgb(96, 165, 250)'")


def test_each_menu_row_wears_the_quadrant_it_sets(board):
    open_console(board)
    board.click("#ctb-console button[aria-haspopup='menu']")
    for qid, hue in QUAD_HUE.items():
        assert board.eval_on_selector(
            f"[data-quad-menu] [data-quad-set='{qid}']",
            "el => getComputedStyle(el).color") == hue
