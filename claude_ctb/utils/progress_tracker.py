"""
Progress Tracker for Multi-Stage Skill Monitoring

Reads active-skill.json (v2 schema) from each session's working directory
and parses [Stage N/M] patterns from screen content as fallback.
Detects stall conditions when a multi-stage skill stops progressing.

Schema v2 fields (written by skill/LLM, CTB reads only):
    schema_version: 2
    stage_num: int
    total_stages: int (>= 1)
    stage_label: str
    status: "in_progress" | "completed" | "failed"
    updated_at: ISO 8601 UTC string

Schema v1 (no schema_version field) → stall detection skipped.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Screen output pattern: [Stage 7/12] or [Stage 7/12] Designer Review: ...
_STAGE_PATTERN = re.compile(r'\[Stage\s+(\d+)/(\d+)\]')


@dataclass
class SkillProgress:
    """Parsed progress from active-skill.json v2."""
    skill: str
    stage_num: int
    total_stages: int
    stage_label: str
    status: str
    updated_at: datetime
    schema_version: int = 2


def read_active_skill(working_dir: str) -> Optional[SkillProgress]:
    """Read and parse .omc/state/active-skill.json from a session's working dir.

    Returns None for: missing file, broken JSON, v1 schema (no schema_version).
    CTB is read-only — never writes to this file.
    """
    if not working_dir:
        return None

    filepath = os.path.join(working_dir, '.omc', 'state', 'active-skill.json')

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"progress_tracker: failed to parse {filepath}: {e}")
        return None

    # v1 best-effort: extract timing + stage for stall detection
    schema_version = data.get('schema_version', 0)
    if schema_version < 2:
        stage_field = data.get('stage', '')
        m = re.match(r'Stage\s+(\d+)', stage_field)
        if not m:
            logger.debug(f"progress_tracker: v1 schema at {filepath}, no parseable stage — skip")
            return None
        stage_num = int(m.group(1))
        updated_at = _parse_updated_at(data.get('updated_at', ''), filepath)
        logger.debug(f"progress_tracker: v1 best-effort parse at {filepath}: stage={stage_num}")
        return SkillProgress(
            skill=data.get('skill', 'unknown'),
            stage_num=stage_num,
            total_stages=999,
            stage_label=data.get('stage_detail', stage_field),
            status='in_progress',
            updated_at=updated_at,
            schema_version=1,
        )

    # Extract required fields with defaults
    stage_num = data.get('stage_num', 0)
    total_stages = data.get('total_stages', 0)

    # Validity check: bad values → skip + warn
    if total_stages < 1:
        logger.warning(f"progress_tracker: total_stages={total_stages} < 1 at {filepath}, stall skip")
        return None
    if stage_num > total_stages:
        logger.warning(f"progress_tracker: stage_num={stage_num} > total_stages={total_stages} at {filepath}, stall skip")
        return None

    # Parse updated_at
    updated_at_str = data.get('updated_at', '')
    updated_at = _parse_updated_at(updated_at_str, filepath)

    return SkillProgress(
        skill=data.get('skill', 'unknown'),
        stage_num=stage_num,
        total_stages=total_stages,
        stage_label=data.get('stage_label', ''),
        status=data.get('status', 'in_progress'),
        updated_at=updated_at,
        schema_version=schema_version,
    )


def _parse_updated_at(updated_at_str: str, filepath: str) -> datetime:
    """Parse ISO datetime string, fallback to file mtime."""
    if updated_at_str:
        try:
            dt = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            logger.warning(f"progress_tracker: bad updated_at '{updated_at_str}', using mtime")

    # Fallback: file modification time
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        return datetime.now(timezone.utc)


def parse_screen_progress(screen_content: str) -> Optional[Tuple[int, int]]:
    """Parse [Stage N/M] from screen content, return last match (most recent).

    Returns (stage_num, total_stages) or None if no pattern found.
    """
    if not screen_content:
        return None

    matches = _STAGE_PATTERN.findall(screen_content)
    if not matches:
        return None

    # Last match = most recent (bottom of screen)
    stage_str, total_str = matches[-1]
    try:
        return int(stage_str), int(total_str)
    except ValueError:
        return None


def detect_stall(
    file_progress: Optional[SkillProgress],
    screen_progress: Optional[Tuple[int, int]],
    session_state: str,
    stall_threshold_seconds: float = 300.0,
) -> bool:
    """Detect if a multi-stage skill has stalled.

    Dual-signal detection matrix:
        file stall + screen IDLE     → stall confirmed
        file stall + screen None     → stall confirmed (file says in_progress, no screen evidence)
        file stall + screen WORKING  → skip (screen overrides stale file)
        file None  + screen IDLE     → stall confirmed (screen shows stage but session idle)
        file None  + screen None     → skip (no evidence)

    Args:
        file_progress: Parsed active-skill.json or None
        screen_progress: (stage_num, total_stages) from screen or None
        session_state: SessionState value string ("working", "waiting", "idle", etc.)
        stall_threshold_seconds: Seconds of updated_at stagnation before stall (default 300)

    Returns:
        True if stall detected, False otherwise.
    """
    # Only detect stall when session is IDLE
    if session_state != 'idle':
        return False

    # --- File-based detection ---
    if file_progress is not None:
        # Not in progress → no stall
        if file_progress.status != 'in_progress':
            return False

        # Completed (stage_num >= total_stages) → no stall
        if file_progress.stage_num >= file_progress.total_stages:
            return False

        # Check elapsed time
        now = datetime.now(timezone.utc)
        elapsed = (now - file_progress.updated_at).total_seconds()

        if elapsed <= stall_threshold_seconds:
            return False

        # File says stall. Check screen for override.
        # If screen shows WORKING patterns, file is stale → not stall.
        # Note: session_state is already checked as IDLE above,
        # so if we reach here, session is IDLE and file is stale.
        # screen_progress presence confirms a Stage was printed.
        # screen_progress=None means no [Stage] on screen, which is fine.
        # Both cases → stall confirmed when IDLE + file stale.
        return True

    # --- Screen-only detection (no file or v1) ---
    if screen_progress is not None:
        # Screen shows [Stage N/M] but session is IDLE → stall
        stage_num, total_stages = screen_progress
        if stage_num < total_stages:
            return True

    # No file, no screen → no evidence → skip
    return False
