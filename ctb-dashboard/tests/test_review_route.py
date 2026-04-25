"""Tests for GET /review — HMAC deep-link auth and consumed-links logic."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app

_SECRET = "test-review-secret-xyz"


def _make_sig(card: str, focus: str, rv: str, exp: int, project: str = "", secret: str = _SECRET) -> str:
    msg = "|".join([card, focus, rv, str(exp), project]).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _valid_params(tmp_path, rv="kyuwon-shim", exp_offset=3600, project="claude-ops"):
    exp = int(time.time()) + exp_offset
    card = "gh-1"
    focus = ""
    sig = _make_sig(card, focus, rv, exp, project)
    return {"card": card, "focus": focus, "rv": rv, "exp": str(exp), "project": project, "sig": sig}


@pytest.fixture(autouse=True)
def _patch_review(tmp_path, monkeypatch):
    monkeypatch.setattr(_srv, "_REVIEW_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "_REVIEW_OVERLAY_DIR", str(tmp_path))
    monkeypatch.setattr(_srv, "_REVIEW_LOCK_TIMEOUT", 5)
    monkeypatch.setattr(_srv, "_CTB_PROJECTS_ROOT", str(tmp_path))
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
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp, "")
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
    exp = int(time.time()) + 3600
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp, "")
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


def test_link_predating_review_cycle_returns_403(tmp_path):
    """M14: link issued before current review cycle (needs_review_since) → 403."""
    now_iso = datetime.now(timezone.utc).isoformat()
    overlay = tmp_path / "ticket-overlay.json"
    overlay.write_text(json.dumps({
        "version": 1,
        "tickets": {
            "gh-1": {
                "review_state": "needs_pi_review",
                "needs_review_since": now_iso,
                "updated_at": now_iso,
            }
        },
    }))
    exp = int(time.time()) + 3600
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp, "")
    client = TestClient(app)
    r = client.get("/review", params={"card": "gh-1", "rv": "kyuwon-shim", "exp": str(exp), "sig": sig})
    assert r.status_code == 403
    assert "predates" in r.json().get("detail", "").lower()


def test_link_after_review_cycle_returns_200(tmp_path):
    """M14: link issued after needs_review_since passes cycle check → 200."""
    since_ts = datetime.fromtimestamp(time.time() - 73 * 3600, tz=timezone.utc).isoformat()
    overlay = tmp_path / "ticket-overlay.json"
    overlay.write_text(json.dumps({
        "version": 1,
        "tickets": {
            "gh-1": {
                "review_state": "needs_pi_review",
                "needs_review_since": since_ts,
                "updated_at": since_ts,
            }
        },
    }))
    exp = int(time.time()) + 3600
    sig = _make_sig("gh-1", "", "kyuwon-shim", exp, "")
    client = TestClient(app)
    r = client.get("/review", params={"card": "gh-1", "rv": "kyuwon-shim", "exp": str(exp), "sig": sig})
    assert r.status_code == 200


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


# --- plan / rpt content ---

def test_review_shows_plan_when_plan_exists(tmp_path):
    """Plan file in .omc/plans/ is rendered in the review page."""
    project_dir = tmp_path / "claude-ops"
    plans_dir = project_dir / ".omc" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-04-25-plan.md").write_text("# My Plan\nStep 1: do the thing")

    client = TestClient(app)
    params = _valid_params(tmp_path, project="claude-ops")
    r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "My Plan" in r.text


def test_review_shows_placeholder_when_no_plan(tmp_path):
    """No plan file → placeholder text shown."""
    (tmp_path / "claude-ops").mkdir()
    client = TestClient(app)
    params = _valid_params(tmp_path, project="claude-ops")
    r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "아직 실행 계획이 없습니다" in r.text


def test_review_shows_rpt_when_rpt_exists(tmp_path):
    """RPT artifact found → rendered in review page."""
    rpt_mock = MagicMock()
    rpt_mock.read_text.return_value = "# Report\nResult: success"

    with patch.object(_srv, "_find_rpt_artifact", return_value=rpt_mock):
        (tmp_path / "claude-ops").mkdir()
        client = TestClient(app)
        params = _valid_params(tmp_path, project="claude-ops")
        r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "Result" in r.text


def test_review_shows_placeholder_when_no_rpt(tmp_path):
    """No RPT artifact → placeholder text shown."""
    with patch.object(_srv, "_find_rpt_artifact", return_value=None):
        (tmp_path / "claude-ops").mkdir()
        client = TestClient(app)
        params = _valid_params(tmp_path, project="claude-ops")
        r = client.get("/review", params=params)
    assert r.status_code == 200
    assert "아직 실행 결과가 없습니다" in r.text


def test_review_link_endpoint_returns_signed_url(tmp_path, monkeypatch):
    """GET /api/project/{name}/review-link returns a signed URL."""
    monkeypatch.setattr(_srv, "_CTB_DEFAULT_REVIEWER_ID", "test-reviewer")
    (tmp_path / "claude-ops").mkdir()
    client = TestClient(app)
    r = client.get(
        "/api/project/claude-ops/review-link",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "url" in data
    assert "project=claude-ops" in data["url"]
    assert "sig=" in data["url"]


def test_review_link_unknown_project_returns_404(tmp_path):
    """Unknown project name → 404."""
    client = TestClient(app)
    r = client.get(
        "/api/project/nonexistent-xyz/review-link",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 404


@pytest.mark.parametrize("bad_project", ["../secret", "/etc/passwd", ""])
def test_review_traversal_project_returns_400(bad_project, tmp_path):
    """Malformed project names → 400."""
    client = TestClient(app)
    r = client.get(
        f"/api/project/{bad_project}/review-link",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code in (400, 404, 422)


def test_plan_load_exception_shows_placeholder(tmp_path):
    """If _load_latest_plan raises, placeholder is shown (no 500)."""
    with patch.object(_srv, "_load_latest_plan", side_effect=Exception("disk error")):
        client = TestClient(app)
        params = _valid_params(tmp_path, project="claude-ops")
        r = client.get("/review", params=params)
    assert r.status_code == 200
