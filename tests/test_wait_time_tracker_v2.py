"""
Test cases for improved wait time tracker v2
"""

import pytest
import time
import unittest.mock
from pathlib import Path
from claude_ops.utils.wait_time_tracker_v2 import ImprovedWaitTimeTracker


class TestImprovedWaitTimeTracker:
    """Test the improved wait time tracker with auto-recovery"""
    
    def test_auto_recovery_from_future_timestamps(self, tmp_path):
        """Test: Automatically fixes future timestamps"""
        # GIVEN: Tracker with a future timestamp
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_future"
        
        # Inject future timestamp
        future_time = time.time() + 3600  # 1 hour in future
        tracker.completion_times[session_name] = future_time
        tracker._save_completions()
        
        # WHEN: Getting wait time (triggers auto-validation)
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_name)
        
        # THEN: Should return reasonable wait time and mark as inaccurate
        assert wait_time >= 0  # No negative times
        assert wait_time <= 600  # Should be reset to reasonable value
        assert not is_accurate  # Should indicate it's a fallback
    
    def test_state_based_auto_completion(self, tmp_path):
        """Test: Auto-marks completion on working→waiting transition"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json"),
            state_path=str(tmp_path / "states.json")
        )
        session_name = "claude_auto"
        
        # GIVEN: Session starts in working state
        tracker.mark_state_transition(session_name, "working")
        
        # No completion time yet
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_name)
        assert not is_accurate  # Using fallback
        
        # WHEN: Session transitions to waiting
        time.sleep(0.1)  # Small delay to ensure different timestamp
        tracker.mark_state_transition(session_name, "waiting")
        
        # THEN: Completion should be auto-marked
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_name)
        assert is_accurate  # Should have real completion time now
        assert wait_time < 1  # Should be very recent
    
    def test_intelligent_fallback_with_tmux_info(self, tmp_path):
        """Test: Intelligent fallback uses tmux session info"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        
        # Mock subprocess to simulate tmux session info
        with unittest.mock.patch('subprocess.run') as mock_run:
            # First call: tmux list-sessions
            mock_run.return_value = unittest.mock.Mock(
                returncode=0,
                stdout=f"claude_test:{int(time.time()) - 3600}:{int(time.time()) - 300}\n"
                # Created 1 hour ago, last activity 5 minutes ago
            )
            
            # WHEN: Getting wait time for session without completion record
            wait_time, is_accurate = tracker.get_wait_time_since_completion("claude_test")
            
            # THEN: Should use intelligent fallback based on activity time
            assert not is_accurate  # It's an estimate
            assert 150 <= wait_time <= 300  # Should estimate based on recent activity
    
    def test_accuracy_indicator(self, tmp_path):
        """Test: Accuracy indicator correctly identifies estimate vs actual"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        
        # Case 1: Real completion time
        session_real = "claude_real"
        tracker.mark_completion(session_real)
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_real)
        assert is_accurate  # Should be accurate
        
        # Case 2: No completion record (fallback)
        session_fallback = "claude_fallback"
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_fallback)
        assert not is_accurate  # Should indicate fallback
        
        # Case 3: Very old completion (triggers fallback)
        session_old = "claude_old"
        tracker.completion_times[session_old] = time.time() - (80 * 3600)  # 80 hours ago (exceeds 72h limit)
        tracker._save_completions()
        wait_time, is_accurate = tracker.get_wait_time_since_completion(session_old)
        assert not is_accurate  # Should use fallback due to age
    
    def test_duplicate_completion_prevention(self, tmp_path):
        """Test: Prevents duplicate completion marks within short time"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_duplicate"
        
        # GIVEN: Initial completion mark
        initial_time = time.time()
        with unittest.mock.patch('time.time', return_value=initial_time):
            tracker.mark_completion(session_name)
        
        # WHEN: Another completion attempted within 30 seconds
        with unittest.mock.patch('time.time', return_value=initial_time + 10):
            tracker.mark_completion(session_name)  # Should be skipped
        
        # THEN: Completion time should not change
        assert tracker.completion_times[session_name] == initial_time
        
        # BUT: Force flag should override
        with unittest.mock.patch('time.time', return_value=initial_time + 10):
            tracker.mark_completion(session_name, force=True)
        
        assert tracker.completion_times[session_name] == initial_time + 10
    
    def test_periodic_auto_validation(self, tmp_path):
        """Test: Periodic validation fixes issues automatically"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json"),
            max_reasonable_wait_hours=12
        )
        
        # GIVEN: Mix of good and bad timestamps
        current_time = time.time()
        tracker.completion_times = {
            "claude_good": current_time - 3600,      # 1 hour ago (good)
            "claude_future": current_time + 3600,     # 1 hour future (bad)
            "claude_old": current_time - (15 * 3600), # 15 hours ago (too old)
        }
        tracker._save_completions()
        
        # WHEN: Auto-validation runs (force it to run by resetting last_validation_time)
        tracker.last_validation_time = 0  # Force validation
        tracker._auto_validate()
        
        # THEN: Bad timestamps should be fixed/removed
        assert "claude_good" in tracker.completion_times
        # Future timestamp should be fixed to be in the past
        fixed_future = tracker.completion_times.get("claude_future", 0)
        assert fixed_future < current_time, f"Future timestamp not fixed: {fixed_future} >= {current_time}"
        assert "claude_old" not in tracker.completion_times  # Removed
    
    def test_cleanup_stale_data(self, tmp_path):
        """Test: Cleanup removes old data correctly"""
        tracker = ImprovedWaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        
        # GIVEN: Mix of fresh and stale data
        current_time = time.time()
        tracker.completion_times = {
            "claude_fresh": current_time - 3600,      # 1 hour (keep)
            "claude_stale": current_time - (30 * 3600), # 30 hours (remove)
        }
        tracker._save_completions()
        
        # WHEN: Cleanup with 24 hour threshold
        tracker.cleanup_stale_data(max_age_hours=24)
        
        # THEN: Only fresh data remains
        assert "claude_fresh" in tracker.completion_times
        assert "claude_stale" not in tracker.completion_times