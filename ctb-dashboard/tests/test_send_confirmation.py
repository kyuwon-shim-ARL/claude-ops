"""A prompt must never disappear quietly.

tmux send-keys returns success no matter what is on the pane, so a send into a
shell, a permission prompt, or a busy session looks identical to a real one.
That is tolerable at a desk and not tolerable from a phone, where the screen is
not visible. Hence: refuse up front on a bad state, and confirm afterwards that
the pane actually changed.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app
from ctb_dashboard.session_readiness import (
    claude_ui_present,
    classify_readiness,
)
from ctb_dashboard.state_detector import SessionState

_SECRET = "confirm-secret"
AUTH = {"X-CTB-Secret": _SECRET}

CLAUDE_SCREEN = "\n".join([
    "· Thinking…",
    "╭──────────────────────────────────────╮",
    "│ >                                    │",
    "╰──────────────────────────────────────╯",
])
SHELL_SCREEN = "\n".join([
    "total 24",
    "drwxr-xr-x. 3 kyuwon kyuwon 4096 Jul 30 18:00 .",
    "[kyuwon@arl claude-ops]$ ",
])


# --- pure readiness classification -----------------------------------------

def test_idle_with_claude_ui_can_send():
    can, reason, _ = classify_readiness(SessionState.IDLE, CLAUDE_SCREEN)
    assert (can, reason) == (True, "ready")


def test_working_is_refused():
    can, reason, msg = classify_readiness(SessionState.WORKING, CLAUDE_SCREEN)
    assert can is False
    assert reason == "working"
    assert msg


def test_awaiting_choice_is_refused_and_points_at_key_sending():
    can, reason, msg = classify_readiness(SessionState.WAITING_INPUT, CLAUDE_SCREEN)
    assert can is False
    assert reason == "awaiting_choice"
    assert "키" in msg, "should tell the user to send a key instead"


def test_shell_is_refused_even_though_state_looks_idle():
    """A bare shell reads as IDLE to the detector -- the UI check is what catches it."""
    can, reason, _ = classify_readiness(SessionState.IDLE, SHELL_SCREEN)
    assert (can, reason) == (False, "shell")


@pytest.mark.parametrize("state", [
    SessionState.ERROR,
    SessionState.CONTEXT_LIMIT,
    SessionState.STUCK_AFTER_AGENT,
])
def test_broken_states_are_refused(state):
    can, reason, _ = classify_readiness(state, CLAUDE_SCREEN)
    assert can is False
    assert reason == state.value


def test_unknown_state_is_allowed_when_ui_is_present():
    """Transient read failures must not brick remote control."""
    can, _, _ = classify_readiness(SessionState.UNKNOWN, CLAUDE_SCREEN)
    assert can is True


def test_claude_ui_present_rejects_empty_and_shell():
    assert claude_ui_present(None) is False
    assert claude_ui_present("") is False
    assert claude_ui_present(SHELL_SCREEN) is False
    assert claude_ui_present(CLAUDE_SCREEN) is True


# --- endpoint behaviour -----------------------------------------------------

class FakeAnalyzer:
    def __init__(self, state, screens):
        self.state = state
        self.screens = list(screens)

    def get_state(self, name, path=None, use_cache=True):
        return self.state

    def get_screen_content(self, name, use_cache=True):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: True)
    monkeypatch.setattr(_srv, "send_prompt", lambda name, text: None)
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)

    def install(state, screens):
        monkeypatch.setattr(_srv, "_state_analyzer", FakeAnalyzer(state, screens))
        return TestClient(app)

    return install


def test_refuses_with_409_and_reports_state(wire):
    client = wire(SessionState.WORKING, [CLAUDE_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "refused"
    assert body["reason"] == "working"
    assert body["state"] == "working"
    assert body["message"]


def test_refusal_happens_before_anything_is_sent(wire, monkeypatch):
    sent = []
    monkeypatch.setattr(_srv, "send_prompt", lambda n, t: sent.append(t))
    client = wire(SessionState.WORKING, [CLAUDE_SCREEN])
    client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert sent == []


def test_confirmed_true_when_screen_changes(wire):
    client = wire(SessionState.IDLE, [CLAUDE_SCREEN, CLAUDE_SCREEN + "\nhi"])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["confirmed"] is True


def test_confirmed_false_when_screen_is_unchanged(wire):
    """Reported honestly rather than dressed up as success."""
    client = wire(SessionState.IDLE, [CLAUDE_SCREEN, CLAUDE_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["confirmed"] is False


def test_shell_session_is_refused_end_to_end(wire):
    client = wire(SessionState.IDLE, [SHELL_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "shell"
