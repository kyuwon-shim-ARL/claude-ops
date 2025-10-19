"""T015: Unit test for SessionReconnectionState exponential backoff calculation."""
import pytest
from claude_ctb.utils.session_reconnect import SessionReconnectionState


class TestSessionReconnectionState:
    """Unit tests for SessionReconnectionState exponential backoff."""

    def test_backoff_sequence(self):
        """Test backoff sequence: 1s, 2s, 4s, 8s, 16s, 30s (max)."""
        state = SessionReconnectionState(
            session_name="test",
            max_duration_seconds=300,
            initial_backoff=1,
            max_backoff=30
        )

        expected = [1, 2, 4, 8, 16, 30, 30]
        actual = [state.get_next_backoff() for _ in range(7)]

        assert actual == expected

    def test_retry_count_increments(self):
        """Test retry_count increments correctly."""
        state = SessionReconnectionState("test", 300, 1, 30)

        for i in range(5):
            state.get_next_backoff()
            assert state.retry_count == i + 1

    def test_max_duration_timeout(self):
        """Test max_duration timeout enforcement."""
        state = SessionReconnectionState("test", max_duration_seconds=10, initial_backoff=1, max_backoff=30)

        # Simulate 11 seconds elapsed
        import time
        state.disconnect_time = time.time() - 11

        assert state.is_timed_out()

    def test_state_transitions(self):
        """Test state transitions: RECONNECTING → SUCCESS/FAILED."""
        state = SessionReconnectionState("test", 300, 1, 30)

        assert state.status == "RECONNECTING"

        state.mark_success()
        assert state.status == "SUCCESS"

        state2 = SessionReconnectionState("test2", 300, 1, 30)
        state2.mark_failed()
        assert state2.status == "FAILED"
