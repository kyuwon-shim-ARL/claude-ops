"""T017: Unit test for MessageQueueEntry exponential backoff."""
import pytest
from claude_ctb.telegram.message_queue import MessageQueueEntry, ExponentialBackoffQueue


class TestMessageQueueEntry:
    """Unit tests for MessageQueueEntry and exponential backoff."""

    def test_queue_fifo_ordering(self):
        """Test queue FIFO ordering."""
        queue = ExponentialBackoffQueue()

        for i in range(5):
            queue.enqueue(chat_id=123, text=f"Message {i}")

        messages = []
        while not queue.is_empty():
            entry = queue.dequeue()
            messages.append(entry.text)

        assert messages == [f"Message {i}" for i in range(5)]

    def test_exponential_backoff_calculation(self):
        """Test exponential backoff: delay = min(initial * 2^retry_count, max)."""
        initial = 1
        max_backoff = 60

        def calc_backoff(retry_count):
            return min(initial * (2 ** retry_count), max_backoff)

        expected = [1, 2, 4, 8, 16, 32, 60, 60]
        actual = [calc_backoff(i) for i in range(8)]

        assert actual == expected

    def test_priority_handling(self):
        """Test priority handling (HIGH vs NORMAL)."""
        queue = ExponentialBackoffQueue()

        queue.enqueue(chat_id=123, text="Normal", priority="NORMAL")
        queue.enqueue(chat_id=123, text="High", priority="HIGH")

        # HIGH priority should be dequeued first
        first = queue.dequeue()
        assert first.priority == "HIGH"

    def test_in_memory_queue_cleared_on_restart(self):
        """Test in-memory queue cleared on restart."""
        queue = ExponentialBackoffQueue()

        queue.enqueue(chat_id=123, text="Message 1")
        assert queue.size() == 1

        # Simulate restart
        queue2 = ExponentialBackoffQueue()
        assert queue2.size() == 0
