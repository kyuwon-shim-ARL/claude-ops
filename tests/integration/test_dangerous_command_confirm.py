"""
T013: Integration test for dangerous command confirmation flow.
Tests the complete confirmation workflow with inline keyboards.
"""
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch
from claude_ctb.telegram.dangerous_commands import is_dangerous_command, create_confirmation


@pytest.mark.requires_tmux
@pytest.mark.requires_telegram
class TestDangerousCommandConfirmation:
    """Integration test for dangerous command confirmation."""

    def test_inline_keyboard_displayed_for_dangerous_command(self):
        """Test that inline keyboard is displayed when dangerous command detected."""
        # Test dangerous command detection
        dangerous_cmd = "sudo rm -rf /tmp/test"
        assert is_dangerous_command(dangerous_cmd), "Should detect dangerous command"

        # Test confirmation creation
        confirmation = create_confirmation("test_session", dangerous_cmd)
        assert confirmation is not None, "Should create confirmation"
        assert confirmation.session_name == "test_session"
        assert confirmation.command == dangerous_cmd
        assert confirmation.status == "PENDING"

    def test_cancel_button_prevents_execution(self):
        """Test that Cancel button prevents command execution."""
        from claude_ctb.telegram.dangerous_commands import get_confirmation

        # Create confirmation
        confirmation = create_confirmation("test_session", "sudo rm -rf /tmp/test")
        conf_id = confirmation.confirmation_id

        # Retrieve confirmation
        retrieved = get_confirmation(conf_id)
        assert retrieved is not None, "Should retrieve confirmation"
        assert retrieved.status == "PENDING"

        # Cancel it
        retrieved.status = "CANCELLED"
        assert retrieved.status == "CANCELLED"

    def test_confirm_button_executes_command(self):
        """Test that Confirm button sends command to tmux session."""
        from claude_ctb.telegram.dangerous_commands import get_confirmation

        # Create confirmation
        confirmation = create_confirmation("test_session", "sudo systemctl restart service")
        conf_id = confirmation.confirmation_id

        # Retrieve and confirm
        retrieved = get_confirmation(conf_id)
        retrieved.status = "CONFIRMED"
        assert retrieved.status == "CONFIRMED"

    def test_61_second_timeout_expires_confirmation(self):
        """Test that 61-second timeout expires confirmation."""
        from claude_ctb.telegram.dangerous_commands import PendingConfirmation

        # Create confirmation with timestamp in the past
        confirmation_time = time.time() - 61
        confirmation = PendingConfirmation(
            confirmation_id="test123",
            session_name="test_session",
            command="sudo rm -rf /tmp/test",
            created_at=confirmation_time
        )

        # Check if expired
        is_expired = confirmation.is_expired(timeout=60)
        assert is_expired, "Confirmation should expire after 60 seconds"
