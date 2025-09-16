"""
Completion Event System

Event-driven architecture for tracking completion times independently
of notification status.
"""

import logging
import time
from typing import Optional, Callable, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class CompletionEventType(Enum):
    """Types of completion events"""
    STATE_TRANSITION = "state_transition"  # Work state changed
    EXPLICIT_COMPLETION = "explicit_completion"  # Explicit completion detected
    TIMEOUT_COMPLETION = "timeout_completion"  # Timeout-based completion
    USER_MARKED = "user_marked"  # User manually marked as complete


@dataclass
class CompletionEvent:
    """Represents a completion event"""
    session_name: str
    event_type: CompletionEventType
    timestamp: float
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class CompletionEventBus:
    """
    Event bus for completion events.
    Decouples completion detection from notification and recording.
    """
    
    def __init__(self):
        self.listeners: List[Callable[[CompletionEvent], None]] = []
        self.event_history: List[CompletionEvent] = []
        self.max_history = 100
    
    def subscribe(self, listener: Callable[[CompletionEvent], None]):
        """
        Subscribe to completion events
        
        Args:
            listener: Function that will be called with CompletionEvent
        """
        if listener not in self.listeners:
            self.listeners.append(listener)
            listener_name = getattr(listener, '__name__', str(listener))
            logger.info(f"Subscribed listener: {listener_name}")
    
    def unsubscribe(self, listener: Callable[[CompletionEvent], None]):
        """
        Unsubscribe from completion events
        
        Args:
            listener: Function to remove from listeners
        """
        if listener in self.listeners:
            self.listeners.remove(listener)
            logger.info(f"Unsubscribed listener: {listener.__name__}")
    
    def emit(self, event: CompletionEvent):
        """
        Emit a completion event to all listeners
        
        Args:
            event: The completion event to emit
        """
        # Add to history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Notify all listeners
        for listener in self.listeners:
            try:
                listener(event)
            except Exception as e:
                listener_name = getattr(listener, '__name__', str(listener))
                logger.error(f"Error in listener {listener_name}: {e}")
    
    def get_recent_events(self, session_name: Optional[str] = None, 
                         limit: int = 10) -> List[CompletionEvent]:
        """
        Get recent completion events
        
        Args:
            session_name: Filter by session name (optional)
            limit: Maximum number of events to return
            
        Returns:
            List of recent completion events
        """
        events = self.event_history
        
        if session_name:
            events = [e for e in events if e.session_name == session_name]
        
        return events[-limit:]
    
    def clear_history(self):
        """Clear event history"""
        self.event_history.clear()


class CompletionTimeRecorder:
    """
    Listens to completion events and records completion times.
    This is separate from notification logic.
    """
    
    def __init__(self, tracker):
        self.tracker = tracker
        self.last_recorded: dict[str, float] = {}
    
    def on_completion_event(self, event: CompletionEvent):
        """
        Handle completion event by recording time
        
        Args:
            event: The completion event
        """
        # Avoid duplicate recordings within 5 seconds
        last_time = self.last_recorded.get(event.session_name, 0)
        if event.timestamp - last_time < 5:
            logger.debug(f"Skipping duplicate completion recording for {event.session_name}")
            return
        
        # Record completion time
        logger.info(f"📝 Recording completion for {event.session_name} (Event: {event.event_type.value})")
        # Use mark_completion_safe to handle session suffix changes properly
        if hasattr(self.tracker, 'mark_completion_safe'):
            self.tracker.mark_completion_safe(event.session_name)
        else:
            # Fallback for compatibility
            self.tracker.mark_completion(event.session_name)
        self.last_recorded[event.session_name] = event.timestamp


class CompletionNotifier:
    """
    Listens to completion events and sends notifications.
    This is separate from time recording logic.
    """
    
    def __init__(self, notifier_factory):
        self.notifier_factory = notifier_factory
        self.last_notified: dict[str, float] = {}
        self.notification_cooldown = 30  # seconds
    
    def on_completion_event(self, event: CompletionEvent):
        """
        Handle completion event by sending notification
        
        Args:
            event: The completion event
        """
        # Check cooldown
        last_time = self.last_notified.get(event.session_name, 0)
        if event.timestamp - last_time < self.notification_cooldown:
            logger.debug(f"Notification on cooldown for {event.session_name}")
            return
        
        # Send notification
        try:
            notifier = self.notifier_factory()
            success = notifier.send_work_completion_notification()
            
            if success:
                logger.info(f"📢 Sent notification for {event.session_name}")
                self.last_notified[event.session_name] = event.timestamp
            else:
                logger.warning(f"Failed to send notification for {event.session_name}")
                
        except Exception as e:
            logger.error(f"Error sending notification for {event.session_name}: {e}")


# Global event bus instance
event_bus = CompletionEventBus()


def emit_completion(session_name: str, event_type: CompletionEventType, 
                    **metadata) -> None:
    """
    Convenience function to emit completion event
    
    Args:
        session_name: Name of the session
        event_type: Type of completion event
        **metadata: Additional metadata for the event
    """
    event = CompletionEvent(
        session_name=session_name,
        event_type=event_type,
        timestamp=time.time(),
        metadata=metadata
    )
    event_bus.emit(event)
