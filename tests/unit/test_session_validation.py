"""T046: Unit test for non-existent session validation."""
import pytest
from claude_ctb.session_manager import SessionManager


class TestSessionValidation:
    """Unit tests for session validation."""

    def test_command_to_nonexistent_session_returns_error(self):
        """Test command sent to non-existent session returns error."""
        manager = SessionManager()

        result = manager.send_command("nonexistent_session", "echo test")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_user_receives_session_not_found_notification(self):
        """Assert user receives 'Session not found' notification."""
        manager = SessionManager()

        result = manager.send_command("nonexistent_session", "test")

        assert "not found" in str(result).lower()

    def test_session_name_validation_reject_invalid_characters(self):
        """Test session name validation (reject invalid characters)."""
        manager = SessionManager()

        invalid_names = [
            "session:with:colons",
            "session with spaces",
            "session;with;semicolons",
            "session/with/slashes"
        ]

        for name in invalid_names:
            result = manager.validate_session_name(name)
            assert result is False

    def test_recently_killed_session_handling(self):
        """Test recently-killed session handling (graceful failure)."""
        manager = SessionManager()

        # Session was just killed
        result = manager.send_command("recently_killed_session", "test")

        # Should fail gracefully, not crash
        assert result is not None

    def test_no_crash_when_target_session_missing(self):
        """Verify no crash when target session missing."""
        manager = SessionManager()

        try:
            result = manager.send_command("missing_session", "test")
            # Should not raise exception
        except Exception as e:
            pytest.fail(f"Should not crash: {e}")
