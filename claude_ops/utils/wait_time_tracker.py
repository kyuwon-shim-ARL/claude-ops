"""
Wait Time Tracker for Session Management

Simple and reliable time tracking for Claude sessions
"""

import time
import json
import os
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WaitTimeTracker:
    """Persistent wait time tracker using file storage"""
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize tracker with optional storage path
        
        Args:
            storage_path: Path to store time data (default: /tmp/claude_wait_times.json)
        """
        if storage_path is None:
            storage_path = "/tmp/claude_wait_times.json"
        
        self.storage_path = Path(storage_path)
        self.wait_times: Dict[str, float] = self._load_times()
    
    def _load_times(self) -> Dict[str, float]:
        """Load times from storage file"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    # Convert to float timestamps
                    return {k: float(v) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load wait times: {e}")
                return {}
        return {}
    
    def _save_times(self):
        """Save times to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.wait_times, f)
        except Exception as e:
            logger.warning(f"Failed to save wait times: {e}")
    
    def update_activity(self, session_name: str):
        """Update activity time for a session (when it becomes active)"""
        self.wait_times[session_name] = time.time()
        self._save_times()
        logger.debug(f"Updated activity time for {session_name}")
    
    def get_wait_time(self, session_name: str) -> float:
        """
        Get wait time for a session
        
        Args:
            session_name: Name of the session
            
        Returns:
            Wait time in seconds (0 if just started tracking)
        """
        if session_name not in self.wait_times:
            # Initialize if not tracked
            self.wait_times[session_name] = time.time()
            self._save_times()
            return 0.0
        
        return time.time() - self.wait_times[session_name]
    
    def reset_session(self, session_name: str):
        """Reset wait time for a session (when it becomes active)"""
        self.wait_times[session_name] = time.time()
        self._save_times()
    
    def remove_session(self, session_name: str):
        """Remove a session from tracking"""
        if session_name in self.wait_times:
            del self.wait_times[session_name]
            self._save_times()
    
    def get_all_wait_times(self) -> Dict[str, float]:
        """Get all current wait times"""
        current_time = time.time()
        result = {}
        
        for session_name, last_time in self.wait_times.items():
            result[session_name] = current_time - last_time
        
        return result
    
    def cleanup_old_sessions(self, max_age_hours: float = 24):
        """Remove sessions older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        for session_name, last_time in self.wait_times.items():
            if current_time - last_time > max_age_seconds:
                to_remove.append(session_name)
        
        for session_name in to_remove:
            del self.wait_times[session_name]
            logger.info(f"Removed old session {session_name} from tracking")
        
        if to_remove:
            self._save_times()


# Global instance for easy access
wait_tracker = WaitTimeTracker()