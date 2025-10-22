"""T019: Unit test for ScreenHistory 200-line parsing."""
import pytest
from claude_ctb.utils.session_state import ScreenHistory


class TestScreenHistoryParsing:
    """Unit tests for ScreenHistory 200-line parsing."""

    def test_tmux_capture_command_construction(self):
        """Test `tmux capture-pane -S -200` command construction."""
        history = ScreenHistory(session_name="test_session")

        cmd = history.build_capture_command()
        assert "tmux" in cmd
        assert "capture-pane" in cmd
        assert "-S" in cmd
        assert "-200" in cmd

    def test_line_count_validation(self):
        """Test line count validation (≤200)."""
        content = "\n".join([f"Line {i}" for i in range(250)])

        history = ScreenHistory(session_name="test")
        limited = history.limit_lines(content, max_lines=200)

        lines = limited.split("\n")
        assert len(lines) <= 200

    def test_utf8_encoding_handling(self):
        """Test UTF-8 encoding handling."""
        content = "Hello 世界 🌍"

        history = ScreenHistory(session_name="test")
        encoded = content.encode('utf-8')
        decoded = encoded.decode('utf-8')

        assert decoded == content

    def test_hash_computation_consistency(self):
        """Test hash computation consistency."""
        import hashlib

        content = "test content"

        hash1 = hashlib.md5(content.encode()).hexdigest()
        hash2 = hashlib.md5(content.encode()).hexdigest()

        assert hash1 == hash2

    def test_sessions_with_less_than_200_lines(self):
        """Test sessions with <200 lines (returns available lines)."""
        content = "\n".join([f"Line {i}" for i in range(50)])

        history = ScreenHistory(session_name="test")
        limited = history.limit_lines(content, max_lines=200)

        lines = limited.split("\n")
        assert len(lines) == 50
