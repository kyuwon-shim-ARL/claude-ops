"""
T014: Integration test for 200-line screen history state detection.
Tests that state detection uses 200-line capture and avoids false positives.
"""
import pytest
import subprocess
import time
from claude_ctb.utils.session_state import get_screen_content, detect_state


class TestStateDetection200Lines:
    """Integration test for 200-line screen history state detection."""

    def test_captures_last_200_lines(self):
        """Test that system captures last 200 lines from session."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Generate 250 lines
            for i in range(250):
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_name, f"echo 'Line {i}'", "Enter"],
                    check=True
                )

            time.sleep(1)

            # Capture screen content (should use -S -200)
            content = get_screen_content(session_name)

            # Count lines
            lines = [l for l in content.split("\n") if l.strip()]

            # Should have at most 200 lines
            assert len(lines) <= 200, f"Should capture at most 200 lines, got {len(lines)}"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_state_detection_analyzes_200_line_buffer(self):
        """Test that state detection analyzes 200-line buffer."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Generate history
            for i in range(250):
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_name, f"echo 'Line {i}'", "Enter"],
                    check=True
                )

            time.sleep(1)

            # Detect state
            state = detect_state(session_name=session_name)

            # State detection should work with 200-line buffer
            assert state is not None, "State detection should return result"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_no_false_positives_from_old_history(self):
        """Test that old completion markers beyond 200 lines don't trigger false notifications."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Generate old completion marker first
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "echo 'esc to interrupt (OLD)'", "Enter"],
                check=True
            )

            # Generate 210 lines to push old marker out of 200-line window
            for i in range(210):
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_name, f"echo 'new line {i}'", "Enter"],
                    check=True
                )

            time.sleep(1)

            # Capture only last 200 lines
            content = get_screen_content(session_name)

            # Old marker should NOT be in 200-line window (it's at line 1, we capture lines 12-211)
            assert "esc to interrupt (OLD)" not in content, \
                "Old completion marker should be outside 200-line window"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)
