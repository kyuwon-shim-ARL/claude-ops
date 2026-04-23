import json, os, tempfile, threading
import pytest
from unittest.mock import patch

def test_load_empty_overlay(tmp_path):
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with patch("ctb_dashboard.ticket_overlay._OVERLAY_PATH", overlay_path):
        from ctb_dashboard.ticket_overlay import load_overlay
        result = load_overlay()
    assert result == {}

def test_save_and_load_overlay(tmp_path):
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with patch("ctb_dashboard.ticket_overlay._OVERLAY_PATH", overlay_path):
        from ctb_dashboard.ticket_overlay import save_overlay, load_overlay
        tickets = {"gh-1": {"review_state": "approved"}}
        save_overlay(tickets)
        loaded = load_overlay()
    assert loaded["gh-1"]["review_state"] == "approved"

def test_apply_overlay_merges(tmp_path):
    overlay_path = str(tmp_path / "ticket-overlay.json")
    with patch("ctb_dashboard.ticket_overlay._OVERLAY_PATH", overlay_path):
        from ctb_dashboard.ticket_overlay import save_overlay, apply_overlay
        save_overlay({"gh-1": {"review_state": "needs_pi_review"}})
        tickets = [{"id": "gh-1", "title": "T"}, {"id": "gh-2", "title": "U"}]
        result = apply_overlay(tickets)
    assert result[0]["review_state"] == "needs_pi_review"
    assert "review_state" not in result[1]
