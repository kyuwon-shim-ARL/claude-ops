"""The work queue rides in the pin set.

`queue` is an ordered list of session names next to the four quadrants. A pin
file written before it existed has no such key, and a tab that loaded the page
before it existed posts sets without one -- neither may lose or wipe it.
"""

import json

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app

AUTH = {"X-CTB-Secret": "s"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(_srv, "_PINNED_PERSIST_PATH", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", "s")
    monkeypatch.setattr(_srv, "_pinned_state", {"Q1": [], "Q2": [], "Q3": [], "Q4": []})
    return TestClient(app)


def test_queue_round_trips(client, tmp_path):
    body = {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": [],
            "queue": ["claude_b", "claude_a"]}
    w = client.post("/api/pinned", json=body, headers=AUTH)
    assert w.status_code == 200
    assert w.json()["queue"] == ["claude_b", "claude_a"]
    assert client.get("/api/pinned").json()["queue"] == ["claude_b", "claude_a"]
    assert json.loads((tmp_path / "pinned.json").read_text())["queue"] == [
        "claude_b", "claude_a"]


def test_a_file_without_a_queue_reads_as_an_empty_one(client, monkeypatch):
    monkeypatch.setattr(_srv, "_pinned_state", {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": []})
    got = client.get("/api/pinned").json()
    assert got["Q1"] == ["claude_a"]
    assert got["queue"] == []


def test_an_old_payload_without_a_queue_is_accepted_and_keeps_the_queue(client):
    client.post("/api/pinned", json={"Q1": [], "Q2": [], "Q3": [], "Q4": [],
                                     "queue": ["claude_b"]}, headers=AUTH)
    w = client.post("/api/pinned", json={"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": []},
                    headers=AUTH)
    assert w.status_code == 200
    assert w.json()["Q1"] == ["claude_a"]
    assert w.json()["queue"] == ["claude_b"]


def test_an_explicit_empty_queue_clears_it(client):
    client.post("/api/pinned", json={"Q1": [], "Q2": [], "Q3": [], "Q4": [],
                                     "queue": ["claude_b"]}, headers=AUTH)
    w = client.post("/api/pinned", json={"Q1": [], "Q2": [], "Q3": [], "Q4": [],
                                         "queue": []}, headers=AUTH)
    assert w.json()["queue"] == []


def test_queued_but_unpinned_is_not_pinned(monkeypatch):
    """Completion alerts go to pinned sessions only; a session in the queue
    and in no quadrant is not one of them."""
    monkeypatch.setattr(_srv, "_pinned_state",
                        {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": [],
                         "queue": ["claude_b", "claude_a"]})
    assert _srv.pinned_session_names() == {"claude_a"}
