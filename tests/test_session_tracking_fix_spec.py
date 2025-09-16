"""
Test specifications for session tracking fix
Tests MUST fail initially (TADD Red Phase)
"""

import unittest
import tempfile
import json
import time
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from claude_ops.utils.wait_time_tracker import WaitTimeTracker


class TestSessionTrackingFix(unittest.TestCase):
    """Test session tracking improvements for suffix handling"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.completion_path = Path(self.temp_dir) / "completion_times.json"
        
        self.tracker = WaitTimeTracker(
            completion_path=str(self.completion_path)
        )

    def test_mark_completion_safe_creates_new_record(self):
        """mark_completion_safe should create new record with logging"""
        with patch('logging.Logger.info') as mock_log:
            # When: mark_completion_safe is called
            self.tracker.mark_completion_safe("claude_project-8")
            
            # Then: Record is created
            self.assertIn("claude_project-8", self.tracker.completion_times)
            self.assertIsInstance(self.tracker.completion_times["claude_project-8"], float)
            
            # And: Appropriate logs are generated
            log_messages = [call[0][0] for call in mock_log.call_args_list]
            self.assertTrue(any("🔔 Marking completion for: claude_project-8" in msg for msg in log_messages))
            self.assertTrue(any("📊 Base name: claude_project" in msg for msg in log_messages))
            self.assertTrue(any("✅ Created completion record" in msg for msg in log_messages))

    def test_mark_completion_safe_updates_existing_record(self):
        """mark_completion_safe should update existing record for same base name"""
        # Given: Existing record with different suffix
        self.tracker.completion_times["claude_project-8"] = time.time() - 1000
        self.tracker._save_completions()
        
        with patch('logging.Logger.info') as mock_log:
            # When: mark_completion_safe with different suffix
            self.tracker.mark_completion_safe("claude_project-29")
            
            # Then: Old record is replaced
            self.assertNotIn("claude_project-8", self.tracker.completion_times)
            self.assertIn("claude_project-29", self.tracker.completion_times)
            
            # And: Only one record exists for the project
            project_records = [k for k in self.tracker.completion_times.keys() 
                             if k.startswith("claude_project")]
            self.assertEqual(len(project_records), 1)
            
            # And: Update is logged
            log_messages = [call[0][0] for call in mock_log.call_args_list]
            self.assertTrue(any("🔄 Updating existing record" in msg for msg in log_messages))
            self.assertTrue(any("✅ Updated completion record" in msg for msg in log_messages))

    def test_completion_tracking_across_suffix_changes(self):
        """Completion tracking should work across session suffix changes"""
        # Given: Session with suffix -8 has completion
        self.tracker.mark_completion_safe("claude_smiles_project-8")
        time.sleep(0.1)
        
        # When: Query with different suffix -29
        has_record = self.tracker.has_completion_record("claude_smiles_project-29")
        wait_time = self.tracker.get_wait_time_since_completion("claude_smiles_project-29")
        
        # Then: Record is found via normalization
        self.assertTrue(has_record)
        self.assertLess(wait_time, 1.0)  # Recent completion
        self.assertGreater(wait_time, 0.05)  # But not instant

    def test_multiple_projects_independent_tracking(self):
        """Different projects should maintain independent tracking"""
        # Given: Two different projects with completions
        self.tracker.mark_completion_safe("claude_project_a-5")
        time.sleep(0.5)
        self.tracker.mark_completion_safe("claude_project_b-7")
        
        # When: Updating one project
        self.tracker.mark_completion_safe("claude_project_a-15")
        
        # Then: Only project_a is updated
        self.assertIn("claude_project_a-15", self.tracker.completion_times)
        self.assertNotIn("claude_project_a-5", self.tracker.completion_times)
        self.assertIn("claude_project_b-7", self.tracker.completion_times)
        
        # And: Wait times are different
        wait_a = self.tracker.get_wait_time_since_completion("claude_project_a-20")
        wait_b = self.tracker.get_wait_time_since_completion("claude_project_b-20")
        
        self.assertLess(wait_a, wait_b)  # project_a was updated more recently

    def test_notification_handler_integration(self):
        """Completion event system should use mark_completion_safe"""
        # Test the actual integration via event system
        from claude_ops.monitoring.completion_event_system import (
            CompletionEventBus, CompletionEvent, CompletionEventType,
            CompletionTimeRecorder
        )
        
        # Set up event system
        event_bus = CompletionEventBus()
        recorder = CompletionTimeRecorder(self.tracker)
        event_bus.subscribe(recorder.on_completion_event)
        
        # When: completion event is emitted
        with patch.object(self.tracker, 'mark_completion_safe') as mock_mark:
            event = CompletionEvent(
                session_name="claude_test_session-42",
                event_type=CompletionEventType.STATE_TRANSITION,
                timestamp=time.time()
            )
            event_bus.emit(event)
            
            # Then: mark_completion_safe is called
            mock_mark.assert_called_once_with("claude_test_session-42")

    def test_persistence_across_restarts(self):
        """Records should persist across tracker restarts"""
        # Given: Records created with safe marking
        self.tracker.mark_completion_safe("claude_persistence_test-1")
        original_time = self.tracker.completion_times["claude_persistence_test-1"]
        
        # When: New tracker instance loads the data
        new_tracker = WaitTimeTracker(completion_path=str(self.completion_path))
        
        # Then: Records are loaded correctly
        self.assertIn("claude_persistence_test-1", new_tracker.completion_times)
        self.assertEqual(
            new_tracker.completion_times["claude_persistence_test-1"],
            original_time
        )
        
        # And: Can still find via normalization
        has_record = new_tracker.has_completion_record("claude_persistence_test-99")
        self.assertTrue(has_record)

    def test_logging_to_debug_file(self):
        """Notifications should be logged to debug file"""
        debug_log_path = "/tmp/claude_notification_debug.log"
        
        # Set up file handler
        logger = logging.getLogger('claude_ops.utils.wait_time_tracker')
        logger.setLevel(logging.INFO)  # Ensure logger level is also set
        handler = logging.FileHandler(debug_log_path, mode='w')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        try:
            # When: Marking completion
            self.tracker.mark_completion_safe("claude_debug_test-1")
            handler.flush()
            
            # Then: Debug file contains the logs
            with open(debug_log_path, 'r') as f:
                log_content = f.read()
                self.assertIn("Marking completion for: claude_debug_test-1", log_content)
                self.assertIn("Base name: claude_debug_test", log_content)
        finally:
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    unittest.main()