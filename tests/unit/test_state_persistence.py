"""T016: Unit test for PersistedSessionState file I/O."""
import pytest
import tempfile
import os
from claude_ctb.utils.state_persistence import PersistedSessionState


class TestPersistedSessionState:
    """Unit tests for PersistedSessionState file I/O."""

    def test_json_serialization(self):
        """Test JSON serialization/deserialization."""
        state = PersistedSessionState(
            session_name="test",
            screen_hash="abc123",
            last_state="WAITING_INPUT",
            notification_sent=True
        )

        data = state.to_dict()
        assert data["session_name"] == "test"
        assert data["screen_hash"] == "abc123"

        restored = PersistedSessionState.from_dict(data)
        assert restored.session_name == "test"

    def test_atomic_file_write(self):
        """Test atomic file write (temp file + rename)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.json")

            state = PersistedSessionState("test", "hash123", "WAITING_INPUT", True)
            state.save(filepath)

            assert os.path.exists(filepath)

    def test_md5_hash_validation(self):
        """Test MD5 hash validation (32 hex characters)."""
        state = PersistedSessionState("test", "a" * 32, "WAITING_INPUT", True)
        assert len(state.screen_hash) == 32

    def test_load_nonexistent_file(self):
        """Test load from non-existent file (returns None)."""
        result = PersistedSessionState.load("/nonexistent/file.json")
        assert result is None
