"""
T037: Unit tests for configuration validation.
Tests default values, environment variable parsing, and validation.
"""
import pytest
import os
from unittest.mock import patch
from claude_ctb.config import ClaudeOpsConfig


class TestConfigValidation:
    """Unit tests for configuration validation."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = ClaudeOpsConfig()

        # Session reconnection defaults
        assert config.session_reconnect_max_duration == 300
        assert config.session_reconnect_initial_backoff == 1
        assert config.session_reconnect_max_backoff == 30

        # Telegram rate limiting defaults
        assert config.telegram_rate_limit_enabled is True
        assert config.telegram_backoff_initial == 1
        assert config.telegram_backoff_max == 60

        # Command confirmation default
        assert config.command_confirmation_timeout == 60

        # Screen history default
        assert config.session_screen_history_lines == 200

    def test_environment_variable_parsing(self):
        """Test that environment variables are parsed correctly."""
        env_vars = {
            "SESSION_RECONNECT_MAX_DURATION": "600",
            "SESSION_RECONNECT_INITIAL_BACKOFF": "2",
            "SESSION_RECONNECT_MAX_BACKOFF": "60",
            "TELEGRAM_RATE_LIMIT_ENABLED": "false",
            "TELEGRAM_BACKOFF_INITIAL": "2",
            "TELEGRAM_BACKOFF_MAX": "120",
            "COMMAND_CONFIRMATION_TIMEOUT": "90",
            "SESSION_SCREEN_HISTORY_LINES": "300"
        }

        with patch.dict(os.environ, env_vars):
            config = ClaudeOpsConfig()

            assert config.session_reconnect_max_duration == 600
            assert config.session_reconnect_initial_backoff == 2
            assert config.session_reconnect_max_backoff == 60
            assert config.telegram_rate_limit_enabled is False
            assert config.telegram_backoff_initial == 2
            assert config.telegram_backoff_max == 120
            assert config.command_confirmation_timeout == 90
            assert config.session_screen_history_lines == 300

    def test_validation_positive_values(self):
        """Test that backoff values are positive."""
        config = ClaudeOpsConfig()

        # All backoff values should be positive
        assert config.session_reconnect_initial_backoff > 0
        assert config.session_reconnect_max_backoff > 0
        assert config.telegram_backoff_initial > 0
        assert config.telegram_backoff_max > 0

    def test_validation_max_greater_than_initial(self):
        """Test that max backoff >= initial backoff."""
        config = ClaudeOpsConfig()

        assert config.session_reconnect_max_backoff >= config.session_reconnect_initial_backoff
        assert config.telegram_backoff_max >= config.telegram_backoff_initial
