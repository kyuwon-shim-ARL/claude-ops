"""
Test for session name normalization feature
"""

import unittest
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from claude_ops.utils.wait_time_tracker import WaitTimeTracker


class TestSessionNameNormalization(unittest.TestCase):
    """Test session name normalization functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "wait_times.json"
        self.state_path = Path(self.temp_dir) / "session_states.json"
        self.completion_path = Path(self.temp_dir) / "completion_times.json"

        self.tracker = WaitTimeTracker(
            storage_path=str(self.storage_path),
            state_path=str(self.state_path),
            completion_path=str(self.completion_path)
        )

    def test_normalize_session_name_removes_trailing_numbers(self):
        """Test that normalize_session_name correctly removes trailing -number suffix"""
        test_cases = [
            ("claude_project-5", "claude_project"),
            ("claude_simple_funcscan_test_run-90", "claude_simple_funcscan_test_run"),
            ("claude_urban-microbiome-toolkit-5", "claude_urban-microbiome-toolkit"),
            ("claude_SMILES_property_webapp-4", "claude_SMILES_property_webapp"),
            ("claude_UMT_opt-16", "claude_UMT_opt"),
            ("claude_claude-dev-kit-1", "claude_claude-dev-kit"),
            ("claude_session", "claude_session"),  # No suffix
            ("claude-ops-2", "claude-ops"),  # Different prefix
            ("test-123-456", "test-123"),  # Multiple numbers
        ]

        for input_name, expected in test_cases:
            with self.subTest(input=input_name):
                result = self.tracker.normalize_session_name(input_name)
                self.assertEqual(result, expected, f"Failed for {input_name}")

    def test_has_completion_record_with_normalized_matching(self):
        """Test that has_completion_record finds records using normalized names"""
        # Add a completion record with a suffix
        self.tracker.completion_times["claude_simple_funcscan_test_run-90"] = 1757603682.27
        self.tracker._save_completions()

        # Test direct match
        self.assertTrue(
            self.tracker.has_completion_record("claude_simple_funcscan_test_run-90"),
            "Direct match should work"
        )

        # Test normalized match with different suffix
        self.assertTrue(
            self.tracker.has_completion_record("claude_simple_funcscan_test_run-95"),
            "Should find record via normalization"
        )

        # Test normalized match with no suffix
        self.assertTrue(
            self.tracker.has_completion_record("claude_simple_funcscan_test_run"),
            "Should find record via normalization (no suffix)"
        )

        # Test non-matching session
        self.assertFalse(
            self.tracker.has_completion_record("claude_different_project-1"),
            "Should not find record for different project"
        )

    def test_get_wait_time_since_completion_with_normalization(self):
        """Test that get_wait_time_since_completion uses normalization"""
        current_time = time.time()
        test_timestamp = current_time - 300  # 5 minutes ago

        # Add a completion record with suffix
        self.tracker.completion_times["claude_urban-microbiome-toolkit-3"] = test_timestamp
        self.tracker._save_completions()

        # Test direct match
        wait_time = self.tracker.get_wait_time_since_completion("claude_urban-microbiome-toolkit-3")
        self.assertAlmostEqual(wait_time, 300, delta=1, msg="Direct match should return correct time")

        # Test normalized match with different suffix
        wait_time = self.tracker.get_wait_time_since_completion("claude_urban-microbiome-toolkit-5")
        self.assertAlmostEqual(wait_time, 300, delta=1, msg="Normalized match should return correct time")

        # Test normalized match with no suffix
        wait_time = self.tracker.get_wait_time_since_completion("claude_urban-microbiome-toolkit")
        self.assertAlmostEqual(wait_time, 300, delta=1, msg="No suffix match should return correct time")

    def test_normalization_preserves_exact_match_priority(self):
        """Test that exact matches are preferred over normalized matches"""
        current_time = time.time()

        # Add two records: one with -90, one with -95
        self.tracker.completion_times["claude_project-90"] = current_time - 600  # 10 min ago
        self.tracker.completion_times["claude_project-95"] = current_time - 300  # 5 min ago
        self.tracker._save_completions()

        # Exact match should return the specific timestamp
        wait_time_90 = self.tracker.get_wait_time_since_completion("claude_project-90")
        self.assertAlmostEqual(wait_time_90, 600, delta=1, msg="Should use exact match for -90")

        wait_time_95 = self.tracker.get_wait_time_since_completion("claude_project-95")
        self.assertAlmostEqual(wait_time_95, 300, delta=1, msg="Should use exact match for -95")

        # New suffix should find one of them (implementation dependent)
        wait_time_new = self.tracker.get_wait_time_since_completion("claude_project-100")
        self.assertTrue(
            290 < wait_time_new < 610,
            f"Should find a normalized match, got {wait_time_new}"
        )

    def test_last_notification_time_support(self):
        """Test that normalization works with last_notification_time attribute"""
        # Simulate having last_notification_time attribute
        self.tracker.last_notification_time = {
            "claude_SMILES_property_webapp-4": time.time()
        }

        # Should find via normalization
        self.assertTrue(
            self.tracker.has_completion_record("claude_SMILES_property_webapp-7"),
            "Should find via last_notification_time normalization"
        )

    def test_empty_completion_times(self):
        """Test behavior with empty completion times"""
        # Ensure completion_times is empty
        self.tracker.completion_times = {}

        # Should not find any records
        self.assertFalse(
            self.tracker.has_completion_record("claude_any_project-1"),
            "Should return False for empty completion_times"
        )

    @patch('subprocess.run')
    def test_fallback_when_no_normalized_match(self, mock_run):
        """Test that fallback is used when no normalized match is found"""
        # Mock tmux output for fallback
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="claude_new_project-1: 1 windows (created Sat Jan 14 10:00:00 2025) [80x24]"
        )

        # No records exist
        self.tracker.completion_times = {}

        # Should use fallback
        wait_time = self.tracker.get_wait_time_since_completion("claude_new_project-1")

        # Fallback should return at least 300 seconds
        self.assertGreaterEqual(wait_time, 300, "Fallback should return minimum 5 minutes")


if __name__ == "__main__":
    unittest.main()