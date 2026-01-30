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
from typing import Dict, Set, Tuple, Optional
from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..utils.notification_debugger import get_debugger, NotificationEvent
from ..utils.task_completion_detector import task_detector, TaskCompletion, AlertPriority
from ..utils.session_reconnect import SessionReconnectionState  # T027: Reconnection tracking
from ..utils.state_persistence import PersistedSessionState  # T028: Restart state persistence
from ..telegram.notifier import SmartNotifier
from .completion_event_system import (
    CompletionEventBus, CompletionEventType, CompletionEvent,
    CompletionTimeRecorder, CompletionNotifier, emit_completion
)
from ..telegram.message_queue import message_queue
# Import improved tracker with state-based completion detection
try:
    from ..utils.wait_time_tracker_v2 import ImprovedWaitTimeTracker, migrate_to_v2
    wait_tracker = migrate_to_v2()  # Auto-migrate on import
except ImportError:
    # Fallback to original tracker
    from ..utils.wait_time_tracker import wait_tracker

logger = logging.getLogger(__name__)


class MultiSessionMonitor:
    """Monitor multiple Claude Code sessions simultaneously"""
    
    def __init__(self, config: ClaudeOpsConfig = None):
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.state_analyzer = SessionStateAnalyzer()  # Unified state detection
        self.tracker = wait_tracker  # Use global wait time tracker
        self.debugger = get_debugger()  # NEW: Debug tracking

        # Initialize event-based completion system
        self.event_bus = CompletionEventBus()
        self.completion_recorder = CompletionTimeRecorder(self.tracker)
        self.event_bus.subscribe(self.completion_recorder.on_completion_event)

        # Simplified state tracking
        self.last_screen_hash: Dict[str, str] = {}      # session -> screen_content_hash
        self.notification_sent: Dict[str, bool] = {}    # session -> notification_sent_flag
        self.last_state: Dict[str, SessionState] = {}   # session -> last_known_state
        self.last_notification_time: Dict[str, float] = {}  # session -> last_notification_timestamp
        self.active_threads: Dict[str, threading.Thread] = {}  # session_name -> thread
        self.thread_lock = threading.Lock()  # Thread-safe operations
        self.running = False
        self.timeout_seconds = 45  # 45-second timeout for work completion

        # Activity tracking for proper state management
        self.last_activity_time: Dict[str, float] = {}  # session -> last_activity_timestamp

        # T027: Session reconnection tracking
        self.reconnection_states: Dict[str, SessionReconnectionState] = {}  # session -> reconnection_state

        # T028: State persistence directory
        import tempfile
        self.state_dir = os.path.join(tempfile.gettempdir(), "claude-ops-state")
        os.makedirs(self.state_dir, exist_ok=True)

    def discover_sessions(self) -> Set[str]:
        """Discover all active Claude sessions"""
        return set(session_manager.get_all_claude_sessions())

    def get_monitoring_status(self) -> Dict[str, any]:
        """
        Get monitoring session health status (T049).

        Returns:
            Status dict with session_count, uptime, last_check_time, is_active
        """
        try:
            # Get all Claude sessions
            sessions = self.discover_sessions()
            session_count = len(sessions)

            # Check if monitoring is active (has active threads)
            is_active = self.running and len(self.active_threads) > 0

            # Get current time
            current_time = time.time()

            return {
                "session_count": session_count,
                "is_active": is_active,
                "active_threads": len(self.active_threads),
                "last_check_time": current_time,
                "sessions": list(sessions)
            }
        except Exception as e:
            logger.error(f"Failed to get monitoring status: {e}")
            return {
                "session_count": 0,
                "is_active": False,
                "active_threads": 0,
                "last_check_time": time.time(),
                "sessions": [],
                "error": str(e)
            }
    
    def get_status_file_for_session(self, session_name: str) -> str:
        """Get status file path for a session"""
        return session_manager.get_status_file_for_session(session_name)

    def get_state_file_path(self, session_name: str) -> str:
        """Get persisted state file path for a session (T028)"""
        return os.path.join(self.state_dir, f"{session_name}.json")

    def load_persisted_state(self, session_name: str) -> Optional[PersistedSessionState]:
        """Load persisted state from disk (T028)"""
        try:
            filepath = self.get_state_file_path(session_name)
            return PersistedSessionState.load(filepath)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Failed to load persisted state for {session_name}: {e}")
            return None

    def save_persisted_state(self, session_name: str, screen_hash: str, state: SessionState, notification_sent: bool):
        """Save persisted state to disk (T028)"""
        try:
            persisted = PersistedSessionState(
                session_name=session_name,
                screen_hash=screen_hash,
                last_state=state.value,
                notification_sent=notification_sent
            )
            filepath = self.get_state_file_path(session_name)
            persisted.save(filepath)
            logger.debug(f"Saved persisted state for {session_name}")
        except Exception as e:
            logger.warning(f"Failed to save persisted state for {session_name}: {e}")
    
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
            # NOTE: Don't reset wait time on screen change anymore!
            # Screen changes happen AFTER work completion too (output being displayed)
            # Wait time should only be reset when WORKING state is detected (line 223)
            # Reset activity tracking only
            self.last_activity_time[session_name] = time.time()
            return True
            
        return False
    
    def is_waiting_for_input(self, session_name: str) -> bool:
        """Check if session is waiting for user input (using unified analyzer)"""
        return self.state_analyzer.is_waiting_for_input(session_name)
    
    def is_working(self, session_name: str) -> bool:
        """Check if session is working (using unified analyzer)"""
        return self.state_analyzer.is_working(session_name)

    def should_send_completion_notification(self, session_name: str) -> Tuple[bool, Optional[TaskCompletion]]:
        """Enhanced notification detection with task-specific completion support"""
        current_state = self.get_session_state(session_name)
        previous_state = self.last_state.get(session_name, SessionState.UNKNOWN)
        current_time = time.time()
        
        # Log state change for debugging
        if previous_state != current_state:
            self.debugger.log_state_change(
                session_name, previous_state, current_state,
                "State transition detected"
            )
        
        # Update last known state
        self.last_state[session_name] = current_state
        
        # Reset notification flag if currently working
        if current_state == SessionState.WORKING:
            self.notification_sent[session_name] = False
            if previous_state != SessionState.WORKING:
                self.tracker.reset_session(session_name)
            return False, None
        
        # Enhanced duplicate prevention
        if self.notification_sent.get(session_name, False):
            return False, None
        
        # Prevent rapid successive notifications (30-second cooldown)
        last_notification_time = self.last_notification_time.get(session_name, 0)
        if current_time - last_notification_time < 30:
            logger.debug(f"Notification cooldown active for {session_name}")
            return False, None
        
        # Check for task-specific completions
        screen_content = self.state_analyzer.get_current_screen_only(session_name)
        task_completion = None
        if screen_content:
            task_completion = task_detector.detect_completion(screen_content)
        
        # Reasons for notification
        notification_reason = ""
        should_notify = False
        
        # 1. Task-specific completion detected (highest priority)
        if task_completion and task_completion.confidence > 0.7:
            should_notify = True
            notification_reason = f"Task completed: {task_completion.message}"
            # Adjust cooldown based on priority
            if task_completion.priority == AlertPriority.CRITICAL:
                should_notify = True  # Always notify for critical
            elif task_completion.priority == AlertPriority.LOW:
                # More restrictive for low priority
                if current_time - last_notification_time < 60:
                    return False, None
        # 2. Original triggers: WORKING->completed or any->WAITING_INPUT
        elif previous_state == SessionState.WORKING and current_state != SessionState.WORKING:
            should_notify = True
            notification_reason = f"Work completed (WORKING → {current_state})"
        elif current_state == SessionState.WAITING_INPUT and previous_state != SessionState.WAITING_INPUT:
            # BUGFIX: Ignore UNKNOWN -> WAITING_INPUT transitions (restart false positive)
            if previous_state != SessionState.UNKNOWN:
                should_notify = True
                notification_reason = "Waiting for input"
        # 3. Quiet completion detection
        elif self.state_analyzer.detect_quiet_completion(session_name):
            should_notify = True
            notification_reason = "Quiet completion detected"
        # 4. Completion message detection
        elif current_state == SessionState.IDLE:
            if screen_content and self.state_analyzer.has_completion_indicators(screen_content):
                # Check if we haven't notified recently
                if current_time - last_notification_time > 10:
                    should_notify = True
                    notification_reason = "Completion message detected"
        
        if should_notify:
            # EMIT COMPLETION EVENT (decoupled from notification)
            # Event-based system ensures completion is always recorded
            if previous_state == SessionState.WORKING and current_state != SessionState.WORKING:
                logger.info(f"🎯 Emitting completion event for {session_name} (WORKING → {current_state})")
                self.event_bus.emit(CompletionEvent(
                    session_name=session_name,
                    event_type=CompletionEventType.STATE_TRANSITION,
                    timestamp=current_time,
                    previous_state=previous_state.value,
                    new_state=current_state.value,
                    metadata={'reason': notification_reason}
                ))
            
            self.notification_sent[session_name] = True
            self.last_notification_time[session_name] = current_time
            logger.info(f"📢 Notification: {session_name} - {notification_reason}")
            
            # Log notification event
            self.debugger.log_notification(
                session_name, NotificationEvent.SENT,
                notification_reason, current_state
            )
            return True, task_completion
        
        return False, None
    
    def session_exists(self, session_name: str) -> bool:
        """Check if tmux session exists"""
        result = os.system(f"tmux has-session -t {session_name} 2>/dev/null")
        return result == 0
    
    
    def _log_scraping_event(self, session_name: str, event_type: str, state: str):
        """Log scraping event and create marker for hooks safety net"""
        import json
        from datetime import datetime

        log_file = os.path.join(os.path.dirname(__file__), '../../logs/scraping_events.jsonl')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_name": session_name,
            "event_type": event_type,
            "state": state,
            "source": "scraping"
        }

        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.debug(f"Failed to log scraping event: {e}")

        # Create marker file to prevent duplicate idle_prompt notification
        # Extract project name from session (claude_<project> -> <project>)
        project_name = session_name
        if session_name.startswith("claude_"):
            project_name = session_name[7:]
        elif session_name.startswith("claude-"):
            project_name = session_name[7:]

        marker_dir = "/tmp/claude-ops-notified"
        marker_file = os.path.join(marker_dir, project_name)
        try:
            os.makedirs(marker_dir, exist_ok=True)
            # Touch the marker file
            with open(marker_file, 'w') as f:
                f.write(datetime.now().isoformat())
            logger.debug(f"Created notification marker: {marker_file}")
        except Exception as e:
            logger.debug(f"Failed to create marker file: {e}")

    def send_completion_notification(self, session_name: str, task_completion: Optional[TaskCompletion] = None):
        """Send work completion notification for a specific session with task details

        Args:
            session_name: The session to send notification for
            task_completion: Optional task completion details
        """
        try:
            # Log for comparison with hooks (POC)
            self._log_scraping_event(session_name, "completion", "notified")

            # Temporarily switch to this session for notification context
            original_session = session_manager.get_active_session()
            session_manager.switch_session(session_name)
            
            # Create a notifier for this session
            session_notifier = SmartNotifier(self.config)

            # Send completion notification
            # NOTE: task_completion support removed - using standard work completion notification
            success = session_notifier.send_work_completion_notification()
            
            # Switch back to original session
            session_manager.switch_session(original_session)
            
            if success:
                priority_emoji = task_detector.get_priority_emoji(task_completion.priority) if task_completion else "✅"
                logger.info(f"{priority_emoji} Sent completion notification for session: {session_name}")
                # NOTE: Completion time is now marked in should_send_completion_notification()
                # This ensures it's recorded even if notification fails
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name} (duplicate or failed)")
                # Still mark completion if state changed (v2 tracker feature)
                if hasattr(self.tracker, 'mark_state_transition'):
                    self.tracker.mark_state_transition(session_name, 'waiting')
                
        except Exception as e:
            logger.error(f"Error sending completion notification for {session_name}: {e}")
    
    
    def monitor_session(self, session_name: str, status_file: str):
        """Monitor a single session using simplified detection logic"""
        try:
            # T028: Load persisted state on startup to skip duplicate notifications
            persisted_state = self.load_persisted_state(session_name)

            # Initialize session tracking
            with self.thread_lock:
                if persisted_state:
                    # Resume from persisted state
                    self.last_screen_hash[session_name] = persisted_state.screen_hash
                    # BUGFIX: Always start with notification_sent=False on restart
                    # The persisted hash allows skip logic, but we should detect NEW work
                    self.notification_sent[session_name] = False
                    try:
                        self.last_state[session_name] = SessionState(persisted_state.last_state)
                    except ValueError:
                        self.last_state[session_name] = SessionState.UNKNOWN
                    logger.info(f"📂 Loaded persisted state for {session_name}: screen_hash={persisted_state.screen_hash[:8]}, notification_sent reset to False")
                else:
                    # Fresh start
                    self.last_screen_hash[session_name] = ""
                    self.notification_sent[session_name] = False
                    self.last_state[session_name] = SessionState.UNKNOWN

                self.last_notification_time[session_name] = 0
                # Initialize wait time tracking
                self.tracker.reset_session(session_name)
                # Initialize activity tracking
                self.last_activity_time[session_name] = time.time()

            logger.info(f"📊 Started simplified monitoring for {session_name}")
            
            while self.running:
                try:
                    # T027: Check if session still exists with reconnection retry logic
                    if not self.session_exists(session_name):
                        # Session disconnected - start or continue reconnection
                        if session_name not in self.reconnection_states:
                            # First detection of disconnection
                            reconnect_state = SessionReconnectionState(
                                session_name=session_name,
                                max_duration_seconds=self.config.session_reconnect_max_duration,
                                initial_backoff=self.config.session_reconnect_initial_backoff,
                                max_backoff=self.config.session_reconnect_max_backoff
                            )
                            self.reconnection_states[session_name] = reconnect_state
                            logger.warning(f"⚠️ Session {session_name} disconnected, starting reconnection attempts")

                        reconnect_state = self.reconnection_states[session_name]

                        # Check if we've exceeded max duration timeout
                        if reconnect_state.is_timed_out():
                            logger.error(f"❌ Session {session_name} reconnection FAILED after {reconnect_state.get_elapsed_time():.1f}s")
                            reconnect_state.mark_failed()
                            break

                        # Check if it's time for next retry
                        if time.time() >= reconnect_state.next_retry_time:
                            backoff = reconnect_state.get_next_backoff()
                            logger.info(f"🔄 Retry #{reconnect_state.retry_count} for {session_name}, next attempt in {backoff}s")

                        # Wait for backoff period before next check
                        time.sleep(min(self.config.check_interval, 1))
                        continue

                    # Session exists - check if we were in reconnection mode
                    if session_name in self.reconnection_states:
                        reconnect_state = self.reconnection_states[session_name]
                        reconnect_state.mark_success()
                        logger.info(f"✅ Session {session_name} reconnected successfully!")
                        del self.reconnection_states[session_name]
                        # Reset state after reconnection
                        self.notification_sent[session_name] = False
                        self.last_state[session_name] = SessionState.UNKNOWN
                    
                    # Check for screen changes (updates activity time)
                    screen_changed = self.has_screen_changed(session_name)
                    
                    # Check if currently working
                    is_working = self.is_working(session_name)
                    
                    # Log activity changes for debugging
                    if screen_changed:
                        logger.debug(f"📺 Screen changed in {session_name}")
                    
                    
                    # Check if we should send completion notification (state transition)
                    should_notify, task_completion = self.should_send_completion_notification(session_name)
                    if should_notify:
                        logger.info(f"🎯 Sending completion notification for {session_name}")
                        self.send_completion_notification(session_name, task_completion)
                        # Reset activity tracking on real completion
                        self.last_activity_time[session_name] = time.time()

                        # T028: Persist state after notification to prevent duplicates on restart
                        current_hash = self.last_screen_hash.get(session_name, "")
                        current_state = self.last_state.get(session_name, SessionState.UNKNOWN)
                        self.save_persisted_state(
                            session_name,
                            current_hash,
                            current_state,
                            notification_sent=True
                        )
                    
                    # Enhanced state change logging with debugger
                    if session_name in self.last_state:
                        prev_state = self.last_state[session_name]
                        curr_state = self.get_session_state(session_name)
                        if prev_state != curr_state:
                            logger.info(f"🔄 {session_name}: {prev_state} → {curr_state}")
                            
                            # Log to debugger for analysis
                            self.debugger.log_state_change(
                                session_name, prev_state, curr_state,
                                "Monitor loop state change"
                            )
                            
                            # Update state in tracker for auto-completion detection
                            if hasattr(self.tracker, 'mark_state_transition'):
                                state_name = 'working' if curr_state == SessionState.WORKING else 'waiting'
                                self.tracker.mark_state_transition(session_name, state_name)
                    
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
                for data_dict in [self.last_screen_hash, self.notification_sent,
                                self.last_state, self.last_notification_time,
                                self.last_activity_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
                if session_name in self.active_threads:
                    del self.active_threads[session_name]

                # T027: Clean up reconnection state
                if session_name in self.reconnection_states:
                    del self.reconnection_states[session_name]

                # T028: Clean up persisted state file
                try:
                    state_file = self.get_state_file_path(session_name)
                    if os.path.exists(state_file):
                        os.remove(state_file)
                        logger.debug(f"Removed persisted state file for {session_name}")
                except Exception as e:
                    logger.warning(f"Failed to remove persisted state file for {session_name}: {e}")

                # Clear state analyzer cache for this session
                self.state_analyzer.clear_cache(session_name)
                # Remove from wait time tracker
                self.tracker.remove_session(session_name)
    
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
                for data_dict in [self.last_screen_hash, self.notification_sent, 
                                self.last_state, self.last_notification_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
    
    def start_monitoring(self):
        """Start monitoring all Claude sessions"""
        logger.info("🚀 Starting multi-session monitoring...")
        self.running = True

        # Discover initial sessions
        active_sessions = self.discover_sessions()

        # Initialize tracker states for all sessions (T056 fix: wait time tracking on restart)
        for session_name in active_sessions:
            try:
                current_state = self.get_session_state(session_name)
                state_name = 'working' if current_state == SessionState.WORKING else 'waiting'
                if hasattr(self.tracker, 'mark_state_transition'):
                    self.tracker.mark_state_transition(session_name, state_name)
                    logger.debug(f"Initialized tracker state for {session_name}: {state_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize tracker for {session_name}: {e}")

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
                    self.tracker.cleanup_old_sessions()  # Clean up old session wait times
                
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
            self.notification_sent.clear()
            self.last_state.clear()
            self.last_notification_time.clear()
        
        logger.info("✅ All monitoring threads stopped and cleaned up")


def main():
    """Main entry point for Telegram bot with optional monitoring"""
    import threading
    from ..telegram.bot import TelegramBridge

    try:
        config = ClaudeOpsConfig()

        if config.hook_only_mode:
            logger.info("🪝 Hook-only mode enabled - notifications via Claude Code hooks")
            # Start Telegram bot only (no monitoring thread)
            bot = TelegramBridge(config)
            logger.info("🤖 Starting Telegram bot (hook-only mode)...")
            bot.run()
        else:
            # Legacy: Start monitoring in separate thread
            monitor = MultiSessionMonitor(config)
            monitor_thread = threading.Thread(target=monitor.start_monitoring, daemon=True)
            monitor_thread.start()
            logger.info("📊 Started monitoring thread (polling mode)")

            # Start Telegram bot (main thread)
            bot = TelegramBridge(config)
            logger.info("🤖 Starting Telegram bot...")
            bot.run()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        if 'monitor' in locals():
            monitor.stop_monitoring()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        if 'monitor' in locals():
            monitor.stop_monitoring()


if __name__ == "__main__":
    main()