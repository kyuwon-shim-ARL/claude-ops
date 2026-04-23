"""Tests for T2 card atom component and /dev/cards preview route."""

from fastapi.testclient import TestClient

from ctb_dashboard.server import app

client = TestClient(app)


def test_dev_cards_renders():
    r = client.get("/dev/cards")
    assert r.status_code == 200
    assert "e023" in r.text or "card" in r.text.lower()


def test_root_has_alpine():
    r = client.get("/")
    assert r.status_code == 200
    assert "alpinejs" in r.text or "alpine" in r.text.lower()
    assert "Content-Security-Policy" in r.headers


def test_root_has_csp_nonce():
    r = client.get("/")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "nonce-" in csp
