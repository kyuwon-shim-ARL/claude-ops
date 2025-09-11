"""
Test to verify 'esc to interrupt' prevents false notifications
"""
import unittest
from unittest.mock import patch, MagicMock
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ops.monitoring.multi_monitor import MultiSessionMonitor

class TestEscInterruptNotificationBug(unittest.TestCase):
    """Test that 'esc to interrupt' prevents false completion notifications"""
    
    def setUp(self):
        """Set up test environment"""
        self.analyzer = SessionStateAnalyzer()
        self.monitor = MultiSessionMonitor()
    
    def test_esc_interrupt_prevents_quiet_completion(self):
        """'esc to interrupt' should prevent quiet completion detection"""
        # Screen content with 'esc to interrupt' clearly visible
        screen_with_esc = """
● Running tests...

Running pytest tests/test_example.py -v
....................

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # Mock the screen content getter
        with patch.object(self.analyzer, 'get_current_screen_only', return_value=screen_with_esc):
            # This should NOT detect quiet completion because 'esc to interrupt' is present
            result = self.analyzer.detect_quiet_completion('test_session')
            self.assertFalse(result, "'esc to interrupt' should prevent quiet completion detection")
    
    def test_esc_interrupt_shows_working_state(self):
        """'esc to interrupt' should indicate WORKING state"""
        screen_with_esc = """
● Building project...

npm run build
Building...

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        with patch.object(self.analyzer, 'get_screen_content', return_value=screen_with_esc):
            state = self.analyzer.get_state('test_session')
            self.assertEqual(state, SessionState.WORKING, 
                           "'esc to interrupt' should indicate WORKING state")
    
    def test_notification_not_sent_when_esc_interrupt_present(self):
        """Notification should not be sent when 'esc to interrupt' is present"""
        # Set up the monitor
        self.monitor.last_state['test_session'] = SessionState.WORKING
        self.monitor.notification_sent['test_session'] = False
        
        # Mock screen with 'esc to interrupt'
        screen_with_esc = """
● Testing application...

Running tests...
Progress: 50/100

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # Mock the state detection to return WORKING when esc is present
        with patch.object(self.monitor, 'get_session_state') as mock_get_state:
            with patch.object(self.monitor.state_analyzer, 'get_current_screen_only', 
                            return_value=screen_with_esc):
                with patch.object(self.monitor.state_analyzer, 'detect_quiet_completion') as mock_quiet:
                    # State should be WORKING due to 'esc to interrupt'
                    mock_get_state.return_value = SessionState.WORKING
                    
                    # Should NOT send notification
                    should_notify = self.monitor.should_send_completion_notification('test_session')
                    self.assertFalse(should_notify, 
                                   "Should not send notification when 'esc to interrupt' is present")
                    
                    # Quiet completion should not even be checked when state is WORKING
                    if mock_get_state.return_value == SessionState.WORKING:
                        # This is correct behavior - no quiet completion check needed
                        pass
    
    def test_actual_bug_scenario(self):
        """Test the actual bug: quiet completion incorrectly triggers with 'esc to interrupt'"""
        # This is the actual bug scenario reported by the user
        screen_content = """
● Running comprehensive test suite...

pytest tests/ -v
test_module1.py::test_function1 PASSED
test_module2.py::test_function2 PASSED
test_module3.py::test_function3 PASSED

esc to interrupt

───────────────────────────────────
│ > 
        """
        
        # The bug: detect_quiet_completion doesn't check for working patterns
        with patch.object(self.analyzer, 'get_current_screen_only', return_value=screen_content):
            # Initialize screen hash for stability check
            self.analyzer._last_screen_hash['test_session'] = 'somehash'
            self.analyzer._screen_stable_count['test_session'] = 3
            
            # This currently returns True (BUG!) because it only checks:
            # 1. We're at a prompt (yes, '>' is there)
            # 2. Screen is stable (yes, we set count to 3)
            # 3. Has output (yes, test results)
            # BUT it doesn't check for 'esc to interrupt'!
            
            result = self.analyzer.detect_quiet_completion('test_session')
            
            # This test will FAIL initially, proving the bug exists
            self.assertFalse(result, 
                           "BUG: detect_quiet_completion should return False when 'esc to interrupt' is present")

if __name__ == '__main__':
    unittest.main()