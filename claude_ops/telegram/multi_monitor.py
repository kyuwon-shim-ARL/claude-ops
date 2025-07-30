"""
Multi-Session Monitor for Claude Code

Monitors all Claude sessions simultaneously and sends notifications
when any session completes work.
"""

import os
import time
import logging
import threading
import subprocess
from typing import Dict, Set
from pathlib import Path
from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from .notifier import SmartNotifier

logger = logging.getLogger(__name__)


class MultiSessionMonitor:
    """Monitor multiple Claude Code sessions simultaneously"""
    
    def __init__(self, config: ClaudeOpsConfig = None):
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.session_states: Dict[str, str] = {}  # session_name -> last_state
        self.status_files: Dict[str, str] = {}    # session_name -> status_file_path
        self.running = False
        
    def discover_sessions(self) -> Set[str]:
        """Discover all active Claude sessions"""
        return set(session_manager.get_all_claude_sessions())
    
    def get_status_file_for_session(self, session_name: str) -> str:
        """Get status file path for a session"""
        return session_manager.get_status_file_for_session(session_name)
    
    def read_session_state(self, status_file: str) -> str:
        """Read current state from status file"""
        try:
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    return f.read().strip()
            return "idle"
        except Exception as e:
            logger.debug(f"Could not read status file {status_file}: {e}")
            return "idle"
    
    def save_session_state(self, status_file: str, state: str) -> None:
        """Save current state to status file"""
        try:
            with open(status_file, 'w') as f:
                f.write(state)
            logger.debug(f"Saved state '{state}' to {status_file}")
        except Exception as e:
            logger.warning(f"Could not write status file {status_file}: {e}")
    
    def detect_session_state(self, session_name: str) -> str:
        """Detect current state by analyzing tmux output"""
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return "idle"
                
            tmux_output = result.stdout
            
            # Check if Claude is working (esc to interrupt)
            if "esc to interrupt" in tmux_output:
                return "working"
                
            # Check if Claude is responding (bullet points in recent lines)
            bottom_lines = '\n'.join(tmux_output.split('\n')[-10:])
            if "●" in bottom_lines or "•" in bottom_lines:
                return "responding"
                
            return "idle"
            
        except Exception as e:
            logger.debug(f"Failed to detect state for {session_name}: {e}")
            return "idle"
    
    def session_exists(self, session_name: str) -> bool:
        """Check if tmux session exists"""
        result = os.system(f"tmux has-session -t {session_name} 2>/dev/null")
        return result == 0
    
    def send_completion_notification(self, session_name: str):
        """Send work completion notification for a specific session"""
        try:
            # Temporarily switch to this session for notification context
            original_session = session_manager.get_active_session()
            session_manager.switch_session(session_name)
            
            # Create a notifier for this session
            session_notifier = SmartNotifier(self.config)
            success = session_notifier.send_work_completion_notification()
            
            # Switch back to original session
            session_manager.switch_session(original_session)
            
            if success:
                logger.info(f"✅ Sent completion notification for session: {session_name}")
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name} (work still in progress or failed)")
                
        except Exception as e:
            logger.error(f"Error sending notification for {session_name}: {e}")
    
    def monitor_session(self, session_name: str, status_file: str):
        """Monitor a single session for state changes"""
        previous_state = self.read_session_state(status_file)
        
        # Add to session_states to track this session
        self.session_states[session_name] = previous_state
        logger.info(f"📊 Started monitoring {session_name}, initial state: {previous_state}")
        
        while self.running:
            try:
                # Check if session still exists
                if not self.session_exists(session_name):
                    logger.debug(f"Session {session_name} no longer exists")
                    break
                
                # Detect current state from tmux output (real-time analysis)
                detected_state = self.detect_session_state(session_name)
                
                # Read saved state from file
                saved_state = self.read_session_state(status_file)
                
                # Update state file if detected state differs from saved state
                if detected_state != saved_state:
                    logger.debug(f"🔄 State mismatch in {session_name}: saved='{saved_state}' detected='{detected_state}' - updating file")
                    self.save_session_state(status_file, detected_state)
                
                current_state = detected_state
                
                # Log state changes for debugging
                if current_state != previous_state:
                    logger.info(f"🔄 State change in {session_name}: {previous_state} -> {current_state}")
                
                # Check for work completion (working -> idle)
                if previous_state == "working" and current_state == "idle":
                    logger.info(f"🎯 Work completion detected in session: {session_name}")
                    self.send_completion_notification(session_name)
                
                # Update previous state and session_states
                previous_state = current_state
                self.session_states[session_name] = current_state
                
                # Wait before next check
                time.sleep(self.config.check_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring session {session_name}: {e}")
                time.sleep(self.config.check_interval)
    
    def start_monitoring(self):
        """Start monitoring all Claude sessions"""
        logger.info("🚀 Starting multi-session monitoring...")
        self.running = True
        
        # Discover initial sessions
        active_sessions = self.discover_sessions()
        threads = []
        
        for session_name in active_sessions:
            status_file = self.get_status_file_for_session(session_name)
            logger.info(f"📊 Monitoring session: {session_name} -> {status_file}")
            
            # Start monitoring thread for this session
            thread = threading.Thread(
                target=self.monitor_session,
                args=(session_name, status_file),
                name=f"monitor-{session_name}",
                daemon=True
            )
            thread.start()
            threads.append(thread)
        
        if not active_sessions:
            logger.warning("❌ No Claude sessions found to monitor")
            return
        
        logger.info(f"✅ Monitoring {len(active_sessions)} sessions: {list(active_sessions)}")
        
        # Session discovery loop
        while self.running:
            try:
                time.sleep(30)  # Check for new sessions every 30 seconds
                
                current_sessions = self.discover_sessions()
                new_sessions = current_sessions - set(self.session_states.keys())
                
                # Start monitoring new sessions
                for session_name in new_sessions:
                    if self.session_exists(session_name):
                        status_file = self.get_status_file_for_session(session_name)
                        logger.info(f"🆕 New session detected: {session_name}")
                        
                        thread = threading.Thread(
                            target=self.monitor_session,
                            args=(session_name, status_file),
                            name=f"monitor-{session_name}",
                            daemon=True
                        )
                        thread.start()
                        threads.append(thread)
                
            except KeyboardInterrupt:
                logger.info("🛑 Multi-session monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in session discovery: {e}")
                time.sleep(30)
        
        self.running = False
        logger.info("🏁 Multi-session monitoring stopped")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False


def main():
    """Main entry point for multi-session monitoring"""
    try:
        config = ClaudeOpsConfig()
        monitor = MultiSessionMonitor(config)
        monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Multi-session monitor stopped by user")
    except Exception as e:
        logger.error(f"Multi-session monitor error: {e}")


if __name__ == "__main__":
    main()