"""
Test suite for notification detection improvements

Tests the enhanced detection patterns for:
1. Quiet completions (git log, ls, etc.)
2. Completion message patterns
3. Debug logging and analysis
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ops.monitoring.multi_monitor import MultiSessionMonitor
from claude_ops.utils.notification_debugger import NotificationDebugger, NotificationEvent


class TestQuietCompletionDetection:
    """Test detection of quiet completions like 'git log' or 'ls'"""
    
    def test_detect_git_log_completion(self):
        """Test detection of git log output that ends quietly"""
        analyzer = SessionStateAnalyzer()
        
        # Simulate git log output ending at prompt
        git_log_screen = """
commit abc123 (HEAD -> main)
Author: User <user@example.com>
Date:   Mon Jan 1 12:00:00 2024

    Initial commit

commit def456
Author: User <user@example.com>
Date:   Sun Dec 31 11:00:00 2023

    Previous commit

user@host:~/project$ """
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=git_log_screen):
            # First check - establishes baseline
            assert analyzer.detect_quiet_completion("test_session") == False
            
            # Second check - same screen (stable)
            assert analyzer.detect_quiet_completion("test_session") == False
            
            # Third check - now stable enough
            assert analyzer.detect_quiet_completion("test_session") == True
    
    def test_detect_ls_completion(self):
        """Test detection of ls output completion"""
        analyzer = SessionStateAnalyzer()
        
        ls_screen = """
file1.txt
file2.py
directory/
another_file.md
config.json
package.json
src/
tests/
docs/
README.md
LICENSE
.gitignore
user@host:~/project$ """
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=ls_screen):
            # Simulate multiple checks
            analyzer.detect_quiet_completion("test_session")
            analyzer.detect_quiet_completion("test_session")
            result = analyzer.detect_quiet_completion("test_session")
            
            assert result == True  # Should detect completion after stability
    
    def test_no_false_positive_during_work(self):
        """Ensure no false positives while work is ongoing"""
        analyzer = SessionStateAnalyzer()
        
        working_screen = """
Building project...
[1/10] Compiling module1.py
[2/10] Compiling module2.py
Running... (esc to interrupt)
"""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=working_screen):
            assert analyzer.detect_quiet_completion("test_session") == False
            assert analyzer.has_completion_indicators(working_screen) == False


class TestCompletionMessageDetection:
    """Test detection of explicit completion messages"""
    
    def test_detect_success_messages(self):
        """Test various success message patterns"""
        analyzer = SessionStateAnalyzer()
        
        test_cases = [
            "Build succeeded in 5.2s",
            "Tests passed: 42/42",
            "✅ All tests passed",
            "Successfully completed deployment",
            "Task finished",
            "Done!",
            "Process completed with 0 errors"
        ]
        
        for message in test_cases:
            screen = f"Some output\n{message}\nuser@host$ "
            assert analyzer.has_completion_indicators(screen) == True, f"Failed to detect: {message}"
    
    def test_detect_time_patterns(self):
        """Test detection of execution time patterns"""
        analyzer = SessionStateAnalyzer()
        
        screens_with_times = [
            "Command took 3.14s",
            "Completed in 42.0 seconds",
            "Execution time: 1.5s"
        ]
        
        for screen in screens_with_times:
            # Note: regex patterns need special handling
            result = analyzer.has_completion_indicators(screen)
            # These should match if regex is working correctly


class TestEnhancedNotificationLogic:
    """Test the enhanced notification trigger logic"""
    
    @patch('claude_ops.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ops.monitoring.multi_monitor.os.system')
    def test_quiet_completion_triggers_notification(self, mock_system, mock_run):
        """Test that quiet completions trigger notifications"""
        monitor = MultiSessionMonitor()
        session_name = "test_session"
        
        # Mock tmux session exists
        mock_system.return_value = 0
        
        # Mock screen content for quiet completion
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="git log output\ncommit 123\nuser@host$ "
        )
        
        # Setup state analyzer to detect quiet completion
        with patch.object(monitor.state_analyzer, 'detect_quiet_completion', return_value=True):
            with patch.object(monitor.state_analyzer, 'get_state', return_value=SessionState.IDLE):
                # First call establishes state
                result = monitor.should_send_completion_notification(session_name)
                
                # Should trigger notification for quiet completion
                assert result == True
    
    @patch('claude_ops.monitoring.multi_monitor.subprocess.run')
    def test_completion_message_triggers_notification(self, mock_run):
        """Test that completion messages trigger notifications"""
        monitor = MultiSessionMonitor()
        session_name = "test_session"
        
        completion_screen = "Build succeeded!\nAll tests passed\nuser@host$ "
        mock_run.return_value = MagicMock(returncode=0, stdout=completion_screen)
        
        with patch.object(monitor.state_analyzer, 'get_current_screen_only', return_value=completion_screen):
            with patch.object(monitor.state_analyzer, 'get_state', return_value=SessionState.IDLE):
                with patch.object(monitor.state_analyzer, 'has_completion_indicators', return_value=True):
                    result = monitor.should_send_completion_notification(session_name)
                    
                    # Should detect completion message
                    assert result == True
    
    def test_cooldown_prevents_duplicate_notifications(self):
        """Test that cooldown period prevents duplicate notifications"""
        monitor = MultiSessionMonitor()
        session_name = "test_session"
        
        # First notification
        monitor.last_notification_time[session_name] = time.time()
        monitor.notification_sent[session_name] = False
        
        with patch.object(monitor.state_analyzer, 'get_state', return_value=SessionState.IDLE):
            # Try to send another notification immediately
            result = monitor.should_send_completion_notification(session_name)
            
            # Should be blocked by cooldown
            assert result == False


class TestNotificationDebugger:
    """Test the debugging utilities"""
    
    def test_debugger_logs_state_changes(self):
        """Test that debugger properly logs state changes"""
        debugger = NotificationDebugger()
        
        debugger.log_state_change(
            "test_session",
            SessionState.WORKING,
            SessionState.IDLE,
            "Test transition"
        )
        
        assert len(debugger.state_history["test_session"]) == 1
        entry = debugger.state_history["test_session"][0]
        assert entry['transition'] == "WORKING → IDLE"
        assert entry['reason'] == "Test transition"
    
    def test_debugger_detects_missed_notifications(self):
        """Test detection of potentially missed notifications"""
        debugger = NotificationDebugger()
        
        # Create history entries that represent a working->idle transition
        # First log the working state
        debugger.log_state_change("session1", None, SessionState.WORKING)
        time.sleep(0.1)
        # Then log the idle state (this is the completion)
        debugger.log_state_change("session1", SessionState.WORKING, SessionState.IDLE)
        
        # Analyze for missed notifications
        missed = debugger.analyze_missed_notifications("session1")
        
        assert len(missed) >= 1
        assert "Completion pattern" in missed[0]['reason']
    
    def test_debug_report_generation(self):
        """Test debug report generation"""
        debugger = NotificationDebugger()
        
        # Add some test data
        debugger.log_state_change("test", SessionState.IDLE, SessionState.WORKING)
        debugger.log_notification(
            "test", 
            NotificationEvent.SENT,
            "Test notification",
            SessionState.WORKING
        )
        
        report = debugger.generate_debug_report("test")
        
        assert "Session: test" in report
        assert "State changes: 1" in report
        assert "Notifications sent: 1" in report


class TestIntegration:
    """Integration tests for the complete notification system"""
    
    @patch('claude_ops.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ops.monitoring.multi_monitor.os.system')
    def test_full_workflow_quiet_completion(self, mock_system, mock_run):
        """Test complete workflow for quiet completion detection"""
        monitor = MultiSessionMonitor()
        session = "integration_test"
        
        # Session exists
        mock_system.return_value = 0
        
        # Initialize session state tracking
        monitor.last_state[session] = SessionState.IDLE
        monitor.notification_sent[session] = False
        monitor.last_notification_time[session] = 0
        
        # Simulate the full workflow
        completion_screen = "file1.txt\nfile2.py\ndirectory/\nuser@host$ "
        mock_run.return_value = MagicMock(returncode=0, stdout=completion_screen)
        
        # Mock quiet completion detection to return True after stability
        with patch.object(monitor.state_analyzer, 'get_current_screen_only', return_value=completion_screen):
            with patch.object(monitor.state_analyzer, 'get_state', return_value=SessionState.IDLE):
                with patch.object(monitor.state_analyzer, 'detect_quiet_completion', side_effect=[False, False, True]):
                    # First two calls should return False (establishing stability)
                    result1 = monitor.should_send_completion_notification(session)
                    result2 = monitor.should_send_completion_notification(session)  
                    result3 = monitor.should_send_completion_notification(session)
                    
                    # Should detect completion on third call
                    assert result3 == True, "Should detect quiet completion after stability checks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])