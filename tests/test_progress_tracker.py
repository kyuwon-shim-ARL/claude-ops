"""Tests for progress_tracker: active-skill.json v2 parsing + screen fallback + stall detection."""

import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from claude_ctb.utils.progress_tracker import (
    read_active_skill,
    parse_screen_progress,
    detect_stall,
    SkillProgress,
)


@pytest.fixture
def tmp_workdir(tmp_path):
    """Create a temporary working directory with .omc/state/."""
    state_dir = tmp_path / ".omc" / "state"
    state_dir.mkdir(parents=True)
    return tmp_path


def _write_skill_json(workdir, data):
    """Helper: write active-skill.json to workdir/.omc/state/."""
    filepath = os.path.join(str(workdir), ".omc", "state", "active-skill.json")
    with open(filepath, "w") as f:
        json.dump(data, f)
    return filepath


def _make_v2(stage_num=3, total_stages=12, status="in_progress", updated_at=None, **extra):
    """Helper: construct v2 schema dict."""
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    data = {
        "schema_version": 2,
        "skill": "rpt",
        "stage": f"Stage {stage_num}",
        "stage_num": stage_num,
        "total_stages": total_stages,
        "stage_label": "Designer Review",
        "status": status,
        "updated_at": updated_at,
        "recovery_hint": "test",
        "state_files": [],
    }
    data.update(extra)
    return data


# ===== T1: read_active_skill =====

class TestReadActiveSkill:
    def test_v2_full_parse(self, tmp_workdir):
        """1. v2 파일 정상 파싱 — 모든 필드 추출."""
        _write_skill_json(tmp_workdir, _make_v2(stage_num=7, total_stages=12))
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        assert result.schema_version == 2
        assert result.stage_num == 7
        assert result.total_stages == 12
        assert result.stage_label == "Designer Review"
        assert result.status == "in_progress"
        assert result.skill == "rpt"

    def test_v1_best_effort_parse(self, tmp_workdir):
        """2. v1 파일 (schema_version 없음) → best-effort SkillProgress."""
        data = {"skill": "rpt", "stage": "Stage 2", "stage_detail": "Color Map",
                "updated_at": "2026-04-21T02:00:00Z"}
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        assert result.schema_version == 1
        assert result.skill == "rpt"
        assert result.stage_num == 2
        assert result.total_stages == 999  # sentinel
        assert result.stage_label == "Color Map"
        assert result.status == "in_progress"

    def test_v1_decimal_stage(self, tmp_workdir):
        """2b. v1 'Stage 2.5' → stage_num=2 (integer part only)."""
        data = {"skill": "rpt", "stage": "Stage 2.5"}
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        assert result.stage_num == 2

    def test_v1_no_stage_field_returns_none(self, tmp_workdir):
        """2c. v1 without parseable stage → None."""
        data = {"skill": "rpt", "phase": "analysis"}
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is None

    def test_broken_json(self, tmp_workdir):
        """3. JSON 파싱 실패 → None, 예외 없음."""
        filepath = os.path.join(str(tmp_workdir), ".omc", "state", "active-skill.json")
        with open(filepath, "w") as f:
            f.write("{broken json!!!")
        result = read_active_skill(str(tmp_workdir))
        assert result is None

    def test_file_missing(self, tmp_workdir):
        """4. 파일 없음 → None."""
        result = read_active_skill(str(tmp_workdir))
        assert result is None

    def test_total_stages_zero(self, tmp_workdir):
        """5. total_stages=0 → None + 경고."""
        _write_skill_json(tmp_workdir, _make_v2(total_stages=0))
        result = read_active_skill(str(tmp_workdir))
        assert result is None

    def test_stage_num_exceeds_total(self, tmp_workdir):
        """6. stage_num > total_stages → None + 경고."""
        _write_skill_json(tmp_workdir, _make_v2(stage_num=15, total_stages=12))
        result = read_active_skill(str(tmp_workdir))
        assert result is None

    def test_empty_workdir(self):
        """read_active_skill(None) → None."""
        assert read_active_skill(None) is None
        assert read_active_skill("") is None

    def test_updated_at_mtime_fallback(self, tmp_workdir):
        """updated_at 파싱 실패 시 파일 mtime fallback."""
        data = _make_v2(updated_at="not-a-date")
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        # mtime fallback should produce a reasonable timestamp
        assert (datetime.now(timezone.utc) - result.updated_at).total_seconds() < 10

    def test_future_updated_at_falls_back_to_mtime(self, tmp_workdir):
        """Future-dated updated_at (e.g. KST-as-UTC bug) → mtime fallback.

        Regression: PIU-v2 case where cc skill wrote local KST time with
        Z suffix (9h ahead of actual UTC). This made elapsed go negative
        and silently disabled stall detection.
        """
        future = (datetime.now(timezone.utc) + timedelta(hours=9)).isoformat().replace("+00:00", "Z")
        data = _make_v2(updated_at=future)
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        # mtime fallback should produce a near-now timestamp, NOT 9h future.
        delta_from_now = (datetime.now(timezone.utc) - result.updated_at).total_seconds()
        assert -5 < delta_from_now < 10, f"expected near-now, got delta={delta_from_now}s"

    def test_future_updated_at_within_tolerance_accepted(self, tmp_workdir):
        """Small clock skew (< 5min) should be accepted as-is (NTP drift tolerance)."""
        near_future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
        data = _make_v2(updated_at=near_future)
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        delta = (result.updated_at - datetime.now(timezone.utc)).total_seconds()
        assert 45 < delta < 75, f"expected ~+60s, got {delta}s (should accept small skew)"

    def test_v1_stage_with_total_extracts_both(self, tmp_workdir):
        """v1 'Stage 3/5' → stage_num=3, total_stages=5 (no sentinel).

        cc/ca skills emit 'Stage N/M' in the v1 `stage` field. Previously the
        parser stripped after the first integer and used sentinel 999 for
        total, which disabled completion detection for these skills.
        """
        data = {
            "skill": "cc",
            "stage": "Stage 3/5",
            "stage_detail": "수렴 판단",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_skill_json(tmp_workdir, data)
        result = read_active_skill(str(tmp_workdir))
        assert result is not None
        assert result.schema_version == 1
        assert result.stage_num == 3
        assert result.total_stages == 5, "total_stages must be parsed, not sentinel 999"


# ===== T2: parse_screen_progress =====

class TestParseScreenProgress:
    def test_basic_pattern(self):
        """7. [Stage 7/12] 파싱 → (7, 12)."""
        content = "some output\n[Stage 7/12] Designer Review: 가독성 검토 중\nmore output"
        assert parse_screen_progress(content) == (7, 12)

    def test_korean_mixed(self):
        """8. 한글 혼재 파싱."""
        content = "[Stage 7/12] Designer Review: 가독성 검토 완료"
        assert parse_screen_progress(content) == (7, 12)

    def test_no_pattern(self):
        """9. 패턴 없음 → None."""
        content = "just some regular output\nno stage info here"
        assert parse_screen_progress(content) is None

    def test_empty_content(self):
        """빈 문자열 → None."""
        assert parse_screen_progress("") is None
        assert parse_screen_progress(None) is None

    def test_multiple_matches_returns_last(self):
        """복수 매치 시 마지막(최신) 반환."""
        content = "[Stage 3/12] MANIFEST\n...\n[Stage 7/12] Designer Review"
        assert parse_screen_progress(content) == (7, 12)

    def test_stage_with_label_in_bracket(self):
        """[Stage 7/12 Designer Review] 파싱 → (7, 12).

        Some skills embed the label inside the brackets instead of after.
        """
        content = "[Stage 7/12 Designer Review] review pending"
        assert parse_screen_progress(content) == (7, 12)

    def test_stage_with_em_dash_round(self):
        """cc/ca convergence loop: [Stage 3/5 — Round 1/2] 파싱 → (3, 5).

        Regression: PIU-v2 case. The em-dash + Round notation was not matched
        by the old regex that required `]` immediately after N/M.
        """
        content = "[Stage 3/5 — Round 1/2] 수렴 판단: H1-H3 반영 확인"
        assert parse_screen_progress(content) == (3, 5)


# ===== T3: detect_stall =====

class TestDetectStall:
    def _make_progress(self, elapsed_seconds=301, stage_num=7, total_stages=12, status="in_progress"):
        """Helper: create SkillProgress with specified elapsed time."""
        updated = datetime.now(timezone.utc) - timedelta(seconds=elapsed_seconds)
        return SkillProgress(
            skill="rpt",
            stage_num=stage_num,
            total_stages=total_stages,
            stage_label="Designer Review",
            status=status,
            updated_at=updated,
        )

    def test_stall_detected(self):
        """10. stall 조건 충족: IDLE + in_progress + stage<total + elapsed 301초."""
        fp = self._make_progress(elapsed_seconds=301)
        assert detect_stall(fp, None, "idle") is True

    def test_boundary_299(self):
        """11. 경계값: elapsed 299초 → False."""
        fp = self._make_progress(elapsed_seconds=299)
        assert detect_stall(fp, None, "idle") is False

    def test_working_skip(self):
        """12. WORKING 상태 → False."""
        fp = self._make_progress(elapsed_seconds=600)
        assert detect_stall(fp, None, "working") is False

    def test_waiting_skip(self):
        """13. WAITING_INPUT → False."""
        fp = self._make_progress(elapsed_seconds=600)
        assert detect_stall(fp, None, "waiting") is False

    def test_completed_skip(self):
        """14. stage_num == total_stages → False."""
        fp = self._make_progress(elapsed_seconds=600, stage_num=12, total_stages=12)
        assert detect_stall(fp, None, "idle") is False

    def test_file_stall_screen_working_skip(self):
        """15. 파일 stall + 화면 WORKING → False (화면 우선)."""
        fp = self._make_progress(elapsed_seconds=600)
        # session_state is "working" means screen shows working
        assert detect_stall(fp, (7, 12), "working") is False

    def test_file_stall_screen_none_confirm(self):
        """16. 파일 stall + 화면 None → True (파일 기준 확정)."""
        fp = self._make_progress(elapsed_seconds=600)
        assert detect_stall(fp, None, "idle") is True

    def test_no_file_screen_idle_confirm(self):
        """17. 파일 없음 + 화면 있음 + IDLE → True."""
        assert detect_stall(None, (7, 12), "idle") is True

    def test_no_file_no_screen_skip(self):
        """18. 파일 없음 + 화면 없음 → False."""
        assert detect_stall(None, None, "idle") is False

    def test_status_completed_skip(self):
        """status=completed → False."""
        fp = self._make_progress(elapsed_seconds=600, status="completed")
        assert detect_stall(fp, None, "idle") is False

    def test_status_failed_skip(self):
        """status=failed → False."""
        fp = self._make_progress(elapsed_seconds=600, status="failed")
        assert detect_stall(fp, None, "idle") is False

    def test_screen_complete_skip(self):
        """화면에서 stage_num >= total → False."""
        assert detect_stall(None, (12, 12), "idle") is False
