"""Every control endpoint that sends input must invalidate the stale screen
cache and kick the poller -- but only after the send actually lands, in that
order, and never on a refused or failed send. Escape, C-c, and /interrupt
additionally queue a hold-clear so a stopped WORKING session doesn't ride
out _WORKING_HOLD_SECONDS; Enter must not.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app
from ctb_dashboard.state_detector import SessionState

_SECRET = "kick-endpoint-secret"
AUTH = {"X-CTB-Secret": _SECRET}
_READY_SCREEN = "╭────────╮\n│ >      │\n╰────────╯"


class _RecordingAnalyzer:
    def __init__(self, events, state=SessionState.IDLE, screen=_READY_SCREEN):
        self._events = events
        self.state = state
        self.screen = screen

    def get_state(self, name, path=None, use_cache=True):
        return self.state

    def get_screen_content(self, name, use_cache=True):
        return self.screen

    def invalidate(self, name):
        self._events.append(("invalidate", name))


@pytest.fixture
def events():
    """Call-order ledger shared by the fake analyzer and the fake
    _kick_poller, so tests can assert ordering without timing."""
    return []


@pytest.fixture
def client(monkeypatch, events):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    monkeypatch.setattr(_srv, "pane_command", lambda name: "claude")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    monkeypatch.setattr(_srv, "_fast_until", 0.0)
    monkeypatch.setattr(_srv, "_hold_clear_pending", set())
    monkeypatch.setattr(_srv, "_poll_kick", None)

    analyzer = _RecordingAnalyzer(events)
    monkeypatch.setattr(_srv, "_state_analyzer", analyzer)

    def recording_kick():
        events.append(("kick", None))
        _srv._fast_until = _srv._fast_until + 1.0  # any real change is enough
        _srv._kick_event().set()

    monkeypatch.setattr(_srv, "_kick_poller", recording_kick)

    monkeypatch.setattr(_srv, "send_prompt", lambda name, text: True)
    monkeypatch.setattr(_srv, "send_free_text", lambda name, text, row, focused: True)
    monkeypatch.setattr(_srv, "send_key", lambda name, key: None)
    monkeypatch.setattr(_srv, "send_interrupt", lambda name: None)
    monkeypatch.setattr(_srv, "send_shell_line", lambda name, text: None)

    _srv._rate_limiter.reset()
    return TestClient(app)


def _fast_until_and_kick_state():
    return _srv._fast_until, _srv._kick_event().is_set()


# --- happy paths: invalidate before kick, in that order -------------------

def test_prompt_invalidates_then_kicks(client, events):
    r = client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert events == [("invalidate", "claude_demo"), ("kick", None)]


def test_shell_prompt_invalidates_then_kicks(client, events, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "_state_analyzer", _RecordingAnalyzer(events, screen="$ "))
    r = client.post(
        "/api/sessions/claude_demo/prompt",
        json={"text": "ls", "shell": True},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert events == [("invalidate", "claude_demo"), ("kick", None)]


def test_key_invalidates_then_kicks(client, events):
    r = client.post("/api/sessions/claude_demo/key", json={"key": "Enter"}, headers=AUTH)
    assert r.status_code == 200
    assert events == [("invalidate", "claude_demo"), ("kick", None)]


def test_interrupt_invalidates_then_kicks(client, events):
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 200
    assert events == [("invalidate", "claude_demo"), ("kick", None)]


# --- hold-clear: Escape / C-c / interrupt queue it, Enter does not --------

def test_enter_does_not_queue_hold_clear(client):
    client.post("/api/sessions/claude_demo/key", json={"key": "Enter"}, headers=AUTH)
    assert _srv._hold_clear_pending == set()


@pytest.mark.parametrize("key", ["Escape", "C-c"])
def test_escape_and_cc_queue_hold_clear(client, key):
    r = client.post("/api/sessions/claude_demo/key", json={"key": key}, headers=AUTH)
    assert r.status_code == 200
    assert _srv._hold_clear_pending == {"claude_demo"}


def test_interrupt_queues_hold_clear(client):
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 200
    assert _srv._hold_clear_pending == {"claude_demo"}


# --- refused / failed sends: no invalidate, no kick, _fast_until untouched -

def test_prompt_refused_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    # WAITING_INPUT with an ordinary Claude screen -> refused as awaiting_choice.
    monkeypatch.setattr(
        _srv, "_state_analyzer",
        _RecordingAnalyzer(events, state=SessionState.WAITING_INPUT, screen=_READY_SCREEN),
    )
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 409
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_prompt_tmux_failure_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    def boom(name, text):
        raise RuntimeError("tmux exploded")

    monkeypatch.setattr(_srv, "send_prompt", boom)
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 502
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_shell_prompt_refused_command_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "rm")  # not allow-listed
    before = _fast_until_and_kick_state()
    r = client.post(
        "/api/sessions/claude_demo/prompt",
        json={"text": "-rf /", "shell": True},
        headers=AUTH,
    )
    assert r.status_code == 409
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_key_not_allowed_leaves_fast_until_and_kick_untouched(client, events):
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/key", json={"key": "F13"}, headers=AUTH)
    assert r.status_code == 422
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_key_tmux_failure_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    def boom(name, key):
        raise RuntimeError("tmux exploded")

    monkeypatch.setattr(_srv, "send_key", boom)
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/key", json={"key": "Enter"}, headers=AUTH)
    assert r.status_code == 502
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_interrupt_tmux_failure_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    def boom(name):
        raise RuntimeError("tmux exploded")

    monkeypatch.setattr(_srv, "send_interrupt", boom)
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 502
    assert events == []
    assert _fast_until_and_kick_state() == before


def test_interrupt_no_session_leaves_fast_until_and_kick_untouched(client, events, monkeypatch):
    monkeypatch.setattr(_srv, "session_exists", lambda name: False)
    before = _fast_until_and_kick_state()
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 404
    assert events == []
    assert _fast_until_and_kick_state() == before


# --- prompt: a stale cache entry must be gone after the send --------------

def test_prompt_send_clears_a_stale_screen_cache_entry(client, monkeypatch):
    """Not just the fake -- exercise the real analyzer's cache so a mutation
    that deletes the invalidate() call is actually caught."""
    from ctb_dashboard.state_detector import SessionStateAnalyzer
    import datetime

    real_analyzer = SessionStateAnalyzer()
    real_analyzer._screen_cache["claude_demo"] = ("stale screen from before send", datetime.datetime.now())
    # Still need get_state()/get_screen_content() to look ready for the
    # readiness gate -- swap in the ready screen beneath the stale cache
    # entry key by monkeypatching capture.
    monkeypatch.setattr(_srv, "_state_analyzer", real_analyzer)

    def fake_capture(name, use_cache=True):
        return _READY_SCREEN

    monkeypatch.setattr(real_analyzer, "get_screen_content", fake_capture)
    monkeypatch.setattr(real_analyzer, "get_state", lambda name, path=None, use_cache=True: SessionState.IDLE)

    r = client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert "claude_demo" not in real_analyzer._screen_cache
