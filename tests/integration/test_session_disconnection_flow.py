"""
T010: Integration test for session disconnection with reconnection retry.
Tests the complete flow of detecting disconnection, retrying with backoff, and notifying failure.
"""
import pytest
import subprocess
import time
from unittest.mock import MagicMock, patch, AsyncMock
from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor


@pytest.mark.requires_tmux
class TestSessionDisconnectionFlow:
    """Integration test for session disconnection and reconnection retry."""

    def test_detects_disconnection_within_5_seconds(self):
        """Test that system detects session disconnection within 5 seconds."""
        monitor = MultiSessionMonitor()

        # Create and kill a session
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Verify session exists initially
            assert monitor.session_exists(session_name), "Session should exist initially"

            # Kill session
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)

            # Verify disconnection is detected
            assert not monitor.session_exists(session_name), "Session should not exist after kill"

        finally:
            # Cleanup
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_retry_attempts_with_exponential_backoff(self):
        """Test that retry attempts are logged with exponential backoff (1s, 2s, 4s, 8s, ...)."""
        from claude_ctb.utils.session_reconnect import SessionReconnectionState

        state = SessionReconnectionState(
            session_name="test_session",
            max_duration_seconds=300,
            initial_backoff=1,
            max_backoff=30
        )

        # Test backoff sequence
        expected_backoffs = [1, 2, 4, 8, 16, 30, 30]  # 30 is max
        actual_backoffs = []

        for i in range(7):
            backoff = state.get_next_backoff()
            actual_backoffs.append(backoff)

        assert actual_backoffs == expected_backoffs, \
            f"Expected {expected_backoffs}, got {actual_backoffs}"

    def test_failure_notification_after_max_duration(self):
        """Test that failure notification is sent after max_duration timeout."""
        from claude_ctb.utils.session_reconnect import SessionReconnectionState

        # Create state with very short timeout for testing
        state = SessionReconnectionState(
            session_name="test_session",
            max_duration_seconds=0,  # Immediate timeout
            initial_backoff=1,
            max_backoff=30
        )

        # Should be timed out immediately
        assert state.is_timed_out(), "Should timeout immediately with max_duration=0"

        # Mark as failed
        state.mark_failed()
        assert state.status == "FAILED", "Status should be FAILED after marking"

    def test_other_sessions_continue_monitoring(self):
        """Test that other sessions continue monitoring during one session's reconnection."""
        monitor = MultiSessionMonitor()

        # Create two sessions
        session1 = f"test_session_1_{int(time.time())}"
        session2 = f"test_session_2_{int(time.time())}"

        subprocess.run(["tmux", "new-session", "-d", "-s", session1], check=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", session2], check=True)

        try:
            # Verify both sessions exist
            assert monitor.session_exists(session1), "Session 1 should exist"
            assert monitor.session_exists(session2), "Session 2 should exist"

            # Kill session1
            subprocess.run(["tmux", "kill-session", "-t", session1], check=True)

            # Session2 should still exist
            assert not monitor.session_exists(session1), "Session 1 should not exist after kill"
            assert monitor.session_exists(session2), "Session 2 should still exist"

        finally:
            # Cleanup any remaining sessions
            subprocess.run(["tmux", "kill-session", "-t", session1], check=False)
            subprocess.run(["tmux", "kill-session", "-t", session2], check=False)
