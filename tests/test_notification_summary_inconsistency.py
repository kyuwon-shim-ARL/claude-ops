"""
Tests for notification and summary system inconsistency
Verifies that both systems use consistent state detection logic
"""
import unittest
from unittest.mock import patch, MagicMock
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ops.utils.session_summary import SessionSummaryHelper
from claude_ops.monitoring.multi_monitor import MultiSessionMonitor

class TestNotificationSummaryConsistency(unittest.TestCase):
    """Test consistency between notification and summary systems"""
    
    def setUp(self):
        """Set up test environment"""
        self.analyzer = SessionStateAnalyzer()
        self.summary_helper = SessionSummaryHelper()
        self.monitor = MultiSessionMonitor()
    
    def test_esc_interrupt_prevents_both_notification_and_summary_working_state(self):
        """Both systems should agree when 'esc to interrupt' is present"""
        # Screen with clear 'esc to interrupt' indicator
        screen_with_esc = """
● Running comprehensive test suite...

pytest tests/test_example.py -v --tb=short
test_example1.py::test_function1 PASSED
test_example2.py::test_function2 PASSED

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # Test both systems with the same screen content
        with patch.object(self.analyzer, 'get_current_screen_only', return_value=screen_with_esc):
            with patch.object(self.analyzer, 'get_screen_content', return_value=screen_with_esc):
                
                # 1. Test notification system (monitor)
                quiet_completion = self.analyzer.detect_quiet_completion('test_session')
                self.assertFalse(quiet_completion, 
                               "Notification system: quiet_completion should be False with 'esc to interrupt'")
                
                # 2. Test general state detection
                general_state = self.analyzer.get_state('test_session')
                self.assertEqual(general_state, SessionState.WORKING,
                               "General state should be WORKING with 'esc to interrupt'")
                
                # 3. Test notification-specific state detection  
                notification_state = self.analyzer.get_state_for_notification('test_session')
                self.assertEqual(notification_state, SessionState.WORKING,
                               "Notification state should be WORKING with 'esc to interrupt'")
                
                # 4. Both should agree!
                self.assertEqual(general_state, notification_state,
                               "General state and notification state should be consistent")
    
    def test_summary_helper_excludes_working_sessions_with_esc_interrupt(self):
        """Summary helper should exclude sessions with 'esc to interrupt' from waiting list"""
        screen_with_esc = """
● Building project...

npm run build
Building for production...

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # Mock session manager to return test session
        with patch('claude_ops.utils.session_summary.session_manager') as mock_manager:
            mock_manager.get_all_claude_sessions.return_value = ['test_session']
            
            # Mock state analyzer to detect working state
            with patch.object(self.summary_helper.state_analyzer, 'get_state_for_notification') as mock_state:
                mock_state.return_value = SessionState.WORKING
                
                # Get waiting sessions - should be empty since session is working
                waiting_sessions = self.summary_helper.get_waiting_sessions_with_times()
                
                self.assertEqual(len(waiting_sessions), 0,
                               "No waiting sessions should be returned when session is WORKING")
    
    def test_state_detection_consistency_across_methods(self):
        """All state detection methods should give consistent results"""
        # Test with various screen contents
        test_scenarios = [
            ("esc to interrupt", SessionState.WORKING),
            ("Running…", SessionState.WORKING), 
            ("Thinking…", SessionState.WORKING),
            ("│ > ", SessionState.IDLE),
            ("$ ", SessionState.IDLE),
        ]
        
        for screen_snippet, expected_state in test_scenarios:
            screen_content = f"""
Some command output...
{screen_snippet}
───────────────────────────────────
│ > 
            """
            
            with patch.object(self.analyzer, 'get_current_screen_only', return_value=screen_content):
                with patch.object(self.analyzer, 'get_screen_content', return_value=screen_content):
                    
                    # Test all three methods
                    general_state = self.analyzer.get_state('test_session')
                    notification_state = self.analyzer.get_state_for_notification('test_session')
                    quiet_completion = self.analyzer.detect_quiet_completion('test_session')
                    
                    # For working states, quiet_completion should be False
                    if expected_state == SessionState.WORKING:
                        self.assertEqual(general_state, SessionState.WORKING,
                                       f"General state should be WORKING for '{screen_snippet}'")
                        self.assertEqual(notification_state, SessionState.WORKING,
                                       f"Notification state should be WORKING for '{screen_snippet}'")
                        self.assertFalse(quiet_completion,
                                       f"Quiet completion should be False for '{screen_snippet}'")
    
    def test_real_world_scenario_long_running_test(self):
        """Test realistic long-running test scenario"""
        long_test_output = """
● Running comprehensive test suite...

pytest tests/ -v --tb=short --maxfail=3
============================== test session starts ===============================
platform linux -- Python 3.11.13, pytest-8.4.1, pluggy-1.6.0
collecting ... collected 161 items

tests/test_config.py::TestClaudeOpsConfig::test_config_initialization PASSED [  0%]
tests/test_config.py::TestClaudeOpsConfig::test_telegram_config_loading PASSED [  1%]
tests/test_config.py::TestClaudeOpsConfig::test_allowed_users_parsing PASSED [  1%]
tests/test_config.py::TestClaudeOpsConfig::test_missing_required_config PASSED [  2%]

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # This scenario should be detected as WORKING, not quiet completion
        with patch.object(self.analyzer, 'get_current_screen_only', return_value=long_test_output):
            with patch.object(self.analyzer, 'get_screen_content', return_value=long_test_output):
                
                # All systems should agree this is WORKING
                self.assertEqual(
                    self.analyzer.get_state('test_session'), 
                    SessionState.WORKING,
                    "Long test with 'esc to interrupt' should be WORKING"
                )
                
                self.assertEqual(
                    self.analyzer.get_state_for_notification('test_session'),
                    SessionState.WORKING, 
                    "Notification state should be WORKING for long test"
                )
                
                self.assertFalse(
                    self.analyzer.detect_quiet_completion('test_session'),
                    "Should not detect quiet completion during long test with 'esc to interrupt'"
                )

class TestSummaryWaitTimeAccuracy(unittest.TestCase):
    """Test summary command wait time calculation accuracy"""
    
    def setUp(self):
        self.summary_helper = SessionSummaryHelper()
    
    def test_wait_time_based_on_actual_completion_not_false_positive(self):
        """Wait time should be based on actual completion, not false positive notifications"""
        # This test verifies the conceptual issue - wait times should only be
        # calculated from genuine completion notifications, not false positives
        
        # Mock a session that appears idle but actually has recent work
        with patch('claude_ops.utils.session_summary.session_manager') as mock_manager:
            mock_manager.get_all_claude_sessions.return_value = ['test_session']
            
            # Mock state as idle (which would trigger wait time calculation)
            with patch.object(self.summary_helper.state_analyzer, 'get_state_for_notification') as mock_state:
                mock_state.return_value = SessionState.IDLE
                
                # Mock wait tracker to return a specific time
                with patch.object(self.summary_helper.tracker, 'get_wait_time_since_completion') as mock_wait:
                    mock_wait.return_value = (300.0, True)  # 5 minutes, accurate
                    
                    # Mock prompt recall
                    with patch.object(self.summary_helper.prompt_recall, 'extract_last_user_prompt') as mock_prompt:
                        mock_prompt.return_value = "test command"
                        
                        waiting_sessions = self.summary_helper.get_waiting_sessions_with_times()
                        
                        # Should include the session with wait time
                        self.assertEqual(len(waiting_sessions), 1)
                        session_name, wait_time, prompt = waiting_sessions[0]
                        self.assertEqual(session_name, 'test_session')
                        self.assertEqual(wait_time, 300.0)

if __name__ == '__main__':
    unittest.main()