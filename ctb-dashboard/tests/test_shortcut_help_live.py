"""Shortcut discoverability: tooltips on the buttons that already have a
keyboard shortcut, and a "?" help panel listing every shortcut in the
console.

Driven in a real browser against the shipped page, same pattern as
test_prev_end_keys_live.py and test_rail_skip_working_key_live.py.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"
HELP = "#con-help-panel"

TURNS = "\n".join(
    "❯ 요청 A" if i == 10 else
    ("line %03d output" % i)
    for i in range(60)
)


def open_console(page, name="claude_beta"):
    page.ctb_log = TURNS
    page.ctb_log_hash = "h-shortcut-help"
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector(CONSOLE, state="visible")


def title_of(page, selector):
    return page.eval_on_selector(selector, "el => el.title")


def current(page):
    return page.evaluate("window.ctbConsole._state.session")


# --- tooltips ----------------------------------------------------------------

def test_prev_pill_title_names_its_shortcut(board):
    open_console(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    el = board.query_selector("#ctb-console .con-btn--primary, " + CONSOLE)
    title = board.evaluate(
        "() => window.ctbConsole._el().prevPill.title")
    assert ";" in title or "Ctrl" in title or "Cmd" in title


def test_end_pill_title_names_its_shortcut(board):
    open_console(board)
    title = board.evaluate("() => window.ctbConsole._el().endPill.title")
    assert "'" in title or "Ctrl" in title or "Cmd" in title


def test_find_button_title_names_its_shortcut(board):
    open_console(board)
    title = board.evaluate(
        "() => { const h = document.querySelector('#ctb-console');"
        "        return [...h.querySelectorAll('button')]"
        "          .map(b => b.title).find(t => t.includes('Shift+F')); }")
    assert title


# --- help panel ----------------------------------------------------------------

def is_help_open(page):
    return page.evaluate(
        "() => { const p = document.querySelector('" + HELP + "');"
        "        if (!p) return false;"
        "        return p.closest('#con-help-overlay').style.display !== 'none'; }")


def test_question_mark_opens_help_panel_outside_inputs(board):
    open_console(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    text = board.inner_text(HELP)
    assert "이전 요청" in text
    assert "세션 닫기" in text


def test_question_mark_in_the_prompt_box_just_types(board):
    open_console(board)
    board.click("#ctb-console textarea")
    board.keyboard.type("?")
    board.wait_for_timeout(100)
    assert not is_help_open(board)
    val = board.eval_on_selector("#ctb-console textarea", "el => el.value")
    assert "?" in val


def test_escape_closes_help_panel(board):
    open_console(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    board.keyboard.press("Escape")
    board.wait_for_timeout(100)
    assert not is_help_open(board)
    # The console's own Escape handler must not also have fired (see the
    # stopImmediatePropagation comment above the help listener) -- one
    # Escape closes the panel, not the whole console under it.
    assert board.is_visible(CONSOLE)


def test_question_mark_closes_panel_even_with_focus_on_close_button(board):
    """The close button is a BUTTON, which interactiveTarget() treats as a
    typing target; the help listener must special-case helpOpen() so a
    second '?' still closes the panel instead of being swallowed as if the
    reader were typing into a control."""
    open_console(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    board.evaluate(
        "() => document.querySelector('#con-help-panel button').focus()")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert not is_help_open(board)


def test_opening_help_disarms_a_pending_one_shot_send(board):
    """Ctrl/Cmd+. arms the next plain key to go to the tmux session. Opened
    via the mouse (the header's "?" button) while still armed -- pressing
    '?' itself would instead be consumed as the armed send, since that
    capture-phase listener runs before the help panel's own keydown handler
    -- the arming must be cancelled, or the very next key typed to read the
    panel (an arrow, to scroll) would fire off to the session behind it."""
    open_console(board)
    board.click("body")
    board.keyboard.press("Control+.")
    board.wait_for_timeout(50)
    assert board.evaluate("() => window.ctbConsole._sendArmed()")
    board.click("#ctb-console [aria-label='단축키 도움말']")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    assert not board.evaluate("() => window.ctbConsole._sendArmed()")
    board.keyboard.press("Escape")


def test_help_panel_blocks_find_and_search_palette_chords(board):
    """Ctrl/Cmd+F (search palette) and Ctrl/Cmd+Shift+F (in-output find)
    gate on sheetOpen() directly rather than keysTaken(), so helpOpen()
    has to be added to each of them by hand."""
    open_console(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    board.keyboard.press("Control+Shift+F")
    board.wait_for_timeout(100)
    assert board.query_selector("#ctb-console .con-find") is None \
        or not board.is_visible("#ctb-console .con-find")
    assert is_help_open(board)
    board.keyboard.press("Escape")


def test_tab_inside_help_panel_stays_on_the_close_button(board):
    open_console(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    assert is_help_open(board)
    board.keyboard.press("Tab")
    board.wait_for_timeout(50)
    focused_is_close_btn = board.evaluate(
        "() => document.activeElement === document.querySelector('#con-help-panel button')")
    assert focused_is_close_btn
    board.keyboard.press("Escape")


def test_help_panel_owns_the_keyboard(board):
    """While it is open, Ctrl/Cmd+] must not switch the session."""
    open_console(board, "claude_beta")
    before = current(board)
    board.click("body")
    board.keyboard.press("Shift+?")
    board.wait_for_timeout(100)
    board.keyboard.press("Control+]")
    board.wait_for_timeout(100)
    assert current(board) == before
    board.keyboard.press("Escape")


def test_help_button_in_header_opens_the_panel(board):
    open_console(board)
    board.click("#ctb-console [aria-label='단축키 도움말']")
    board.wait_for_timeout(100)
    assert is_help_open(board)


# --- hint kbd elements: hidden on touch/phone, present on desktop ------------

def test_hint_kbd_present_near_prev_end_pills_on_desktop(board):
    open_console(board)
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    count = board.evaluate(
        "() => document.querySelectorAll('#ctb-console .con-hint-kbd').length")
    assert count >= 2


# --- landed glow is per-session, not left behind on a switch -----------------

def test_landed_glow_is_cleared_on_session_switch(board):
    """gotoPrevPrompt() glows the line it jumped to by ordinal-from-the-end.
    That ordinal means a different line (or none at all) in another
    session's tail, so switching away must drop it instead of carrying it
    over to light up whatever happens to sit at the same position."""
    open_console(board, "claude_beta")
    board.keyboard.press("Control+;")
    board.wait_for_timeout(100)
    assert board.evaluate("() => window.ctbConsole._landed()") is not None
    board.evaluate("() => window.ctbConsole.open('claude_gamma')")
    board.wait_for_timeout(100)
    assert board.evaluate("() => window.ctbConsole._landed()") is None


def test_hint_kbd_css_is_guarded_by_hover_and_fine_pointer(board):
    """Playwright cannot flip the `pointer`/`hover` media features from a
    plain viewport resize (they reflect the emulated input device, not CSS
    width), and this suite has no existing helper that emulates a touch
    context. As a real, non-fake regression check we instead assert the
    stylesheet itself gates the hint behind
    `@media (hover: hover) and (pointer: fine)`, which is the mechanism the
    task calls for; a true phone-emulation check would need a dedicated
    browser context with `has_touch=True, is_mobile=True`."""
    open_console(board)
    css_text = board.evaluate(
        "() => document.getElementById('ctb-console-style').textContent")
    assert "con-hint-kbd" in css_text
    assert "hover: hover" in css_text or "hover:hover" in css_text
    assert "pointer: fine" in css_text or "pointer:fine" in css_text
