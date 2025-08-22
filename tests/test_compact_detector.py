"""
Test suite for /compact prompt detection and execution
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from claude_ops.utils.compact_detector import CompactPromptDetector, CompactExecutor
from claude_ops.telegram.compact_handler import CompactTelegramHandler


class TestCompactPromptDetector:
    """Test /compact prompt detection"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.detector = CompactPromptDetector()
    
    def test_detect_korean_suggestion(self):
        """Test Korean /compact suggestion detection"""
        screen_content = """
        작업이 완료되었습니다.
        이제 `/compact`를 실행하여 컨텍스트를 정리하세요.
        """
        
        assert self.detector.detect_suggestion(screen_content) == True
        commands = self.detector.extract_commands(screen_content)
        assert '/compact' in commands
    
    def test_detect_english_suggestion(self):
        """Test English /compact suggestion detection"""
        screen_content = """
        Task completed successfully.
        Now run `/compact` to organize the context.
        """
        
        assert self.detector.detect_suggestion(screen_content) == True
        commands = self.detector.extract_commands(screen_content)
        assert '/compact' in commands
    
    def test_detect_command_with_options(self):
        """Test /compact with options detection"""
        screen_content = """
        세션을 아카이빙하려면:
        `/compact --archive`를 실행하세요.
        """
        
        assert self.detector.detect_suggestion(screen_content) == True
        commands = self.detector.extract_commands(screen_content)
        assert '/compact --archive' in commands
    
    def test_detect_multiple_commands(self):
        """Test multiple /compact commands detection"""
        screen_content = """
        다음 명령들을 순서대로 실행하세요:
        1. `/compact --archive`
        2. `/compact --merge sessions/2025-08/*`
        """
        
        assert self.detector.detect_suggestion(screen_content) == True
        commands = self.detector.extract_commands(screen_content)
        assert len(commands) == 2
        assert '/compact --archive' in commands
        assert '/compact --merge sessions/2025-08/*' in commands
    
    def test_no_suggestion_detection(self):
        """Test when there's no /compact suggestion"""
        screen_content = """
        Regular work in progress...
        No special commands needed.
        """
        
        assert self.detector.detect_suggestion(screen_content) == False
        commands = self.detector.extract_commands(screen_content)
        assert len(commands) == 0
    
    def test_should_notify_caching(self):
        """Test notification caching to avoid duplicates"""
        session = "claude_test"
        command = "/compact"
        
        # First time should notify
        assert self.detector.should_notify(session, command) == True
        
        # Second time should not notify (cached)
        assert self.detector.should_notify(session, command) == False
    
    def test_analyze_context(self):
        """Test full context analysis"""
        screen_content = """
        작업 완료!
        이제 `/compact --archive`를 실행하여 세션을 정리하세요.
        그리고 `/compact --report`로 보고서를 생성하세요.
        """
        
        analysis = self.detector.analyze_context(screen_content)
        
        assert analysis['has_suggestion'] == True
        assert len(analysis['commands']) == 2
        assert analysis['is_multi_step'] == True
        assert '/compact --archive' in analysis['commands']
        assert '/compact --report' in analysis['commands']


class TestCompactExecutor:
    """Test /compact command execution"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.executor = CompactExecutor()
    
    @patch('subprocess.run')
    def test_execute_single_command(self, mock_run):
        """Test executing a single /compact command"""
        mock_run.return_value = Mock(returncode=0, stderr='')
        
        result = self.executor.execute_command('claude_test', '/compact')
        
        assert result == True
        mock_run.assert_called_once()
        assert 'tmux send-keys' in mock_run.call_args[0][0]
        assert '/compact' in mock_run.call_args[0][0]
    
    @patch('subprocess.run')
    def test_execute_command_failure(self, mock_run):
        """Test command execution failure handling"""
        mock_run.return_value = Mock(returncode=1, stderr='Session not found')
        
        result = self.executor.execute_command('claude_invalid', '/compact')
        
        assert result == False
        assert len(self.executor.execution_log) == 1
        assert self.executor.execution_log[0]['success'] == False
    
    @patch('subprocess.run')
    @patch('time.sleep')
    def test_execute_sequence(self, mock_sleep, mock_run):
        """Test executing a sequence of commands"""
        mock_run.return_value = Mock(returncode=0, stderr='')
        
        commands = ['/compact --archive', '/compact --report']
        result = self.executor.execute_sequence('claude_test', commands, delay=0.5)
        
        assert result == True
        assert mock_run.call_count == 2
        assert mock_sleep.call_count == 1  # Called between commands
        mock_sleep.assert_called_with(0.5)


class TestCompactTelegramHandler:
    """Test Telegram integration for /compact"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.handler = CompactTelegramHandler()
    
    def test_create_notification_message_single(self):
        """Test creating notification message for single command"""
        analysis = {
            'commands': ['/compact --archive'],
            'is_multi_step': False
        }
        
        message = self.handler.create_notification_message('claude_test', analysis)
        
        assert '📦 **컨텍스트 정리 제안**' in message
        assert 'test' in message  # Session name without claude_ prefix
        assert '`/compact --archive`' in message
    
    def test_create_notification_message_multi(self):
        """Test creating notification message for multiple commands"""
        analysis = {
            'commands': ['/compact --archive', '/compact --report'],
            'is_multi_step': True
        }
        
        message = self.handler.create_notification_message('claude_project', analysis)
        
        assert '순서대로 실행' in message
        assert '1. `/compact --archive`' in message
        assert '2. `/compact --report`' in message
    
    def test_create_inline_keyboard_single(self):
        """Test creating inline keyboard for single command"""
        commands = ['/compact']
        keyboard = self.handler.create_inline_keyboard('claude_test', commands)
        
        buttons = keyboard.inline_keyboard
        assert len(buttons) == 2  # Execute/Copy row + Cancel row
        assert buttons[0][0].text == '🚀 실행'
        assert buttons[0][1].text == '📋 복사'
        assert buttons[1][0].text == '❌ 무시'
    
    def test_create_inline_keyboard_multi(self):
        """Test creating inline keyboard for multiple commands"""
        commands = ['/compact --archive', '/compact --report']
        keyboard = self.handler.create_inline_keyboard('claude_test', commands)
        
        buttons = keyboard.inline_keyboard
        assert len(buttons) == 4  # 2 command rows + Execute all row + Cancel row
        assert '1. /compact --archive' in buttons[0][0].text
        assert '2. /compact --report' in buttons[1][0].text
        assert buttons[2][0].text == '⚡ 모두 실행'
        assert buttons[3][0].text == '❌ 무시'


class TestRealUserScenarios:
    """Test real user scenarios end-to-end"""
    
    def test_scenario_simple_compact(self):
        """Test scenario: Claude suggests simple /compact"""
        # 1. Claude outputs suggestion
        screen_content = """
        ✅ 모든 작업이 완료되었습니다!
        
        이제 `/compact`를 실행하여 컨텍스트를 정리하세요.
        """
        
        # 2. Detector identifies it
        detector = CompactPromptDetector()
        assert detector.detect_suggestion(screen_content) == True
        
        # 3. Extract command
        commands = detector.extract_commands(screen_content)
        assert commands == ['/compact']
        
        # 4. Create notification
        handler = CompactTelegramHandler()
        analysis = {'commands': commands, 'is_multi_step': False}
        message = handler.create_notification_message('claude_myproject', analysis)
        
        assert 'myproject' in message
        assert '`/compact`' in message
    
    def test_scenario_complex_workflow(self):
        """Test scenario: Multi-step /compact workflow"""
        # 1. Claude outputs complex suggestion
        screen_content = """
        개발 사이클이 완료되었습니다.
        
        다음 단계를 수행하세요:
        1. `/compact --archive` - 현재 세션 아카이빙
        2. `/compact --merge sessions/2025-08/*` - 이번 달 세션 병합
        3. `/compact --report` - 최종 보고서 생성
        """
        
        # 2. Detector identifies multiple commands
        detector = CompactPromptDetector()
        assert detector.detect_suggestion(screen_content) == True
        
        # 3. Extract all commands
        commands = detector.extract_commands(screen_content)
        assert len(commands) == 3
        assert '/compact --archive' in commands
        assert '/compact --merge sessions/2025-08/*' in commands
        assert '/compact --report' in commands
        
        # 4. Analyze context
        analysis = detector.analyze_context(screen_content)
        assert analysis['has_suggestion'] == True
        assert analysis['is_multi_step'] == True
        
        # 5. Create notification with multi-step buttons
        handler = CompactTelegramHandler()
        keyboard = handler.create_inline_keyboard('claude_project', commands)
        
        buttons = keyboard.inline_keyboard
        assert len(buttons) == 5  # 3 commands + Execute all + Cancel
        assert '⚡ 모두 실행' in buttons[3][0].text
    
    @patch('subprocess.run')
    def test_scenario_actual_execution(self, mock_run):
        """Test scenario: Actual command execution via button click"""
        mock_run.return_value = Mock(returncode=0, stderr='')
        
        # User clicks "Execute" button
        executor = CompactExecutor()
        success = executor.execute_command('claude_myapp', '/compact --archive')
        
        assert success == True
        
        # Verify tmux command was sent
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'tmux send-keys' in call_args
        assert 'claude_myapp' in call_args
        assert '/compact --archive' in call_args
        assert 'Enter' in call_args


if __name__ == '__main__':
    pytest.main([__file__, '-v'])