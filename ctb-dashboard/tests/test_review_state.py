"""Tests for ReviewController state machine."""
import json
from unittest.mock import patch

import pytest

from ctb_dashboard.review import InvalidReviewTransition, ReviewController


def make_controller(tmp_path):
    return ReviewController(overlay_dir=str(tmp_path))


def test_mark_needs_review_from_planned(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1", reviewer_ids=["kyuwon-shim"])
    t = rc.get_ticket("gh-1")
    assert t["review_state"] == "needs_pi_review"
    assert t["review_history"][-1]["notification_status"] == "pending"


def test_mark_needs_review_suppress_notification(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1", suppress_notification=True)
    t = rc.get_ticket("gh-1")
    assert t["review_history"][-1]["notification_status"] == "suppressed"


def test_approve_from_needs_pi_review(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.approve("gh-1", "kyuwon-shim")
    t = rc.get_ticket("gh-1")
    assert t["review_state"] == "in_progress"
    actions = [h["action"] for h in t["review_history"]]
    assert "approved" in actions
    assert "in_progress" in actions


def test_reject_from_needs_pi_review(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.reject("gh-1", "kyuwon-shim", verdict_choice="discard")
    t = rc.get_ticket("gh-1")
    assert t["review_state"] == "rejected"
    assert t["review_history"][-1]["verdict_choice"] == "discard"


def test_revise_cycles_back_to_needs_pi_review(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.reject("gh-1", "kyuwon-shim")
    rc.revise("gh-1", "kyuwon-shim", comment="please revise scope")
    t = rc.get_ticket("gh-1")
    assert t["review_state"] == "needs_pi_review"
    actions = [h["action"] for h in t["review_history"]]
    assert "revising" in actions
    assert actions[-1] == "needs_pi_review"


def test_illegal_transition_planned_to_approved(tmp_path):
    rc = make_controller(tmp_path)
    with pytest.raises(InvalidReviewTransition):
        rc.approve("gh-1", "kyuwon-shim")


def test_illegal_transition_approved_to_rejected(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.approve("gh-1", "kyuwon-shim")
    with pytest.raises(InvalidReviewTransition):
        rc.reject("gh-1", "kyuwon-shim")


def test_illegal_transition_needs_pi_review_to_revising(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    with pytest.raises(InvalidReviewTransition):
        rc.revise("gh-1", "kyuwon-shim")


def test_double_approve_raises(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.approve("gh-1", "kyuwon-shim")
    with pytest.raises(InvalidReviewTransition):
        rc.approve("gh-1", "kyuwon-shim")


def test_history_trimmed_to_50(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-trim")
    # Manually inflate history beyond cap
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with open(overlay_path) as f:
        data = json.load(f)
    ticket = data["tickets"]["gh-trim"]
    old_entries = [{"action": f"old-{i}", "ts": "2020-01-01T00:00:00+00:00"} for i in range(55)]
    ticket["review_history"] = old_entries + ticket["review_history"]
    with open(overlay_path, "w") as f:
        json.dump(data, f)
    # Trigger another write to invoke trimming
    rc.reject("gh-trim", "kyuwon-shim")
    t = rc.get_ticket("gh-trim")
    assert len(t["review_history"]) <= 50


def test_history_overflow_written_to_audit(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-audit")
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with open(overlay_path) as f:
        data = json.load(f)
    ticket = data["tickets"]["gh-audit"]
    old_entries = [{"action": f"old-{i}", "ts": "2020-01-01T00:00:00+00:00"} for i in range(55)]
    ticket["review_history"] = old_entries + ticket["review_history"]
    with open(overlay_path, "w") as f:
        json.dump(data, f)
    rc.reject("gh-audit", "kyuwon-shim")
    audit_path = tmp_path / "gh-audit-audit.jsonl"
    assert audit_path.exists()
    lines = audit_path.read_text().strip().splitlines()
    assert len(lines) > 0


def test_audit_write_failure_retains_full_history(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-nofail")
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with open(overlay_path) as f:
        data = json.load(f)
    ticket = data["tickets"]["gh-nofail"]
    old_entries = [{"action": f"old-{i}", "ts": "2020-01-01T00:00:00+00:00"} for i in range(55)]
    ticket["review_history"] = old_entries + ticket["review_history"]
    with open(overlay_path, "w") as f:
        json.dump(data, f)
    with patch("ctb_dashboard.review._append_audit", return_value=False):
        rc.reject("gh-nofail", "kyuwon-shim")
    t = rc.get_ticket("gh-nofail")
    assert len(t["review_history"]) > 50


def test_list_needs_review(tmp_path):
    rc = make_controller(tmp_path)
    rc.mark_needs_review("gh-1")
    rc.mark_needs_review("gh-2")
    rc.mark_needs_review("gh-3")
    rc.approve("gh-3", "kyuwon-shim")
    pending = rc.list_needs_review()
    ids = {t["id"] for t in pending}
    assert "gh-1" in ids
    assert "gh-2" in ids
    assert "gh-3" not in ids


def test_overlay_dir_default_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CTB_REVIEW_OVERLAY_DIR", str(tmp_path))
    rc = ReviewController()
    assert rc.overlay_dir == str(tmp_path)
