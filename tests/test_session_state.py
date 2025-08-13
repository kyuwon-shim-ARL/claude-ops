"""
Unit tests for session state detection module

Tests the unified SessionStateAnalyzer to ensure reliable and consistent
state detection across all components.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from claude_ops.utils.session_state import (
    SessionStateAnalyzer, 
    SessionState, 
    StateTransition,
    session_state_analyzer
)


class TestSessionState:
    """Test SessionState enum"""
    
    def test_state_enum_values(self):
        """Test that all required states are defined"""
        assert SessionState.ERROR.value == "error"
        assert SessionState.WAITING_INPUT.value == "waiting"
        assert SessionState.WORKING.value == "working" 
        assert SessionState.IDLE.value == "idle"
        assert SessionState.UNKNOWN.value == "unknown"
    
    def test_state_priority(self):
        """Test state priority ordering"""
        analyzer = SessionStateAnalyzer()
        
        # ERROR should have highest priority (lowest number)
        assert analyzer.STATE_PRIORITY[SessionState.ERROR] == 0
        assert analyzer.STATE_PRIORITY[SessionState.WAITING_INPUT] == 1
        assert analyzer.STATE_PRIORITY[SessionState.WORKING] == 2
        assert analyzer.STATE_PRIORITY[SessionState.IDLE] == 3
        assert analyzer.STATE_PRIORITY[SessionState.UNKNOWN] == 4


class TestStateTransition:
    """Test StateTransition class"""
    
    def test_transition_creation(self):
        """Test creating state transitions"""
        transition = StateTransition(
            session="test_session",
            from_state=SessionState.IDLE,
            to_state=SessionState.WORKING
        )
        
        assert transition.session == "test_session"
        assert transition.from_state == SessionState.IDLE
        assert transition.to_state == SessionState.WORKING
        assert isinstance(transition.timestamp, datetime)
    
    def test_transition_repr(self):
        """Test string representation"""
        transition = StateTransition(
            session="test",
            from_state=SessionState.IDLE,
            to_state=SessionState.WORKING
        )
        
        expected = "StateTransition(test: SessionState.IDLE → SessionState.WORKING)"
        assert str(transition) == expected


class TestSessionStateAnalyzer:
    """Test SessionStateAnalyzer class"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = SessionStateAnalyzer()
    
    @patch('claude_ops.utils.session_state.subprocess.run')
    def test_get_screen_content_success(self, mock_run):
        """Test successful screen content retrieval"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test screen content"
        mock_run.return_value = mock_result
        
        content = self.analyzer.get_screen_content("test_session", use_cache=False)
        
        assert content == "test screen content"
        mock_run.assert_called_once_with(
            "tmux capture-pane -t test_session -p -S -200",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
    
    @patch('claude_ops.utils.session_state.subprocess.run')
    def test_get_screen_content_failure(self, mock_run):
        """Test screen content retrieval failure"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result
        
        content = self.analyzer.get_screen_content("test_session", use_cache=False)
        
        assert content is None
    
    def test_detect_working_state_true(self):
        """Test working state detection - positive cases"""
        test_cases = [
            "Some output\n● Command\n  ⎿  Running…\nMore content",
            "Content\nesc to interrupt\nEnd",
            "Start\ntokens · esc to interrupt)\nFinish",
            "Beginning\nctrl+b to run in background\nEnd"
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result is True, f"Failed for: {screen_content}"
    
    def test_detect_working_state_false(self):
        """Test working state detection - negative cases"""
        test_cases = [
            "Just normal output\nNo working patterns\nComplete",
            "",  # Empty content
            "Old command\n● Previous\n  ⎿  Running…\n" + "\n" * 25 + "Recent idle content",  # Old pattern far back
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result is False, f"Failed for: {screen_content}"
    
    def test_detect_input_waiting_true(self):
        """Test input waiting detection - positive cases"""
        test_cases = [
            "Some content\nDo you want to proceed?\n❯ 1. Yes\n  2. No",
            "Output\n❯ 1. Option A\n❯ 2. Option B",
            "Content\nChoose an option:\nSelect your choice",
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_input_waiting(screen_content)
            assert result is True, f"Failed for: {screen_content}"
    
    def test_detect_input_waiting_false(self):
        """Test input waiting detection - negative cases"""
        test_cases = [
            "Normal output\nNo selection prompts\nRegular content",
            "",  # Empty content
            "Just text\nNothing special\nEnd",
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_input_waiting(screen_content)
            assert result is False, f"Failed for: {screen_content}"
    
    def test_detect_error_state_true(self):
        """Test error state detection - positive cases"""
        test_cases = [
            "Command output\nError: Something went wrong\nEnd",
            "Process\nFailed: Connection timeout\nResult",
            "Start\nException: Invalid input\nFinish",
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_error_state(screen_content)
            assert result is True, f"Failed for: {screen_content}"
    
    def test_detect_error_state_false(self):
        """Test error state detection - negative cases"""
        test_cases = [
            "Normal successful output\nCompleted successfully\nDone",
            "",  # Empty content
            "Regular process\nNo errors\nFinished",
        ]
        
        for screen_content in test_cases:
            result = self.analyzer._detect_error_state(screen_content)
            assert result is False, f"Failed for: {screen_content}"
    
    @patch('claude_ops.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_priority_resolution(self, mock_get_content):
        """Test state priority resolution when multiple states detected"""
        # Screen content that has both working and waiting patterns
        mock_get_content.return_value = (
            "● Command running\n"
            "  ⎿  Running…\n"
            "Output content\n"
            "Do you want to proceed?\n"
            "❯ 1. Yes\n"
            "  2. No"
        )
        
        state = self.analyzer.get_state("test_session")
        
        # WAITING_INPUT should win over WORKING due to higher priority
        assert state == SessionState.WAITING_INPUT
    
    @patch('claude_ops.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_idle(self, mock_get_content):
        """Test idle state when no specific patterns found"""
        mock_get_content.return_value = "Normal idle content\nNo special patterns\nJust text"
        
        state = self.analyzer.get_state("test_session")
        assert state == SessionState.IDLE
    
    @patch('claude_ops.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_unknown(self, mock_get_content):
        """Test unknown state when screen content unavailable"""
        mock_get_content.return_value = None
        
        state = self.analyzer.get_state("test_session")
        assert state == SessionState.UNKNOWN
    
    @patch('claude_ops.utils.session_state.SessionStateAnalyzer.get_state')
    def test_legacy_functions(self, mock_get_state):
        """Test legacy compatibility functions"""
        # Test is_working
        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_working("test") is True
        
        mock_get_state.return_value = SessionState.IDLE
        assert self.analyzer.is_working("test") is False
        
        # Test is_waiting_for_input
        mock_get_state.return_value = SessionState.WAITING_INPUT
        assert self.analyzer.is_waiting_for_input("test") is True
        
        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_waiting_for_input("test") is False
        
        # Test is_idle
        mock_get_state.return_value = SessionState.IDLE
        assert self.analyzer.is_idle("test") is True
        
        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_idle("test") is False


class TestGlobalFunctions:
    """Test global compatibility functions"""
    
    @patch('claude_ops.utils.session_state.session_state_analyzer.is_working')
    def test_is_session_working(self, mock_is_working):
        """Test global is_session_working function"""
        mock_is_working.return_value = True
        
        from claude_ops.utils.session_state import is_session_working
        result = is_session_working("test_session")
        
        assert result is True
        mock_is_working.assert_called_once_with("test_session")
    
    @patch('claude_ops.utils.session_state.session_state_analyzer.get_state_details')
    def test_get_session_working_info(self, mock_get_details):
        """Test global get_session_working_info function"""
        mock_get_details.return_value = {
            "state": SessionState.WORKING,
            "screen_length": 1000,
            "working_patterns_found": ["Running…"],
            "analysis": {"decision_logic": "test logic"}
        }
        
        from claude_ops.utils.session_state import get_session_working_info
        result = get_session_working_info("test_session")
        
        expected = {
            "screen_length": 1000,
            "working_patterns_found": ["Running…"],
            "final_decision": True,
            "logic": "test logic"
        }
        
        assert result == expected


class TestIntegration:
    """Integration tests with real-world scenarios"""
    
    def test_real_world_scenario_git_commit(self):
        """Test detection with real git commit scenario"""
        screen_content = """
● Bash(git add .)
  ⎿  (No content)

● Bash(git commit -m "test commit")
  ⎿  [main abc1234] test commit
     1 file changed, 10 insertions(+)

● Bash(git push)
  ⎿  Running…

✢ Unravelling… (0s · ⚒ 113 tokens · esc to interrupt)

 >                                                                                      

  ⏵⏵ accept edits on (shift+tab to cycle)
"""
        
        analyzer = SessionStateAnalyzer()
        
        # Should detect as working due to "Running…" and "esc to interrupt" in recent content
        result = analyzer._detect_working_state(screen_content)
        assert result is True
    
    def test_real_world_scenario_user_prompt(self):
        """Test detection with real user prompt scenario"""
        screen_content = """
● Task completed successfully

Results:
- File created: config.json
- Dependencies installed
- Server configured

Do you want to proceed with deployment?
❯ 1. Yes
  2. No, and tell Claude what to do differently (esc)
"""
        
        analyzer = SessionStateAnalyzer()
        
        # Should detect as waiting for input
        working = analyzer._detect_working_state(screen_content)
        waiting = analyzer._detect_input_waiting(screen_content)
        
        assert working is False  # No active work
        assert waiting is True   # User input required


if __name__ == "__main__":
    pytest.main([__file__])