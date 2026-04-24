"""Tests for T4 session-ticket badge API endpoint."""

import json

from fastapi.testclient import TestClient

from ctb_dashboard.server import app

client = TestClient(app)


def test_session_ticket_links_status_ok():
    r = client.get("/api/session-ticket-links")
    assert r.status_code == 200


def test_session_ticket_links_headers_present():
    r = client.get("/api/session-ticket-links")
    assert "x-server-time" in r.headers
    assert "x-badge-ttl" in r.headers
    assert int(r.headers["x-badge-ttl"]) == 30
    assert int(r.headers["x-server-time"]) > 0


def test_session_ticket_links_json_structure():
    r = client.get("/api/session-ticket-links")
    data = r.json()
    assert "links" in data
    assert "ttl" in data
    assert isinstance(data["links"], dict)
    assert data["ttl"] == 30


def test_session_ticket_links_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("ctb_dashboard.server._TICKET_LINKS_PATH", str(tmp_path / "nonexistent.json"))
    r = client.get("/api/session-ticket-links")
    assert r.status_code == 200
    assert r.json()["links"] == {}


def test_session_ticket_links_reads_file(tmp_path, monkeypatch):
    links_file = tmp_path / "session-ticket-links.json"
    links_file.write_text(json.dumps({"my-session": {"ticket_id": "T42", "review_state": "needs_pi_review"}}))
    monkeypatch.setattr("ctb_dashboard.server._TICKET_LINKS_PATH", str(links_file))
    r = client.get("/api/session-ticket-links")
    data = r.json()
    assert "my-session" in data["links"]
    assert data["links"]["my-session"]["ticket_id"] == "T42"
