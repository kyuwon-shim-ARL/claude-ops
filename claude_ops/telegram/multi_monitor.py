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
        self.active_threads: Dict[str, threading.Thread] = {}  # session_name -> thread
        self.thread_lock = threading.Lock()  # Thread-safe operations
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
            
            # Check for special waiting states that indicate completion
            bottom_lines = '\n'.join(tmux_output.split('\n')[-5:]).lower()
            waiting_patterns = [
                "ready to code",           # Basic ready state
                "bash command",            # Bash tool waiting
                "select option",           # Option selection
                "choose an option",        # Option selection variant
                "enter your choice",       # Choice prompt
                "press enter to continue", # Continuation prompt
                "waiting for input",       # Input waiting
                "type your response",      # Response waiting
                "what would you like",     # Question prompt
                "how can i help",          # Help prompt
                "continue?",               # Continuation question
                "proceed?",                # Proceed question
                "confirm?",                # Confirmation question
            ]
            
            for pattern in waiting_patterns:
                if pattern in bottom_lines:
                    logger.debug(f"Detected waiting state '{pattern}' in {session_name}")
                    return "waiting_input"
                
            # Check if Claude is responding (bullet points in recent lines)
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
    
    def send_completion_notification(self, session_name: str, state_type: str = "completion"):
        """Send work completion notification for a specific session"""
        try:
            # Temporarily switch to this session for notification context
            original_session = session_manager.get_active_session()
            session_manager.switch_session(session_name)
            
            # Create a notifier for this session
            session_notifier = SmartNotifier(self.config)
            
            # Send different notifications based on state
            if state_type == "waiting_input":
                success = session_notifier.send_waiting_input_notification()
            else:
                success = session_notifier.send_work_completion_notification()
            
            # Switch back to original session
            session_manager.switch_session(original_session)
            
            if success:
                logger.info(f"✅ Sent {state_type} notification for session: {session_name}")
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name} ({state_type} - work still in progress or failed)")
                
        except Exception as e:
            logger.error(f"Error sending {state_type} notification for {session_name}: {e}")
    
    def monitor_session(self, session_name: str, status_file: str):
        """Monitor a single session for state changes"""
        try:
            previous_state = self.read_session_state(status_file)
            
            # Add to session_states to track this session (thread-safe)
            with self.thread_lock:
                self.session_states[session_name] = previous_state
            
            logger.info(f"📊 Started monitoring {session_name}, initial state: {previous_state}")
            
            while self.running:
                try:
                    # Check if session still exists
                    if not self.session_exists(session_name):
                        logger.info(f"📤 Session {session_name} no longer exists, stopping monitor")
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
                    
                    # Check for work completion (working -> idle/waiting_input)
                    if previous_state == "working" and current_state in ["idle", "waiting_input"]:
                        logger.info(f"🎯 Work completion detected in session: {session_name}")
                        self.send_completion_notification(session_name)
                    
                    # Check for special waiting states that need attention
                    elif previous_state in ["working", "responding"] and current_state == "waiting_input":
                        logger.info(f"⏸️ Claude waiting for input in session: {session_name}")
                        self.send_completion_notification(session_name, "waiting_input")
                    
                    # Update previous state and session_states (thread-safe)
                    previous_state = current_state
                    with self.thread_lock:
                        self.session_states[session_name] = current_state
                    
                    # Wait before next check
                    time.sleep(self.config.check_interval)
                    
                except Exception as e:
                    logger.error(f"Error monitoring session {session_name}: {e}")
                    time.sleep(self.config.check_interval)
        
        finally:
            # Clean up when thread exits
            logger.info(f"🧹 Monitor thread for {session_name} is exiting")
            with self.thread_lock:
                if session_name in self.session_states:
                    del self.session_states[session_name]
                if session_name in self.active_threads:
                    del self.active_threads[session_name]
    
    def start_session_thread(self, session_name: str) -> bool:
        """Start monitoring thread for a session (thread-safe)"""
        with self.thread_lock:
            # Check if thread already exists and is alive
            if session_name in self.active_threads:
                existing_thread = self.active_threads[session_name]
                if existing_thread.is_alive():
                    logger.debug(f"🔄 Thread for {session_name} already running, skipping")
                    return False
                else:
                    # Clean up dead thread
                    del self.active_threads[session_name]
            
            # Start new thread
            status_file = self.get_status_file_for_session(session_name)
            logger.info(f"📊 Starting thread for session: {session_name} -> {status_file}")
            
            thread = threading.Thread(
                target=self.monitor_session,
                args=(session_name, status_file),
                name=f"monitor-{session_name}",
                daemon=True
            )
            thread.start()
            self.active_threads[session_name] = thread
            return True
    
    def cleanup_dead_threads(self):
        """Clean up finished threads"""
        with self.thread_lock:
            dead_sessions = []
            for session_name, thread in self.active_threads.items():
                if not thread.is_alive():
                    dead_sessions.append(session_name)
            
            for session_name in dead_sessions:
                logger.debug(f"🧹 Cleaning up dead thread for {session_name}")
                del self.active_threads[session_name]
                if session_name in self.session_states:
                    del self.session_states[session_name]
    
    def start_monitoring(self):
        """Start monitoring all Claude sessions"""
        logger.info("🚀 Starting multi-session monitoring...")
        self.running = True
        
        # Discover initial sessions
        active_sessions = self.discover_sessions()
        
        # Start monitoring threads for initial sessions
        started_count = 0
        for session_name in active_sessions:
            if self.start_session_thread(session_name):
                started_count += 1
        
        if started_count == 0:
            logger.warning("❌ No Claude sessions found to monitor")
        else:
            logger.info(f"✅ Started monitoring {started_count} sessions: {list(active_sessions)}")
        
        # Session discovery loop
        while self.running:
            try:
                time.sleep(30)  # Check for new sessions every 30 seconds
                
                # Clean up dead threads first
                self.cleanup_dead_threads()
                
                # Discover current sessions
                current_sessions = self.discover_sessions()
                monitored_sessions = set(self.active_threads.keys())
                new_sessions = current_sessions - monitored_sessions
                
                # Start monitoring new sessions
                for session_name in new_sessions:
                    if self.session_exists(session_name):
                        if self.start_session_thread(session_name):
                            logger.info(f"🆕 New session detected and monitoring started: {session_name}")
                
            except KeyboardInterrupt:
                logger.info("🛑 Multi-session monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in session discovery: {e}")
                time.sleep(30)
        
        self.running = False
        logger.info("🏁 Multi-session monitoring stopped")
    
    def stop_monitoring(self):
        """Stop monitoring and clean up all threads"""
        logger.info("🛑 Stopping multi-session monitoring...")
        self.running = False
        
        # Wait for all threads to finish (with timeout)
        with self.thread_lock:
            active_sessions = list(self.active_threads.keys())
        
        for session_name in active_sessions:
            thread = self.active_threads.get(session_name)
            if thread and thread.is_alive():
                logger.debug(f"⏳ Waiting for {session_name} monitor thread to stop...")
                thread.join(timeout=5)  # Wait max 5 seconds per thread
        
        # Force cleanup any remaining threads
        with self.thread_lock:
            self.active_threads.clear()
            self.session_states.clear()
        
        logger.info("✅ All monitoring threads stopped and cleaned up")


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