"""
Test cases for wait time calculation edge cases and bugs
"""

import pytest
import time
import json
import unittest.mock
from pathlib import Path
from datetime import datetime, timedelta
from claude_ops.utils.wait_time_tracker import WaitTimeTracker


class TestWaitTimeEdgeCases:
    """Test edge cases that cause incorrect wait time calculation"""
    
    def test_timestamp_not_updated_on_completion(self, tmp_path):
        """Test: completion timestamp not being updated causes accumulating wait times"""
        # GIVEN: A tracker with initial completion time
        tracker = WaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_test_session"
        
        # Initial completion at T0
        initial_time = time.time()
        tracker.mark_completion(session_name)
        
        # WHEN: Time passes but completion is not marked again (Hook failure scenario)
        # Simulate 1 hour passing
        future_time = initial_time + 3600
        
        # Mock time.time() to return future time
        import unittest.mock
        with unittest.mock.patch('time.time', return_value=future_time):
            wait_time_1 = tracker.get_wait_time_since_completion(session_name)
        
        # Another hour passes, still no new completion mark
        future_time_2 = initial_time + 7200  # 2 hours total
        with unittest.mock.patch('time.time', return_value=future_time_2):
            wait_time_2 = tracker.get_wait_time_since_completion(session_name)
        
        # THEN: Wait time keeps accumulating incorrectly
        assert wait_time_1 == pytest.approx(3600, rel=0.1)  # Should be 1 hour
        assert wait_time_2 == pytest.approx(7200, rel=0.1)  # Should be 2 hours
        
        # This is the bug: wait time keeps growing even though session might have
        # completed work multiple times without proper notification
    
    def test_rapid_state_changes_missed_by_polling(self, tmp_path):
        """Test: Rapid WORKING->WAITING transitions missed by 5-second polling"""
        tracker = WaitTimeTracker(
            storage_path=str(tmp_path / "wait.json"),
            state_path=str(tmp_path / "states.json"),
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_rapid_session"
        
        # GIVEN: Session completes work at T0
        initial_time = time.time()
        tracker.mark_completion(session_name)
        
        # WHEN: Session rapidly goes WORKING->WAITING->WORKING within polling interval
        # This simulates Claude completing a quick task in < 5 seconds
        
        # At T+1s: Still reports as waiting (correct)
        with unittest.mock.patch('time.time', return_value=initial_time + 1):
            wait_1 = tracker.get_wait_time_since_completion(session_name)
            assert wait_1 == pytest.approx(1.0, rel=0.1)
        
        # At T+3s: Claude starts and completes another task (but no mark_completion called)
        # This would happen if polling missed the state change
        
        # At T+3600s (1 hour later): Still using old completion time
        with unittest.mock.patch('time.time', return_value=initial_time + 3600):
            wait_2 = tracker.get_wait_time_since_completion(session_name)
            # BUG: Shows 1 hour wait even though work was done 3 seconds after initial
            assert wait_2 == pytest.approx(3600, rel=0.1)
    
    def test_fallback_calculation_with_old_sessions(self, tmp_path):
        """Test: Fallback mechanism for sessions older than 24 hours"""
        tracker = WaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_old_session"
        
        # GIVEN: A completion timestamp from 25 hours ago
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        tracker.completion_times[session_name] = old_time
        tracker._save_completions()
        
        # WHEN: Getting wait time (should trigger fallback due to >24h)
        wait_time = tracker.get_wait_time_since_completion(session_name)
        
        # THEN: Should use fallback estimate instead of 25 hours
        # Fallback returns minimum 300 seconds (5 minutes) when session doesn't exist
        assert wait_time >= 300  # At least 5 minutes
        assert wait_time < 25 * 3600  # But not 25 hours
    
    def test_future_timestamp_corruption(self, tmp_path):
        """Test: System clock changes or corruption causes future timestamps"""
        tracker = WaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        session_name = "claude_future_session"
        
        # GIVEN: A corrupted future timestamp (1 hour in the future)
        future_time = time.time() + 3600
        tracker.completion_times[session_name] = future_time
        tracker._save_completions()
        
        # WHEN: Validation and fix is run
        tracker.validate_and_fix_timestamps()
        
        # THEN: Future timestamp should be corrected to reasonable past time
        corrected_time = tracker.completion_times.get(session_name)
        if corrected_time:  # Might be deleted if > 24h rule applies
            assert corrected_time < time.time()  # Must be in the past
            wait_time = tracker.get_wait_time_since_completion(session_name)
            assert wait_time >= 0  # Wait time must be positive
            assert wait_time <= 3600  # Should be reasonable (not negative or huge)
    
    def test_concurrent_session_timestamp_mixing(self, tmp_path):
        """Test: Multiple sessions updating timestamps concurrently"""
        tracker = WaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        
        # GIVEN: Multiple sessions with different completion times
        sessions = {
            "claude_session_1": time.time() - 3600,  # 1 hour ago
            "claude_session_2": time.time() - 7200,  # 2 hours ago  
            "claude_session_3": time.time() - 300,   # 5 minutes ago
        }
        
        for session, timestamp in sessions.items():
            tracker.completion_times[session] = timestamp
        tracker._save_completions()
        
        # WHEN: Getting wait times for all sessions
        wait_times = {}
        for session in sessions:
            wait_times[session] = tracker.get_wait_time_since_completion(session)
        
        # THEN: Each session should have correct individual wait time
        assert wait_times["claude_session_1"] == pytest.approx(3600, rel=0.1)
        assert wait_times["claude_session_2"] == pytest.approx(7200, rel=0.1)
        assert wait_times["claude_session_3"] == pytest.approx(300, rel=0.1)
        
        # WHEN: One session updates, others shouldn't be affected
        tracker.mark_completion("claude_session_2")
        
        # THEN: Only session_2 wait time should reset
        new_wait_2 = tracker.get_wait_time_since_completion("claude_session_2")
        assert new_wait_2 < 10  # Should be near 0
        
        # Others should remain unchanged
        assert tracker.get_wait_time_since_completion("claude_session_1") == pytest.approx(3600, rel=0.1)
        assert tracker.get_wait_time_since_completion("claude_session_3") == pytest.approx(300, rel=0.1)
    
    def test_stale_timestamp_cleanup(self, tmp_path):
        """Test: Automatic cleanup of stale timestamps older than 24 hours"""
        tracker = WaitTimeTracker(
            completion_path=str(tmp_path / "completions.json")
        )
        
        # GIVEN: Mix of fresh and stale timestamps
        current_time = time.time()
        sessions = {
            "claude_fresh": current_time - 3600,      # 1 hour ago (fresh)
            "claude_stale": current_time - (30 * 3600),  # 30 hours ago (stale)
            "claude_recent": current_time - 600,      # 10 minutes ago (fresh)
        }
        
        for session, timestamp in sessions.items():
            tracker.completion_times[session] = timestamp
        tracker._save_completions()
        
        # WHEN: Cleanup is triggered
        tracker.cleanup_old_sessions(max_age_hours=24)
        
        # Reload to check persistence
        tracker.completion_times = tracker._load_completions()
        
        # THEN: Stale session should be removed
        assert "claude_fresh" in tracker.completion_times
        assert "claude_recent" in tracker.completion_times
        assert "claude_stale" not in tracker.completion_times  # Should be cleaned up
    
    def test_wait_time_persistence_across_restart(self, tmp_path):
        """Test: Wait times persist correctly across bot restarts"""
        completion_file = tmp_path / "completions.json"
        
        # GIVEN: Tracker with some completion times
        tracker1 = WaitTimeTracker(completion_path=str(completion_file))
        tracker1.mark_completion("claude_session_a")
        time.sleep(0.1)  # Small delay
        tracker1.mark_completion("claude_session_b")
        
        # Save initial wait times
        initial_waits = {
            "a": tracker1.get_wait_time_since_completion("claude_session_a"),
            "b": tracker1.get_wait_time_since_completion("claude_session_b"),
        }
        
        # WHEN: Bot restarts (new tracker instance)
        del tracker1  # Simulate shutdown
        tracker2 = WaitTimeTracker(completion_path=str(completion_file))
        
        # THEN: Wait times should be consistent (slightly increased due to time passing)
        new_waits = {
            "a": tracker2.get_wait_time_since_completion("claude_session_a"),
            "b": tracker2.get_wait_time_since_completion("claude_session_b"),
        }
        
        # Should be slightly more but in same ballpark
        assert new_waits["a"] >= initial_waits["a"]
        assert new_waits["b"] >= initial_waits["b"]
        assert new_waits["a"] - initial_waits["a"] < 1  # Less than 1 second difference
        assert new_waits["b"] - initial_waits["b"] < 1