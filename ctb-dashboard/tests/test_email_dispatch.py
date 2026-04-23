"""Tests for notifications.py — email dispatch and reviewer loading."""
import asyncio
import json
from unittest.mock import patch

import pytest

from ctb_dashboard.notifications import (
    dispatch_review_notification,
    load_reviewers,
    notification_config_status,
)


@pytest.fixture
def overlay_dir(tmp_path):
    overlay_path = tmp_path / "ticket-overlay.json"
    overlay_path.write_text(
        json.dumps({
            "version": 1,
            "tickets": {
                "gh-1": {
                    "review_state": "needs_pi_review",
                    "review_history": [{"action": "needs_pi_review", "ts": "2026-01-01T00:00:00+00:00"}],
                }
            },
        })
    )
    reviewers_path = tmp_path / "reviewers.yaml"
    reviewers_path.write_text("kyuwon-shim:\n  email: kyuwon.shim@ip-korea.org\n")
    return tmp_path


def test_load_reviewers_ok(overlay_dir):
    reviewers = load_reviewers(str(overlay_dir))
    assert "kyuwon-shim" in reviewers
    assert reviewers["kyuwon-shim"]["email"] == "kyuwon.shim@ip-korea.org"


def test_load_reviewers_missing_warns(tmp_path, capsys):
    reviewers = load_reviewers(str(tmp_path))
    assert reviewers == {}
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_load_reviewers_empty_warns(tmp_path, capsys):
    (tmp_path / "reviewers.yaml").write_text("")
    reviewers = load_reviewers(str(tmp_path))
    assert reviewers == {}
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_notification_config_status_ok(overlay_dir):
    assert notification_config_status(str(overlay_dir)) == "ok"


def test_notification_config_status_missing(tmp_path):
    assert notification_config_status(str(tmp_path)) == "missing"


def test_notification_config_status_empty(tmp_path):
    (tmp_path / "reviewers.yaml").write_text("")
    assert notification_config_status(str(tmp_path)) == "empty"


def test_dispatch_sends_email(overlay_dir):
    with patch("ctb_dashboard.notifications._send_email_cmd", return_value=True) as mock_send:
        results = asyncio.run(
            dispatch_review_notification("gh-1", ["kyuwon-shim"], "http://review-url", str(overlay_dir))
        )
    assert results["kyuwon-shim"] == "sent"
    assert mock_send.called
    call_args = mock_send.call_args[0]
    assert call_args[0] == "kyuwon.shim@ip-korea.org"
    assert "gh-1" in call_args[1]


def test_dispatch_retries_on_failure(overlay_dir):
    call_count = 0

    def flaky(to, subject, body):
        nonlocal call_count
        call_count += 1
        return call_count >= 3  # succeeds on 3rd attempt

    with patch("ctb_dashboard.notifications._send_email_cmd", side_effect=flaky):
        with patch("asyncio.sleep", return_value=None):
            results = asyncio.run(
                dispatch_review_notification("gh-1", ["kyuwon-shim"], "http://review-url", str(overlay_dir))
            )
    assert results["kyuwon-shim"] == "sent"
    assert call_count == 3


def test_dispatch_marks_failed_after_3_retries(overlay_dir):
    with patch("ctb_dashboard.notifications._send_email_cmd", return_value=False):
        with patch("asyncio.sleep", return_value=None):
            results = asyncio.run(
                dispatch_review_notification("gh-1", ["kyuwon-shim"], "http://review-url", str(overlay_dir))
            )
    assert results["kyuwon-shim"] == "failed"
    # Check overlay updated
    import json as _json
    data = _json.loads((overlay_dir / "ticket-overlay.json").read_text())
    history = data["tickets"]["gh-1"]["review_history"]
    needs_pr_entry = next((h for h in reversed(history) if h.get("action") == "needs_pi_review"), None)
    assert needs_pr_entry is not None
    assert needs_pr_entry.get("reviewer_statuses", {}).get("kyuwon-shim") == "failed"


def test_dispatch_unknown_reviewer(overlay_dir):
    results = asyncio.run(
        dispatch_review_notification("gh-1", ["unknown-person"], "http://url", str(overlay_dir))
    )
    assert results["unknown-person"] == "failed"
