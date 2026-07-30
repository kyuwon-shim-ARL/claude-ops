"""Discrete key sending -- how a phone answers Claude's permission prompts.

send_prompt deliberately refuses when a session is WAITING_INPUT, which is
precisely when a y/n or numbered choice is needed. This endpoint covers that
gap, and its safety property is the allowlist: it must not become a way to type
shell commands around the destructive-command screening.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard import session_input
from ctb_dashboard.server import app

_SECRET = "key-endpoint-secret"
AUTH = {"X-CTB-Secret": _SECRET}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    sent = []
    monkeypatch.setattr(_srv, "send_key", lambda name, key: sent.append((name, key)))
    return sent


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("key", ["Enter", "Escape", "y", "n", "1", "2", "Up", "Down", "C-c"])
def test_allowlisted_keys_are_sent(client, keys, key):
    r = client.post("/api/sessions/claude_demo/key", json={"key": key}, headers=AUTH)
    assert r.status_code == 200
    assert keys == [("claude_demo", key)]


@pytest.mark.parametrize("key", [
    "rm -rf /",        # a command, not a key
    "C-u",             # not allowlisted
    "M-x",
    "sudo",
    "",
    "Enter Enter",
    "q",
])
def test_non_allowlisted_input_is_422(client, keys, key):
    r = client.post("/api/sessions/claude_demo/key", json={"key": key}, headers=AUTH)
    assert r.status_code == 422
    assert keys == [], "nothing outside the allowlist may reach tmux"


def test_requires_token(client, keys):
    r = client.post("/api/sessions/claude_demo/key", json={"key": "Enter"})
    assert r.status_code == 403
    assert keys == []


def test_unknown_session_is_404(client, keys):
    r = client.post("/api/sessions/nope/key", json={"key": "Enter"}, headers=AUTH)
    assert r.status_code == 404
    assert keys == []


def test_invalid_session_name_is_422(client, keys):
    r = client.post("/api/sessions/bad%20name!/key", json={"key": "Enter"}, headers=AUTH)
    assert r.status_code == 422
    assert keys == []


def test_tmux_failure_is_502(client, keys, monkeypatch):
    def blow_up(name, key):
        raise RuntimeError("tmux send-keys failed")

    monkeypatch.setattr(_srv, "send_key", blow_up)
    r = client.post("/api/sessions/claude_demo/key", json={"key": "Enter"}, headers=AUTH)
    assert r.status_code == 502


# --- the allowlist itself ---------------------------------------------------

def test_send_key_rejects_outside_allowlist_before_tmux(monkeypatch):
    calls = []
    monkeypatch.setattr(session_input.subprocess, "run",
                        lambda argv, **kw: calls.append(argv))
    with pytest.raises(ValueError):
        session_input.send_key("claude_demo", "C-u")
    assert calls == []


def test_allowlist_has_no_multi_key_or_command_entries():
    """A space would mean 'more than one key' and defeat the point."""
    for key in session_input.ALLOWED_KEYS:
        assert " " not in key, f"{key!r} is not a single key"
        assert key, "empty key in allowlist"


def test_allowlist_covers_permission_prompt_answers():
    """The reason this endpoint exists."""
    required = {"y", "n", "Enter", "Escape", "1", "2", "Up", "Down"}
    assert required <= session_input.ALLOWED_KEYS
