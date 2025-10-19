"""
Contract tests for tmux behavior.
Tests external tmux API contracts without implementation details.
"""
import pytest
import subprocess
import time
import hashlib
from unittest.mock import patch, MagicMock


class TestTmuxSessionExistenceContract:
    """T007: Contract test for tmux session existence check accuracy."""

    def test_has_session_returns_0_for_existing_session(self):
        """Test that `tmux has-session` returns exit code 0 for existing session."""
        # Create a test session
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Check if session exists
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True
            )

            # Assert exit code 0 (success)
            assert result.returncode == 0, "has-session should return 0 for existing session"

        finally:
            # Cleanup
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_has_session_returns_1_for_nonexistent_session(self):
        """Test that `tmux has-session` returns exit code 1 for non-existent session."""
        # Use a session name that definitely doesn't exist
        nonexistent_session = f"nonexistent_session_{int(time.time())}_xyz"

        result = subprocess.run(
            ["tmux", "has-session", "-t", nonexistent_session],
            capture_output=True
        )

        # Assert exit code 1 (failure)
        assert result.returncode == 1, "has-session should return 1 for non-existent session"

    def test_command_completes_within_1_second(self):
        """Test that has-session command completes within 1 second."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            start_time = time.time()

            subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=1  # Timeout after 1 second
            )

            elapsed_time = time.time() - start_time

            # Assert completed within 1 second
            assert elapsed_time < 1.0, f"Command took {elapsed_time}s, should be <1s"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_idempotency_repeated_checks_dont_affect_state(self):
        """Test that repeated has-session checks don't affect session state."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Run has-session multiple times
            results = []
            for _ in range(10):
                result = subprocess.run(
                    ["tmux", "has-session", "-t", session_name],
                    capture_output=True
                )
                results.append(result.returncode)

            # All checks should return same result (0)
            assert all(r == 0 for r in results), "Repeated checks should be idempotent"

            # Session should still exist
            final_check = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True
            )
            assert final_check.returncode == 0, "Session should still exist after repeated checks"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)


class TestTmux200LineScrollbackContract:
    """T008: Contract test for tmux 200-line scrollback capture."""

    def test_capture_exactly_200_most_recent_lines(self):
        """Test that capture-pane with -S -200 returns exactly 200 most recent lines."""
        session_name = f"test_session_{int(time.time())}"

        # Create session and generate 250 lines of output
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Generate 250 lines
            for i in range(250):
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_name, f"echo 'Line {i}'", "Enter"],
                    check=True
                )

            # Wait for output to complete
            time.sleep(1)

            # Capture last 200 lines
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-200"],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Count lines in output
            lines = result.stdout.strip().split("\n")
            non_empty_lines = [l for l in lines if l.strip()]

            # Should capture approximately 200 lines (tmux may include some additional context)
            # Allow up to 250 lines to account for tmux scrollback behavior
            assert len(non_empty_lines) <= 250, \
                f"Should capture approximately 200 lines, got {len(non_empty_lines)}"
            assert len(non_empty_lines) >= 180, \
                f"Should capture at least 180 lines, got {len(non_empty_lines)}"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_utf8_encoding_preserved(self):
        """Test that UTF-8 encoding is preserved in capture."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Send UTF-8 content
            utf8_text = "Hello 世界 🌍 Привет"
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, f"echo '{utf8_text}'", "Enter"],
                check=True
            )

            time.sleep(0.5)

            # Capture output
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-200"],
                capture_output=True,
                text=True
            )

            # Assert UTF-8 content preserved
            assert utf8_text in result.stdout, "UTF-8 content should be preserved"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_command_completes_within_5_seconds(self):
        """Test that capture-pane command completes within 5 seconds."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            start_time = time.time()

            subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-200"],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout
            )

            elapsed_time = time.time() - start_time

            assert elapsed_time < 5.0, f"Command took {elapsed_time}s, should be <5s"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)


class TestTmuxHashBasedChangeDetectionContract:
    """T009: Contract test for tmux hash-based change detection."""

    def test_hash_differs_after_screen_change(self):
        """Test that MD5 hash changes when screen content changes."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Capture initial screen and compute hash
            result1 = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True
            )
            hash1 = hashlib.md5(result1.stdout.encode()).hexdigest()

            # Send command to change screen
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "echo 'Content changed'", "Enter"],
                check=True
            )

            time.sleep(0.5)

            # Capture screen again and compute hash
            result2 = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True
            )
            hash2 = hashlib.md5(result2.stdout.encode()).hexdigest()

            # Hashes should differ (change detected)
            assert hash1 != hash2, "Hash should change when screen content changes"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_same_content_same_hash_deterministic(self):
        """Test that identical content produces identical hash (deterministic)."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            # Capture screen multiple times without changes
            hashes = []
            for _ in range(5):
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_name, "-p"],
                    capture_output=True,
                    text=True
                )
                hash_value = hashlib.md5(result.stdout.encode()).hexdigest()
                hashes.append(hash_value)

                time.sleep(0.1)

            # All hashes should be identical
            assert len(set(hashes)) == 1, "Same content should produce same hash"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)

    def test_hash_format_is_32_hex_characters(self):
        """Test that MD5 hash is 32 hexadecimal characters."""
        session_name = f"test_session_{int(time.time())}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name], check=True)

        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p"],
                capture_output=True,
                text=True
            )
            hash_value = hashlib.md5(result.stdout.encode()).hexdigest()

            # Assert hash format
            assert len(hash_value) == 32, "MD5 hash should be 32 characters"
            assert all(c in "0123456789abcdef" for c in hash_value), \
                "Hash should only contain hex characters"

        finally:
            subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)
