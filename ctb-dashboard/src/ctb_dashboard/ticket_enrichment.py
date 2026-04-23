"""
L1 ticket enrichment: attach context/choices/signals slots to raw ticket dicts.
Haiku-based enrichment with mtime+SHA256 cache. Rate-limited via app.state semaphore.
"""
import asyncio
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

_CACHE_PATH = os.path.expanduser("~/.claude-ops/l1-enrichment-cache.json")
_CACHE_MAX_AGE = None  # infinite TTL; invalidated by mtime+hash change

def _cache_key(source: str, ticket_id: str, body: str) -> str:
    raw = f"{source}:{ticket_id}:{body[:512]}"
    return hashlib.sha256(raw.encode()).hexdigest()

def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    try:
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning("l1-enrichment-cache save failed: %s", e)

def _native_l1(ticket: dict) -> dict | None:
    """Static rule-based L1 extraction (no LLM). Returns None if insufficient data."""
    source = ticket.get("source", "")
    body = str(ticket.get("body", ticket.get("detail", ticket.get("title", ""))))
    if not body:
        return None
    if source in ("manifest", "gstack-design"):
        return {
            "l1_context": ticket.get("title", "")[:120],
            "l1_choices": body[:120] if body else "",
            "l1_signals": f"status:{ticket.get('status','?')}",
        }
    if source in ("github", "prd"):
        return {
            "l1_context": ticket.get("title", "")[:120],
            "l1_choices": body[:120],
            "l1_signals": f"source:{source}",
        }
    return None

async def _haiku_enrich(ticket: dict, semaphore: asyncio.Semaphore) -> dict | None:
    """Call Haiku to fill L1 slots. Returns None on timeout/error."""
    try:
        async with semaphore:
            import anthropic  # noqa: PLC0415
            client = anthropic.AsyncAnthropic()
            prompt = (
                f"Ticket: {json.dumps({'title': ticket.get('title'), 'body': str(ticket.get('body', ticket.get('detail', '')))[:400]})}\n\n"
                "Output JSON only: {\"l1_context\": \"<past>\", \"l1_choices\": \"<present options>\", \"l1_signals\": \"<evidence>\"}"
            )
            msg = await asyncio.wait_for(
                client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=10.0,
            )
            text = msg.content[0].text.strip()
            return json.loads(text)
    except Exception as e:
        logger.warning("Haiku L1 enrichment failed for %s: %s", ticket.get("id"), e)
        return None

async def attach_l1(tickets: list[dict], semaphore: asyncio.Semaphore | None = None) -> list[dict]:
    """Attach body_structured L1 slots to each ticket. Uses cache + Haiku fallback."""
    cache = _load_cache()
    result = []
    haiku_tasks = []

    for ticket in tickets:
        body = str(ticket.get("body", ticket.get("detail", ticket.get("title", ""))))
        key = _cache_key(ticket.get("source", ""), ticket.get("id", ""), body)

        if key in cache:
            ticket = {**ticket, "body_structured": cache[key], "_l1_source": "cache"}
            result.append(ticket)
            haiku_tasks.append(None)
            continue

        native = _native_l1(ticket)
        if native:
            cache[key] = native
            ticket = {**ticket, "body_structured": native, "_l1_source": "native"}
            result.append(ticket)
            haiku_tasks.append(None)
        else:
            result.append(ticket)
            haiku_tasks.append((len(result) - 1, key, ticket))

    if semaphore:
        pending = [(i, k, t) for item in haiku_tasks if item is not None for i, k, t in [item]]
        coros = [_haiku_enrich(t, semaphore) for _, _, t in pending]
        enriched = await asyncio.gather(*coros, return_exceptions=True)
        for (idx, key, _), enc in zip(pending, enriched):
            if isinstance(enc, dict):
                cache[key] = enc
                result[idx] = {**result[idx], "body_structured": enc, "_l1_source": "haiku"}
            else:
                result[idx] = {**result[idx], "body_structured": None, "_l1_source": "haiku_failed"}

    _save_cache(cache)
    return result
