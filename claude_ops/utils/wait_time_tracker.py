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
    
    def __init__(self, storage_path: Optional[str] = None, state_path: Optional[str] = None, 
                 completion_path: Optional[str] = None):
        """
        Initialize tracker with optional storage path
        
        Args:
            storage_path: Path to store time data (default: /tmp/claude_wait_times.json)
            state_path: Path to store state data (default: /tmp/claude_session_states.json)
            completion_path: Path to store completion times (default: /tmp/claude_completion_times.json)
        """
        if storage_path is None:
            storage_path = "/tmp/claude_wait_times.json"
        if state_path is None:
            state_path = "/tmp/claude_session_states.json"
        if completion_path is None:
            completion_path = "/tmp/claude_completion_times.json"
        
        self.storage_path = Path(storage_path)
        self.state_path = Path(state_path)
        self.completion_path = Path(completion_path)
        self.wait_times: Dict[str, float] = self._load_times()
        self.session_states: Dict[str, str] = self._load_states()  # Track last known state
        self.completion_times: Dict[str, float] = self._load_completions()  # Track completion notification times
    
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
    
    def _load_states(self) -> Dict[str, str]:
        """Load session states from storage file"""
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load session states: {e}")
                return {}
        return {}
    
    def _save_times(self):
        """Save times to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.wait_times, f)
        except Exception as e:
            logger.warning(f"Failed to save wait times: {e}")
    
    def _save_states(self):
        """Save session states to storage file"""
        try:
            with open(self.state_path, 'w') as f:
                json.dump(self.session_states, f)
        except Exception as e:
            logger.warning(f"Failed to save session states: {e}")
    
    def _load_completions(self) -> Dict[str, float]:
        """Load completion times from storage file"""
        if self.completion_path.exists():
            try:
                with open(self.completion_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load completion times: {e}")
                return {}
        return {}
    
    def _save_completions(self):
        """Save completion times to storage file"""
        try:
            with open(self.completion_path, 'w') as f:
                json.dump(self.completion_times, f)
        except Exception as e:
            logger.warning(f"Failed to save completion times: {e}")
    
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
            # Initialize if not tracked - DO NOT save yet
            # Will be saved when state actually changes to waiting
            return 0.0
        
        return time.time() - self.wait_times[session_name]
    
    def reset_session(self, session_name: str):
        """Reset wait time for a session (when it becomes active/working)"""
        # Only reset if we were tracking it as waiting
        if session_name in self.wait_times:
            del self.wait_times[session_name]
            self._save_times()
        # Mark as working
        self.session_states[session_name] = "working"
        self._save_states()
    
    def mark_as_waiting(self, session_name: str):
        """Mark a session as waiting (only if not already waiting)"""
        # Check if state changed from working to waiting
        last_state = self.session_states.get(session_name, "unknown")
        
        if last_state != "waiting":
            # State changed to waiting - record the timestamp
            self.wait_times[session_name] = time.time()
            self._save_times()
            self.session_states[session_name] = "waiting"
            self._save_states()
            logger.debug(f"State changed: {session_name} from {last_state} to waiting")
        # If already waiting, keep the existing timestamp
    
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
    
    def mark_completion(self, session_name: str):
        """Mark when a completion notification was sent for a session"""
        self.completion_times[session_name] = time.time()
        self._save_completions()
        logger.info(f"Marked completion time for {session_name}")
    
    def get_wait_time_since_completion(self, session_name: str) -> float:
        """
        Get time elapsed since last completion notification
        
        Args:
            session_name: Name of the session
            
        Returns:
            Time in seconds since last completion (uses fallback if no record or unreasonable)
        """
        if session_name not in self.completion_times:
            # Use fallback mechanism: estimate based on session creation time
            return self._get_fallback_wait_time(session_name)
        
        wait_time = time.time() - self.completion_times[session_name]
        
        # Sanity check: if wait time is > 24 hours, use fallback instead
        # This handles cases where completion times are stale/incorrect
        if wait_time > 24 * 3600:  # 24 hours
            logger.warning(f"Unreasonably long wait time ({wait_time/3600:.1f}h) for {session_name}, using fallback")
            return self._get_fallback_wait_time(session_name)
        
        return wait_time
    
    def has_completion_record(self, session_name: str) -> bool:
        """Check if session has completion notification record that's still valid (< 24h)"""
        if session_name not in self.completion_times:
            return False
        
        wait_time = time.time() - self.completion_times[session_name]
        return wait_time <= 24 * 3600  # Only consider valid if < 24 hours
    
    def _get_fallback_wait_time(self, session_name: str) -> float:
        """
        Fallback mechanism: estimate wait time from session creation time
        
        This is used when completion notification is missing due to Hook system issues
        
        Args:
            session_name: Name of the session
            
        Returns:
            Estimated wait time in seconds (minimum 300 = 5 minutes to indicate uncertainty)
        """
        import subprocess
        from datetime import datetime
        
        try:
            # Get session creation time from tmux
            result = subprocess.run(
                f"tmux list-sessions | grep '^{session_name}:' | head -1",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"Could not get creation time for {session_name}, using default estimate")
                return 300.0  # 5 minutes minimum estimate
            
            # Parse tmux output format: "session: windows (created date) [size]"
            # Extract creation time string
            session_line = result.stdout.strip()
            import re
            
            # Look for creation date pattern: "created Thu Aug 15 10:30:45 2025"
            date_match = re.search(r'created (.+) \d{4}\)', session_line)
            if not date_match:
                logger.warning(f"Could not parse creation date from: {session_line}")
                return 300.0
                
            current_year = datetime.now().year
            date_str = date_match.group(1) + f" {current_year}"  # Add year back
            
            # Parse date string to timestamp using standard library
            try:
                # Expected format: "Sat Aug 16 12:51:34 2025" 
                created_dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
                created_timestamp = created_dt.timestamp()
            except Exception as e:
                # Fallback: use a reasonable estimate based on the fact the session exists
                logger.warning(f"Could not parse date string '{date_str}': {e}")
                return 1800.0  # 30 minutes as reasonable estimate
                
            current_time = time.time()
            session_age = current_time - created_timestamp
            
            # Conservative estimate: assume completed relatively recently
            # Use 80% of session age as estimated wait time (reasonable assumption)
            estimated_wait = session_age * 0.8
            
            # Minimum 5 minutes to indicate this is an estimate
            estimated_wait = max(300.0, estimated_wait)
            
            logger.info(f"Using fallback estimate for {session_name}: {estimated_wait:.0f}s (session age: {session_age:.0f}s)")
            return estimated_wait
            
        except Exception as e:
            logger.error(f"Fallback estimation failed for {session_name}: {e}")
            # Ultimate fallback: indicate uncertainty with fixed time
            return 1800.0  # 30 minutes as "unknown but likely been waiting"
    
    def cleanup_old_sessions(self, max_age_hours: float = 24):
        """Remove sessions older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Clean up wait_times
        to_remove_wait = []
        for session_name, last_time in self.wait_times.items():
            if current_time - last_time > max_age_seconds:
                to_remove_wait.append(session_name)
        
        for session_name in to_remove_wait:
            del self.wait_times[session_name]
            logger.info(f"Removed old session {session_name} from wait tracking")
        
        if to_remove_wait:
            self._save_times()
        
        # Clean up completion_times (stale data > 24 hours)
        to_remove_completion = []
        for session_name, completion_time in self.completion_times.items():
            if current_time - completion_time > max_age_seconds:
                to_remove_completion.append(session_name)
        
        for session_name in to_remove_completion:
            del self.completion_times[session_name]
            logger.info(f"Removed stale completion time for {session_name}")
        
        if to_remove_completion:
            self._save_completions()


# Global instance for easy access
wait_tracker = WaitTimeTracker()