"""Ctrl/Cmd+; walks back to the previous request, Ctrl/Cmd+' goes to the end --
the keyboard halves of the "이전 요청" and "끝으로" pills. Bound on `code`
(Semicolon / Quote) so a layout that prints something else on the cap still
works.

Driven in a real browser against the shipped page, because both are
document-level keydown listeners.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"

TURNS = "\n".join(
    "❯ 요청 A" if i == 10 else
    "❯ 요청 B" if i == 70 else
    ("line %03d output" % i)
    for i in range(120)
)


def with_turns(page):
    page.ctb_log = TURNS
    page.ctb_log_hash = "h-turns"
    page.evaluate("name => window.ctbConsole.open(name)", "claude_beta")
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def where(page, line):
    return page.evaluate(
        "line => { const el = document.querySelector('#ctb-console pre');"
        "          const n = el.querySelector(`[data-line='${line}']`);"
        "          return n.getBoundingClientRect().top"
        "                 - el.getBoundingClientRect().top; }", line)


def at_bottom(page):
    return page.eval_on_selector(
        "#ctb-console pre",
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 8")


def test_ctrl_semicolon_walks_back_one_request_at_a_time(board):
    with_turns(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(200)
    assert 0 < where(board, 70) < 80
    board.keyboard.press("Control+;")
    board.wait_for_timeout(200)
    assert 0 < where(board, 10) < 80


def test_ctrl_quote_goes_back_to_the_end(board):
    with_turns(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(200)
    assert not at_bottom(board)
    board.keyboard.press("Control+'")
    board.wait_for_function(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        return el.scrollHeight - el.scrollTop - el.clientHeight < 8; }")


def test_the_keys_bind_on_the_physical_key(board):
    """A layout that prints something else on the caps still reaches them."""
    with_turns(board)
    board.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown', "
        "{code:'Semicolon', key:'x', ctrlKey:true, bubbles:true, cancelable:true}))")
    board.wait_for_timeout(200)
    assert 0 < where(board, 70) < 80
    board.evaluate(
        "() => document.dispatchEvent(new KeyboardEvent('keydown', "
        "{code:'Quote', key:'x', ctrlKey:true, bubbles:true, cancelable:true}))")
    board.wait_for_timeout(300)
    assert at_bottom(board)


def test_without_the_modifier_the_keys_are_just_typing(board):
    with_turns(board)
    board.keyboard.press(";")
    board.wait_for_timeout(200)
    assert at_bottom(board)


# --- the landed request glows briefly ----------------------------------------

LONG = "\n".join(
    "❯ 요청 A" if i == 10 else
    "❯ 요청 B 첫 줄" if i == 70 else
    "  이어지는 둘째 줄" if i == 71 else
    ("line %03d output" % i)
    for i in range(120)
)


def lit(page):
    """Rows currently carrying the landing glow."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#ctb-console [data-line]')]"
        "  .filter(n => n.classList.contains('con-landed'))"
        "  .map(n => +n.getAttribute('data-line'))")


def open_long(page):
    page.ctb_log = LONG
    page.ctb_log_hash = "h-long"
    page.evaluate("name => window.ctbConsole.open(name)", "claude_beta")
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def test_the_request_landed_on_glows_with_its_continuation(board):
    open_long(board)
    assert lit(board) == []
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    assert lit(board) == [70, 71]


def test_the_glow_moves_with_the_walk(board):
    open_long(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    assert lit(board) == [10]


def test_the_glow_fades_out(board):
    open_long(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(2600)
    assert lit(board) == []


def test_a_repaint_mid_glow_does_not_wipe_it(board):
    open_long(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    board.evaluate("() => window.ctbConsole._renderTail(window.ctbConsole._state.lines.join('\\n'))")
    assert lit(board) == [70, 71]


# --- the pills stay out of the way until reached for -------------------------

PREV = "#ctb-console button[aria-label='이전 요청으로 가기']"


def opacity(page, sel):
    return page.eval_on_selector(sel, "el => +getComputedStyle(el).opacity")


def test_the_pill_is_faint_until_hovered(board):
    with_turns(board)
    board.wait_for_selector(PREV, state="visible")
    board.wait_for_timeout(300)                      # past the transition
    assert opacity(board, PREV) < 0.6
    board.hover(PREV)
    board.wait_for_timeout(300)
    assert opacity(board, PREV) == 1
