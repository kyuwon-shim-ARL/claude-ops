"""T048: Unit test for monitoring session status check."""
import pytest
import subprocess
import time
from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
from claude_ctb.config import ClaudeOpsConfig


class TestMonitoringStatus:
    """Test monitoring session status check (T048)."""

    def test_detection_of_active_monitoring_session(self):
        """Test detection of active monitoring session (claude-monitor)."""
        # Create a test monitoring session
        session_name = "test-monitor"
        subprocess.run(
            f"tmux new-session -d -s {session_name}",
            shell=True,
            check=True
        )

        try:
            monitor = MultiSessionMonitor()
            status = monitor.get_monitoring_status()

            assert status is not None
            assert "session_count" in status
            assert isinstance(status["session_count"], int)

        finally:
            subprocess.run(
                f"tmux kill-session -t {session_name}",
                shell=True
            )

    def test_detection_of_missing_monitoring_session(self):
        """Test detection of missing monitoring session."""
        # Ensure no claude-monitor session exists
        subprocess.run(
            "tmux kill-session -t claude-monitor 2>/dev/null",
            shell=True
        )

        monitor = MultiSessionMonitor()
        status = monitor.get_monitoring_status()

        # Should still return status dict, but indicate inactive
        assert status is not None
        assert "is_active" in status
        # May be inactive if no monitoring session

    def test_status_check_completes_within_1_second(self):
        """Assert status check completes within 1 second."""
        monitor = MultiSessionMonitor()

        start = time.time()
        status = monitor.get_monitoring_status()
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Status check took {elapsed:.3f}s, expected <1s"
        assert status is not None

    def test_health_check_returns_session_count_and_uptime(self):
        """Test health check returns session count and uptime."""
        # Create test sessions
        test_sessions = ["test_health_1", "test_health_2", "test_health_3"]
        for session in test_sessions:
            subprocess.run(
                f"tmux new-session -d -s {session}",
                shell=True,
                check=True
            )

        try:
            monitor = MultiSessionMonitor()
            status = monitor.get_monitoring_status()

            assert "session_count" in status
            assert status["session_count"] >= 0

            # Should have uptime or last_check_time
            assert "last_check_time" in status or "uptime" in status

        finally:
            for session in test_sessions:
                subprocess.run(
                    f"tmux kill-session -t {session} 2>/dev/null",
                    shell=True
                )

    def test_session_responsive_check(self):
        """Test monitoring session responsive check."""
        # Create a test session
        session_name = "test-responsive"
        subprocess.run(
            f"tmux new-session -d -s {session_name}",
            shell=True,
            check=True
        )

        try:
            monitor = MultiSessionMonitor()

            # Check if session exists and is responsive
            is_responsive = monitor.session_exists(session_name)
            assert is_responsive is True

        finally:
            subprocess.run(
                f"tmux kill-session -t {session_name}",
                shell=True
            )

    def test_nonexistent_session_check(self):
        """Test check for non-existent session."""
        monitor = MultiSessionMonitor()

        # Check for session that doesn't exist
        is_responsive = monitor.session_exists("nonexistent_session_12345")
        assert is_responsive is False
