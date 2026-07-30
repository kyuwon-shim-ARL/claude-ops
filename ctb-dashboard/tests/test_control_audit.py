"""Audit trail and rate limiting on the control endpoints.

The property that matters most here is a negative one: the prompt text must
never reach the log file. Everything else is bookkeeping.
"""

import json

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.control_audit as _audit_mod
import ctb_dashboard.server as _srv
from ctb_dashboard.control_audit import RateLimiter, record
from ctb_dashboard.server import app
from ctb_dashboard.state_detector import SessionState

_SECRET = "audit-secret"
AUTH = {"X-CTB-Secret": _SECRET}
SECRET_TEXT = "이건-로그에-절대-남으면-안-되는-프롬프트-본문"

_READY_SCREEN = "╭────────╮\n│ >      │\n╰────────╯"


class _ReadyAnalyzer:
    def get_state(self, name, path=None, use_cache=True):
        return SessionState.IDLE

    def get_screen_content(self, name, use_cache=True):
        return _READY_SCREEN


@pytest.fixture
def audit_log(tmp_path, monkeypatch):
    path = tmp_path / "control-audit.log"
    monkeypatch.setattr(_audit_mod, "AUDIT_PATH", str(path))
    return path


@pytest.fixture
def client(monkeypatch, audit_log):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    monkeypatch.setattr(_srv, "send_prompt", lambda name, text: None)
    monkeypatch.setattr(_srv, "send_key", lambda name, key: None)
    monkeypatch.setattr(_srv, "send_interrupt", lambda name: None)
    monkeypatch.setattr(_srv, "_state_analyzer", _ReadyAnalyzer())
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    _srv._rate_limiter.reset()
    return TestClient(app)


def _entries(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- the negative property --------------------------------------------------

def test_prompt_body_is_never_written_to_the_log(client, audit_log):
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": SECRET_TEXT}, headers=AUTH)
    assert r.status_code == 200

    raw = audit_log.read_text()
    assert SECRET_TEXT not in raw
    for fragment in SECRET_TEXT.split("-"):
        if len(fragment) > 3:
            assert fragment not in raw


# --- what it does record ----------------------------------------------------

def test_successful_prompt_is_recorded(client, audit_log):
    client.post("/api/sessions/claude_demo/prompt",
                json={"text": "hello"}, headers=AUTH)
    rows = _entries(audit_log)
    assert len(rows) == 1
    row = rows[0]
    assert row["endpoint"] == "prompt"
    assert row["session"] == "claude_demo"
    assert row["ok"] is True
    assert row["client"]
    assert row["ts"].endswith("Z")


@pytest.mark.parametrize("path,body,reason", [
    ("/api/sessions/nope/prompt", {"text": "hi"}, "no_session"),
    ("/api/sessions/claude_demo/prompt", {"text": "sudo rm -rf /"}, "dangerous_pattern"),
])
def test_rejections_are_recorded_with_a_reason(client, audit_log, path, body, reason):
    client.post(path, json=body, headers=AUTH)
    rows = _entries(audit_log)
    assert rows and rows[-1]["ok"] is False
    assert rows[-1]["reason"] == reason


def test_key_and_interrupt_are_recorded(client, audit_log):
    client.post("/api/sessions/claude_demo/key", json={"key": "y"}, headers=AUTH)
    client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    kinds = [r["endpoint"] for r in _entries(audit_log)]
    assert "key" in kinds and "interrupt" in kinds


def test_unauthenticated_calls_do_not_reach_the_audit(client, audit_log):
    """Auth is decided first, so a 403 is not an action worth recording."""
    client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"})
    assert _entries(audit_log) == []


def test_audit_write_failure_does_not_break_the_endpoint(client, monkeypatch):
    """Auditing must never be able to take down what it audits."""
    monkeypatch.setattr(_audit_mod, "AUDIT_PATH", "/proc/definitely/not/writable/x.log")
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200


# --- rate limiting ----------------------------------------------------------

def test_prompt_is_rate_limited(client):
    limit = _srv._rate_limiter.max_events
    for _ in range(limit):
        r = client.post("/api/sessions/claude_demo/prompt",
                        json={"text": "hi"}, headers=AUTH)
        assert r.status_code == 200
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 429


def test_rate_limit_is_recorded(client, audit_log):
    for _ in range(_srv._rate_limiter.max_events + 1):
        client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert _entries(audit_log)[-1]["reason"] == "rate_limited"


def test_key_shares_the_same_budget(client):
    """The resource being protected is tmux, not a per-route quota."""
    for _ in range(_srv._rate_limiter.max_events):
        client.post("/api/sessions/claude_demo/key", json={"key": "y"}, headers=AUTH)
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 429


def test_interrupt_is_not_rate_limited(client):
    """Stopping a runaway session must not be the thing you get throttled on."""
    for _ in range(_srv._rate_limiter.max_events):
        client.post("/api/sessions/claude_demo/key", json={"key": "y"}, headers=AUTH)
    r = client.post("/api/sessions/claude_demo/interrupt", headers=AUTH)
    assert r.status_code == 200


# --- limiter unit -----------------------------------------------------------

def test_window_slides():
    rl = RateLimiter(max_events=2, window=10)
    assert rl.allow(now=100) is True
    assert rl.allow(now=101) is True
    assert rl.allow(now=102) is False
    # Once the first two fall out of the window, capacity returns.
    assert rl.allow(now=111.5) is True


def test_reset_clears_the_window():
    rl = RateLimiter(max_events=1, window=60)
    assert rl.allow(now=1) is True
    assert rl.allow(now=2) is False
    rl.reset()
    assert rl.allow(now=3) is True


def test_record_creates_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "dir" / "audit.log"
    monkeypatch.setattr(_audit_mod, "AUDIT_PATH", str(target))
    record("prompt", "claude_demo", "127.0.0.1", True)
    assert target.exists()
    assert json.loads(target.read_text().strip())["session"] == "claude_demo"
