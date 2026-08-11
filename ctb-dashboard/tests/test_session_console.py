"""Structural guards for the session console UI.

There is no JS runtime in this suite, so these assert the invariants that would
otherwise regress silently: the console stays in its own module, the tail poll
stays bounded to one session, and nothing inline sneaks past the CSP.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ctb_dashboard.server import app

SRC = Path(__file__).resolve().parents[1] / "src" / "ctb_dashboard"
CONSOLE_JS = SRC / "static" / "js" / "session-control.js"
TOKEN_JS = SRC / "static" / "js" / "control-token.js"
INDEX = SRC / "templates" / "index.html"


@pytest.fixture(scope="module")
def console_js() -> str:
    return CONSOLE_JS.read_text()


@pytest.fixture(scope="module")
def index_html() -> str:
    return INDEX.read_text()


# --- module separation (M5: index.html must not keep growing) ---------------

def test_console_lives_in_its_own_module():
    assert CONSOLE_JS.exists(), "console logic must be a separate static module"
    assert TOKEN_JS.exists()


def test_index_only_gains_the_trigger_not_the_logic(index_html):
    """The template should reference the console, not implement it."""
    assert "data-console-session" in index_html
    assert "/static/js/session-control.js" in index_html
    # Console implementation must not have leaked into the template. Only
    # console-specific markers -- index.html has its own unrelated timers.
    for marker in ("/prompt", "/key", "/interrupt", "ctb-console", "visualViewport"):
        assert marker not in index_html, f"{marker!r} belongs in the JS module"


def test_module_loads_after_its_dependency(index_html):
    """session-control.js calls window.ctbControl, so token JS must come first."""
    assert index_html.index("control-token.js") < index_html.index("session-control.js")


# --- CSP safety -------------------------------------------------------------

def test_no_inline_event_handlers_in_console_js(console_js):
    """CSP forbids inline handlers; the module must use addEventListener."""
    assert "addEventListener" in console_js
    for attr in ("onclick=", "onkeydown=", "onfocus=", "onsubmit="):
        assert attr not in console_js


def test_no_eval_or_new_function(console_js):
    for bad in ("eval(", "new Function("):
        assert bad not in console_js


# --- bounded polling (M3: one capture-pane per tick, not one per card) ------

def test_single_poll_timer(console_js):
    """Exactly one interval, so the poll cost cannot scale with card count."""
    assert console_js.count("setInterval(") == 1


def test_polling_targets_only_the_open_session(console_js):
    assert "state.session" in console_js
    # The tail request is built from the single open session, not a list.
    assert "'/api/sessions/' + encodeURIComponent(name) + '/log?lines='" in console_js


def test_polling_stops_on_close_and_when_hidden(console_js):
    assert "stopPolling" in console_js
    assert "visibilitychange" in console_js
    assert "document.hidden" in console_js


def test_stale_response_for_a_previous_session_is_discarded(console_js):
    """Switching sessions mid-flight must not paint the old pane."""
    assert "state.session !== name" in console_js


# --- input behaviour --------------------------------------------------------

def test_enter_sends_and_shift_enter_inserts_a_newline(console_js):
    assert "e.key === 'Enter'" in console_js
    assert "preventDefault" in console_js


# --- soft-keyboard IME -------------------------------------------------------
#
# Reported from a phone (2026-08-05): typing a prompt and pressing return left
# a newline in the box without sending, and it took another return or two to go.
# A soft-keyboard IME (Hangul here) does not report the return that commits a
# composition as Enter — it arrives with isComposing set, or as keyCode 229, or
# as an unnamed key — so a handler that only looks for key === 'Enter' misses
# it and the browser inserts a line break instead. Deciding on the line break
# itself is engine-independent: whatever the keyboard called it, the browser is
# telling us it is about to break the line, and without Shift that is the send.
# iOS WebKit cannot be launched on this host, so these pin the structure and a
# Chromium run covers the behaviour.

def _input_key_handlers(console_js: str) -> str:
    start = console_js.index("input.addEventListener('keydown'")
    return console_js[start:console_js.index("input.addEventListener('focus'", start)]


def test_a_composing_enter_does_not_submit_on_keydown(console_js):
    """Mid-composition the return belongs to the IME, not to us."""
    handlers = _input_key_handlers(console_js)
    assert "isComposing" in handlers
    assert "229" in handlers, "keyCode 229 is how a soft keyboard says 'IME is handling this'"


def test_an_inserted_line_break_sends(console_js):
    """The IME path: no Enter keydown ever arrives, only the line break."""
    handlers = _input_key_handlers(console_js)
    assert "beforeinput" in handlers
    assert "insertLineBreak" in handlers


def test_shift_enter_is_still_a_newline_on_the_line_break_path(console_js):
    """beforeinput carries no modifiers, so the keydown must record Shift."""
    handlers = _input_key_handlers(console_js)
    assert "shiftKey" in handlers
    body = handlers[handlers.index("beforeinput"):]
    assert "shift" in body.lower(), "the line-break path must honour Shift+Enter"


def test_textarea_is_used_so_multiline_is_possible(console_js):
    assert "createElement('textarea')" in console_js


def test_keyboard_overlap_is_handled(console_js):
    """Mobile: the sheet must sit above the on-screen keyboard."""
    assert "visualViewport" in console_js
    assert "scrollIntoView" in console_js


# --- honest reporting -------------------------------------------------------

def test_unconfirmed_send_is_surfaced_not_hidden(console_js):
    """confirmed:false must not be reported as a plain success."""
    assert "confirmed === false" in console_js


def test_refusal_and_block_paths_are_handled(console_js):
    for status in ("409", "400"):
        assert status in console_js


# --- approval-prompt keys (T7 UI) ------------------------------------------

@pytest.mark.parametrize("key", [
    "'y'", "'n'", "'Enter'", "'Escape'", "'Tab'", "'Up'", "'Down'",
    "'1'", "'2'", "'3'", "'4'", "'5'", "'Left'", "'Right'",
])
def test_approval_keys_are_offered(console_js, key):
    assert key in console_js


def test_every_offered_key_is_one_the_server_accepts(console_js):
    """A button the server rejects is a dead control on a phone."""
    from ctb_dashboard.session_input import ALLOWED_KEYS
    row = console_js[console_js.index("['y', 'y'"):]
    row = row[:row.index("].forEach")]
    offered = re.findall(r"\['[^']*', '([^']+)'", row)
    assert offered, "could not read the key row"
    unknown = sorted(set(offered) - set(ALLOWED_KEYS))
    assert not unknown, f"buttons the server would refuse: {unknown}"


def test_copy_button_works_without_a_secure_context(console_js):
    """The dashboard is served over plain http on the tailnet, where
    navigator.clipboard does not exist. The legacy execCommand path must be
    present and must not be gated behind the async API succeeding."""
    assert "execCommand('copy')" in console_js
    assert "legacyCopy" in console_js
    # Feature-detect, never assume the secure-context API.
    assert "navigator.clipboard && navigator.clipboard.writeText" in console_js


def test_copy_failure_tells_the_user_what_to_do(console_js):
    """A silent no-op copy is worse than none -- the fallback hint must exist."""
    # The JS source keeps Korean as \\u escapes, so match the escaped form.
    assert "\\uae38\\uac8c \\ub20c\\ub7ec" in console_js  # "길게 눌러" hint


def test_tail_text_is_selectable(console_js):
    """Manual long-press selection is the last resort; user-select must allow it."""
    assert "user-select:text" in console_js


def test_tap_range_selection_exists(console_js):
    """Tap a line, tap another, copy that span -- no drag, no model cooperation.

    Replaces the earlier [[COPY]] marker convention, which worked but rented
    space in the global CLAUDE.md that every session paid for on every turn.
    """
    assert "onLineTap" in console_js
    assert "selectionRange" in console_js
    assert "copySelection" in console_js
    assert "clearSelection" in console_js
    # No trace of the retired convention.
    for gone in ("[[COPY]]", "extractCopyBlock", "updateCopyChip"):
        assert gone not in console_js


def test_selection_uses_click_not_touchstart(console_js):
    """touchstart would fire mid-scroll and select lines the user was passing."""
    assert "tail.addEventListener('click'" in console_js
    # Match the listener registration, not the word in the explanatory comment.
    assert "addEventListener('touchstart'" not in console_js


def test_tail_refresh_is_frozen_while_selecting(console_js):
    """Lines must not shift under a finger mid-selection, and the poll must
    resume once the selection is cleared."""
    assert "if (state.selStart !== null) return;" in console_js
    assert "stopPolling();" in console_js
    assert "if (state.session && !state.timer) startPolling();" in console_js


def test_selection_resets_on_session_switch_and_close(console_js):
    assert console_js.count("state.selStart = null;") >= 2


def test_copied_text_is_cleaned(console_js):
    """Both whole-screen and range copies go through the same dedent path."""
    assert "cleanLines(state.lines.slice(range[0], range[1] + 1))" in console_js
    assert "cleanLines(state.lines.slice())" in console_js


def test_interrupt_control_exists(console_js):
    assert "/interrupt" in console_js


# --- card tap routing -------------------------------------------------------
#
# The 💬 button sits inside the card, and the card's own tap handler is
# registered on the grid — an ancestor of the card but a descendant of the
# document the console listens on. So the card handler runs FIRST and the
# console's stopPropagation() cannot undo it: tapping 💬 used to also fire the
# card action (desktop terminal focus), which is why the two controls looked
# identical on desktop. The card handler must opt out of the console button
# the same way it already opts out of pin and delete.

def _card_tap_handler(index_html: str) -> str:
    """The grid click listener that implements card tap."""
    start = index_html.index("// --- Card tap handler")
    # Terminate on the listener's own closing line, not on a nested callback's.
    return index_html[start:index_html.index("\n    });", start)]


def test_card_tap_ignores_the_console_button(index_html):
    handler = _card_tap_handler(index_html)
    assert "data-console-session" in handler, (
        "tapping 💬 must not also trigger the card action"
    )


def test_card_tap_opts_out_of_every_in_card_control(index_html):
    handler = _card_tap_handler(index_html)
    for control in ("data-pin-session", "data-delete-session", "data-console-session"):
        assert control in handler, f"card tap must skip {control}"


def _card_tap_branches(index_html: str) -> tuple:
    """(mobile, desktop) bodies of the handler's isMobile() split.

    Asserting on the whole handler cannot tell the two branches apart, so a
    swapped if/else — the likeliest regression here — would pass. Split first.
    """
    handler = _card_tap_handler(index_html)
    after_if = handler[handler.index("isMobile()) {") + len("isMobile()) {"):]
    mobile, _, desktop = after_if.partition("} else {")
    assert desktop, "card tap must keep an else branch for desktop"
    return mobile, desktop


def test_mobile_card_tap_opens_the_console(index_html):
    """On a phone the console is the primary action, not a clipboard copy.

    The copy predates the console and pasted `/sessions <name>` into Telegram;
    with the console shipped it only forces the user to hit a 24px icon.
    """
    mobile, desktop = _card_tap_branches(index_html)
    assert "ctbConsole.open" in mobile
    assert "ctbConsole.open" not in desktop, "console-open belongs to the mobile branch"
    assert "/sessions ${name}" not in mobile, (
        "the Telegram-era clipboard copy should no longer be the mobile action"
    )


def test_desktop_card_tap_still_focuses_the_terminal(index_html):
    """Focus switches the real tmux client — the console cannot replace it."""
    mobile, desktop = _card_tap_branches(index_html)
    assert "focusSession(card, name)" in desktop
    assert "focusSession" not in mobile, "a phone has no terminal to focus"


def _console_btn_media_query(index_html: str) -> str:
    """The whole @media block that styles .console-btn.

    Brace-matched rather than split on the first few `}`: reordering rules
    inside the block is behaviour-preserving CSS, and a helper that loses the
    block when that happens reports a confusing failure for a non-bug.
    """
    style = index_html[index_html.index("<style>"):index_html.index("</style>")]
    for m in re.finditer(r"@media[^{]*\{", style):
        depth, i = 0, m.end() - 1
        while i < len(style):
            if style[i] == "{":
                depth += 1
            elif style[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = style[m.start():i + 1]
        if ".console-btn" in block:
            return block
    raise AssertionError("no @media block targets .console-btn")


def test_console_button_is_hidden_on_mobile(index_html):
    """Mobile card tap already opens the console, so the icon is redundant."""
    block = _console_btn_media_query(index_html)
    assert "display: none" in block or "display:none" in block


def test_hiding_the_console_button_beats_its_inline_style(index_html):
    """The button carries inline display:flex, which only !important overrides."""
    assert "display:flex" in index_html[index_html.index("data-console-session"):][:400]
    block = _console_btn_media_query(index_html)
    assert "!important" in block, "inline display:flex would otherwise win"


def _is_mobile_body(index_html: str) -> str:
    js = index_html[index_html.index("function isMobile"):]
    return js[:js.index("}")]


def test_mobile_is_decided_by_pointer_not_width(index_html):
    """A phone in landscape is still a phone.

    The predicate used to also require innerWidth < 768, which most current
    phones exceed in landscape (iPhone 14: 852px). Rotating the device flipped
    the card tap to the desktop branch, where the tmux focus cannot succeed —
    it fell through to copying `/sessions <name>`, the very Telegram-era
    behaviour the console replaced. Pointer type does not change on rotation.
    """
    js = _is_mobile_body(index_html)
    assert "pointer: coarse" in js
    assert "innerWidth" not in js, "width must not decide this — landscape flips it"
    assert "768" not in js


def test_hide_rule_matches_the_isMobile_predicate(index_html):
    """CSS and JS must agree on what 'mobile' is, or the icon hides on a device
    whose card tap still focuses a terminal (leaving no way into the console)."""
    block = _console_btn_media_query(index_html)
    assert "pointer: coarse" in block
    for width_cond in ("max-width", "min-width"):
        assert width_cond not in block, (
            f"{width_cond} would reintroduce the orientation flip"
        )


def _no_attached_client_branch(index_html: str) -> str:
    """The focusSession branch taken when no tmux client is attached."""
    start = index_html.index("data.error === 'no_attached_client'")
    return index_html[start:index_html.index("} else {", start)]


def test_no_terminal_falls_back_to_the_console(index_html):
    """Copying `/sessions <name>` helps nobody when there is no terminal.

    The clipboard fallback assumes somewhere to paste it. If no tmux client is
    attached there is no such place, so hand the user the console instead —
    the one thing that still works without a terminal.
    """
    branch = _no_attached_client_branch(index_html)
    assert "ctbConsole.open" in branch
    assert "copyFallback" not in branch


def test_other_focus_failures_still_copy(index_html):
    """A server error is not 'no terminal' — the copy stays a useful escape."""
    body = index_html[index_html.index("function focusSession"):]
    body = body[:body.index("\n    }\n")]
    assert "copyFallback(card, cmd, 'Focus failed" in body
    assert "copyFallback(card, cmd, 'Network error" in body


def test_console_button_still_rendered_for_desktop(index_html):
    """Hiding is presentational — desktop's only route to the console stays."""
    assert "data-console-session" in index_html


# --- served correctly -------------------------------------------------------

def test_static_modules_are_served():
    client = TestClient(app)
    for path in ("/static/js/session-control.js", "/static/js/control-token.js"):
        r = client.get(path)
        assert r.status_code == 200, path


def test_dashboard_page_references_both_modules():
    client = TestClient(app)
    body = client.get("/").text
    assert "/static/js/control-token.js" in body
    assert "/static/js/session-control.js" in body


# --- service worker scope ----------------------------------------------------
#
# Root cause of every "push never registers" report (2026-08-09): the worker was
# registered from /static/sw.js, so its scope was /static/ and nothing
# controlled the app at /. navigator.serviceWorker.ready waits for an active
# worker in the *page's* scope, so it never settled and registration timed out
# at the first step. Confirmed in a browser: scope /static/, controller null,
# ready unresolved after 10s. The app-shell caching never worked either.

def test_the_worker_is_served_from_the_root():
    """Scope comes from the script's directory; only a root path governs /."""
    client = TestClient(app)
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "addEventListener('push'" in r.text


def test_the_page_registers_the_root_worker(index_html):
    assert "register('/sw.js'" in index_html
    assert "register('/static/sw.js')" not in index_html


def test_a_worker_left_at_the_old_scope_is_cleaned_up(index_html):
    """Phones carry the /static/ registration; it controls nothing and made
    getRegistrations() look healthy while push could not work."""
    assert "unregister" in index_html


# --- pins are shared state, and were read once ------------------------------
#
# Pins set in one client did not appear in another: /api/pinned was fetched only
# at connect. Worse, the stale cache is what a later pin action posts back, so
# an old tab could overwrite pins made elsewhere.

def test_pins_are_refreshed_after_the_initial_load(index_html):
    assert "refreshPinned" in index_html
    fetches = index_html.count("'/api/pinned'")
    assert fetches >= 2, "pins must be re-read, not only fetched at connect"


@pytest.mark.parametrize("fn_name", ["togglePin", "moveToQuadrant"])
def test_a_pin_change_is_one_serialised_read_modify_write(index_html, fn_name):
    """A pin change rewrites the whole set, so two must never overlap.

    Serialising only the writes was not enough: both clicks could still be
    inside their read when the other wrote, so each rebuilt from the same older
    copy and the second overwrote the first — pinning a second session appeared
    to unpin the first.
    """
    fn = index_html[index_html.index(f"function {fn_name}("):]
    fn = fn[:fn.index("\n    }\n")]
    assert "_queuePins" in fn, "must run inside the queue"
    assert "_fetchPins" in fn, "must re-read the server inside that step"
    assert fn.index("_fetchPins") < fn.index("_writePins"), "read before write"


def test_a_pin_click_repaints_after_the_change_lands(index_html):
    """togglePin became queued and async, so the render fired straight after it
    still drew the old cache — the pin looked like it bounced back, and a second
    click (thinking it had not registered) toggled it off again."""
    start = index_html.index("// --- Pin button event delegation ---")
    handler = index_html[start:index_html.index("\n    });", start)]
    assert "togglePin(" in handler
    assert ".then(" in handler or "await" in handler, (
        "the repaint must wait for the change to land"
    )
