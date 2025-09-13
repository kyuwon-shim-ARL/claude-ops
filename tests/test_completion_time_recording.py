"""
Test Completion Time Recording System

Ensures completion times are recorded correctly regardless of notification status.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from claude_ops.monitoring.multi_monitor import MultiSessionMonitor
from claude_ops.utils.session_state import SessionState
from claude_ops.utils.wait_time_tracker_v2 import ImprovedWaitTimeTracker
from claude_ops.monitoring.completion_event_system import CompletionEventType


class TestCompletionTimeRecording:
    """Test suite for completion time recording"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.monitor = MultiSessionMonitor()
        self.session_name = "test_session"
        
    def test_completion_recorded_on_state_transition(self):
        """
        Test that completion time is recorded when transitioning from WORKING to any other state
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.WORKING
        self.monitor.notification_sent[self.session_name] = False
        
        # Mock the completion recorder
        mock_recorder = Mock()
        self.monitor.completion_recorder = mock_recorder
        
        # Mock state analyzer to return IDLE (work completed)
        with patch.object(self.monitor, 'get_session_state', return_value=SessionState.IDLE):
            # Execute
            should_notify, task_completion = self.monitor.should_send_completion_notification(self.session_name)
            
        # Verify event was emitted (which triggers recording)
        assert len(self.monitor.event_bus.event_history) > 0
        last_event = self.monitor.event_bus.event_history[-1]
        assert last_event.session_name == self.session_name
        assert last_event.event_type.value == "state_transition"
        assert should_notify is True
    
    def test_completion_recorded_even_when_notification_fails(self):
        """
        Test that completion time is recorded even if notification sending fails
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.WORKING
        
        # Mock tracker
        mock_tracker = Mock(spec=ImprovedWaitTimeTracker)
        self.monitor.tracker = mock_tracker
        
        # Mock notifier to fail
        with patch('claude_ops.telegram.notifier.SmartNotifier') as mock_notifier_class:
            mock_notifier = Mock()
            mock_notifier.send_work_completion_notification.return_value = False  # Notification fails
            mock_notifier_class.return_value = mock_notifier
            
            # Execute
            self.monitor.send_completion_notification(self.session_name)
            
        # Verify completion was still marked (in should_send_completion_notification)
        # Note: This will only work after our fix is applied
        assert mock_tracker.mark_completion.called or mock_tracker.mark_state_transition.called
    
    def test_no_duplicate_completion_marking(self):
        """
        Test that completion is not marked multiple times for the same transition
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.IDLE  # Already idle
        self.monitor.notification_sent[self.session_name] = False
        
        # Mock tracker
        mock_tracker = Mock(spec=ImprovedWaitTimeTracker)
        self.monitor.tracker = mock_tracker
        
        # Mock state analyzer to return IDLE (no state change)
        with patch.object(self.monitor, 'get_session_state', return_value=SessionState.IDLE):
            # Execute
            should_notify, task_completion = self.monitor.should_send_completion_notification(self.session_name)
            
        # Verify completion was NOT marked (no state transition)
        mock_tracker.mark_completion.assert_not_called()
    
    def test_completion_recorded_for_working_to_waiting_transition(self):
        """
        Test that completion is recorded for WORKING -> WAITING_INPUT transition
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.WORKING
        self.monitor.notification_sent[self.session_name] = False
        
        # Clear event history
        self.monitor.event_bus.clear_history()
        
        # Mock state analyzer to return WAITING_INPUT
        with patch.object(self.monitor, 'get_session_state', return_value=SessionState.WAITING_INPUT):
            # Execute
            should_notify, task_completion = self.monitor.should_send_completion_notification(self.session_name)
            
        # Verify event was emitted
        assert len(self.monitor.event_bus.event_history) > 0
        last_event = self.monitor.event_bus.event_history[-1]
        assert last_event.session_name == self.session_name
        assert last_event.new_state == SessionState.WAITING_INPUT.value
        assert should_notify is True
    
    def test_completion_recorded_for_working_to_error_transition(self):
        """
        Test that completion is recorded for WORKING -> ERROR transition
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.WORKING
        self.monitor.notification_sent[self.session_name] = False
        
        # Clear event history
        self.monitor.event_bus.clear_history()
        
        # Mock state analyzer to return ERROR
        with patch.object(self.monitor, 'get_session_state', return_value=SessionState.ERROR):
            # Execute
            should_notify, task_completion = self.monitor.should_send_completion_notification(self.session_name)
            
        # Verify event was emitted
        assert len(self.monitor.event_bus.event_history) > 0
        last_event = self.monitor.event_bus.event_history[-1]
        assert last_event.session_name == self.session_name
        assert last_event.new_state == SessionState.ERROR.value
        assert should_notify is True
    
    def test_event_based_completion_recording(self):
        """
        Test that the event-based system properly records completions
        """
        # Setup
        self.monitor.last_state[self.session_name] = SessionState.WORKING
        self.monitor.notification_sent[self.session_name] = False
        
        # Clear event history
        self.monitor.event_bus.clear_history()
        
        # Create a mock completion recorder to verify it gets called
        mock_on_completion = Mock()
        self.monitor.event_bus.subscribe(mock_on_completion)
        
        # Mock state analyzer
        with patch.object(self.monitor, 'get_session_state', return_value=SessionState.IDLE):
            # Execute
            should_notify, _ = self.monitor.should_send_completion_notification(self.session_name)
            
        # Verify event was emitted and listener was called
        assert len(self.monitor.event_bus.event_history) > 0
        mock_on_completion.assert_called_once()
        
        # Verify the event details
        call_args = mock_on_completion.call_args[0][0]  # Get the event passed to listener
        assert call_args.session_name == self.session_name
        assert call_args.event_type == CompletionEventType.STATE_TRANSITION
        assert should_notify is True
    
    def test_completion_time_persists_to_file(self):
        """
        Integration test: Verify completion time is actually saved to JSON file
        """
        import json
        import tempfile
        from pathlib import Path
        
        # Use temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write('{}')
        
        try:
            # Create tracker with temp file
            tracker = ImprovedWaitTimeTracker(completion_path=tmp_path)
            
            # Mark completion
            test_session = "test_session_persist"
            tracker.mark_completion(test_session)
            
            # Read file directly
            with open(tmp_path, 'r') as f:
                data = json.load(f)
            
            # Verify session is in file
            assert test_session in data
            assert isinstance(data[test_session], (int, float))
            assert data[test_session] > 0
            
        finally:
            # Cleanup
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
