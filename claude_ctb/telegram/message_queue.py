"""
Message queue for Telegram rate limit handling with exponential backoff.
"""
from dataclasses import dataclass, field
from typing import Optional
import time
import uuid
import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class MessageQueueEntry:
    """
    Entry in the message queue with retry tracking.

    Attributes:
        message_id: Unique identifier for this message
        chat_id: Telegram chat ID
        text: Message content
        retry_count: Number of retry attempts
        next_retry_time: Timestamp for next retry
        enqueue_time: When message was first queued
        priority: Message priority (HIGH, NORMAL)
    """

    chat_id: int
    text: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    retry_count: int = 0
    next_retry_time: float = field(default_factory=time.time)
    enqueue_time: float = field(default_factory=time.time)
    priority: str = "NORMAL"  # HIGH or NORMAL


class ExponentialBackoffQueue:
    """
    In-memory queue with exponential backoff for failed messages.

    Attributes:
        initial_backoff: Initial backoff delay (default: 1s)
        max_backoff: Maximum backoff delay (default: 60s)
        queue: Internal queue storage
    """

    def __init__(self, initial_backoff: int = 1, max_backoff: int = 60):
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self._queue = deque()

    def enqueue(
        self,
        chat_id: int,
        text: str,
        priority: str = "NORMAL"
    ) -> MessageQueueEntry:
        """
        Add message to queue.

        Args:
            chat_id: Telegram chat ID
            text: Message content
            priority: Message priority (HIGH/NORMAL)

        Returns:
            MessageQueueEntry that was enqueued
        """
        entry = MessageQueueEntry(
            chat_id=chat_id,
            text=text,
            priority=priority
        )

        if priority == "HIGH":
            # High priority messages go to front
            self._queue.appendleft(entry)
        else:
            self._queue.append(entry)

        # T040: Log message enqueued
        logger.info(
            f"Message enqueued (priority={priority}, queue_size={self.size()}): "
            f"{text[:50]}{'...' if len(text) > 50 else ''}"
        )

        return entry

    def dequeue(self) -> Optional[MessageQueueEntry]:
        """
        Remove and return next message from queue.

        Returns:
            MessageQueueEntry or None if queue empty
        """
        if len(self._queue) == 0:
            return None

        return self._queue.popleft()

    def size(self) -> int:
        """Return current queue size."""
        return len(self._queue)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0

    def calculate_backoff(self, retry_count: int) -> int:
        """
        Calculate exponential backoff delay.

        Formula: min(initial * 2^retry_count, max)

        Args:
            retry_count: Number of retry attempts

        Returns:
            Backoff delay in seconds
        """
        backoff = min(
            self.initial_backoff * (2 ** retry_count),
            self.max_backoff
        )
        return backoff

    async def retry_with_backoff(self, entry: MessageQueueEntry):
        """
        Re-queue message with exponential backoff.

        Args:
            entry: Message entry to retry
        """
        entry.retry_count += 1
        backoff = self.calculate_backoff(entry.retry_count)
        entry.next_retry_time = time.time() + backoff

        # T040: Log retry attempt with backoff
        delivery_latency = time.time() - entry.enqueue_time
        logger.info(
            f"Message retry #{entry.retry_count} with {backoff}s backoff "
            f"(queue_size={self.size()}, latency={delivery_latency:.1f}s): "
            f"{entry.text[:50]}{'...' if len(entry.text) > 50 else ''}"
        )

        # Re-add to queue
        self._queue.append(entry)

    def get_queue(self):
        """Get reference to internal queue (for testing)."""
        return self._queue


# Global queue instance (in-memory, cleared on restart)
_global_queue: Optional[ExponentialBackoffQueue] = None


def get_global_queue() -> ExponentialBackoffQueue:
    """Get or create global message queue instance."""
    global _global_queue
    if _global_queue is None:
        _global_queue = ExponentialBackoffQueue()
    return _global_queue


# Legacy compatibility: Old file-based message queue (kept for backward compatibility)
class MessageQueue:
    """Legacy file-based message queue (deprecated, use ExponentialBackoffQueue instead)."""

    def __init__(self, queue_dir: str = "/tmp/claude-ops-messages"):
        from pathlib import Path
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(exist_ok=True, parents=True)

    def add_message(self, message_text: str, user_id: Optional[str] = None) -> bool:
        """Add message to legacy queue."""
        return True

    def get_pending_messages(self):
        """Get pending messages from legacy queue."""
        return []

    def mark_processed(self, message_id: str) -> bool:
        """Mark message as processed."""
        return True


# Global legacy queue instance
message_queue = MessageQueue()


def add_keyboard_message(message_text: str) -> bool:
    """Legacy function: Add keyboard message."""
    return message_queue.add_message(message_text)
