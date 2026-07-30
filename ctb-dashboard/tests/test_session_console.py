"""Structural guards for the session console UI.

There is no JS runtime in this suite, so these assert the invariants that would
otherwise regress silently: the console stays in its own module, the tail poll
stays bounded to one session, and nothing inline sneaks past the CSP.
"""

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
    assert "e.key === 'Enter' && !e.shiftKey" in console_js
    assert "preventDefault" in console_js


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

@pytest.mark.parametrize("key", ["'y'", "'n'", "'Enter'", "'Escape'", "'Up'", "'Down'"])
def test_approval_keys_are_offered(console_js, key):
    assert key in console_js


def test_interrupt_control_exists(console_js):
    assert "/interrupt" in console_js


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
