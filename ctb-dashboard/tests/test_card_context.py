"""Card context must describe what the session is doing NOW.

Field incident (2026-07-31): the dashboard showed "[e025] PI Review Link" as
the work context for a session whose real work was three months newer. Every
activity-claiming source (mode state, critique-lock, skill sessions) was
correctly skipped as inactive, so a MANIFEST.yaml last touched in April won by
default -- extract_work_context had no notion of freshness at all. These tests
pin the rule: a source may only claim "current work" if its file is recent.
"""

import json
import os
import time

import pytest

from ctb_dashboard.state_detector import SessionStateAnalyzer

FRESH = time.time()
STALE = time.time() - 30 * 86400  # a month ago


@pytest.fixture
def analyzer():
    return SessionStateAnalyzer()


def _age(path, ts):
    os.utime(path, (ts, ts))


def _write_lock(tmp_path, verdict, summary, skill="cc", ts=None):
    d = tmp_path / ".omc" / "state"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "critique-lock.json"
    f.write_text(json.dumps({
        "final_verdict": verdict,
        "ticket_summary": summary,
        "source_skill": skill,
    }))
    if ts:
        _age(f, ts)
    return f


def _write_manifest(tmp_path, ts=None):
    out = tmp_path / "outputs"
    out.mkdir(exist_ok=True)
    f = out / "MANIFEST.yaml"
    f.write_text(
        "experiments:\n  e025:\n    title: PI Review Link\n    status: active\n"
    )
    if ts:
        _age(f, ts)
    return f


# --- freshness ---------------------------------------------------------------

def test_stale_manifest_does_not_claim_current_work(analyzer, tmp_path):
    """The reproduced incident: a months-old MANIFEST outranking everything."""
    _write_manifest(tmp_path, ts=STALE)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is None or "e025" not in result


def test_fresh_manifest_still_works(analyzer, tmp_path):
    _write_manifest(tmp_path, ts=FRESH)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result and "e025" in result


def test_stale_mode_state_is_ignored(analyzer, tmp_path):
    d = tmp_path / ".omc" / "state"
    d.mkdir(parents=True)
    f = d / "ralph-state.json"
    f.write_text(json.dumps({"status": "active", "goal": "ancient goal"}))
    _age(f, STALE)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is None or "ancient goal" not in result


def test_fresh_mode_state_still_wins(analyzer, tmp_path):
    d = tmp_path / ".omc" / "state"
    d.mkdir(parents=True)
    (d / "ralph-state.json").write_text(
        json.dumps({"status": "active", "goal": "current goal"})
    )
    result = analyzer.extract_work_context(str(tmp_path))
    assert result == "[ralph] current goal"


def test_stale_converged_lock_is_ignored(analyzer, tmp_path):
    _write_lock(tmp_path, "CONVERGED", "old plan", ts=STALE)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is None or "old plan" not in result


# --- recently EXECUTED is the best available context -------------------------

def test_recently_executed_lock_shows_with_done_marker(analyzer, tmp_path):
    """A ticket finished yesterday beats a bare directory name.

    EXECUTED used to be skipped entirely, which is exactly how this repo's card
    fell through to a stale MANIFEST.
    """
    _write_lock(tmp_path, "EXECUTED", "아이폰 원격 조작 단일화", skill="cc", ts=FRESH)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result == "[cc✓] 아이폰 원격 조작 단일화"


def test_stale_executed_lock_is_ignored(analyzer, tmp_path):
    _write_lock(tmp_path, "EXECUTED", "finished long ago", ts=STALE)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is None or "finished long ago" not in result


def test_executing_lock_still_shows_without_done_marker(analyzer, tmp_path):
    _write_lock(tmp_path, "EXECUTING", "진행 중 티켓", skill="cc", ts=FRESH)
    result = analyzer.extract_work_context(str(tmp_path))
    assert result == "[cc] 진행 중 티켓"


# --- screen progress (B: [Stage N/M] badge) ---------------------------------

@pytest.mark.parametrize("screen,expected", [
    ("[Stage 3/5] 수렴 루프", (3, 5)),
    ("x\n[Stage 1/4] plan\n...\n[Stage 2/4 — Round 1] critique", (2, 4)),
    ("no stages here", None),
    ("", None),
    (None, None),
])
def test_extract_screen_progress(analyzer, screen, expected):
    assert analyzer.extract_screen_progress(screen) == expected


def test_progress_pattern_matches_the_bot_parser(analyzer):
    """Same [Stage N/M ...] grammar the monitor uses (progress_tracker.py).

    Kept as behavioural parity -- ctb-dashboard does not import claude_ctb.
    """
    assert analyzer.extract_screen_progress("[Stage 4/5 — Verify] 검증") == (4, 5)


# --- last reply line (B: what Claude just said) ------------------------------

REAL_TAIL = "\n".join([
    "❯ 안녕 (대시보드 콘솔 연결 테스트)",
    "",
    "● 안녕하세요 — 연결 정상입니다. 세션 컨텍스트도 그대로 유지되고 있습니다.",
    "",
    "─────────────",
    "  [OMC#4.14.1] | Model: Opus 5 | ctx:26%",
    "  ⏵⏵ bypass permissions on (shift+tab to cycle)",
])


def test_last_reply_from_a_real_pane(analyzer):
    """Captured from a live session, not invented -- the glyph-guessing lesson."""
    reply = analyzer.extract_last_reply(REAL_TAIL)
    assert reply is not None
    assert reply.startswith("안녕하세요 — 연결 정상입니다")


def test_last_reply_picks_the_most_recent_bullet(analyzer):
    screen = "● first answer\nnoise\n● second answer\n❯ "
    assert analyzer.extract_last_reply(screen) == "second answer"


def test_last_reply_ignores_empty_bullets_and_missing_screen(analyzer):
    assert analyzer.extract_last_reply("●\n● \n❯ ") is None
    assert analyzer.extract_last_reply(None) is None
    assert analyzer.extract_last_reply("") is None


def test_last_reply_is_truncated(analyzer):
    reply = analyzer.extract_last_reply("● " + "가" * 500)
    assert reply is not None and len(reply) <= 120
