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
import hashlib
from typing import Dict, Set
from pathlib import Path
from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..telegram.notifier import SmartNotifier
from ..telegram.keyboard_handler import keyboard_handler
from ..telegram.message_queue import message_queue

logger = logging.getLogger(__name__)


class MultiSessionMonitor:
    """Monitor multiple Claude Code sessions simultaneously"""
    
    def __init__(self, config: ClaudeOpsConfig = None):
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.state_analyzer = SessionStateAnalyzer()  # Unified state detection
        
        # Simplified state tracking
        self.last_screen_hash: Dict[str, str] = {}      # session -> screen_content_hash
        self.last_activity_time: Dict[str, float] = {}  # session -> timestamp
        self.notification_sent: Dict[str, bool] = {}    # session -> notification_sent_flag
        self.last_state: Dict[str, SessionState] = {}   # session -> last_known_state
        self.last_notification_time: Dict[str, float] = {}  # session -> last_notification_timestamp
        self.active_threads: Dict[str, threading.Thread] = {}  # session_name -> thread
        self.thread_lock = threading.Lock()  # Thread-safe operations
        self.running = False
        self.timeout_seconds = 45  # 45-second timeout for work completion
        
        # Share activity times with SessionSummaryHelper
        from ..utils.session_summary import SessionSummaryHelper
        SessionSummaryHelper._last_activity_times = self.last_activity_time
        
    def discover_sessions(self) -> Set[str]:
        """Discover all active Claude sessions"""
        return set(session_manager.get_all_claude_sessions())
    
    def get_status_file_for_session(self, session_name: str) -> str:
        """Get status file path for a session"""
        return session_manager.get_status_file_for_session(session_name)
    
    # Removed read_session_state and save_session_state methods
    # They are no longer needed with simplified detection
    
    def get_session_state(self, session_name: str) -> SessionState:
        """Get current session state using unified analyzer"""
        # 알림용이므로 현재 화면만 기반으로 상태 판단
        return self.state_analyzer.get_state_for_notification(session_name)
    
    def get_screen_content_hash(self, session_name: str) -> str:
        """Get hash of current screen content for change detection"""
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return ""
                
            # Create hash of screen content
            content = result.stdout.strip()
            return hashlib.md5(content.encode()).hexdigest()
            
        except Exception as e:
            logger.debug(f"Failed to get screen content hash for {session_name}: {e}")
            return ""
    
    def has_screen_changed(self, session_name: str) -> bool:
        """Check if screen content has changed since last check"""
        current_hash = self.get_screen_content_hash(session_name)
        
        if not current_hash:
            return False
            
        last_hash = self.last_screen_hash.get(session_name, "")
        
        if current_hash != last_hash:
            self.last_screen_hash[session_name] = current_hash
            self.last_activity_time[session_name] = time.time()
            return True
            
        return False
    
    def is_waiting_for_input(self, session_name: str) -> bool:
        """Check if session is waiting for user input (using unified analyzer)"""
        return self.state_analyzer.is_waiting_for_input(session_name)
    
    def is_working(self, session_name: str) -> bool:
        """Check if session is working (using unified analyzer)"""
        return self.state_analyzer.is_working(session_name)

    def should_send_completion_notification(self, session_name: str) -> bool:
        """Determine if completion notification should be sent based on state transitions"""
        current_state = self.get_session_state(session_name)
        previous_state = self.last_state.get(session_name, SessionState.UNKNOWN)
        
        # Update last known state
        self.last_state[session_name] = current_state
        
        # Reset notification flag if currently working
        if current_state == SessionState.WORKING:
            self.notification_sent[session_name] = False
            self.last_activity_time[session_name] = time.time()
            return False
        
        # Enhanced duplicate prevention
        if self.notification_sent.get(session_name, False):
            return False
        
        # Prevent rapid successive notifications (30-second cooldown)
        current_time = time.time()
        last_notification_time = self.last_notification_time.get(session_name, 0)
        
        if current_time - last_notification_time < 30:  # 30-second cooldown
            logger.debug(f"Notification cooldown active for {session_name}")
            return False
        
        # Notification triggers: WORKING->completed or any->WAITING_INPUT
        should_notify = (
            (previous_state == SessionState.WORKING and current_state != SessionState.WORKING) or
            (current_state == SessionState.WAITING_INPUT and previous_state != SessionState.WAITING_INPUT)
        )
        
        if should_notify:
            self.notification_sent[session_name] = True
            self.last_notification_time[session_name] = current_time
            logger.info(f"State transition: {session_name} {previous_state} → {current_state}")
            return True
            
        return False
    
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
            
            # With simplified detection, we primarily send work completion notifications
            # The smart notifier will handle the specific context
            success = session_notifier.send_work_completion_notification()
            
            # Switch back to original session
            session_manager.switch_session(original_session)
            
            if success:
                logger.info(f"✅ Sent completion notification for session: {session_name}")
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name} (duplicate or failed)")
                
        except Exception as e:
            logger.error(f"Error sending completion notification for {session_name}: {e}")
    
    
    def monitor_session(self, session_name: str, status_file: str):
        """Monitor a single session using simplified detection logic"""
        try:
            # Initialize session tracking
            with self.thread_lock:
                self.last_screen_hash[session_name] = ""
                self.last_activity_time[session_name] = time.time()
                self.notification_sent[session_name] = False
                self.last_state[session_name] = SessionState.UNKNOWN
                self.last_notification_time[session_name] = 0
            
            logger.info(f"📊 Started simplified monitoring for {session_name}")
            
            while self.running:
                try:
                    # Check if session still exists
                    if not self.session_exists(session_name):
                        logger.info(f"📤 Session {session_name} no longer exists, stopping monitor")
                        break
                    
                    # Check for screen changes (updates activity time)
                    screen_changed = self.has_screen_changed(session_name)
                    
                    # Check if currently working
                    is_working = self.is_working(session_name)
                    
                    # Log activity changes for debugging
                    if screen_changed:
                        logger.debug(f"📺 Screen changed in {session_name}")
                    
                    
                    # Check if we should send completion notification
                    if self.should_send_completion_notification(session_name):
                        logger.info(f"🎯 Sending completion notification for {session_name}")
                        self.send_completion_notification(session_name, "completion")
                    
                    # Log state changes for debugging
                    if session_name in self.last_state:
                        prev_state = self.last_state[session_name]
                        curr_state = self.get_session_state(session_name)
                        if prev_state != curr_state:
                            logger.info(f"🔄 {session_name}: {prev_state} → {curr_state}")
                    
                    # Wait before next check
                    time.sleep(self.config.check_interval)
                    
                except Exception as e:
                    logger.error(f"Error monitoring session {session_name}: {e}")
                    time.sleep(self.config.check_interval)
        
        finally:
            # Clean up when thread exits
            logger.info(f"🧹 Monitor thread for {session_name} is exiting")
            with self.thread_lock:
                # Clean up all session data
                for data_dict in [self.last_screen_hash, self.last_activity_time, 
                                self.notification_sent, self.last_state, self.last_notification_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
                if session_name in self.active_threads:
                    del self.active_threads[session_name]
                
                # Clear state analyzer cache for this session
                self.state_analyzer.clear_cache(session_name)
    
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
        """Clean up finished threads and their associated data"""
        with self.thread_lock:
            dead_sessions = []
            for session_name, thread in self.active_threads.items():
                if not thread.is_alive():
                    dead_sessions.append(session_name)
            
            for session_name in dead_sessions:
                logger.debug(f"🧹 Cleaning up dead thread for {session_name}")
                del self.active_threads[session_name]
                # Clean up all associated data
                for data_dict in [self.last_screen_hash, self.last_activity_time,
                                self.notification_sent, self.last_state, self.last_notification_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
    
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
                time.sleep(5)  # 5 second sleep for monitoring cycle
                
                # Regular monitoring tasks
                current_time = time.time()
                
                # Clean up dead threads first
                if current_time % 30 < 5:  # Every 30 seconds
                    self.cleanup_dead_threads()
                
                # Periodic cache cleanup (every 5 minutes)
                if current_time % 300 < 5:  # Every 5 minutes
                    self.state_analyzer.cleanup_expired_cache()
                    message_queue.cleanup_old_messages()  # Clean old keyboard messages too
                
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
        """Stop monitoring and clean up all threads and data"""
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
        
        # Force cleanup any remaining threads and all data
        with self.thread_lock:
            self.active_threads.clear()
            self.last_screen_hash.clear()
            self.last_activity_time.clear()
            self.notification_sent.clear()
            self.last_state.clear()
            self.last_notification_time.clear()
        
        logger.info("✅ All monitoring threads stopped and cleaned up")


def main():
    """Main entry point for multi-session monitoring with Telegram bot"""
    import threading
    from ..telegram.bot import TelegramBridge
    
    try:
        config = ClaudeOpsConfig()
        
        # Start monitoring in separate thread
        monitor = MultiSessionMonitor(config)
        monitor_thread = threading.Thread(target=monitor.start_monitoring, daemon=True)
        monitor_thread.start()
        logger.info("📊 Started monitoring thread")
        
        # Start Telegram bot (main thread)
        bot = TelegramBridge(config)
        logger.info("🤖 Starting Telegram bot...")
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Multi-session monitor and bot stopped by user")
        if 'monitor' in locals():
            monitor.stop_monitoring()
    except Exception as e:
        logger.error(f"Multi-session monitor error: {e}")
        if 'monitor' in locals():
            monitor.stop_monitoring()


if __name__ == "__main__":
    main()