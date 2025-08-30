"""
Smart Fallback Notification Tracker

Handles fallback notifications when primary notifications fail.
Only sends notifications when screen is frozen and no notification was sent.
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FallbackState:
    """Track fallback notification state for a session"""
    last_screen_hash: str = ""
    last_screen_change_time: float = 0
    notification_sent_times: List[float] = None
    primary_notification_time: float = 0
    fallback_active: bool = False
    
    def __post_init__(self):
        if self.notification_sent_times is None:
            self.notification_sent_times = []


class FallbackNotificationTracker:
    """
    Smart fallback notification system that only activates when:
    1. Primary notification system has failed or missed
    2. Screen hasn't changed for specified intervals
    3. No previous notification at this interval
    """
    
    # Fallback intervals in seconds: 1min, 5min, 15min
    FALLBACK_INTERVALS = [60, 300, 900]
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize fallback tracker with persistent storage"""
        if storage_path is None:
            storage_path = "/tmp/claude_fallback_states.json"
        
        self.storage_path = Path(storage_path)
        self.session_states: Dict[str, FallbackState] = self._load_states()
        
    def _load_states(self) -> Dict[str, FallbackState]:
        """Load fallback states from storage"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    states = {}
                    for session_name, state_data in data.items():
                        state = FallbackState(**state_data)
                        states[session_name] = state
                    return states
            except Exception as e:
                logger.warning(f"Failed to load fallback states: {e}")
                return {}
        return {}
    
    def _save_states(self):
        """Save fallback states to storage"""
        try:
            data = {}
            for session_name, state in self.session_states.items():
                data[session_name] = asdict(state)
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save fallback states: {e}")
    
    def update_screen_hash(self, session_name: str, screen_hash: str) -> bool:
        """
        Update screen hash and return whether screen changed
        
        Returns:
            True if screen changed, False if screen is frozen
        """
        if session_name not in self.session_states:
            self.session_states[session_name] = FallbackState()
        
        state = self.session_states[session_name]
        
        # Check if screen changed
        if screen_hash != state.last_screen_hash:
            # Screen changed - reset fallback tracking
            state.last_screen_hash = screen_hash
            state.last_screen_change_time = time.time()
            state.fallback_active = False
            state.notification_sent_times = []
            self._save_states()
            return True
        
        # Screen hasn't changed
        return False
    
    def record_primary_notification(self, session_name: str):
        """Record when primary notification was successfully sent"""
        if session_name not in self.session_states:
            self.session_states[session_name] = FallbackState()
        
        state = self.session_states[session_name]
        state.primary_notification_time = time.time()
        state.fallback_active = False  # Reset fallback when primary succeeds
        state.notification_sent_times = []
        self._save_states()
        
        logger.info(f"Primary notification recorded for {session_name}, fallback deactivated")
    
    def should_send_fallback(self, session_name: str, screen_hash: str, 
                            primary_notification_failed: bool = False) -> Tuple[bool, Optional[int]]:
        """
        Determine if fallback notification should be sent
        
        Args:
            session_name: Session to check
            screen_hash: Current screen hash
            primary_notification_failed: Whether primary notification has failed
            
        Returns:
            Tuple of (should_send, interval_index) where interval_index indicates which
            interval triggered (0=1min, 1=5min, 2=15min) or None
        """
        # Update screen state first
        screen_changed = self.update_screen_hash(session_name, screen_hash)
        
        if screen_changed:
            # Screen is active, no fallback needed
            return False, None
        
        state = self.session_states.get(session_name)
        if not state:
            return False, None
        
        # Only activate fallback if primary notification has failed or been missed
        if not primary_notification_failed and not state.fallback_active:
            # Check if enough time has passed without primary notification
            # (indicates primary might have failed)
            time_since_primary = time.time() - state.primary_notification_time
            if time_since_primary < 60:  # Less than 1 minute since primary
                return False, None
        
        # Activate fallback mode
        if not state.fallback_active:
            state.fallback_active = True
            logger.info(f"Fallback mode activated for {session_name}")
        
        # Check how long screen has been frozen
        time_frozen = time.time() - state.last_screen_change_time
        
        # Check each interval
        for i, interval in enumerate(self.FALLBACK_INTERVALS):
            if time_frozen >= interval:
                # Check if we already sent notification for this interval
                interval_notified = any(
                    abs(sent_time - (state.last_screen_change_time + interval)) < 30
                    for sent_time in state.notification_sent_times
                )
                
                if not interval_notified:
                    # Should send fallback notification
                    logger.info(
                        f"Fallback trigger for {session_name}: "
                        f"Screen frozen for {time_frozen:.0f}s (interval: {interval}s)"
                    )
                    return True, i
        
        return False, None
    
    def record_fallback_sent(self, session_name: str, interval_index: int):
        """Record that fallback notification was sent"""
        if session_name not in self.session_states:
            return
        
        state = self.session_states[session_name]
        current_time = time.time()
        state.notification_sent_times.append(current_time)
        self._save_states()
        
        interval = self.FALLBACK_INTERVALS[interval_index]
        logger.info(
            f"Fallback notification sent for {session_name} at {interval}s interval "
            f"({interval_index + 1}/{len(self.FALLBACK_INTERVALS)})"
        )
    
    def reset_session(self, session_name: str):
        """Reset fallback tracking for a session"""
        if session_name in self.session_states:
            del self.session_states[session_name]
            self._save_states()
            logger.debug(f"Reset fallback tracking for {session_name}")
    
    def cleanup_old_sessions(self, max_age_hours: float = 24):
        """Remove sessions older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        for session_name, state in self.session_states.items():
            if current_time - state.last_screen_change_time > max_age_seconds:
                to_remove.append(session_name)
        
        for session_name in to_remove:
            del self.session_states[session_name]
            logger.info(f"Removed old fallback state for {session_name}")
        
        if to_remove:
            self._save_states()
    
    def get_fallback_status(self, session_name: str) -> Dict:
        """Get current fallback status for a session"""
        if session_name not in self.session_states:
            return {"active": False, "notifications_sent": 0}
        
        state = self.session_states[session_name]
        time_frozen = time.time() - state.last_screen_change_time if state.last_screen_change_time else 0
        
        return {
            "active": state.fallback_active,
            "screen_frozen_seconds": int(time_frozen),
            "notifications_sent": len(state.notification_sent_times),
            "intervals_completed": [
                i for i, interval in enumerate(self.FALLBACK_INTERVALS)
                if any(
                    abs(sent_time - (state.last_screen_change_time + interval)) < 30
                    for sent_time in state.notification_sent_times
                )
            ]
        }


# Global instance
fallback_tracker = FallbackNotificationTracker()