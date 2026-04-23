"""
Shadow-store overlay for per-ticket review metadata.
Single source: ~/.claude-ops/ticket-overlay.json
Uses file locking to prevent concurrent write corruption.
"""
import json
import logging
import os
from contextlib import nullcontext
from typing import Any

logger = logging.getLogger(__name__)

_OVERLAY_PATH = os.path.expanduser("~/.claude-ops/ticket-overlay.json")


def _get_filelock(path: str):
    """Return a filelock object for the given path."""
    try:
        import filelock  # noqa: PLC0415
        return filelock.FileLock(path + ".lock", timeout=5)
    except ImportError:
        logger.warning("filelock not available; concurrent writes may corrupt overlay")
        return None


def load_overlay() -> dict[str, Any]:
    lock = _get_filelock(_OVERLAY_PATH)
    ctx = lock if lock else nullcontext()
    with ctx:
        try:
            with open(_OVERLAY_PATH) as f:
                data = json.load(f)
            return data.get("tickets", {})
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning("overlay load failed: %s", e)
            return {}


def save_overlay(tickets: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_OVERLAY_PATH), exist_ok=True)
    lock = _get_filelock(_OVERLAY_PATH)
    ctx = lock if lock else nullcontext()
    with ctx:
        try:
            existing = {}
            try:
                with open(_OVERLAY_PATH) as f:
                    existing = json.load(f)
            except Exception:
                pass
            existing["version"] = 1
            existing["tickets"] = tickets
            with open(_OVERLAY_PATH, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.error("overlay save failed: %s", e)


def apply_overlay(tickets: list[dict]) -> list[dict]:
    """Merge overlay metadata into ticket list (non-destructive)."""
    overlay = load_overlay()
    if not overlay:
        return tickets
    result = []
    for t in tickets:
        tid = t.get("id", "")
        meta = overlay.get(tid, {})
        if meta:
            t = {**t, **meta}
        result.append(t)
    return result
