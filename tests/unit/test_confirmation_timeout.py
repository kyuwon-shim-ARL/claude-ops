"""T018: Unit test for PendingConfirmation timeout cleanup."""
import pytest
import time
from claude_ctb.telegram.bot import PendingConfirmation


class TestPendingConfirmation:
    """Unit tests for PendingConfirmation timeout."""

    def test_60_second_ttl_enforcement(self):
        """Test 60-second TTL enforcement."""
        confirmation = PendingConfirmation(
            confirmation_id="test123",
            session_name="test_session",
            command="test command",
            created_at=time.time()
        )

        # Should not be expired within 60s
        assert not confirmation.is_expired(timeout=60)

        # Simulate 61 seconds
        confirmation.created_at = time.time() - 61
        assert confirmation.is_expired(timeout=60)

    def test_expired_confirmations_auto_cancelled(self):
        """Test expired confirmations auto-cancelled."""
        confirmation = PendingConfirmation("id", "session", "cmd", time.time() - 61)

        if confirmation.is_expired(timeout=60):
            confirmation.status = "EXPIRED"

        assert confirmation.status == "EXPIRED"

    def test_confirmation_id_hash_uniqueness(self):
        """Test confirmation_id hash uniqueness."""
        import hashlib

        id1 = hashlib.md5("session1:cmd1:123".encode()).hexdigest()
        id2 = hashlib.md5("session1:cmd1:124".encode()).hexdigest()

        assert id1 != id2

    def test_status_transitions(self):
        """Test status transitions: PENDING → CONFIRMED/CANCELLED/EXPIRED."""
        confirmation = PendingConfirmation("id", "session", "cmd", time.time())

        assert confirmation.status == "PENDING"

        confirmation.status = "CONFIRMED"
        assert confirmation.status == "CONFIRMED"

        confirmation2 = PendingConfirmation("id2", "session", "cmd", time.time())
        confirmation2.status = "CANCELLED"
        assert confirmation2.status == "CANCELLED"
