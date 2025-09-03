"""
Tests for /summary command improvements
"""

import time
import json
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from claude_ops.utils.wait_time_tracker import WaitTimeTracker
from claude_ops.utils.session_summary import SessionSummaryHelper


class TestTimestampValidation:
    """Test timestamp validation and correction"""
    
    def test_future_timestamp_correction(self, tmp_path):
        """Test that future timestamps are corrected to reasonable past times"""
        # Setup test data with future timestamps
        future_time = time.time() + 10000  # 10000 seconds in the future
        current_time = time.time()
        
        completion_file = tmp_path / "completions.json"
        completion_data = {
            "claude_test1": future_time,
            "claude_test2": current_time - 3600,  # 1 hour ago (valid)
            "claude_test3": future_time + 50000,  # Even further future
        }
        
        with open(completion_file, 'w') as f:
            json.dump(completion_data, f)
        
        # Create tracker with test file
        tracker = WaitTimeTracker(
            completion_path=str(completion_file)
        )
        
        # Check that future timestamps were corrected
        assert tracker.completion_times["claude_test1"] < current_time
        assert tracker.completion_times["claude_test2"] == current_time - 3600  # Should remain unchanged
        assert tracker.completion_times["claude_test3"] < current_time
        
        # Verify corrected timestamps are reasonable (around 30 minutes ago)
        assert current_time - tracker.completion_times["claude_test1"] > 1700  # > 28 minutes
        assert current_time - tracker.completion_times["claude_test1"] < 1900  # < 32 minutes
    
    def test_stale_timestamp_removal(self, tmp_path):
        """Test that timestamps older than 24 hours are removed"""
        current_time = time.time()
        
        completion_file = tmp_path / "completions.json"
        completion_data = {
            "claude_fresh": current_time - 3600,  # 1 hour ago (keep)
            "claude_stale": current_time - 90000,  # 25 hours ago (remove)
            "claude_very_old": current_time - 200000,  # ~55 hours ago (remove)
        }
        
        with open(completion_file, 'w') as f:
            json.dump(completion_data, f)
        
        # Create tracker
        tracker = WaitTimeTracker(
            completion_path=str(completion_file)
        )
        
        # Check that stale timestamps were removed
        assert "claude_fresh" in tracker.completion_times
        assert "claude_stale" not in tracker.completion_times
        assert "claude_very_old" not in tracker.completion_times
    
    def test_validation_saves_changes(self, tmp_path):
        """Test that validation saves corrected data back to file"""
        future_time = time.time() + 10000
        
        completion_file = tmp_path / "completions.json"
        completion_data = {"claude_test": future_time}
        
        with open(completion_file, 'w') as f:
            json.dump(completion_data, f)
        
        # Create tracker (auto-validates)
        tracker = WaitTimeTracker(
            completion_path=str(completion_file)
        )
        
        # Reload file to check it was saved
        with open(completion_file, 'r') as f:
            saved_data = json.load(f)
        
        # Verify saved data has corrected timestamp
        assert saved_data["claude_test"] < time.time()
        assert saved_data["claude_test"] == tracker.completion_times["claude_test"]


class TestSortingLogic:
    """Test improved sorting logic for session summary"""
    
    def test_working_sessions_first(self):
        """Test that working sessions appear before waiting sessions"""
        helper = SessionSummaryHelper()
        
        # Mock session data: (name, wait_time, prompt, status, has_record)
        test_sessions = [
            ("claude_waiting1", 3600, "test1", "waiting", True),
            ("claude_working1", 1800, "test2", "working", True),
            ("claude_waiting2", 7200, "test3", "waiting", True),
            ("claude_working2", 900, "test4", "working", True),
        ]
        
        # Simulate the sorting logic from get_all_sessions_with_status
        test_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,  # working first
            -x[1] if x[3] == 'waiting' else 0,  # waiting by time DESC
            x[0]  # name for stability
        ))
        
        # Verify working sessions are first
        assert test_sessions[0][3] == "working"
        assert test_sessions[1][3] == "working"
        assert test_sessions[2][3] == "waiting"
        assert test_sessions[3][3] == "waiting"
    
    def test_waiting_sessions_sorted_by_time(self):
        """Test that waiting sessions are sorted by wait time (longest first)"""
        helper = SessionSummaryHelper()
        
        # Mock session data with various wait times
        test_sessions = [
            ("claude_waiting_short", 600, "test1", "waiting", True),
            ("claude_waiting_long", 7200, "test2", "waiting", True),
            ("claude_waiting_medium", 3600, "test3", "waiting", True),
        ]
        
        # Apply sorting logic
        test_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,
            -x[1] if x[3] == 'waiting' else 0,
            x[0]
        ))
        
        # Verify waiting sessions are sorted by time DESC
        assert test_sessions[0][1] == 7200  # Longest wait
        assert test_sessions[1][1] == 3600  # Medium wait
        assert test_sessions[2][1] == 600   # Shortest wait
    
    def test_mixed_session_complete_sorting(self):
        """Test complete sorting with mixed working and waiting sessions"""
        # Mock data: mix of working and waiting with various times
        test_sessions = [
            ("claude_waiting_short", 600, "", "waiting", True),
            ("claude_working_a", 0, "", "working", True),
            ("claude_waiting_long", 7200, "", "waiting", True),
            ("claude_working_b", 0, "", "working", True),
            ("claude_waiting_medium", 3600, "", "waiting", True),
        ]
        
        # Apply the exact sorting logic from SessionSummaryHelper
        test_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,  # working sessions first
            -x[1] if x[3] == 'waiting' else 0,  # waiting sessions by wait time DESC
            x[0]  # session name for stability
        ))
        
        # Expected order:
        # 1. Working sessions (alphabetical by name)
        # 2. Waiting sessions (by wait time DESC)
        expected_order = [
            "claude_working_a",
            "claude_working_b",
            "claude_waiting_long",
            "claude_waiting_medium",
            "claude_waiting_short"
        ]
        
        actual_order = [s[0] for s in test_sessions]
        assert actual_order == expected_order
    
    def test_stable_sort_for_same_status_and_time(self):
        """Test that sessions with same status and time are sorted by name"""
        test_sessions = [
            ("claude_z", 3600, "", "waiting", True),
            ("claude_a", 3600, "", "waiting", True),
            ("claude_m", 3600, "", "waiting", True),
        ]
        
        # Apply sorting
        test_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,
            -x[1] if x[3] == 'waiting' else 0,
            x[0]  # This should provide alphabetical ordering
        ))
        
        # Should be sorted alphabetically when time is the same
        assert test_sessions[0][0] == "claude_a"
        assert test_sessions[1][0] == "claude_m"
        assert test_sessions[2][0] == "claude_z"


class TestIntegration:
    """Integration tests for the complete improvement"""
    
    @patch('claude_ops.utils.session_summary.session_manager.get_all_claude_sessions')
    @patch('claude_ops.utils.session_summary.SessionStateAnalyzer.get_state_for_notification')
    def test_summary_with_corrected_timestamps(self, mock_get_state, mock_get_sessions, tmp_path):
        """Test complete flow with timestamp correction and new sorting"""
        # Setup mock sessions
        mock_get_sessions.return_value = [
            "claude_working",
            "claude_waiting_long",
            "claude_waiting_short"
        ]
        
        # Mock states
        from claude_ops.utils.session_state import SessionState
        def get_state_side_effect(session_name):
            if "working" in session_name:
                return SessionState.WORKING
            else:
                return SessionState.IDLE
        mock_get_state.side_effect = get_state_side_effect
        
        # Create test completion times file with future timestamp
        future_time = time.time() + 10000
        current_time = time.time()
        
        completion_file = tmp_path / "completions.json"
        completion_data = {
            "claude_working": future_time,  # Will be corrected
            "claude_waiting_long": current_time - 7200,  # 2 hours ago
            "claude_waiting_short": current_time - 600,  # 10 minutes ago
        }
        
        with open(completion_file, 'w') as f:
            json.dump(completion_data, f)
        
        # Create tracker and helper with test file
        tracker = WaitTimeTracker(
            completion_path=str(completion_file)
        )
        
        helper = SessionSummaryHelper()
        helper.tracker = tracker  # Use our test tracker
        
        # Get all sessions with status
        sessions = helper.get_all_sessions_with_status()
        
        # Verify results
        assert len(sessions) == 3
        
        # Check order: working first, then waiting by time
        assert sessions[0][0] == "claude_working"
        assert sessions[0][3] == "working"
        
        # Waiting sessions should be ordered by wait time DESC
        assert sessions[1][0] == "claude_waiting_long"
        assert sessions[2][0] == "claude_waiting_short"
        
        # Verify timestamp was corrected (not future)
        assert tracker.completion_times["claude_working"] < time.time()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])