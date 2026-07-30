"""HTTP contract for the prompt / interrupt endpoints.

These are the endpoints that let a phone drive a live coding session, so the
rejection paths matter as much as the happy path.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app
from ctb_dashboard.state_detector import SessionState

_SECRET = "prompt-endpoint-secret"
AUTH = {"X-CTB-Secret": _SECRET}

# A pane showing Claude's input box, so the readiness gate lets the send through.
# Readiness itself is covered in tests/test_send_confirmation.py.
_READY_SCREEN = "╭────────╮\n│ >      │\n╰────────╯"


class _ReadyAnalyzer:
    def get_state(self, name, path=None, use_cache=True):
        return SessionState.IDLE

    def get_screen_content(self, name, use_cache=True):
        return _READY_SCREEN


@pytest.fixture
def sent(monkeypatch):
    """Auth on, session present, session ready, tmux stubbed."""
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    monkeypatch.setattr(_srv, "_state_analyzer", _ReadyAnalyzer())
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    calls = []
    monkeypatch.setattr(_srv, "send_prompt", lambda name, text: calls.append((name, text)))
    monkeypatch.setattr(_srv, "send_interrupt", lambda name: calls.append((name, "<ESC>")))
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def test_prompt_is_delivered(client, sent):
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "테스트 돌려줘"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "sent"
    assert sent == [("claude_demo", "테스트 돌려줘")]


def test_multiline_prompt_is_accepted(client, sent):
    """Shift+Enter in the UI produces newlines; they must not be rejected."""
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "첫 줄\n둘째 줄"}, headers=AUTH)
    assert r.status_code == 200
    assert sent == [("claude_demo", "첫 줄\n둘째 줄")]


def test_invalid_session_name_is_422(client, sent):
    r = client.post("/api/sessions/bad%20name!/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 422
    assert sent == []


def test_unknown_session_is_404(client, sent):
    r = client.post("/api/sessions/not-a-session/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 404
    assert sent == []


def test_missing_token_is_403(client, sent):
    r = client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"})
    assert r.status_code == 403
    assert sent == [], "auth must be decided before anything reaches tmux"


def test_destructive_text_is_blocked(client, sent):
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "sudo rm -rf /"}, headers=AUTH)
    assert r.status_code == 400
    assert sent == []


def test_empty_text_is_422(client, sent, monkeypatch):
    def refuse(name, text):
        raise ValueError("prompt is empty")

    monkeypatch.setattr(_srv, "send_prompt", refuse)
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "   "}, headers=AUTH)
    assert r.status_code == 422


def test_tmux_failure_is_502_not_200(client, sent, monkeypatch):
    """A silent 200 on a failed send is the thing we most want to avoid."""
    def blow_up(name, text):
        raise RuntimeError("tmux send-keys failed (rc=1)")

    monkeypatch.setattr(_srv, "send_prompt", blow_up)
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 502


def test_interrupt_sends_escape(client, sent):
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "interrupted"
    assert sent == [("claude_demo", "<ESC>")]


def test_interrupt_requires_token(client, sent):
    assert client.post("/api/sessions/claude_demo/interrupt").status_code == 403
    assert sent == []


def test_interrupt_unknown_session_is_404(client, sent):
    r = client.post("/api/sessions/not-a-session/interrupt", headers=AUTH)
    assert r.status_code == 404
    assert sent == []
