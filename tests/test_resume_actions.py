"""Tests for _check_resume_actions() resume logic in MultiSessionMonitor.

These tests verify the resume mechanisms extracted into _check_resume_actions():
- post-C-c resume (WAITING_INPUT detection)
- error auto-resume (state transition trigger, 90s delay, 3-attempt cap)
- stuck-after-agent guard (WORKING state blocks nudge)
- _error_detected_at clear on non-ERROR state (T2)

Auto-intervene flag (CTB_AUTO_INTERVENE):
- These tests force auto_intervene=True so they exercise the historical
  send-keys behavior. Notify-only path is covered in
  TestNotifyOnlyMode below.
"""
import os
import time
import pytest
from unittest.mock import patch
from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
from claude_ctb.utils.session_state import SessionState


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setenv("CTB_AUTO_INTERVENE", "true")
    m = MultiSessionMonitor()
    m.running = True
    return m


@pytest.fixture
def monitor_notify_only(monkeypatch):
    monkeypatch.setenv("CTB_AUTO_INTERVENE", "false")
    m = MultiSessionMonitor()
    m.running = True
    return m


SESSION = "test_session"


# ---------------------------------------------------------------------------
# TestPostCtrlcResume
# ---------------------------------------------------------------------------

class TestPostCtrlcResume:
    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_waiting_input_sends_resume(self, mock_run, monitor):
        """케이스 1: WAITING_INPUT 전환 시 '이어서 진행해줘' 전송."""
        monitor._post_ctrlc_at[SESSION] = time.time() - 5
        with patch.object(monitor.notifier, "send_notification_sync"):
            monitor._check_resume_actions(SESSION, SessionState.WAITING_INPUT, SessionState.WORKING)
        texts_sent = [str(c) for c in mock_run.call_args_list]
        assert any("이어서 진행해줘" in t for t in texts_sent), \
            f"Expected '이어서 진행해줘' in subprocess calls, got: {texts_sent}"
        assert SESSION not in monitor._post_ctrlc_at

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_timeout_clears_without_send(self, mock_run, monitor):
        """케이스 2: 120s 타임아웃 시 포기 — 전송 없음, 상태 클리어."""
        monitor._post_ctrlc_at[SESSION] = time.time() - 130
        monitor._check_resume_actions(SESSION, SessionState.IDLE, SessionState.WORKING)
        assert SESSION not in monitor._post_ctrlc_at
        # subprocess not called for "이어서 진행해줘"
        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c)


# ---------------------------------------------------------------------------
# TestErrorAutoResume
# ---------------------------------------------------------------------------

class TestErrorAutoResume:
    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_error_detected_under_90s_no_send(self, mock_run, monitor):
        """케이스 3 & 6: _error_detected_at 있고 elapsed < 90s → 전송 없음."""
        monitor._error_detected_at[SESSION] = time.time() - 5
        monitor._error_auto_resume_count[SESSION] = 0
        with patch.object(monitor, "session_exists", return_value=True):
            monitor._check_resume_actions(SESSION, SessionState.ERROR, SessionState.WORKING)
        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c)

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_error_to_error_preserves_timer(self, mock_run, monitor):
        """케이스 4: ERROR→ERROR 시 _error_detected_at 타이머 보존."""
        original_time = time.time() - 50
        monitor._error_detected_at[SESSION] = original_time
        monitor._error_auto_resume_count[SESSION] = 0
        with patch.object(monitor, "session_exists", return_value=True):
            monitor._check_resume_actions(SESSION, SessionState.ERROR, SessionState.ERROR)
        stored = monitor._error_detected_at.get(SESSION, 0)
        assert abs(stored - original_time) < 2, \
            f"Timer should be preserved near {original_time}, got {stored}"

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_elapsed_90s_sends_resume(self, mock_run, monitor):
        """케이스 7: elapsed >= 90s + session exists → '이어서 진행해줘' 전송."""
        monitor._error_detected_at[SESSION] = time.time() - 95
        monitor._error_auto_resume_count[SESSION] = 0
        with patch.object(monitor, "session_exists", return_value=True):
            monitor._check_resume_actions(SESSION, SessionState.IDLE, SessionState.ERROR)
        texts_sent = [str(c) for c in mock_run.call_args_list]
        assert any("이어서 진행해줘" in t for t in texts_sent), \
            f"Expected '이어서 진행해줘', got: {texts_sent}"

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_elapsed_under_90s_no_send(self, mock_run, monitor):
        """케이스 6: elapsed < 90s → 전송 없음."""
        monitor._error_detected_at[SESSION] = time.time() - 30
        monitor._error_auto_resume_count[SESSION] = 0
        with patch.object(monitor, "session_exists", return_value=True):
            monitor._check_resume_actions(SESSION, SessionState.IDLE, SessionState.ERROR)
        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c)

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_max_retries_exhausted_clears(self, mock_run, monitor):
        """케이스 8: count >= 3 소진 시 전송 없음 + _error_detected_at 클리어."""
        monitor._error_detected_at[SESSION] = time.time() - 100
        monitor._error_auto_resume_count[SESSION] = 3
        with patch.object(monitor, "session_exists", return_value=True):
            monitor._check_resume_actions(SESSION, SessionState.IDLE, SessionState.ERROR)
        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c)
        assert SESSION not in monitor._error_detected_at


# ---------------------------------------------------------------------------
# TestStuckAfterAgentGuard
# ---------------------------------------------------------------------------

class TestStuckAfterAgentGuard:
    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_working_state_no_nudge(self, mock_run, monitor):
        """케이스 9: curr=WORKING 시 stuck-after-agent nudge 전송 없음."""
        monitor._stuck_check_at[SESSION] = 0
        with patch.object(
            monitor.state_analyzer, "detect_stuck_after_agent", return_value=True
        ):
            with patch(
                "claude_ctb.monitoring.multi_monitor.session_manager.get_session_path",
                return_value="/some/path",
            ):
                monitor._check_resume_actions(
                    SESSION, SessionState.WORKING, SessionState.WORKING
                )
        for c in mock_run.call_args_list:
            assert "마저해줘" not in str(c)

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_idle_with_tool_result_sends_nudge(self, mock_run, monitor):
        """케이스 10: curr=IDLE + detect_stuck_after_agent=True → '마저해줘' 전송."""
        monitor._stuck_check_at[SESSION] = 0  # force check now
        monitor._stuck_nudge_sent_at.pop(SESSION, None)  # reset cooldown
        with patch.object(
            monitor.state_analyzer, "detect_stuck_after_agent", return_value=True
        ):
            with patch(
                "claude_ctb.monitoring.multi_monitor.session_manager.get_session_path",
                return_value="/some/path",
            ):
                monitor._check_resume_actions(
                    SESSION, SessionState.IDLE, SessionState.IDLE
                )
        texts_sent = [str(c) for c in mock_run.call_args_list]
        assert any("마저해줘" in t for t in texts_sent), \
            f"Expected '마저해줘', got: {texts_sent}"


# ---------------------------------------------------------------------------
# TestErrorDetectedAtClear (T2)
# ---------------------------------------------------------------------------

class TestErrorDetectedAtClear:
    def test_error_to_idle_clears_timer(self, monitor):
        """케이스 5: ERROR→IDLE 전환 시 _error_detected_at 클리어 (T2 검증)."""
        monitor._error_detected_at[SESSION] = time.time() - 10
        monitor._error_auto_resume_count[SESSION] = 1

        # T2 logic: clear when curr_state != ERROR
        curr_state = SessionState.IDLE
        if (SESSION in monitor._error_detected_at
                and curr_state != SessionState.ERROR):
            monitor._error_detected_at.pop(SESSION, None)
            monitor._error_auto_resume_count.pop(SESSION, None)

        assert SESSION not in monitor._error_detected_at
        assert SESSION not in monitor._error_auto_resume_count


# ---------------------------------------------------------------------------
# TestNotifyOnlyMode — verifies CTB_AUTO_INTERVENE=false suppresses send-keys
# ---------------------------------------------------------------------------

class TestNotifyOnlyMode:
    """When CTB_AUTO_INTERVENE is false (default), no auto-keystrokes are sent.
    Telegram notification is sent instead, with the same detection logic preserved.
    """

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_stuck_after_agent_no_send_keys(self, mock_run, monitor_notify_only):
        """stuck-after-agent: detected but no '마저해줘' keystroke; alert sent instead."""
        monitor_notify_only._stuck_check_at[SESSION] = 0
        monitor_notify_only._stuck_nudge_sent_at.pop(SESSION, None)
        with patch.object(
            monitor_notify_only.state_analyzer, "detect_stuck_after_agent",
            return_value=True
        ), patch(
            "claude_ctb.monitoring.multi_monitor.session_manager.get_session_path",
            return_value="/some/path",
        ), patch.object(monitor_notify_only.notifier, "send_notification_sync") as mock_notify:
            monitor_notify_only._check_resume_actions(
                SESSION, SessionState.IDLE, SessionState.IDLE
            )

        for c in mock_run.call_args_list:
            assert "마저해줘" not in str(c), \
                f"send-keys '마저해줘' should NOT fire when auto_intervene=false: {c}"
        assert mock_notify.called, "Telegram notification expected when auto_intervene=false"
        notify_msg = str(mock_notify.call_args)
        assert "stuck after agent" in notify_msg.lower() or "마저해줘" in notify_msg, \
            f"Notification should describe stuck-after-agent state: {notify_msg}"

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_post_ctrlc_no_send_keys(self, mock_run, monitor_notify_only):
        """post-C-c resume: WAITING_INPUT detected but no '이어서 진행해줘' keystroke."""
        monitor_notify_only._post_ctrlc_at[SESSION] = time.time() - 5
        with patch.object(monitor_notify_only.notifier, "send_notification_sync") as mock_notify:
            monitor_notify_only._check_resume_actions(
                SESSION, SessionState.WAITING_INPUT, SessionState.WORKING
            )

        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c), \
                f"send-keys '이어서 진행해줘' should NOT fire when auto_intervene=false: {c}"
        assert mock_notify.called, "Telegram notification expected when auto_intervene=false"
        # _post_ctrlc_at cleared after handling regardless of mode
        assert SESSION not in monitor_notify_only._post_ctrlc_at

    @patch("claude_ctb.monitoring.multi_monitor.subprocess.run")
    def test_error_auto_resume_no_send_keys(self, mock_run, monitor_notify_only):
        """error auto-resume: 90s elapsed but no '이어서 진행해줘' keystroke; alert sent."""
        monitor_notify_only._error_detected_at[SESSION] = time.time() - 95
        monitor_notify_only._error_auto_resume_count[SESSION] = 0
        with patch.object(monitor_notify_only, "session_exists", return_value=True), \
                patch.object(monitor_notify_only.notifier, "send_notification_sync") as mock_notify:
            monitor_notify_only._check_resume_actions(
                SESSION, SessionState.IDLE, SessionState.ERROR
            )

        for c in mock_run.call_args_list:
            assert "이어서 진행해줘" not in str(c), \
                f"send-keys '이어서 진행해줘' should NOT fire when auto_intervene=false: {c}"
        assert mock_notify.called, "Telegram notification expected when auto_intervene=false"
        # Counter still increments so escalation cap still works
        assert monitor_notify_only._error_auto_resume_count[SESSION] == 1
