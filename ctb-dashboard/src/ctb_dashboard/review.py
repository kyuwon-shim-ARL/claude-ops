"""
PI review state machine for CTB Dashboard.
Single shared lock file (overlay.lock) guards all overlay writes.
All writes use write-then-rename for atomicity.
"""
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_OVERLAY_DIR = os.path.expanduser("~/.claude-ops")
_HISTORY_CAP = 50
_LOCK_TIMEOUT_DEFAULT = 10

VALID_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"needs_pi_review"},
    "needs_pi_review": {"approved", "rejected"},
    "approved": {"in_progress"},
    "in_progress": set(),
    "rejected": {"discarded", "revising"},
    "revising": {"needs_pi_review"},
    "discarded": set(),
}


class InvalidReviewTransition(Exception):
    pass


def _get_overlay_dir() -> str:
    return os.path.expanduser(
        os.environ.get("CTB_REVIEW_OVERLAY_DIR", _DEFAULT_OVERLAY_DIR)
    )


def _get_lock_timeout() -> int:
    return int(os.environ.get("CTB_REVIEW_OVERLAY_LOCK_TIMEOUT", str(_LOCK_TIMEOUT_DEFAULT)))


def _get_filelock(lock_path: str):
    try:
        import filelock  # noqa: PLC0415
        return filelock.FileLock(lock_path, timeout=_get_lock_timeout())
    except ImportError:
        logger.warning("filelock not available; concurrent writes may corrupt overlay")
        return None


def _atomic_write(path: str, data: Any) -> None:
    """Write JSON to path using write-then-rename for atomicity."""
    dir_ = os.path.dirname(path)
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _append_audit(audit_path: str, entries: list[dict]) -> bool:
    """Append entries to audit JSONL. Returns True on success."""
    dir_ = os.path.dirname(audit_path)
    os.makedirs(dir_, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                # Preserve existing content
                try:
                    with open(audit_path) as existing:
                        for line in existing:
                            f.write(line)
                except FileNotFoundError:
                    pass
                for entry in entries:
                    f.write(json.dumps(entry) + "\n")
            os.replace(tmp, audit_path)
            return True
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning("audit.jsonl write failed for %s: %s", audit_path, e)
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewController:
    def __init__(self, overlay_dir: str | None = None):
        self.overlay_dir = overlay_dir or _get_overlay_dir()
        self._overlay_path = os.path.join(self.overlay_dir, "ticket-overlay.json")
        self._lock_path = os.path.join(self.overlay_dir, "overlay.lock")

    def _load(self) -> dict[str, Any]:
        try:
            with open(self._overlay_path) as f:
                return json.load(f).get("tickets", {})
        except FileNotFoundError:
            return {}

    def _save(self, tickets: dict[str, Any]) -> None:
        try:
            with open(self._overlay_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing["version"] = 1
        existing["tickets"] = tickets
        _atomic_write(self._overlay_path, existing)

    def _trim_history(self, ticket_id: str, history: list[dict]) -> list[dict]:
        """Keep last _HISTORY_CAP entries; archive overflow to audit.jsonl."""
        if len(history) <= _HISTORY_CAP:
            return history
        overflow = history[: len(history) - _HISTORY_CAP]
        kept = history[len(history) - _HISTORY_CAP :]
        audit_path = os.path.join(self.overlay_dir, f"{ticket_id}-audit.jsonl")
        ok = _append_audit(audit_path, overflow)
        if not ok:
            # Do NOT drop overflow — return full history unchanged
            logger.warning("audit append failed; retaining full history for %s", ticket_id)
            return history
        return kept

    def _transition(
        self,
        ticket_id: str,
        from_states: set[str],
        to_state: str,
        history_entry: dict,
    ) -> None:
        from contextlib import nullcontext  # noqa: PLC0415
        lock = _get_filelock(self._lock_path)
        ctx = lock if lock else nullcontext()
        with ctx:
            tickets = self._load()
            ticket = tickets.get(ticket_id, {})
            current = ticket.get("review_state", "planned")
            if current not in from_states:
                raise InvalidReviewTransition(
                    f"Cannot transition {ticket_id}: {current!r} → {to_state!r}. "
                    f"Expected one of {from_states!r}."
                )
            if to_state not in VALID_TRANSITIONS.get(current, set()):
                raise InvalidReviewTransition(
                    f"Transition {current!r} → {to_state!r} not allowed."
                )
            ticket["review_state"] = to_state
            history = ticket.get("review_history", [])
            history.append(history_entry)
            history = self._trim_history(ticket_id, history)
            ticket["review_history"] = history
            ticket["updated_at"] = _now_iso()
            tickets[ticket_id] = ticket
            self._save(tickets)

    def mark_needs_review(
        self,
        ticket_id: str,
        reviewer_ids: list[str] | None = None,
        suppress_notification: bool = False,
    ) -> None:
        """Transition to needs_pi_review. Allowed from planned or revising."""
        from contextlib import nullcontext  # noqa: PLC0415
        notification_status = "suppressed" if suppress_notification else "pending"
        lock = _get_filelock(self._lock_path)
        ctx = lock if lock else nullcontext()
        with ctx:
            tickets = self._load()
            ticket = tickets.get(ticket_id, {})
            current = ticket.get("review_state", "planned")
            if current not in {"planned", "revising"}:
                raise InvalidReviewTransition(
                    f"{ticket_id}: cannot mark_needs_review from {current!r}"
                )
            ticket["review_state"] = "needs_pi_review"
            if reviewer_ids:
                ticket.setdefault("reviewer_ids", reviewer_ids)
            history = ticket.get("review_history", [])
            history.append(
                {
                    "action": "needs_pi_review",
                    "ts": _now_iso(),
                    "notification_status": notification_status,
                }
            )
            history = self._trim_history(ticket_id, history)
            ticket["review_history"] = history
            ticket["updated_at"] = _now_iso()
            tickets[ticket_id] = ticket
            self._save(tickets)

    def approve(self, ticket_id: str, reviewer_id: str) -> None:
        """Transition needs_pi_review → approved → in_progress."""
        from contextlib import nullcontext  # noqa: PLC0415
        lock = _get_filelock(self._lock_path)
        ctx = lock if lock else nullcontext()
        with ctx:
            tickets = self._load()
            ticket = tickets.get(ticket_id, {})
            current = ticket.get("review_state", "planned")
            if current != "needs_pi_review":
                raise InvalidReviewTransition(
                    f"{ticket_id}: approve requires needs_pi_review, got {current!r}"
                )
            ts = _now_iso()
            history = ticket.get("review_history", [])
            history.append({"action": "approved", "reviewer": reviewer_id, "ts": ts})
            history.append({"action": "in_progress", "ts": ts})
            history = self._trim_history(ticket_id, history)
            ticket["review_state"] = "in_progress"
            ticket["review_history"] = history
            ticket["updated_at"] = ts
            tickets[ticket_id] = ticket
            self._save(tickets)

    def reject(
        self,
        ticket_id: str,
        reviewer_id: str,
        verdict_choice: str = "",
        draft_pending: bool = False,
    ) -> None:
        """Transition needs_pi_review → rejected."""
        self._transition(
            ticket_id,
            from_states={"needs_pi_review"},
            to_state="rejected",
            history_entry={
                "action": "rejected",
                "reviewer": reviewer_id,
                "verdict_choice": verdict_choice,
                "draft_pending": draft_pending,
                "ts": _now_iso(),
            },
        )

    def revise(self, ticket_id: str, reviewer_id: str, comment: str = "") -> None:
        """Transition rejected → revising → needs_pi_review."""
        self._transition(
            ticket_id,
            from_states={"rejected"},
            to_state="revising",
            history_entry={
                "action": "revising",
                "reviewer": reviewer_id,
                "comment": comment,
                "ts": _now_iso(),
            },
        )
        # Auto-reenter needs_pi_review (suppress_notification=False → sends new notification)
        self.mark_needs_review(ticket_id, suppress_notification=False)

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        tickets = self._load()
        return tickets.get(ticket_id, {})

    def list_needs_review(self) -> list[dict[str, Any]]:
        """Return all tickets with review_state == needs_pi_review."""
        tickets = self._load()
        return [
            {"id": tid, **tdata}
            for tid, tdata in tickets.items()
            if tdata.get("review_state") == "needs_pi_review"
        ]
