"""Tests for reject_drafts.py — Haiku draft generation."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from ctb_dashboard.reject_drafts import generate_draft, schedule_draft


@pytest.fixture
def overlay_setup(tmp_path):
    overlay_path = str(tmp_path / "ticket-overlay.json")
    lock_path = str(tmp_path / "overlay.lock")
    data = {
        "version": 1,
        "tickets": {
            "gh-1": {
                "review_state": "rejected",
                "review_history": [
                    {"action": "rejected", "reviewer": "kyuwon-shim", "ts": "2026-01-01T00:00:00+00:00"}
                ],
            }
        },
    }
    with open(overlay_path, "w") as f:
        json.dump(data, f)
    return overlay_path, lock_path


def test_generate_draft_stores_result(tmp_path, overlay_setup):
    overlay_path, lock_path = overlay_setup
    semaphore = asyncio.Semaphore(1)
    draft_result = {"discard_rationale": "Not needed", "revised_plan_summary": "Revised scope"}

    with patch("ctb_dashboard.reject_drafts._haiku_draft", new_callable=AsyncMock, return_value=draft_result):
        asyncio.run(generate_draft("gh-1", "body", "comment", semaphore, overlay_path, lock_path))

    with open(overlay_path) as f:
        data = json.load(f)
    last_entry = data["tickets"]["gh-1"]["review_history"][-1]
    assert last_entry.get("reject_draft") == draft_result
    assert last_entry.get("draft_pending") is False


def test_generate_draft_timeout_stores_none(tmp_path, overlay_setup):
    overlay_path, lock_path = overlay_setup
    semaphore = asyncio.Semaphore(1)

    with patch("ctb_dashboard.reject_drafts._haiku_draft", new_callable=AsyncMock, return_value=None):
        asyncio.run(generate_draft("gh-1", "body", "comment", semaphore, overlay_path, lock_path))

    with open(overlay_path) as f:
        data = json.load(f)
    last_entry = data["tickets"]["gh-1"]["review_history"][-1]
    assert last_entry.get("reject_draft") is None
    assert last_entry.get("draft_pending") is False


def test_draft_pending_prevents_duplicate(tmp_path, overlay_setup):
    """Second call while first is pending should be a no-op."""
    overlay_path, lock_path = overlay_setup
    semaphore = asyncio.Semaphore(1)
    call_count = 0

    async def slow_haiku(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"discard_rationale": "x", "revised_plan_summary": "y"}

    async def run_both():
        t1 = asyncio.create_task(generate_draft("gh-1", "body", "comment", semaphore, overlay_path, lock_path))
        t2 = asyncio.create_task(generate_draft("gh-1", "body", "comment", semaphore, overlay_path, lock_path))
        await asyncio.gather(t1, t2)

    with patch("ctb_dashboard.reject_drafts._haiku_draft", side_effect=slow_haiku):
        asyncio.run(run_both())

    assert call_count == 1


def test_schedule_draft_returns_task(tmp_path, overlay_setup):
    overlay_path, lock_path = overlay_setup
    semaphore = asyncio.Semaphore(1)

    async def run():
        with patch("ctb_dashboard.reject_drafts._haiku_draft", new_callable=AsyncMock, return_value=None):
            task = schedule_draft("gh-1", "body", "comment", semaphore, overlay_path, lock_path)
            assert isinstance(task, asyncio.Task)
            await task

    asyncio.run(run())
