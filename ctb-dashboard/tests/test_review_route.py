"""Tests for GET /review — HMAC deep-link auth and consumed-links logic."""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app

_SECRET = "test-review-secret-xyz"


def _make_sig(card: str, focus: str, rv: str, exp: int, secret: str = _SECRET) -> str:
    msg = f"{card}|{focus}|{rv}|{exp}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _valid_params(tmp_path, rv="kyuwon-shim", exp_offset=3600):
    exp = int(time.time()) + exp_offset
    card = "gh-1"
    focus = ""
    sig = _make_sig(card, focus, rv, exp)
    return {"card": card, "focus": focus, "rv": rv, "exp": str(exp), "sig": sig}


@pytest.fixture(autouse=True)
def _patch_review(tmp_path, monkeypatch):
    monkeypatch.setattr(_srv, "_REVIEW_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "_REVIEW_OVERLAY_DIR", str(tmp_path))
    monkeypatch.setattr(_srv, "_REVIEW_LOCK_TIMEOUT", 5)
    yield


def test_unsigned_returns_403():
    client = TestClient(app)
    r = client.get("/review")
    assert r.status_code == 403


def test_missing_sig_returns_403():
    client = TestClient(app)
    exp = int(time.time()) + 3600
    r = client.get("/review", params={"rv": "kyuwon-shim", "exp": str(exp)})
    assert r.status_code == 403


def test_expired_returns_403(tmp_path):
    client = TestClient(app)
    exp = int(time.time()) - 1  # already expired
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp)
    r = client.get("/review", params={"card": "gh-1", "rv": "kyuwon-shim", "exp": str(exp), "sig": sig})
    assert r.status_code == 403


def test_invalid_sig_returns_403(tmp_path):
    client = TestClient(app)
    exp = int(time.time()) + 3600
    r = client.get("/review", params={
        "card": "gh-1", "rv": "kyuwon-shim", "exp": str(exp), "sig": "deadbeef"
    })
    assert r.status_code == 403


def test_valid_returns_200(tmp_path):
    client = TestClient(app)
    params = _valid_params(tmp_path)
    r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "PI Review Gate" in r.text


def test_replayed_returns_403(tmp_path):
    """Second request with same sig returns 403."""
    client = TestClient(app)
    params = _valid_params(tmp_path)
    r1 = client.get("/review", params=params)
    assert r1.status_code == 200
    r2 = client.get("/review", params=params)
    assert r2.status_code == 403


def test_write_failed_sig_can_retry(tmp_path):
    """A sig stored as write-failed is allowed one more attempt."""
    # Pre-seed consumed-links.json with write-failed status
    exp = int(time.time()) + 3600
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp)
    consumed_path = tmp_path / "consumed-links.json"
    consumed_path.write_text(json.dumps({
        "links": {sig: {"status": "write-failed", "consumed_at": "2026-01-01T00:00:00+00:00"}}
    }))

    client = TestClient(app)
    r = client.get("/review", params={
        "card": "gh-1", "rv": "kyuwon-shim", "exp": str(exp), "sig": sig
    })
    assert r.status_code == 200


def test_review_secret_not_set_returns_403(monkeypatch):
    monkeypatch.setattr(_srv, "_REVIEW_SECRET", "")
    client = TestClient(app)
    r = client.get("/review", params={"rv": "x", "exp": "9999999999", "sig": "abc"})
    assert r.status_code == 403


def test_review_lists_needs_pi_review_tickets(tmp_path):
    overlay = tmp_path / "ticket-overlay.json"
    overlay.write_text(json.dumps({
        "version": 1,
        "tickets": {
            "gh-42": {"review_state": "needs_pi_review", "updated_at": "2026-01-01T00:00:00+00:00"},
            "gh-99": {"review_state": "approved"},
        }
    }))
    client = TestClient(app)
    params = _valid_params(tmp_path)
    r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "gh-42" in r.text
    assert "gh-99" not in r.text
