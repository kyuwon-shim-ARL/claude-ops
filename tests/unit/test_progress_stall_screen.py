"""
Tests for screen_progress primary source-of-truth in _check_progress_stall.

Verifies:
- T1: screen_progress is used over file_progress when screen is current
- T2: _is_screen_progress_current correctly filters residual screen text
- T3: Recovery trigger resets nudge state when telegram exhausted + screen ahead of file
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor, _is_screen_progress_current
from claude_ctb.utils.progress_tracker import SkillProgress
from claude_ctb.utils.session_state import SessionState


# ---------------------------------------------------------------------------
# Helper: build a minimal SkillProgress
# ---------------------------------------------------------------------------

def _skill_progress(skill: str, stage_num: int, total_stages: int = 12) -> SkillProgress:
    return SkillProgress(
        skill=skill,
        stage_num=stage_num,
        total_stages=total_stages,
        stage_label="",
        status="in_progress",
        updated_at=datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor(tmp_path):
    mon = MultiSessionMonitor.__new__(MultiSessionMonitor)
    mon._progress_nudge_count = {}
    mon._progress_telegram_sent = {}
    mon._progress_nudge_sent_at = {}
    mon._progress_last_stage = {}
    mon._progress_check_at = {}
    mon._progress_check_interval = 15
    mon.thread_lock = MagicMock()
    mon.notifier = MagicMock()
    mon.state_analyzer = MagicMock()
    return mon


def _call_stall_check(monitor, session, file_prog, screen_text, *, exhausted=False):
    """Drive _check_progress_stall with controlled inputs.

    Patches:
    - session_manager.get_session_path → '/tmp/fakedir'
    - read_active_skill → file_prog
    - state_analyzer.get_screen_content → screen_text (scrollback, Fix 2)
    - detect_progress_stall → True  (stall always detected so we test escalation logic)
    - _is_ticket_done_guard → False
    - subprocess.run  (captured)
    """
    if exhausted:
        monitor._progress_telegram_sent[session] = True
        monitor._progress_nudge_count[session] = 2
        monitor._progress_last_stage[session] = 8

    monitor.state_analyzer.get_screen_content.return_value = screen_text

    with patch('claude_ctb.monitoring.multi_monitor.session_manager') as mock_sm, \
         patch('claude_ctb.monitoring.multi_monitor.read_active_skill', return_value=file_prog), \
         patch('claude_ctb.monitoring.multi_monitor.detect_progress_stall', return_value=True), \
         patch.object(monitor, '_is_ticket_done_guard', return_value=False), \
         patch('subprocess.run') as mock_run:
        mock_sm.get_session_path.return_value = '/tmp/fakedir'
        monitor._check_progress_stall(session, SessionState.IDLE)
        return mock_run


# ---------------------------------------------------------------------------
# Unit tests for _is_screen_progress_current helper (T2)
# ---------------------------------------------------------------------------

class TestIsScreenProgressCurrent:
    def test_file_none_returns_true(self):
        assert _is_screen_progress_current(None, "some content") is True

    def test_empty_screen_returns_true(self):
        assert _is_screen_progress_current(_skill_progress("rpt", 7), "") is True

    def test_whitespace_only_returns_true(self):
        assert _is_screen_progress_current(_skill_progress("rpt", 7), "   \n  ") is True

    def test_skill_present_returns_true(self):
        assert _is_screen_progress_current(_skill_progress("rpt", 7), "rpt [Stage 8/12]") is True

    def test_skill_absent_returns_false(self):
        assert _is_screen_progress_current(
            _skill_progress("rpt", 7), "other content [Stage 12/12]"
        ) is False


# ---------------------------------------------------------------------------
# Case A: stale file (stage 7), screen ahead (8/12), skill in screen → nudge
# ---------------------------------------------------------------------------

class TestCaseA_ScreenPrimaryNudge:
    def test_screen_stage_triggers_reset_and_nudge(self, monitor):
        """
        file.stage=7 (stale), screen='rpt [Stage 8/12]'.
        screen_is_current=True → current_stage=8, last_stage=-1 → stage change
        → counters reset → nudge #1 fired.
        """
        session = "session-a"
        mock_run = _call_stall_check(
            monitor, session,
            file_prog=_skill_progress("rpt", 7),
            screen_text="rpt [Stage 8/12]",
        )

        assert monitor._progress_nudge_count.get(session, 0) == 1
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert "이어서 진행해줘" in cmd_args


# ---------------------------------------------------------------------------
# Case B: skill NOT in screen → screen_is_current=False → file fallback
# ---------------------------------------------------------------------------

class TestCaseB_ResidualScreen:
    def test_residual_screen_rejected(self):
        """Skill name absent from screen → _is_screen_progress_current=False."""
        result = _is_screen_progress_current(
            _skill_progress("rpt", 7),
            "other-skill [Stage 12/12]",
        )
        assert result is False

    def test_file_fallback_when_screen_not_current(self, monitor):
        """screen has different skill → screen_is_current=False → file.stage_num used."""
        session = "session-b"
        # last_stage=-1, file.stage=7 → stage change detected with file stage
        mock_run = _call_stall_check(
            monitor, session,
            file_prog=_skill_progress("rpt", 7),
            screen_text="other-skill [Stage 12/12]",  # rpt NOT in screen
        )

        # stage change: current_stage=7 (file), last_stage=-1 → nudge fires
        assert monitor._progress_nudge_count.get(session, 0) == 1
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Case C: file=None, screen=(3,12) → current_stage=3 → nudge
# ---------------------------------------------------------------------------

class TestCaseC_FileNone:
    def test_file_none_allows_screen_through(self):
        """file_progress=None → _is_screen_progress_current returns True (conservative)."""
        assert _is_screen_progress_current(None, "rpt [Stage 3/12]") is True

    def test_file_none_uses_screen_stage(self, monitor):
        """file=None, screen=(3,12) → current_stage=3, nudge fires."""
        session = "session-c"
        mock_run = _call_stall_check(
            monitor, session,
            file_prog=None,
            screen_text="rpt [Stage 3/12]",
        )

        assert monitor._progress_nudge_count.get(session, 0) == 1
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# Case D: telegram exhausted + file=7 + screen=(8,12) → T3 recovery → nudge
# ---------------------------------------------------------------------------

class TestCaseD_Recovery:
    def test_recovery_resets_and_fires_nudge(self, monitor):
        """
        Initial: telegram_sent=True, nudge_count=2, last_stage=8.
        file.stage=7, screen='rpt [Stage 8/12]' → T3 recovery fires:
          nudge_count→0, telegram_sent→False, last_stage popped.
        fall-through → nudge_count becomes 1, tmux send-keys called.
        """
        session = "session-d"
        mock_run = _call_stall_check(
            monitor, session,
            file_prog=_skill_progress("rpt", 7),
            screen_text="rpt [Stage 8/12]",
            exhausted=True,
        )

        # State reset + nudge fired
        assert monitor._progress_nudge_count[session] == 1
        assert monitor._progress_telegram_sent[session] is False
        assert session not in monitor._progress_last_stage
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert "이어서 진행해줘" in cmd_args


# ---------------------------------------------------------------------------
# Fix 4: Incomplete workflow warning on WORKING→IDLE completion
# ---------------------------------------------------------------------------

class TestIncompleteWorkflowWarning:

    @pytest.fixture
    def notify_monitor(self, monitor):
        """Extend base monitor fixture with attributes needed by send_completion_notification."""
        monitor.config = MagicMock()
        monitor.tracker = MagicMock()
        monitor.debugger = MagicMock()
        return monitor

    def test_incomplete_stage_sends_warning(self, notify_monitor):
        """WORKING→IDLE with [Stage 7/12] in scrollback → warning Telegram sent."""
        session = "session-warn"
        notify_monitor.last_state = {session: SessionState.IDLE}
        notify_monitor.notification_sent = {session: True}
        notify_monitor.last_notification_time = {session: 0}

        scrollback = "output...\n[Stage 7/12] Designer Review\n✻ Cogitated for 35m 19s\n❯ "
        notify_monitor.state_analyzer.get_screen_content.return_value = scrollback

        with patch('claude_ctb.monitoring.multi_monitor.session_manager') as mock_sm, \
             patch('claude_ctb.monitoring.multi_monitor.SmartNotifier') as MockNotifier, \
             patch('claude_ctb.monitoring.multi_monitor.task_detector') as mock_td:
            mock_sm.get_active_session.return_value = "other"
            MockNotifier.return_value.send_work_completion_notification.return_value = True
            mock_td.get_priority_emoji.return_value = "✅"

            notify_monitor.send_completion_notification(session, None)

            # Should have called send_notification_sync with warning
            notify_monitor.notifier.send_notification_sync.assert_called_once()
            call_args = notify_monitor.notifier.send_notification_sync.call_args[0][0]
            assert "Stage 7/12" in call_args
            assert "멈춤" in call_args

    def test_complete_stage_no_warning(self, notify_monitor):
        """WORKING→IDLE with [Stage 12/12] in scrollback → no warning."""
        session = "session-ok"
        notify_monitor.last_state = {session: SessionState.IDLE}
        notify_monitor.notification_sent = {session: True}
        notify_monitor.last_notification_time = {session: 0}

        scrollback = "output...\n[Stage 12/12] Final Check\n✻ Done\n❯ "
        notify_monitor.state_analyzer.get_screen_content.return_value = scrollback

        with patch('claude_ctb.monitoring.multi_monitor.session_manager') as mock_sm, \
             patch('claude_ctb.monitoring.multi_monitor.SmartNotifier') as MockNotifier, \
             patch('claude_ctb.monitoring.multi_monitor.task_detector') as mock_td:
            mock_sm.get_active_session.return_value = "other"
            MockNotifier.return_value.send_work_completion_notification.return_value = True
            mock_td.get_priority_emoji.return_value = "✅"

            notify_monitor.send_completion_notification(session, None)

            # No warning sent (stage complete)
            notify_monitor.notifier.send_notification_sync.assert_not_called()
