"""
Configuration Management Tests

Tests for ClaudeOpsConfig and environment variable handling
"""

import os
import tempfile
from unittest.mock import patch
from claude_ops.config import ClaudeOpsConfig


class TestClaudeOpsConfig:
    """Test ClaudeOpsConfig initialization and validation"""
    
    def test_config_initialization(self):
        """Test basic config initialization"""
        config = ClaudeOpsConfig()
        assert config is not None
        assert hasattr(config, 'telegram_bot_token')
        assert hasattr(config, 'telegram_chat_id')
    
    @patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'test_token_123',
        'TELEGRAM_CHAT_ID': '123456789'
    })
    def test_telegram_config_loading(self):
        """Test telegram configuration loading"""
        config = ClaudeOpsConfig()
        assert config.telegram_bot_token == 'test_token_123'
        assert config.telegram_chat_id == '123456789'
    
    @patch.dict(os.environ, {
        'ALLOWED_USER_IDS': '123,456,789'
    })
    def test_allowed_users_parsing(self):
        """Test allowed users list parsing"""
        config = ClaudeOpsConfig()
        expected = [123, 456, 789]
        assert config.allowed_user_ids == expected
    
    @patch('claude_ops.config.load_dotenv')
    def test_missing_required_config(self, mock_load_dotenv):
        """Test behavior with missing required configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = ClaudeOpsConfig()
            assert config.telegram_bot_token == ""
            assert config.telegram_chat_id == ""
    
    @patch.dict(os.environ, {
        'CHECK_INTERVAL': '5',
        'LOG_LEVEL': 'DEBUG'
    })
    def test_optional_config_loading(self):
        """Test optional configuration parameters"""
        config = ClaudeOpsConfig()
        assert config.check_interval == 5
    
    def test_config_validation(self):
        """Test configuration validation methods"""
        with patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': 'test_token',
            'ALLOWED_USER_IDS': '123'
        }):
            config = ClaudeOpsConfig()
            assert config.validate_telegram_config()
    
    def test_custom_env_file(self):
        """Test loading from custom .env file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('TELEGRAM_BOT_TOKEN=custom_token\n')
            f.write('TELEGRAM_CHAT_ID=987654321\n')
            env_file_path = f.name
        
        try:
            with patch.dict(os.environ, {}, clear=True):
                config = ClaudeOpsConfig(env_file=env_file_path)
                assert config.telegram_bot_token == 'custom_token'
                assert config.telegram_chat_id == '987654321'
        finally:
            os.unlink(env_file_path)


class TestConfigIntegration:
    """Integration tests for configuration management"""
    
    def test_config_with_all_features(self):
        """Test configuration with all features enabled"""
        env_vars = {
            'TELEGRAM_BOT_TOKEN': 'full_test_token',
            'TELEGRAM_CHAT_ID': '111222333',
            'ALLOWED_USER_IDS': '111,222,333',
            'CLAUDE_WORKING_DIR': '/test/work/dir',
            'CHECK_INTERVAL': '10',
            'LOG_LEVEL': 'INFO'
        }
        
        with patch.dict(os.environ, env_vars):
            config = ClaudeOpsConfig()
            assert config.telegram_bot_token == 'full_test_token'
            assert config.telegram_chat_id == '111222333'
            assert config.allowed_user_ids == [111, 222, 333]
            assert config.check_interval == 10
    
    @patch('claude_ops.config.load_dotenv')
    def test_config_defaults(self, mock_load_dotenv):
        """Test default configuration values"""
        with patch.dict(os.environ, {}, clear=True):
            config = ClaudeOpsConfig()
            # Test default values
            assert config.check_interval == 3  # Default check interval
            assert config.allowed_user_ids == []  # Empty list by default