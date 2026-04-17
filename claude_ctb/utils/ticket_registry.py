"""
Ticket Registry for CTB nudge suppression.

Maps tmux session names to GitHub Issues or OMC state paths.
When a ticket is done, the monitor suppresses nudges for that session.

Registry location: {state_dir}/session-tickets.json
Lock file:        {state_dir}/session-tickets.lock

Thread safety:
  Acquisition order: filelock → _cache_lock  (always in this order to prevent deadlock)
"""

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Module-level cache: issue_num → (is_closed, checked_at, last_success_at)
# Protected by _cache_lock. Acquire filelock BEFORE _cache_lock.
_gh_cache: Dict[int, Tuple[bool, float, float]] = {}
_cache_lock = threading.Lock()

_GH_TTL = 120.0        # seconds before re-checking GitHub
_GH_FALLBACK_MAX = 600.0  # max seconds to serve stale cache on gh failure
_STALE_AGE = 86400.0   # 24 hours — registry entries older than this are removed

_REGISTRY_FILE = "session-tickets.json"
_LOCK_FILE = "session-tickets.lock"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry_path(state_dir: str) -> str:
    return os.path.join(state_dir, _REGISTRY_FILE)


def _lock_path(state_dir: str) -> str:
    return os.path.join(state_dir, _LOCK_FILE)


def _get_filelock(state_dir: str):
    """Return a FileLock for the registry, or a no-op context manager if unavailable."""
    try:
        from filelock import FileLock
        return FileLock(_lock_path(state_dir), timeout=5)
    except Exception as exc:
        logger.warning("[ticket_registry] filelock unavailable (%s) — proceeding without", exc)
        return _NoOpLock()


class _NoOpLock:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _load_registry(state_dir: str) -> dict:
    path = _registry_path(state_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[ticket_registry] failed to load registry: %s", exc)
        return {}


def _save_registry(registry: dict, state_dir: str) -> None:
    """Atomic write via tmp → rename (same-fs guaranteed by using state_dir for tmp)."""
    os.makedirs(state_dir, exist_ok=True)
    path = _registry_path(state_dir)
    fd, tmp_path = tempfile.mkstemp(dir=state_dir, prefix=".session-tickets-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        logger.warning("[ticket_registry] failed to save registry: %s", exc)


def _cleanup_stale(registry: dict, now: float) -> dict:
    """Remove entries older than _STALE_AGE."""
    return {
        k: v for k, v in registry.items()
        if now - v.get("registered_at_ts", now) < _STALE_AGE
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register(
    session_name: str,
    ticket_type: str,
    ref_or_path: object,
    state_dir: str,
) -> None:
    """Register a session → ticket mapping.

    Args:
        session_name: tmux session name (e.g. 'claude-ops-main')
        ticket_type:  'github_issue' or 'omc_task'
        ref_or_path:  GitHub issue number (int) or OMC state file path (str)
        state_dir:    directory for registry files
    """
    now = time.time()
    entry = {
        "type": ticket_type,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "registered_at_ts": now,
    }
    if ticket_type == "github_issue":
        entry["ref"] = int(ref_or_path)
    else:
        entry["state_path"] = str(ref_or_path)

    lock = _get_filelock(state_dir)
    with lock:
        registry = _load_registry(state_dir)
        registry = _cleanup_stale(registry, now)
        registry[session_name] = entry
        _save_registry(registry, state_dir)

    logger.info("[ticket_registry] registered %s → %s %s", session_name, ticket_type, ref_or_path)


def unregister(session_name: str, state_dir: str) -> None:
    """Remove a session from the registry."""
    lock = _get_filelock(state_dir)
    with lock:
        registry = _load_registry(state_dir)
        if session_name in registry:
            del registry[session_name]
            _save_registry(registry, state_dir)
            logger.info("[ticket_registry] unregistered %s", session_name)


def is_ticket_done(session_name: str, state_dir: str) -> Optional[bool]:
    """Check whether the ticket for *session_name* is complete.

    Returns:
        True  — ticket is closed/done
        False — ticket is still open (or check failed → fail-open, nudge allowed)
        None  — session not registered; caller should use default behaviour
    """
    lock = _get_filelock(state_dir)
    with lock:
        registry = _load_registry(state_dir)

    entry = registry.get(session_name)
    if entry is None:
        return None

    ticket_type = entry.get("type")
    try:
        if ticket_type == "github_issue":
            issue_num = entry.get("ref")
            if issue_num is None:
                return False
            return _check_github_issue(int(issue_num))
        elif ticket_type == "omc_task":
            state_path = entry.get("state_path", "")
            return _check_omc_state(state_path)
        else:
            logger.warning("[ticket_registry] unknown ticket type '%s' for %s", ticket_type, session_name)
            return False
    except Exception as exc:
        # H9: exceptions → False (fail-open, nudge allowed)
        logger.debug("[ticket_registry] is_ticket_done error for %s: %s — returning False (nudge allowed)", session_name, exc)
        return False


# ---------------------------------------------------------------------------
# GitHub Issue check (with TTL cache + fallback)
# ---------------------------------------------------------------------------

def _check_github_issue(issue_num: int) -> bool:
    """Return True if the GitHub issue is CLOSED.

    Cache TTL = 120s. On gh failure, falls back to last known state for up to 600s.
    On exception → False (fail-open, nudge allowed).
    """
    now = time.time()

    # Acquire _cache_lock AFTER any filelock (deadlock prevention).
    with _cache_lock:
        cached = _gh_cache.get(issue_num)
        if cached is not None:
            is_closed, checked_at, last_success_at = cached
            age = now - checked_at
            if age < _GH_TTL:
                return is_closed

    # Cache miss or expired — call gh CLI
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_num), "--json", "state",
             "-R", "kyuwon-shim-ARL/claude-ops"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh exited {result.returncode}: {result.stderr.strip()}")
        data = json.loads(result.stdout)
        is_closed = data.get("state", "").upper() == "CLOSED"
        with _cache_lock:
            _gh_cache[issue_num] = (is_closed, now, now)
        return is_closed

    except Exception as exc:
        logger.debug("[ticket_registry] gh check failed for #%d: %s", issue_num, exc)
        # Fallback: serve last known state within fallback window
        with _cache_lock:
            cached = _gh_cache.get(issue_num)
        if cached is not None:
            is_closed, _, last_success_at = cached
            if now - last_success_at < _GH_FALLBACK_MAX:
                logger.debug(
                    "[ticket_registry] serving fallback cache for #%d (age %.0fs)",
                    issue_num, now - last_success_at,
                )
                return is_closed
        # No usable cache — fail-open (nudge allowed)
        return False


# ---------------------------------------------------------------------------
# OMC state check
# ---------------------------------------------------------------------------

def _check_omc_state(state_path: str) -> bool:
    """Return True if the OMC state is inactive (completed).

    M14: Completion criteria:
      - File does not exist → True (completed / cleaned up)
      - File exists and active == False → True
      - File exists and active == True → False
      - Cancelled/failed states (active missing, final_verdict in terminal set) → True
    """
    if not state_path or not os.path.exists(state_path):
        return True  # missing file = task ended
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # active field takes priority
        if "active" in state:
            return not bool(state["active"])
        # No active field — check final_verdict
        verdict = state.get("final_verdict", "")
        terminal = {"EXECUTED", "CANCELLED", "FAILED", "VERIFY_FAILED", "STALLED"}
        if verdict in terminal:
            return True
        return False
    except Exception as exc:
        logger.debug("[ticket_registry] omc state read error (%s): %s", state_path, exc)
        return False  # fail-open


# ---------------------------------------------------------------------------
# Auto-registration from critique-lock.json
# ---------------------------------------------------------------------------

def register_from_critique_lock(
    state_dir: str,
    lock_path: str = ".omc/state/critique-lock.json",
) -> bool:
    """Register current session's GitHub Issue from critique-lock.json.

    Session name resolution order:
      1. CLAUDE_SESSION_ID environment variable
      2. TMUX environment variable (parsed to session name; empty string treated as None)
      3. → None → warning + return False

    Returns True if registered, False if skipped.
    """
    # Resolve session name
    session_name = os.environ.get("CLAUDE_SESSION_ID", "").strip() or None
    if not session_name:
        tmux_env = os.environ.get("TMUX", "").strip()
        if tmux_env:
            # TMUX=/tmp/tmux-1000/default,12345,0 → session name is last component
            parts = tmux_env.split(",")
            if len(parts) >= 3:
                session_name = parts[-1].strip() or None
    if not session_name:
        logger.warning(
            "[ticket_registry] register_from_critique_lock: session_id 불명 "
            "(CLAUDE_SESSION_ID/TMUX 없음) — 레지스트리 등록 skip"
        )
        return False

    # Read critique-lock.json
    if not os.path.exists(lock_path):
        logger.debug("[ticket_registry] critique-lock.json not found at %s — skip", lock_path)
        return False
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except Exception as exc:
        logger.warning("[ticket_registry] failed to read critique-lock.json: %s", exc)
        return False

    github_issue = lock.get("github_issue")
    if not github_issue:
        logger.debug("[ticket_registry] no github_issue in critique-lock — skip")
        return False

    try:
        issue_num = int(github_issue)
    except (TypeError, ValueError):
        logger.warning("[ticket_registry] github_issue is not int (%r) — skip", github_issue)
        return False

    register(session_name, "github_issue", issue_num, state_dir)
    logger.info(
        "[ticket_registry] auto-registered session=%s issue=#%d from critique-lock",
        session_name, issue_num,
    )
    return True
