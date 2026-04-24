"""
Haiku-powered async reject draft generation for PI review.
Non-blocking: caller gets a task handle; draft stored in overlay when ready.
"""
import asyncio
import json
import logging
import weakref

logger = logging.getLogger(__name__)

# Per-ticket locks — WeakValueDictionary auto-cleans when no coroutine holds a ref
_draft_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
# In-progress flag (plain dict, cleared in finally)
_draft_pending: dict[str, bool] = {}


async def _haiku_draft(ticket_body: str, reviewer_comment: str, semaphore: asyncio.Semaphore) -> dict[str, str] | None:
    try:
        import anthropic  # noqa: PLC0415
        async with semaphore:
            client = anthropic.AsyncAnthropic()
            prompt = (
                f"Ticket: {ticket_body[:400]}\n"
                f"Reviewer comment: {reviewer_comment[:200]}\n\n"
                'Output JSON only: {"discard_rationale": "...", "revised_plan_summary": "..."}'
            )
            msg = await asyncio.wait_for(
                client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=10.0,
            )
            return json.loads(msg.content[0].text.strip())
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("Haiku reject draft failed: %s", e)
        return None


async def _store_draft(
    ticket_id: str,
    draft: dict[str, str] | None,
    overlay_path: str,
    lock_path: str,
) -> None:
    """Write draft result into the last review_history entry."""
    from contextlib import nullcontext  # noqa: PLC0415

    try:
        import filelock  # noqa: PLC0415
        lock = filelock.FileLock(lock_path, timeout=10)
    except ImportError:
        lock = None
    ctx = lock if lock else nullcontext()
    try:
        with ctx:
            try:
                with open(overlay_path) as f:
                    data = json.load(f)
            except Exception:
                return
            tickets = data.get("tickets", {})
            ticket = tickets.get(ticket_id, {})
            history = ticket.get("review_history", [])
            if history:
                history[-1]["reject_draft"] = draft
                history[-1]["draft_pending"] = False
            ticket["review_history"] = history
            tickets[ticket_id] = ticket
            data["tickets"] = tickets
            import tempfile, os  # noqa: PLC0415, E401
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
    except Exception as e:
        logger.warning("Could not store reject draft for %s: %s", ticket_id, e)


async def generate_draft(
    ticket_id: str,
    ticket_body: str,
    reviewer_comment: str,
    semaphore: asyncio.Semaphore,
    overlay_path: str,
    lock_path: str,
) -> None:
    """Generate Haiku reject draft and store in overlay (non-blocking via create_task)."""
    # Outer flag check (no await before lock acquire) is atomic in asyncio cooperative
    # scheduling — concurrent tasks that pass are caught by the inner double-check.
    if _draft_pending.get(ticket_id):
        return
    # Immediate local binding prevents GC from collecting the Lock before we acquire it
    lock = _draft_locks.setdefault(ticket_id, asyncio.Lock())
    async with lock:
        if _draft_pending.get(ticket_id):
            return
        _draft_pending[ticket_id] = True
        try:
            draft = await _haiku_draft(ticket_body, reviewer_comment, semaphore)
        finally:
            _draft_pending.pop(ticket_id, None)
    await _store_draft(ticket_id, draft, overlay_path, lock_path)


def schedule_draft(
    ticket_id: str,
    ticket_body: str,
    reviewer_comment: str,
    semaphore: asyncio.Semaphore,
    overlay_path: str,
    lock_path: str,
) -> asyncio.Task[None]:
    """Schedule draft generation as a background task. Non-blocking."""
    return asyncio.create_task(
        generate_draft(ticket_id, ticket_body, reviewer_comment, semaphore, overlay_path, lock_path),
        name=f"reject-draft-{ticket_id}",
    )
