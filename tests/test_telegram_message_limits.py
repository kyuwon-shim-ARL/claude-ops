"""
텔레그램 메시지 길이 제한 기능 테스트 스펙
Tests for telegram message length limit improvements
"""
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from claude_ctb.telegram.bot import TelegramBridge
from claude_ctb.config import ClaudeOpsConfig
from telegram import Update, Message, User, Chat

class TestTelegramMessageLimits(unittest.TestCase):
    """텔레그램 메시지 길이 제한 개선 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        # Mock config
        self.mock_config = MagicMock(spec=ClaudeOpsConfig)
        self.mock_config.telegram_bot_token = "test_token"
        self.mock_config.telegram_chat_id = "test_chat"
        self.mock_config.session_name = "test_session"
        
        # Create bot instance
        self.bot = TelegramBridge(self.mock_config)
        
        # Mock telegram objects
        self.mock_user = MagicMock(spec=User)
        self.mock_user.id = 123456789
        self.mock_user.is_bot = False
        
        self.mock_chat = MagicMock(spec=Chat)
        self.mock_chat.id = "test_chat"
        
        self.mock_message = MagicMock(spec=Message)
        self.mock_message.from_user = self.mock_user
        self.mock_message.chat = self.mock_chat
        self.mock_message.reply_to_message = None
        
        self.mock_update = MagicMock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message = self.mock_message
        self.mock_update.message.reply_text = AsyncMock()
    
    def test_message_splitting_utility_exists(self):
        """메시지 분할 유틸리티 함수가 존재해야 함"""
        # This will fail initially - utility doesn't exist yet
        from claude_ctb.telegram.message_utils import split_long_message
        
        long_text = "A" * 6000  # 6000 characters
        result = split_long_message(long_text, max_length=4000)
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 1)  # Should be split into multiple messages
        self.assertTrue(all(len(msg) <= 4000 for msg in result))
    
    def test_smart_message_splitting_preserves_lines(self):
        """스마트 분할이 줄바꿈을 기준으로 자연스럽게 분할해야 함"""
        from claude_ctb.telegram.message_utils import split_long_message
        
        # Create a message with natural break points
        lines = []
        for i in range(100):
            lines.append(f"● Session {i:03d}: very_long_session_name_that_takes_space_{i}")
        
        long_text = "\n".join(lines)  # Each line ~60 chars, total ~6000 chars
        result = split_long_message(long_text, max_length=3000)
        
        # Should split at line boundaries, not mid-line
        for message in result:
            self.assertFalse(message.startswith("ession"))  # No mid-word splits
            self.assertTrue(message.count("● Session") > 0)  # Contains complete entries
    
    def test_markdown_preservation_in_split_messages(self):
        """분할된 메시지에서 마크다운 서식이 보존되어야 함"""
        from claude_ctb.telegram.message_utils import split_long_message
        
        # Message with markdown formatting
        markdown_text = ""
        for i in range(50):
            markdown_text += f"**Session {i}**\n"
            markdown_text += f"`/sessions session_{i}`\n"
            markdown_text += f"*Status: active*\n\n"
        
        result = split_long_message(markdown_text, max_length=2000, preserve_markdown=True)
        
        # Each split should have balanced markdown
        for message in result:
            self.assertEqual(message.count("**") % 2, 0)  # Even number of **
            self.assertEqual(message.count("`") % 2, 0)  # Even number of `
    
    @patch('claude_ctb.session_manager.session_manager')
    async def test_sessions_command_handles_long_session_list(self, mock_session_manager):
        """긴 세션 목록에 대해 /sessions 명령어가 정상 동작해야 함"""
        # Create 30 sessions with long names
        long_sessions = [f"claude_very_long_project_name_session_{i:03d}" for i in range(30)]
        
        mock_session_manager.get_all_claude_sessions.return_value = long_sessions
        mock_session_manager.get_active_session.return_value = long_sessions[0]
        
        # Mock context
        mock_context = MagicMock()
        mock_context.args = []
        
        # This should not raise "message too long" error
        try:
            await self.bot.sessions_command(self.mock_update, mock_context)
            success = True
        except Exception as e:
            success = False
            self.fail(f"sessions_command failed with long session list: {e}")
        
        # Should have sent at least one message
        self.mock_update.message.reply_text.assert_called()
        
        # Verify no single message exceeds the limit
        all_calls = self.mock_update.message.reply_text.call_args_list
        for call in all_calls:
            message_text = call[0][0] if call[0] else ""
            self.assertLessEqual(len(message_text), 5000, 
                               f"Message too long: {len(message_text)} chars")
    
    def test_safe_send_message_function_exists(self):
        """안전한 메시지 전송 함수가 존재해야 함"""
        # This will fail initially - function doesn't exist yet
        from claude_ctb.telegram.message_utils import safe_send_message
        
        # Should be a callable function
        self.assertTrue(callable(safe_send_message))
    
    async def test_safe_send_message_auto_splits_long_content(self):
        """safe_send_message가 긴 내용을 자동으로 분할해야 함"""
        from claude_ctb.telegram.message_utils import safe_send_message
        
        long_content = "This is a very long message. " * 200  # ~6000 chars
        
        # Mock the actual send function
        mock_send_func = AsyncMock()
        
        await safe_send_message(mock_send_func, long_content, max_length=3000)
        
        # Should have been called multiple times (message was split)
        self.assertGreater(mock_send_func.call_count, 1)
        
        # Verify no single call exceeded the limit
        for call in mock_send_func.call_args_list:
            message = call[0][0] if call[0] else call.kwargs.get('text', '')
            self.assertLessEqual(len(message), 3000)
    
    def test_current_message_limits_are_too_restrictive(self):
        """현재 3500자 제한이 너무 제한적임을 보여주는 테스트"""
        # This test documents the current problem
        current_limit = 3500
        
        # Typical session list that should be reasonable but hits the limit
        session_names = [
            "claude_very_long_data_analysis_project_with_complex_name_v2_final",
            "claude_comprehensive_web_scraping_automation_system_advanced", 
            "claude_machine_learning_pipeline_with_deep_neural_networks_gpu",
            "claude_enterprise_database_migration_tool_postgresql_to_mongodb",
            "claude_microservices_api_integration_service_kubernetes_deployment",
        ] * 15  # 75 sessions with very long names
        
        # Build message like current sessions_command does
        message = "🔄 활성 Claude 세션 목록\n\n"
        for session in session_names:
            message += f"⏸️ {session}\n"
        
        # This reasonable session list exceeds current limit
        self.assertGreater(len(message), current_limit, 
                          f"Message length {len(message)} should exceed current limit {current_limit}")
        
        # But should be within the new proposed limit
        proposed_limit = 5000
        # If still over 5000, that's fine - will be split
        # The point is 5000 gives more headroom before splitting


class TestMessageUtilsIntegration(unittest.TestCase):
    """메시지 유틸리티 통합 테스트"""
    
    def test_sessions_command_uses_safe_send(self):
        """sessions 명령어가 safe_send_message를 사용해야 함"""
        # This specific command was updated to use safe_send_message
        from claude_ctb.telegram.bot import TelegramBridge
        import inspect
        
        # Check sessions_command specifically
        method = getattr(TelegramBridge, 'sessions_command')
        if callable(method):
            source = inspect.getsource(method)
            self.assertIn('safe_send_message', source,
                        "sessions_command should use safe_send_message")


if __name__ == '__main__':
    unittest.main()