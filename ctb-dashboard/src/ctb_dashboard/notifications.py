"""
Email dispatch and Telegram escalation for PI review notifications.
_send_email_cmd() is the subprocess boundary — patch it in tests.
"""
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_current_proc: subprocess.Popen | None = None


def _get_overlay_dir() -> str:
    return os.path.expanduser(
        os.environ.get("CTB_REVIEW_OVERLAY_DIR", "~/.claude-ops")
    )


def _send_email_cmd(to: str, subject: str, body: str) -> bool:
    """Subprocess boundary — patch this in tests to avoid real email sends."""
    global _current_proc
    try:
        _current_proc = subprocess.Popen(
            ["send-email", to, subject, body],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = _current_proc.communicate(timeout=30)
        rc = _current_proc.returncode
        _current_proc = None
        return rc == 0
    except Exception as e:
        logger.warning("send-email failed: %s", e)
        _current_proc = None
        return False


def load_reviewers(overlay_dir: str | None = None) -> dict[str, dict]:
    """Load reviewers.yaml. Returns {} and warns if missing/empty."""
    dir_ = overlay_dir or _get_overlay_dir()
    yaml_path = Path(dir_) / "reviewers.yaml"
    if not yaml_path.exists():
        print(f"[CTB WARNING] reviewers.yaml not found at {yaml_path}", file=sys.stderr)
        return {}
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(yaml_path.read_text()) or {}
        if not data:
            print(f"[CTB WARNING] reviewers.yaml is empty at {yaml_path}", file=sys.stderr)
            return {}
        return data
    except Exception as e:
        logger.warning("Failed to load reviewers.yaml: %s", e)
        return {}


def notification_config_status(overlay_dir: str | None = None) -> str:
    """Return ok|missing|empty for healthz."""
    dir_ = overlay_dir or _get_overlay_dir()
    yaml_path = Path(dir_) / "reviewers.yaml"
    if not yaml_path.exists():
        return "missing"
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(yaml_path.read_text()) or {}
        return "ok" if data else "empty"
    except Exception:
        return "missing"


def _update_notification_status(
    ticket_id: str, reviewer_id: str, status: str, overlay_path: str, lock_path: str
) -> None:
    """Update the latest review_history entry's notification_status for a reviewer."""
    from contextlib import nullcontext  # noqa: PLC0415
    import json, tempfile  # noqa: PLC0415, E401

    try:
        import filelock  # noqa: PLC0415
        lock = filelock.FileLock(lock_path, timeout=10)
    except ImportError:
        lock = None
    ctx = lock if lock else nullcontext()
    with ctx:
        try:
            with open(overlay_path) as f:
                data = json.load(f)
        except Exception:
            return
        tickets = data.get("tickets", {})
        ticket = tickets.get(ticket_id, {})
        history = ticket.get("review_history", [])
        # Find last needs_pi_review entry and update
        for entry in reversed(history):
            if entry.get("action") == "needs_pi_review":
                entry.setdefault("reviewer_statuses", {})[reviewer_id] = status
                break
        ticket["review_history"] = history
        tickets[ticket_id] = ticket
        data["tickets"] = tickets
        dir_ = os.path.dirname(overlay_path)
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, overlay_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass


async def dispatch_review_notification(
    ticket_id: str,
    reviewer_ids: list[str],
    signed_url: str,
    overlay_dir: str | None = None,
) -> dict[str, str]:
    """
    Dispatch email to each reviewer. 3 retries with exponential backoff.
    Returns dict of reviewer_id → sent|failed.
    """
    dir_ = overlay_dir or _get_overlay_dir()
    overlay_path = os.path.join(dir_, "ticket-overlay.json")
    lock_path = os.path.join(dir_, "overlay.lock")
    reviewers = load_reviewers(dir_)
    results: dict[str, str] = {}

    for rv_id in reviewer_ids:
        rv = reviewers.get(rv_id)
        if not rv or not rv.get("email"):
            logger.warning("No email found for reviewer %s", rv_id)
            results[rv_id] = "failed"
            continue

        subject = f"[CTB Review] Ticket {ticket_id} needs your review"
        body = (
            f"Ticket {ticket_id} has been submitted for PI review.\n\n"
            f"Review link (valid 72h): {signed_url}\n\n"
            "Click the link to approve or reject."
        )
        success = False
        for attempt in range(3):
            if _send_email_cmd(rv["email"], subject, body):
                success = True
                break
            await asyncio.sleep(2**attempt)

        status = "sent" if success else "failed"
        results[rv_id] = status
        _update_notification_status(ticket_id, rv_id, status, overlay_path, lock_path)

    return results


def _load_overlay_tickets(overlay_path: str) -> dict[str, Any]:
    import json  # noqa: PLC0415
    try:
        with open(overlay_path) as f:
            return json.load(f).get("tickets", {})
    except Exception:
        return {}


def _all_notifications_failed(ticket: dict) -> bool:
    """Check if all reviewer notification attempts have failed."""
    history = ticket.get("review_history", [])
    for entry in reversed(history):
        if entry.get("action") == "needs_pi_review":
            statuses = entry.get("reviewer_statuses", {})
            if not statuses:
                return False
            return all(v == "failed" for v in statuses.values())
    return False


def _hours_since(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        return delta.total_seconds() / 3600
    except Exception:
        return 0.0


async def _send_telegram(chat_id: str, message: str) -> None:
    """Send Telegram message via existing CTB bot configuration."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token or not chat_id:
            logger.warning("Telegram escalation: missing token or chat_id")
            return
        import urllib.request  # noqa: PLC0415
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = f'{{"chat_id": "{chat_id}", "text": {message!r}}}'.encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning("Telegram escalation failed: %s", e)


async def escalation_loop(
    overlay_dir: str | None = None,
    telegram_chat_id: str | None = None,
    interval_seconds: float = 900,
    escalation_hours: float = 24.0,
) -> None:
    """
    Runs every 15 min (default). Tickets with needs_pi_review + all-notifications-failed
    + older than escalation_hours → Telegram escalation.

    NOTE: In single-reviewer environments, the Telegram recipient may be the same
    person as the email recipient, limiting the usefulness of escalation. This feature
    is designed for multi-reviewer environments.
    """
    dir_ = overlay_dir or _get_overlay_dir()
    overlay_path = os.path.join(dir_, "ticket-overlay.json")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            tickets = _load_overlay_tickets(overlay_path)
            for ticket_id, ticket in tickets.items():
                if ticket.get("review_state") != "needs_pi_review":
                    continue
                if not _all_notifications_failed(ticket):
                    continue
                updated_at = ticket.get("updated_at", "")
                if _hours_since(updated_at) < escalation_hours:
                    continue
                msg = (
                    f"[CTB Escalation] Ticket {ticket_id} has been awaiting PI review "
                    f"for >{escalation_hours:.0f}h and all email notifications failed. "
                    "Manual review required."
                )
                logger.warning("Escalating ticket %s to Telegram", ticket_id)
                await _send_telegram(telegram_chat_id or "", msg)
        except asyncio.CancelledError:
            # Drain: wait for any running subprocess
            global _current_proc
            if _current_proc is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(
                            asyncio.get_event_loop().run_in_executor(None, _current_proc.wait)
                        ),
                        timeout=30,
                    )
                except asyncio.TimeoutError:
                    try:
                        _current_proc.kill()
                        _current_proc.wait()
                    except Exception:
                        pass
            raise
