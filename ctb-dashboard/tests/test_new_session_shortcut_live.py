"""The new-session sheet opens from the keyboard.

Same shape as the board's search shortcut: Ctrl/Cmd+N, or a bare "n" when
nothing is being typed into. The bare letter is what actually lands on a
desktop -- browsers keep Ctrl+N for "new window" and a page never sees it, so
the chord only reaches the page in an installed PWA window and the VSCode
webview, and this suite is the only place both can be exercised.

The sheet itself is untouched; what is asserted is when the key opens it and
when it must keep its hands off.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

PALETTE = "[role='dialog'][aria-label='세션 검색']"
SHEET = "#new-session-modal"


def opened(page):
    return page.eval_on_selector_all(
        SHEET, "els => els.some(e => e.style.display !== 'none')")


def test_bare_n_opens_the_sheet(board):
    board.keyboard.press("n")
    board.wait_for_selector(SHEET, state="visible")


def test_the_chord_opens_the_sheet(board):
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")


def test_typing_n_into_the_search_palette_does_not_open_it(board):
    """In a text field "n" is just a letter -- and the board's only text
    field is the session palette, since the filter box was retired."""
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.press("n")
    assert board.input_value(f"{PALETTE} input") == "n"
    assert not opened(board)


def test_ctrl_shift_n_is_left_to_the_browser(board):
    board.keyboard.press("Control+Shift+n")
    assert not opened(board)


CONSOLE = "#ctb-console"
QUAD_BTN = "#ctb-console button[aria-haspopup='menu']"


def open_console(page, name="claude_alpha"):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector(CONSOLE, state="visible")


def test_an_open_console_keeps_the_bare_letter(board):
    """A terminal surface with a caret in its prompt box: "n" is a letter."""
    open_console(board)
    board.keyboard.press("n")
    assert not opened(board)


def test_the_chord_works_over_an_open_console(board):
    """The point of the console is not having to go back to the board.

    Starting another session is part of that, so the chord reaches in.
    """
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    # And it draws above the console rather than under it. (Document order,
    # not the order the selectors are written in.)
    sheet_z = board.eval_on_selector(SHEET, "e => +getComputedStyle(e).zIndex")
    console_z = board.eval_on_selector(CONSOLE, "e => +getComputedStyle(e).zIndex")
    assert sheet_z > console_z


def test_the_console_search_palette_keeps_the_chord(board):
    """One overlay at a time; the palette already owns the keyboard."""
    open_console(board)
    board.keyboard.press("Control+f")
    board.wait_for_selector("[role='dialog'][aria-label='세션 검색']", state="visible")
    board.keyboard.press("Control+n")
    assert not opened(board)


def test_the_importance_menu_keeps_the_chord(board):
    open_console(board)
    board.click(QUAD_BTN)
    board.wait_for_selector("[data-quad-menu]")
    board.keyboard.press("Control+n")
    assert not opened(board)


def test_escape_closes_the_sheet_and_leaves_the_console(board):
    """Both handlers sit on the document, and both used to fire."""
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.keyboard.press("Escape")
    board.wait_for_selector(SHEET, state="hidden")
    assert board.is_visible(CONSOLE)


@pytest.mark.parametrize("chord", ["Control+Tab", "Control+]", "Control+2"])
def test_session_switches_stand_down_under_the_sheet(board, chord):
    """Each one walked to another session behind a dialog naming this one.

    The accelerator matters: a bare "]" was never bound, so pressing that
    proved nothing about the guard.
    """
    open_console(board, "claude_beta")
    open_console(board, "claude_alpha")      # gives Ctrl+Tab somewhere to go
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    before = board.evaluate("window.ctbConsole._state.session")
    board.keyboard.press(chord)
    board.wait_for_timeout(100)
    assert board.evaluate("window.ctbConsole._state.session") == before


def test_no_key_reaches_the_session_under_the_sheet(board):
    """Ctrl+U is a kill-line sent to tmux, not a local edit."""
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    before = [p for p in board.ctb_requests if p.endswith("/key")]
    board.keyboard.press("Control+u")
    board.wait_for_timeout(150)
    assert [p for p in board.ctb_requests if p.endswith("/key")] == before


def test_escape_when_the_sheet_was_built_first(board):
    """Which Escape listener runs first is decided by which was built first.

    Opened from the board once, the sheet's listener is registered before the
    console's, so the console's "stand down while the sheet is open" check
    runs after the sheet has already hidden itself -- and it closed the
    console too.
    """
    board.keyboard.press("n")                 # builds the sheet, from the board
    board.wait_for_selector(SHEET, state="visible")
    board.keyboard.press("Escape")
    board.wait_for_selector(SHEET, state="hidden")
    open_console(board)                       # builds the console second
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.keyboard.press("Escape")
    board.wait_for_selector(SHEET, state="hidden")
    assert board.is_visible(CONSOLE)


def test_tab_stays_inside_the_sheet(board):
    """Under it is a prompt box that reads Enter as "send to the session"."""
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    for _ in range(25):
        board.keyboard.press("Tab")
        assert board.evaluate(
            "() => document.getElementById('new-session-modal')"
            ".contains(document.activeElement)")


def test_speech_that_lands_late_does_not_steal_the_caret(board):
    """A clip recorded before the sheet went up can transcribe after it."""
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.evaluate("() => window.ctbConsole._sttDraft('받아쓴 문장')")
    assert board.evaluate(
        "() => document.getElementById('new-session-modal')"
        ".contains(document.activeElement)")
    # The text still lands in the console's prompt; only the caret stays put.
    assert "받아쓴 문장" in board.input_value("#ctb-console textarea")


def test_the_new_session_lands_in_the_console(board):
    """Created from in here, it opens here -- no trip back to the board."""
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.click("#new-session-projects button")          # pick a project
    board.click(f"{SHEET} button:has-text('세션 시작')")
    board.wait_for_selector(SHEET, state="hidden")
    board.wait_for_function(
        "() => window.ctbConsole._state.session === 'claude_fresh'")


def test_a_second_press_does_not_reopen_the_sheet(board):
    """show() refetches the project list and resets the form.

    Asserted by the fetch it would make: the field's own text survives a
    reopen, so the visible state cannot tell the two apart.
    """
    board.keyboard.press("n")
    board.wait_for_selector(SHEET, state="visible")
    board.wait_for_function(
        "() => document.querySelectorAll('#new-session-modal button').length > 0")
    before = board.ctb_requests.count("/api/projects")
    assert before > 0
    # The chord, not the bare letter: the caret sits in the sheet's search
    # field, where a bare "n" is just a character.
    board.keyboard.press("Control+n")
    board.wait_for_timeout(200)
    assert board.ctb_requests.count("/api/projects") == before


def test_the_cmd_chord_works_too(board):
    """Cmd+N on a Mac is the same request as Ctrl+N.

    Pressed over an open console: on the bare board an unrecognised modifier
    would fall through to the plain "n" shortcut and open the sheet anyway,
    so only a surface that swallows the letter can tell the two apart.
    """
    open_console(board)
    board.keyboard.press("Meta+n")
    board.wait_for_selector(SHEET, state="visible")


def test_a_dragged_card_keeps_the_key(board):
    """A sheet over the drop target loses the move that was in flight."""
    card = board.query_selector('[data-session-name="claude_alpha"]')
    box = card.bounding_box()
    board.mouse.move(box["x"] + 40, box["y"] + 20)
    board.mouse.down()
    board.mouse.move(box["x"] + 120, box["y"] + 90, steps=8)
    assert board.evaluate("window.ctbBoardBusy()")
    board.keyboard.press("n")
    assert not opened(board)
    board.mouse.up()


def test_an_open_delete_dialog_keeps_the_key(board):
    # Dispatched, not moved-to: Tailwind's grid is blocked in this fixture, so
    # the cards stack and a real pointer lands on whichever is on top.
    board.eval_on_selector('[data-delete-session="claude_gamma"]', "el => el.click()")
    board.wait_for_selector("#delete-modal", state="visible")
    board.keyboard.press("n")
    assert not opened(board)


def test_a_composing_ime_keeps_the_key(board):
    """Mid-Hangul, the keystroke belongs to the IME, not to a shortcut."""
    board.evaluate(
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key:'n', isComposing:true, bubbles:true}))")
    assert not opened(board)


def test_the_palette_chord_still_belongs_to_the_palette(board):
    """Ctrl+F claims the chord even with its own palette already open.

    Letting it through would hand the second press to the browser's find bar
    over a page whose search box is invisible behind the sheet.
    """
    open_console(board)
    board.keyboard.press("Control+f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.type("al")
    board.keyboard.press("Control+f")
    assert board.evaluate(
        """() => {
             const a = document.activeElement;
             return a.tagName === 'INPUT' && a.selectionStart === 0
                    && a.selectionEnd === a.value.length && a.value === 'al';
           }""")


def test_the_palette_chord_stands_down_under_the_sheet(board):
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.keyboard.press("Control+f")
    board.wait_for_timeout(100)
    assert not board.is_visible(PALETTE)


def test_focus_lands_in_the_sheet_in_new_project_mode(board):
    """The mode is remembered; the control that gets focus has to follow it.

    With the new-project pane up, focusing the (now hidden) project search
    left the caret in the console's prompt box: Tab from there sends a key to
    that session and Enter sends the draft, while the sheet is on screen.
    """
    open_console(board)
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    board.click(f"{SHEET} button:has-text('새 프로젝트')")
    board.keyboard.press("Escape")
    board.wait_for_selector(SHEET, state="hidden")
    board.click("#ctb-console textarea")          # the caret goes back under
    board.keyboard.press("Control+n")
    board.wait_for_selector(SHEET, state="visible")
    assert board.evaluate(
        "() => document.getElementById('new-session-modal')"
        ".contains(document.activeElement)")


@pytest.mark.parametrize("state_js", [
    "window.ctbConsole._state && (window.ctbConsole._stt().busy = true)",
    "window.ctbConsole._stt().rec = {}",
])
def test_a_mic_in_flight_keeps_the_chord(board, state_js):
    """Recording, or still acquiring: the sheet would cover its stop key."""
    open_console(board)
    board.evaluate(f"() => {{ {state_js}; }}")
    board.keyboard.press("Control+n")
    board.wait_for_timeout(100)
    assert not opened(board)


def test_a_close_in_flight_keeps_the_chord(board):
    """Close and restore both call show() on success, which moves the console."""
    open_console(board)
    board.evaluate("() => window.ctbConsole._setClosing(true)")
    board.keyboard.press("Control+n")
    board.wait_for_timeout(100)
    assert not opened(board)
