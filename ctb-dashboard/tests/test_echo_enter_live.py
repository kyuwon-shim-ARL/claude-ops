"""An Enter nobody pressed must not reach the session.

The audit log shows it on every day since at least 2026-09-20, on the phone
and on the desktop: a prompt, then within two seconds a bare Enter from the
same client -- 40 to 60 percent of sends. The send clears the box, so any
line-break event that lands after it hits the empty-box rule ("an empty box
means press Enter") and goes to the session as a keystroke. On a phone the
user pressed nothing.

Driven in a real browser; the echo is played as the event the phone could be
sending (a late beforeinput line break), since iOS's own keyboard cannot be.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

BOX = "#ctb-console textarea"


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector("#ctb-console", state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def line_break(page):
    page.eval_on_selector(BOX, """el => el.dispatchEvent(new InputEvent('beforeinput',
        {inputType: 'insertLineBreak', bubbles: true, cancelable: true}))""")


def enters(page):
    return [k for k in page.ctb_keys if k.get("key") == "Enter"]


def send_text(page, text="결과 알려줘"):
    page.fill(BOX, text)
    page.press(BOX, "Enter")
    page.wait_for_function(
        "() => document.querySelector('#ctb-console textarea').value === ''")


def test_a_line_break_echoing_a_send_is_not_sent_as_enter(board):
    open_console(board)
    send_text(board)
    line_break(board)                 # the echo, arriving after the box cleared
    board.wait_for_timeout(300)
    assert enters(board) == [], "an Enter nobody pressed went to the session"


def test_an_empty_enter_a_moment_later_still_goes(board):
    """Answering a prompt with Enter on an empty box is a real gesture and
    must keep working -- only the echo window is closed."""
    open_console(board)
    send_text(board)
    board.wait_for_timeout(1700)
    line_break(board)
    board.wait_for_timeout(300)
    assert len(enters(board)) == 1
    assert enters(board)[0].get("via", "").startswith("empty:beforeinput")


def test_an_empty_enter_with_no_send_before_it_goes(board):
    open_console(board)
    board.press(BOX, "Enter")
    board.wait_for_timeout(300)
    assert [k.get("via") for k in enters(board)] == ["empty:keydown"]


def test_the_key_pad_says_where_its_keys_came_from(board):
    open_console(board)
    board.click("#ctb-console button[aria-label='Tab 키 전송']")
    board.wait_for_timeout(300)
    assert board.ctb_keys and board.ctb_keys[-1] == {"key": "Tab", "via": "pad"}
