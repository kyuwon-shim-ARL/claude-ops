"""Typing an answer into a chooser's "Type something." field from a phone.

AskUserQuestion puts a free-text row under its options. The prompt endpoint
refused every send while a chooser was up (awaiting_choice), so the one answer
that needs typing could not be given remotely: pressing the row's number from
the key pad opened the field, and then there was no way to put text in it.

Checked against a live Claude Code 2.1.282 pane: the row's digit focuses the
field, a bracketed paste lands in it, and Enter answers the question with the
pasted text verbatim. The fixtures are captures from that session.

The multi-select chooser is excluded on purpose: there the digit toggles a
checkbox instead of opening a field (askq_multiselect.txt).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
import ctb_dashboard.session_input as _inp
from ctb_dashboard.server import app
from ctb_dashboard.session_readiness import classify_readiness, free_text_row
from ctb_dashboard.state_detector import SessionState

FIX = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIX / name).read_text()


# --- finding the row ----------------------------------------------------------

def test_the_row_is_found_before_it_is_focused():
    assert free_text_row(fixture("askq_single_unfocused.txt")) == (3, False)


def test_the_row_is_found_once_focused():
    assert free_text_row(fixture("askq_single_focused_empty.txt")) == (3, True)


def test_the_row_is_found_once_text_replaces_its_label():
    """Typed text replaces "Type something." -- the label cannot be the key."""
    assert free_text_row(fixture("askq_single_focused_text.txt")) == (3, True)


def test_a_multi_select_chooser_has_no_field_to_type_into():
    assert free_text_row(fixture("askq_multiselect.txt")) is None


def test_a_menu_without_the_chat_row_is_not_askuserquestion():
    """A permission prompt is numbered too, and its rows must not be typed into."""
    screen = "\n".join([
        " Do you want to proceed?",
        " ❯ 1. Yes",
        "   2. Yes, and don't ask again",
        "   3. No, and tell Claude what to do differently (esc)",
        "─" * 40,
        "Enter to confirm · Esc to cancel",
    ])
    assert free_text_row(screen) is None


def test_no_screen_no_row():
    assert free_text_row(None) is None
    assert free_text_row("") is None


def test_an_old_chooser_in_scrollback_does_not_count():
    """Only a chooser still on the foot of the pane is being asked."""
    screen = fixture("askq_single_unfocused.txt").rstrip("\n") + "\n" + "\n".join([
        "● User answered Claude's questions:",
        "  ⎿  · Pick a size? → Small",
        "─" * 40,
        "❯ ",
        "─" * 40,
    ])
    assert free_text_row(screen) is None


# --- the gate -----------------------------------------------------------------

def test_a_chooser_with_a_field_lets_text_through():
    can, reason, _ = classify_readiness(
        SessionState.WAITING_INPUT, fixture("askq_single_unfocused.txt"), "claude")
    assert can and reason == "free_text"


def test_a_chooser_without_a_field_still_refuses():
    can, reason, _ = classify_readiness(
        SessionState.WAITING_INPUT, fixture("askq_multiselect.txt"), "claude")
    assert not can and reason == "awaiting_choice"


# --- the endpoint -------------------------------------------------------------

_SECRET = "free-text-secret"
AUTH = {"X-CTB-Secret": _SECRET}


class _ChooserAnalyzer:
    def __init__(self, screen):
        self.screen = screen

    def get_state(self, name, path=None, use_cache=True):
        return SessionState.WAITING_INPUT

    def get_screen_content(self, name, use_cache=True):
        return self.screen


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: True)
    monkeypatch.setattr(_srv, "pane_command", lambda name: "claude")
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    calls = []
    monkeypatch.setattr(_srv, "send_prompt",
                        lambda name, text: calls.append(("prompt", name, text)))
    monkeypatch.setattr(_srv, "send_free_text",
                        lambda name, text, row, focused:
                        calls.append(("free", name, text, row, focused)) or True)
    return monkeypatch, calls


def test_the_endpoint_answers_through_the_field(wired):
    mp, calls = wired
    mp.setattr(_srv, "_state_analyzer",
               _ChooserAnalyzer(fixture("askq_single_unfocused.txt")))
    r = TestClient(app).post("/api/sessions/claude_demo/prompt",
                             json={"text": "중간 크기"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert calls == [("free", "claude_demo", "중간 크기", 3, False)]


def test_the_endpoint_still_refuses_a_multi_select(wired):
    mp, calls = wired
    mp.setattr(_srv, "_state_analyzer",
               _ChooserAnalyzer(fixture("askq_multiselect.txt")))
    r = TestClient(app).post("/api/sessions/claude_demo/prompt",
                             json={"text": "x"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "awaiting_choice"
    assert calls == []


# --- the keystrokes -----------------------------------------------------------

class _Pane:
    """A tmux stand-in: records what was sent, plays back screens in order."""

    def __init__(self, monkeypatch, screens):
        self.sent = []
        self.screens = list(screens)
        monkeypatch.setattr(_inp, "_tmux", self._tmux)
        monkeypatch.setattr(_inp, "_capture", self._capture)
        monkeypatch.setattr(_inp, "_FIELD_POLL", 0)
        monkeypatch.setattr(_inp, "_ENTER_SETTLE", 0)

    def _tmux(self, argv, stdin_text=None):
        if argv[1] == "send-keys":
            self.sent.append(("key", argv[-1]))
        elif argv[1] == "load-buffer":
            self.sent.append(("paste", stdin_text))

    def _capture(self, name):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]


def test_an_unfocused_field_is_opened_by_its_digit_first(monkeypatch):
    focused = fixture("askq_single_focused_empty.txt")
    typed = fixture("askq_single_focused_text.txt")
    answered = "● User answered Claude's questions:\n" + "─" * 40 + "\n❯ \n" + "─" * 40
    pane = _Pane(monkeypatch, [focused, typed, answered])
    assert _inp.send_free_text("claude_demo", "중간 크기", 3, False) is True
    assert pane.sent == [("key", "3"), ("paste", "중간 크기"), ("key", "Enter")]


def test_a_focused_field_is_not_sent_the_digit(monkeypatch):
    """The digit would be typed into the field as a '3'."""
    typed = fixture("askq_single_focused_text.txt")
    answered = "● User answered Claude's questions:\n" + "─" * 40 + "\n❯ \n" + "─" * 40
    pane = _Pane(monkeypatch, [typed, answered])
    _inp.send_free_text("claude_demo", "중간 크기", 3, True)
    assert ("key", "3") not in pane.sent
    assert pane.sent[0] == ("paste", "중간 크기")


def test_newlines_are_flattened_for_a_one_line_field(monkeypatch):
    typed = fixture("askq_single_focused_text.txt")
    pane = _Pane(monkeypatch, [typed])
    _inp.send_free_text("claude_demo", "첫 줄\n둘째 줄", 3, True)
    assert ("paste", "첫 줄 둘째 줄") in pane.sent


def test_a_field_that_never_opens_is_not_typed_into(monkeypatch):
    """If the digit did not focus the field, the text would land elsewhere."""
    pane = _Pane(monkeypatch, [fixture("askq_single_unfocused.txt")])
    with pytest.raises(RuntimeError):
        _inp.send_free_text("claude_demo", "중간 크기", 3, False)
    assert pane.sent == [("key", "3")]
