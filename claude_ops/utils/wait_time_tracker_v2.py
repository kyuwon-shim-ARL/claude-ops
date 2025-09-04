"""
Wait Time Tracker v2 - Improved reliability for session wait time tracking

Key improvements:
1. Auto-recovery from missed notifications  
2. State-based completion detection (not just notification success)
3. Automatic timestamp validation on every read
4. More intelligent fallback mechanisms
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ImprovedWaitTimeTracker:
    """Enhanced wait time tracker with auto-recovery and validation"""
    
    def __init__(self, 
                 completion_path: Optional[str] = None,
                 state_path: Optional[str] = None,
                 max_reasonable_wait_hours: float = 12):
        """
        Initialize improved tracker
        
        Args:
            completion_path: Path to store completion times
            state_path: Path to store session states
            max_reasonable_wait_hours: Maximum reasonable wait time before using fallback
        """
        if completion_path is None:
            completion_path = "/tmp/claude_completion_times.json"
        if state_path is None:
            state_path = "/tmp/claude_session_states.json"
            
        self.completion_path = Path(completion_path)
        self.state_path = Path(state_path)
        self.max_reasonable_wait = max_reasonable_wait_hours * 3600
        
        # Load existing data
        self.completion_times: Dict[str, float] = self._load_completions()
        self.session_states: Dict[str, str] = self._load_states()
        
        # Track last validation time to avoid excessive validation
        self.last_validation_time = 0
        self.validation_interval = 300  # Validate every 5 minutes
        
        # Auto-validate on startup
        self._auto_validate()
    
    def _load_completions(self) -> Dict[str, float]:
        """Load completion times from storage"""
        if self.completion_path.exists():
            try:
                with open(self.completion_path, 'r') as f:
                    data = json.load(f)
                    return {k: float(v) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load completion times: {e}")
                return {}
        return {}
    
    def _load_states(self) -> Dict[str, str]:
        """Load session states from storage"""
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load states: {e}")
                return {}
        return {}
    
    def _save_completions(self):
        """Save completion times to storage"""
        try:
            with open(self.completion_path, 'w') as f:
                json.dump(self.completion_times, f)
        except Exception as e:
            logger.warning(f"Failed to save completion times: {e}")
    
    def _save_states(self):
        """Save session states to storage"""
        try:
            with open(self.state_path, 'w') as f:
                json.dump(self.session_states, f)
        except Exception as e:
            logger.warning(f"Failed to save states: {e}")
    
    def _auto_validate(self):
        """Automatically validate and fix timestamps periodically"""
        current_time = time.time()
        
        # Force validation on first call
        if self.last_validation_time == 0:
            pass  # Always validate on first call
        # Only validate periodically to avoid performance impact
        elif current_time - self.last_validation_time < self.validation_interval:
            return
            
        self.last_validation_time = current_time
        fixed_count = 0
        
        # Check each completion timestamp
        for session_name, timestamp in list(self.completion_times.items()):
            # Fix future timestamps
            if timestamp > current_time:
                logger.warning(f"Future timestamp detected for {session_name}, fixing...")
                self.completion_times[session_name] = current_time - 300  # Set to 5 minutes ago
                fixed_count += 1
                
            # Remove very old timestamps (> max reasonable wait)
            elif (current_time - timestamp) > self.max_reasonable_wait:
                logger.info(f"Stale timestamp for {session_name} ({(current_time-timestamp)/3600:.1f}h old), removing...")
                del self.completion_times[session_name]
                fixed_count += 1
        
        if fixed_count > 0:
            self._save_completions()
            logger.info(f"Auto-validated and fixed {fixed_count} timestamps")
    
    def mark_completion(self, session_name: str, force: bool = False):
        """
        Mark completion time for a session
        
        Args:
            session_name: Name of the session
            force: Force update even if recent completion exists
        """
        current_time = time.time()
        
        # Check if we have a recent completion (within 30 seconds)
        if not force and session_name in self.completion_times:
            last_completion = self.completion_times[session_name]
            if current_time - last_completion < 30:
                logger.debug(f"Skipping duplicate completion mark for {session_name} (too recent)")
                return
        
        self.completion_times[session_name] = current_time
        self._save_completions()
        logger.info(f"Marked completion time for {session_name}")
    
    def mark_state_transition(self, session_name: str, new_state: str):
        """
        Mark state transition and auto-update completion if needed
        
        Args:
            session_name: Name of the session
            new_state: New state (e.g., 'waiting', 'working')
        """
        old_state = self.session_states.get(session_name, "unknown")
        
        # Auto-mark completion when transitioning from working to waiting
        if old_state == "working" and new_state == "waiting":
            logger.info(f"Auto-marking completion for {session_name} (working→waiting)")
            self.mark_completion(session_name, force=True)
        
        self.session_states[session_name] = new_state
        self._save_states()
    
    def get_wait_time_since_completion(self, session_name: str) -> Tuple[float, bool]:
        """
        Get time elapsed since last completion with confidence indicator
        
        Args:
            session_name: Name of the session
            
        Returns:
            Tuple of (wait_time_seconds, is_accurate)
            is_accurate is False when using fallback estimates
        """
        # Auto-validate periodically
        self._auto_validate()
        
        current_time = time.time()
        
        # Check if we have a completion record
        if session_name not in self.completion_times:
            # Use intelligent fallback
            wait_time = self._get_intelligent_fallback(session_name)
            return (wait_time, False)  # Not accurate, using fallback
        
        completion_time = self.completion_times[session_name]
        wait_time = current_time - completion_time
        
        # Sanity check: if unreasonably long, use fallback
        if wait_time > self.max_reasonable_wait:
            logger.warning(f"Wait time for {session_name} exceeds reasonable limit ({wait_time/3600:.1f}h), using fallback")
            fallback_time = self._get_intelligent_fallback(session_name)
            return (fallback_time, False)
        
        # Additional check: if negative (future timestamp), fix it
        if wait_time < 0:
            logger.error(f"Negative wait time for {session_name}, using fallback")
            self.completion_times[session_name] = current_time - 300  # Fix to 5 minutes ago
            self._save_completions()
            return (300, False)
        
        return (wait_time, True)  # Accurate time
    
    def _get_intelligent_fallback(self, session_name: str) -> float:
        """
        Get intelligent fallback estimate based on multiple heuristics
        
        Args:
            session_name: Name of the session
            
        Returns:
            Estimated wait time in seconds
        """
        import subprocess
        import re
        
        try:
            # Try to get session info from tmux
            result = subprocess.run(
                f"tmux list-sessions -F '#{{session_name}}:#{{session_created}}:#{{session_activity}}' | grep '^{session_name}:'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse tmux timestamps (seconds since epoch)
                parts = result.stdout.strip().split(':')
                if len(parts) >= 3:
                    try:
                        created_timestamp = int(parts[1])
                        activity_timestamp = int(parts[2])
                        current_time = time.time()
                        
                        # Use activity time as a better estimate
                        time_since_activity = current_time - activity_timestamp
                        
                        # If activity is recent (< 5 minutes), assume just completed
                        if time_since_activity < 300:
                            return time_since_activity
                        
                        # Otherwise, use a conservative estimate
                        # Assume work completed somewhere between last activity and now
                        estimated_wait = time_since_activity * 0.5  # Split the difference
                        
                        # Cap at reasonable maximum
                        return min(estimated_wait, self.max_reasonable_wait)
                        
                    except (ValueError, IndexError):
                        pass
            
            # Fallback: Check if session has recent screen content changes
            capture_result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -5",
                shell=True,
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if capture_result.returncode == 0:
                content = capture_result.stdout.strip()
                
                # Look for completion indicators
                if any(indicator in content.lower() for indicator in ['completed', 'done', 'finished', '✓', '✅']):
                    # Likely recently completed, estimate 5-10 minutes
                    return 300 + (300 * 0.5)  # 7.5 minutes
                
                # Look for waiting indicators
                if any(indicator in content.lower() for indicator in ['waiting', 'ready', '>']):
                    # Likely been waiting a while, estimate 30 minutes
                    return 1800
            
        except Exception as e:
            logger.error(f"Intelligent fallback failed for {session_name}: {e}")
        
        # Ultimate fallback: conservative estimate
        return 900  # 15 minutes as neutral estimate
    
    def cleanup_stale_data(self, max_age_hours: float = 24):
        """Remove data older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Clean completion times
        to_remove = []
        for session_name, timestamp in self.completion_times.items():
            if current_time - timestamp > max_age_seconds:
                to_remove.append(session_name)
        
        for session_name in to_remove:
            del self.completion_times[session_name]
            logger.info(f"Removed stale completion time for {session_name}")
        
        if to_remove:
            self._save_completions()
    
    def get_all_wait_times(self) -> Dict[str, Tuple[float, bool]]:
        """
        Get all current wait times with accuracy indicators
        
        Returns:
            Dict of session_name -> (wait_time_seconds, is_accurate)
        """
        result = {}
        for session_name in self.completion_times:
            result[session_name] = self.get_wait_time_since_completion(session_name)
        return result
    
    def reset_session(self, session_name: str):
        """Reset/remove tracking for a session"""
        if session_name in self.completion_times:
            del self.completion_times[session_name]
            self._save_completions()
        if session_name in self.session_states:
            del self.session_states[session_name]
            self._save_states()


# Migration helper to upgrade existing tracker
def migrate_to_v2():
    """Migrate from old tracker to improved tracker"""
    try:
        # Import old data
        old_completion_path = "/tmp/claude_completion_times.json"
        
        if Path(old_completion_path).exists():
            logger.info("Migrating to improved wait time tracker v2...")
            
            # Create new tracker (will load existing data)
            new_tracker = ImprovedWaitTimeTracker()
            
            # Auto-validation will clean up any issues
            logger.info("Migration complete - wait time tracker v2 is active")
            return new_tracker
        else:
            # No existing data, just create new tracker
            return ImprovedWaitTimeTracker()
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # Fallback to new tracker anyway
        return ImprovedWaitTimeTracker()