"""Tests for escalation_loop — simulated clock tests."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch


from ctb_dashboard.notifications import escalation_loop


def make_overlay(tmp_path, updated_hours_ago: float, all_failed: bool = True):
    ts = (datetime.now(timezone.utc) - timedelta(hours=updated_hours_ago)).isoformat()
    reviewer_statuses = {"kyuwon-shim": "failed"} if all_failed else {"kyuwon-shim": "sent"}
    data = {
        "version": 1,
        "tickets": {
            "gh-1": {
                "review_state": "needs_pi_review",
                "updated_at": ts,
                "review_history": [
                    {
                        "action": "needs_pi_review",
                        "ts": ts,
                        "reviewer_statuses": reviewer_statuses,
                    }
                ],
            }
        },
    }
    overlay_path = tmp_path / "ticket-overlay.json"
    overlay_path.write_text(json.dumps(data))
    return str(tmp_path)


def test_escalation_fires_after_24h(tmp_path):
    overlay_dir = make_overlay(tmp_path, updated_hours_ago=25.0, all_failed=True)

    async def run():
        telegram_calls = []

        async def mock_telegram(chat_id, msg):
            telegram_calls.append((chat_id, msg))

        with patch("ctb_dashboard.notifications._send_telegram", side_effect=mock_telegram):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_sleep.side_effect = [None, asyncio.CancelledError()]
                try:
                    await escalation_loop(
                        overlay_dir=overlay_dir,
                        telegram_chat_id="test-chat-id",
                        interval_seconds=0,
                        escalation_hours=24.0,
                    )
                except asyncio.CancelledError:
                    pass

        return telegram_calls

    calls = asyncio.run(run())
    assert len(calls) == 1
    assert "gh-1" in calls[0][1]


def test_escalation_does_not_fire_before_24h(tmp_path):
    overlay_dir = make_overlay(tmp_path, updated_hours_ago=12.0, all_failed=True)

    async def run():
        telegram_calls = []

        async def mock_telegram(chat_id, msg):
            telegram_calls.append(msg)

        with patch("ctb_dashboard.notifications._send_telegram", side_effect=mock_telegram):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_sleep.side_effect = [None, asyncio.CancelledError()]
                try:
                    await escalation_loop(
                        overlay_dir=overlay_dir,
                        telegram_chat_id="test-chat-id",
                        interval_seconds=0,
                        escalation_hours=24.0,
                    )
                except asyncio.CancelledError:
                    pass

        return telegram_calls

    calls = asyncio.run(run())
    assert len(calls) == 0


def test_escalation_does_not_fire_when_email_sent(tmp_path):
    overlay_dir = make_overlay(tmp_path, updated_hours_ago=25.0, all_failed=False)

    async def run():
        telegram_calls = []

        async def mock_telegram(chat_id, msg):
            telegram_calls.append(msg)

        with patch("ctb_dashboard.notifications._send_telegram", side_effect=mock_telegram):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_sleep.side_effect = [None, asyncio.CancelledError()]
                try:
                    await escalation_loop(
                        overlay_dir=overlay_dir,
                        telegram_chat_id="test-chat-id",
                        interval_seconds=0,
                        escalation_hours=24.0,
                    )
                except asyncio.CancelledError:
                    pass

        return telegram_calls

    calls = asyncio.run(run())
    assert len(calls) == 0


def test_escalation_cancelled_cleanly(tmp_path):
    overlay_dir = make_overlay(tmp_path, updated_hours_ago=0, all_failed=True)

    async def run():
        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=asyncio.CancelledError()):
            try:
                await escalation_loop(
                    overlay_dir=overlay_dir,
                    interval_seconds=0,
                )
            except asyncio.CancelledError:
                pass  # Expected clean exit

    asyncio.run(run())  # Should not raise or hang
