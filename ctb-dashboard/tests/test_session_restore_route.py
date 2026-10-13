"""The delete route remembers what it closed; restore brings it back."""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard import session_restore as sr
from ctb_dashboard.server import app

_SECRET = "control-secret-under-test"
_H = {"X-CTB-Secret": _SECRET}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "_CLOSED_HISTORY_PATH", str(tmp_path / "closed.json"))
    monkeypatch.setattr(sr, "get_session_path", lambda name: str(tmp_path))
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: set())
    return TestClient(app)


def test_a_safe_delete_is_remembered(client, monkeypatch):
    monkeypatch.setattr(_srv, "delete_session", lambda n, f, w=True: {"status": "deleted", "session": n})
    r = client.post("/api/sessions/claude_x/delete", json={"force": False}, headers=_H)
    assert r.status_code == 200
    closed = client.get("/api/sessions/closed").json()["closed"]
    assert [c["session"] for c in closed] == ["claude_x"]


def test_a_trashed_worktree_is_remembered_with_its_trash_path(client, monkeypatch):
    monkeypatch.setattr(_srv, "delete_session",
                        lambda n, f, w=True: {"status": "deleted", "session": n, "trashed_to": "/r/.claude/trash/x-1",
                                            "trashed_from": "/r/.claude/worktrees/x"})
    client.post("/api/sessions/claude_r_wt_x/delete", json={"force": True}, headers=_H)
    closed = client.get("/api/sessions/closed").json()["closed"]
    assert closed[0]["trashed_to"] == "/r/.claude/trash/x-1"
    assert closed[0]["trashed_from"] == "/r/.claude/worktrees/x"


def test_a_blocked_delete_is_not_remembered(client, monkeypatch):
    monkeypatch.setattr(_srv, "delete_session",
                        lambda n, f, w=True: {"status": "blocked", "check": {"safe": False, "reasons": ["dirty"]}})
    r = client.post("/api/sessions/claude_x/delete", json={"force": False}, headers=_H)
    assert r.status_code == 409
    assert client.get("/api/sessions/closed").json()["closed"] == []


def test_restore_relaunches_the_last_closed_and_returns_it(client, monkeypatch):
    monkeypatch.setattr(_srv, "delete_session", lambda n, f, w=True: {"status": "deleted", "session": n})
    launched = []
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: launched.append(s))
    client.post("/api/sessions/claude_a/delete", json={"force": False}, headers=_H)
    client.post("/api/sessions/claude_b/delete", json={"force": False}, headers=_H)
    r = client.post("/api/sessions/restore", json={}, headers=_H)
    assert r.status_code == 200 and r.json()["session"] == "claude_b"
    assert launched == ["claude_b"]
    r = client.post("/api/sessions/restore", json={}, headers=_H)
    assert r.json()["session"] == "claude_a"
    assert client.post("/api/sessions/restore", json={}, headers=_H).status_code == 404


def test_restore_requires_the_token(client):
    assert client.post("/api/sessions/restore", json={}).status_code == 403
