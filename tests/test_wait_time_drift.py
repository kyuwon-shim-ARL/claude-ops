"""
e009: Tests for wait-time fallback fix + unified 168h cleanup threshold.

Covers:
- 168h threshold does not prematurely delete completion records
- Deletion only occurs after 168h
- _get_intelligent_fallback uses last_state_change_time instead of tmux
- Sort order stays stable for sessions older than 72h
- cleanup_stale_data and _auto_validate use the same 168h threshold
"""

import time
import pytest
import unittest.mock
from claude_ctb.utils.wait_time_tracker_v2 import ImprovedWaitTimeTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tracker(tmp_path, **kwargs):
    return ImprovedWaitTimeTracker(
        completion_path=str(tmp_path / "completions.json"),
        state_path=str(tmp_path / "states.json"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# T1: 168h threshold — no premature deletion at 72h
# ---------------------------------------------------------------------------

class TestUnified168hThreshold:
    def test_168h_threshold_no_premature_deletion(self, tmp_path):
        """completion_time at 72h past should NOT be removed by _auto_validate"""
        tracker = make_tracker(tmp_path)  # default 168h

        current_time = time.time()
        session = "claude_drift_test"
        # 72 hours ago — old threshold would have deleted this
        tracker.completion_times[session] = current_time - (72 * 3600)
        tracker._save_completions()

        # Force validation
        tracker.last_validation_time = 0
        tracker._auto_validate()

        assert session in tracker.completion_times, (
            "Session deleted at 72h — threshold is not 168h"
        )

    def test_168h_threshold_deletes_after_168h(self, tmp_path):
        """completion_time older than 168h MUST be removed by _auto_validate"""
        tracker = make_tracker(tmp_path)

        current_time = time.time()
        session = "claude_very_old"
        # 169 hours ago — beyond the threshold
        tracker.completion_times[session] = current_time - (169 * 3600)
        tracker._save_completions()

        tracker.last_validation_time = 0
        tracker._auto_validate()

        assert session not in tracker.completion_times, (
            "Session not deleted at 169h — _auto_validate threshold wrong"
        )

    def test_dual_cleanup_paths_unified(self, tmp_path):
        """cleanup_stale_data default and _auto_validate use the same 168h threshold"""
        tracker = make_tracker(tmp_path)

        current_time = time.time()
        session = "claude_unified"
        # 100 hours ago — within 168h so both paths must keep it
        tracker.completion_times[session] = current_time - (100 * 3600)
        tracker._save_completions()

        # _auto_validate path
        tracker.last_validation_time = 0
        tracker._auto_validate()
        assert session in tracker.completion_times, (
            "_auto_validate deleted entry at 100h (should keep until 168h)"
        )

        # cleanup_stale_data path (default 168h)
        tracker.cleanup_stale_data()
        assert session in tracker.completion_times, (
            "cleanup_stale_data deleted entry at 100h (should keep until 168h)"
        )

        # Now push past 168h and confirm both would remove it
        tracker.completion_times[session] = current_time - (170 * 3600)
        tracker._save_completions()

        tracker.cleanup_stale_data()
        assert session not in tracker.completion_times, (
            "cleanup_stale_data did not delete entry at 170h"
        )


# ---------------------------------------------------------------------------
# T2: _get_intelligent_fallback uses last_state_change_time
# ---------------------------------------------------------------------------

class TestFallbackUsesStateChangeTime:
    def test_fallback_uses_state_change_time(self, tmp_path):
        """When last_state_change_time is set, fallback returns elapsed time without tmux call"""
        tracker = make_tracker(tmp_path)
        session = "claude_fallback_test"

        # Simulate a state transition 120 seconds ago
        fake_now = time.time()
        tracker.last_state_change_time[session] = fake_now - 120

        with unittest.mock.patch("subprocess.run") as mock_run:
            wait_time, is_accurate = tracker.get_wait_time_since_completion(session)

            # subprocess.run should NOT have been called
            mock_run.assert_not_called()

        assert not is_accurate  # no completion_times entry → fallback
        assert 118 <= wait_time <= 125, (
            f"Expected ~120s from last_state_change_time, got {wait_time}"
        )

    def test_fallback_falls_through_to_tmux_without_state_change_time(self, tmp_path):
        """When last_state_change_time is absent, tmux is still tried (legacy compat)"""
        tracker = make_tracker(tmp_path)
        session = "claude_no_state_change"

        # No last_state_change_time entry
        assert session not in tracker.last_state_change_time

        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.Mock(
                returncode=1, stdout=""
            )
            wait_time, is_accurate = tracker.get_wait_time_since_completion(session)
            mock_run.assert_called()  # tmux attempted

        assert not is_accurate

    def test_mark_state_transition_records_time(self, tmp_path):
        """mark_state_transition must update last_state_change_time"""
        tracker = make_tracker(tmp_path)
        session = "claude_transition"

        before = time.time()
        tracker.mark_state_transition(session, "waiting")
        after = time.time()

        assert session in tracker.last_state_change_time
        assert before <= tracker.last_state_change_time[session] <= after


# ---------------------------------------------------------------------------
# T3: Sort stability after 72h
# ---------------------------------------------------------------------------

class TestSortOrderStableAfter72h:
    def test_sort_order_stable_after_72h(self, tmp_path):
        """Sessions with completion times > 72h ago must have deterministic wait times"""
        tracker = make_tracker(tmp_path)

        current_time = time.time()
        sessions = {
            "claude_a": current_time - (80 * 3600),   # 80h — older
            "claude_b": current_time - (100 * 3600),  # 100h — oldest
            "claude_c": current_time - (74 * 3600),   # 74h — least old
        }

        for name, ts in sessions.items():
            tracker.completion_times[name] = ts
        tracker._save_completions()

        wait_times = {}
        for name in sessions:
            wt, accurate = tracker.get_wait_time_since_completion(name)
            wait_times[name] = (wt, accurate)

        # All should be accurate (within 168h threshold)
        for name, (wt, accurate) in wait_times.items():
            assert accurate, f"{name} should be accurate at <168h but got accurate={accurate}"

        # Sort order: largest wait_time first (longest wait = oldest completion)
        sorted_sessions = sorted(wait_times.items(), key=lambda x: x[1][0], reverse=True)
        names_in_order = [s for s, _ in sorted_sessions]

        assert names_in_order == ["claude_b", "claude_a", "claude_c"], (
            f"Sort order wrong: {names_in_order}"
        )
