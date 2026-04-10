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
from ..utils.overload_retry import OverloadRetryState, _FALLBACK_PROMPT  # 529 overloaded auto-retry
from ..utils.state_persistence import PersistedSessionState  # T028: Restart state persistence
from ..telegram.notifier import SmartNotifier
from .completion_event_system import (
    CompletionEventBus, CompletionEventType, CompletionEvent,
    CompletionTimeRecorder, CompletionNotifier, emit_completion
)
from ..telegram.message_queue import message_queue
from ..web_dashboard.shared_state import SharedSessionState
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

        # e006: Shared session state for web dashboard consumers
        self.shared_state = SharedSessionState()

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

        # Screen change tracking for race condition prevention
        # Tracks when screen last changed to detect tool-transition micro-gaps
        self.last_screen_change_time: Dict[str, float] = {}  # session -> timestamp

        # Context limit auto-restart cooldown (prevent re-detection from residual scroll buffer)
        self._context_limit_restart_time: Dict[str, float] = {}  # session -> restart_timestamp

        # T027: Session reconnection tracking
        self.reconnection_states: Dict[str, SessionReconnectionState] = {}  # session -> reconnection_state
        # 529 overloaded auto-retry
        self.overload_retry_states: Dict[str, OverloadRetryState] = {}     # session -> retry_state
        # stuck-after-agent auto-nudge: tracks last send time per session
        self._stuck_nudge_sent_at: Dict[str, float] = {}  # session -> timestamp
        # stuck-after-agent detection cooldown: avoid JSONL disk I/O every loop
        self._stuck_check_at: Dict[str, float] = {}       # session -> last check timestamp
        self._stuck_check_interval = 10.0                 # recheck at most every 10s
        # stuck-ca auto-nudge: detects /ca stalled in EXECUTING state
        self._ca_nudge_sent_at: Dict[str, float] = {}     # session -> timestamp
        self._ca_check_at: Dict[str, float] = {}          # session -> last check timestamp

        # working-stall detection: WORKING 상태가 너무 오래 지속될 때 알림
        self._working_since: Dict[str, float] = {}        # session -> WORKING 진입 시간
        self._stall_notified_at: Dict[str, float] = {}    # session -> 마지막 stall 알림 시간
        self._stall_threshold: float = float(os.getenv("STALL_THRESHOLD_SECONDS", "600"))  # 기본 10분
        self._stall_notify_cooldown: float = 300.0        # 5분 쿨다운

        # error auto-resume: auto-send "이어서 진행해줘" after Error Detected
        self._error_detected_at: Dict[str, float] = {}    # session -> when error was detected
        self._error_auto_resume_count: Dict[str, int] = {} # session -> resume attempt count

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
            now = time.time()
            self.last_activity_time[session_name] = now
            self.last_screen_change_time[session_name] = now
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
            # Only re-arm notification if enough time has passed since last notification.
            # This prevents the repeated false alarm cycle:
            #   WORKING → micro-gap(notify) → WORKING(re-arm) → micro-gap(notify again)
            # By keeping notification_sent=True for 30s after a notification,
            # micro-gaps within that window are suppressed.
            last_notif = self.last_notification_time.get(session_name, 0)
            if current_time - last_notif > 30:
                self.notification_sent[session_name] = False
            if previous_state != SessionState.WORKING:
                self.tracker.reset_session(session_name)
                # working-stall: WORKING 진입 시간 기록
                self._working_since[session_name] = current_time
            return False, None
        else:
            # working-stall: WORKING 이탈 시 추적 제거
            self._working_since.pop(session_name, None)
            self._stall_notified_at.pop(session_name, None)

        # 0. Context limit detected (highest priority - requires immediate action)
        # CRITICAL: Check BEFORE notification_sent guard because context limit
        # requires auto-restart regardless of whether a regular completion
        # notification was already sent. Without this, the sequence
        # WORKING→IDLE(notified)→CONTEXT_LIMIT would be permanently blocked.
        restart_cooldown = 60
        last_restart = self._context_limit_restart_time.get(session_name, 0)
        if current_state == SessionState.CONTEXT_LIMIT and previous_state != SessionState.CONTEXT_LIMIT and (current_time - last_restart) > restart_cooldown:
            self.notification_sent[session_name] = True
            self.last_notification_time[session_name] = current_time
            logger.info(f"📢 Notification: {session_name} - Context limit reached - session needs restart")
            self.debugger.log_notification(
                session_name, NotificationEvent.SENT,
                "Context limit reached - session needs restart", current_state
            )
            # NOTE: Event bus CompletionEvent is intentionally NOT emitted here.
            # CONTEXT_LIMIT is handled via send_context_limit_notification() which
            # triggers auto-restart, not the regular completion event pipeline.
            return True, None

        # Context-limit cooldown expiry re-arm fallback:
        # If a context-limit restart happened and the cooldown has since expired,
        # clear notification_sent so the next completion can fire normally.
        if last_restart > 0 and (current_time - last_restart) > restart_cooldown:
            if self.notification_sent.get(session_name, False):
                self.notification_sent[session_name] = False
                logger.debug(f"Re-armed notification for {session_name} after context-limit cooldown expired")

        # Enhanced duplicate prevention (does not apply to CONTEXT_LIMIT above)
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

        # RACE CONDITION GUARD: If screen was changing very recently,
        # we might be in a tool-transition micro-gap where "esc to interrupt"
        # briefly disappeared. Require screen stability before notifying.
        last_change = self.last_screen_change_time.get(session_name, 0)
        screen_stable_duration = current_time - last_change if last_change else float('inf')
        # Require at least 2 poll intervals (6s) of screen stability
        # to avoid false alarms during rapid tool transitions
        min_stability = self.config.check_interval * 2  # default: 6 seconds

        # Reasons for notification
        notification_reason = ""
        should_notify = False

        # 1. Task-specific completion detected
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
        elif previous_state == SessionState.WORKING and current_state not in (SessionState.WORKING, SessionState.SCHEDULED):
            # RACE CONDITION FIX: During tool transitions, Claude briefly shows no
            # working indicators. Require screen stability to confirm real completion.
            # SCHEDULED is treated as still-working (e.g. PIU-v2 running cron tasks)
            if screen_stable_duration >= min_stability:
                should_notify = True
                notification_reason = f"Work completed (WORKING → {current_state})"
            else:
                logger.debug(f"Suppressed notification for {session_name}: "
                           f"screen changed {screen_stable_duration:.1f}s ago "
                           f"(need {min_stability}s stability)")
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
                # Require screen stability AND cooldown to prevent false alarms
                if current_time - last_notification_time > 10 and screen_stable_duration >= min_stability:
                    should_notify = True
                    notification_reason = "Completion message detected"
        
        # EMIT COMPLETION EVENT unconditionally on state transition
        # This MUST be outside the should_notify guard because:
        # 1. Screen stability may suppress notification for 1-2 poll cycles
        # 2. But completion_time must be recorded immediately for wait time tracking
        # 3. previous_state is consumed (updated to current) after this method returns
        if previous_state == SessionState.WORKING and current_state not in (SessionState.WORKING, SessionState.SCHEDULED):
            logger.info(f"🎯 Emitting completion event for {session_name} (WORKING → {current_state})")
            self.event_bus.emit(CompletionEvent(
                session_name=session_name,
                event_type=CompletionEventType.STATE_TRANSITION,
                timestamp=current_time,
                previous_state=previous_state.value,
                new_state=current_state.value,
                metadata={'reason': notification_reason or 'state_transition'}
            ))

        if should_notify:
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

    def send_context_limit_notification(self, session_name: str):
        """Send context limit alert and auto-restart the session.

        When auto-restart is enabled (default), automatically restarts the session
        with a fresh context and handoff prompt. Sends a Telegram notification
        informing the user of the auto-restart.

        When auto-restart is disabled, sends a notification with restart/ignore buttons.

        Args:
            session_name: The session that hit the context limit
        """
        try:
            import json
            import requests

            self._log_scraping_event(session_name, "context_limit", "notified")

            bot_token = self.config.telegram_bot_token
            chat_id = self.config.telegram_chat_id
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            if self.config.context_limit_auto_restart:
                # Auto-restart mode: notify + restart
                message = (
                    f"⚠️ *Context Limit Reached*\n\n"
                    f"세션 `{session_name}` 컨텍스트 한도 도달.\n"
                    f"🔄 자동 재시작 중..."
                )
                data = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                }
                requests.post(url, data=data, timeout=10)

                # Perform auto-restart
                success = self._auto_restart_session(session_name)

                # Send result notification
                if success:
                    result_msg = (
                        f"✅ `{session_name}` 자동 재시작 완료!\n\n"
                        f"🆕 Fresh context (이전 대화 없음)\n"
                        f"📋 핸드오프 프롬프트 전송됨"
                    )
                else:
                    result_msg = (
                        f"❌ `{session_name}` 자동 재시작 실패.\n"
                        f"수동으로 `/restart` 해주세요."
                    )
                data = {
                    "chat_id": chat_id,
                    "text": result_msg,
                    "parse_mode": "Markdown",
                }
                requests.post(url, data=data, timeout=10)
            else:
                # Manual mode: send notification with buttons
                message = (
                    f"⚠️ *Context Limit Reached*\n\n"
                    f"세션 `{session_name}`의 컨텍스트 윈도우가 가득 찼습니다.\n"
                    f"`/compact`는 이 상태에서 작동하지 않습니다 (API 호출 deadlock).\n\n"
                    f"🔄 새 세션으로 재시작하려면 아래 버튼을 눌러주세요."
                )
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "🔄 Restart Session", "callback_data": f"ctx_restart:{session_name}"},
                        {"text": "❌ Ignore", "callback_data": f"ctx_ignore:{session_name}"},
                    ]]
                }
                data = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "reply_markup": json.dumps(keyboard),
                }
                response = requests.post(url, data=data, timeout=10)
                if response.status_code == 200:
                    logger.info(f"⚠️ Sent context limit notification for session: {session_name}")
                else:
                    logger.error(f"Telegram API error {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"Error sending context limit notification for {session_name}: {e}")

    def _wait_for_prompt(self, session_name: str, timeout: int = 30, prompt_chars: tuple = ('❯ ', '$ ')) -> bool:
        """Wait for a shell/Claude prompt to appear in the tmux session.

        Polls the last 5 lines of the tmux pane until a prompt character
        is found or timeout is reached.

        Args:
            session_name: The tmux session to poll
            timeout: Maximum seconds to wait
            prompt_chars: Tuple of prompt endings to look for

        Returns:
            True if prompt detected, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_name, "-p"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines[-5:]:
                        if any(line.rstrip().endswith(p.rstrip()) for p in prompt_chars):
                            return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _auto_restart_session(self, session_name: str) -> bool:
        """Auto-restart a Claude session that hit context limit.

        Exits the current session, clears the terminal (to prevent re-detection
        from old scroll buffer), collects handoff context, and starts
        a fresh Claude session with the handoff prompt.

        Uses prompt-polling instead of fixed delays to ensure each step
        completes before proceeding. Sends Enter separately from handoff
        text with verification retry.

        Args:
            session_name: The tmux session to restart

        Returns:
            True if restart succeeded, False otherwise
        """
        try:
            logger.info(f"🔄 Auto-restarting {session_name} after context limit...")

            # Step 1: Exit current Claude session
            subprocess.run(["tmux", "send-keys", "-t", session_name, "C-c"], timeout=5)
            time.sleep(1)
            # Send /exit, Escape (dismiss autocomplete), Enter separately
            # Claude Code's autocomplete intercepts Enter if sent atomically with /exit
            subprocess.run(["tmux", "send-keys", "-t", session_name, "/exit"], timeout=5)
            time.sleep(0.5)
            subprocess.run(["tmux", "send-keys", "-t", session_name, "Escape"], timeout=5)
            time.sleep(0.3)
            subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], timeout=5)

            # Wait for shell prompt instead of fixed 3s delay
            if not self._wait_for_prompt(session_name, timeout=15, prompt_chars=('❯ ', '$ ')):
                logger.warning(f"⚠️ {session_name}: shell prompt not detected after /exit, proceeding anyway")

            # Step 2: Collect handoff context BEFORE clearing screen
            handoff = self._build_handoff_prompt(session_name)

            # Step 3: Clear terminal to remove old "Context limit reached" from scroll buffer
            # This prevents the monitor from re-detecting the old text and creating a restart loop
            subprocess.run(["tmux", "send-keys", "-t", session_name, "clear", "Enter"], timeout=5)
            time.sleep(1)

            # Step 4: Start fresh Claude session (NO --continue)
            subprocess.run(["tmux", "send-keys", "-t", session_name, "claude --dangerously-skip-permissions", "Enter"], timeout=5)

            # Wait for Claude's input prompt (❯) instead of fixed 5s delay
            if not self._wait_for_prompt(session_name, timeout=30, prompt_chars=('❯ ',)):
                logger.warning(f"⚠️ {session_name}: Claude prompt not detected after startup, proceeding anyway")

            # Step 5: Send handoff prompt with robust Enter delivery
            if handoff:
                if len(handoff) > 4000:
                    handoff = handoff[:3900] + "\n\n[핸드오프 프롬프트가 잘렸습니다. 상태 파일을 직접 확인해주세요.]"

                # Send text first, then Enter separately to prevent Enter loss
                subprocess.run(["tmux", "send-keys", "-t", session_name, handoff], timeout=10)
                time.sleep(0.5)
                subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], timeout=5)
                time.sleep(1)

                # Verify: check if Claude started working (not still showing prompt)
                # If prompt still visible, Enter was lost — retry
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_name, "-p"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    last_lines = result.stdout.strip().split('\n')[-5:]
                    still_prompting = any(
                        line.rstrip().endswith('❯') or line.rstrip().endswith('❯ ')
                        for line in last_lines
                    )
                    if still_prompting:
                        logger.warning(f"⚠️ {session_name}: Enter may have been lost, retrying...")
                        time.sleep(1)
                        subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], timeout=5)

            logger.info(f"✅ Auto-restart completed for {session_name}")

            # Reset monitor state + set cooldown to prevent re-detection from residual text
            with self.thread_lock:
                self.last_state[session_name] = SessionState.WORKING
                self.notification_sent[session_name] = True  # Block notifications during cooldown
                self._context_limit_restart_time[session_name] = time.time()

            return True

        except Exception as e:
            logger.error(f"❌ Auto-restart failed for {session_name}: {e}")
            # Set cooldown even on failure to prevent rapid-retry storm
            with self.thread_lock:
                self._context_limit_restart_time[session_name] = time.time()
            return False

    def _build_handoff_prompt(self, session_name: str) -> str:
        """Build a handoff prompt from screen log + minimal metadata.

        Uses the last 50 lines of tmux screen output as primary context,
        since OMC state files (notepad, MANIFEST) are auto-loaded by the
        new session's hooks. Only adds branch name and active OMC modes
        as lightweight metadata.

        Args:
            session_name: The tmux session name

        Returns:
            Handoff prompt string for the new session (max ~2500 chars)
        """
        parts = ["이전 세션이 context limit에 도달하여 새 세션으로 자동 재시작되었습니다.\n"]

        # 1. Metadata: branch + active OMC modes
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", session_name, "-p", "#{pane_current_path}"],
                capture_output=True, text=True, timeout=5
            )
            cwd = result.stdout.strip() if result.returncode == 0 else None

            if cwd and os.path.isdir(cwd):
                branch = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=cwd, capture_output=True, text=True, timeout=5
                )
                branch_name = branch.stdout.strip() if branch.returncode == 0 else "unknown"

                # Check active OMC modes
                omc_state_dir = os.path.join(cwd, '.omc', 'state')
                active_modes = []
                if os.path.isdir(omc_state_dir):
                    for f in os.listdir(omc_state_dir):
                        if f.endswith('-state.json'):
                            active_modes.append(f.replace('-state.json', ''))

                meta = f"Branch: `{branch_name}`"
                if active_modes:
                    meta += f" | OMC: `{', '.join(active_modes)}`"
                parts.append(meta + "\n")
        except Exception:
            pass

        # 2. Screen log: last 50 lines (primary context)
        try:
            screen = subprocess.run(
                ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-50"],
                capture_output=True, text=True, timeout=5
            )
            if screen.returncode == 0 and screen.stdout.strip():
                lines = screen.stdout.strip().split('\n')
                # Filter out context limit error lines (noise for new session)
                filtered = [
                    line for line in lines
                    if "Context limit reached" not in line
                    and "context window exceeded" not in line
                    and "Conversation is too long" not in line
                ]
                screen_text = '\n'.join(filtered)
                # Truncate to ~2000 chars
                if len(screen_text) > 2000:
                    screen_text = screen_text[-2000:]
                parts.append(f"## 직전 화면 로그\n```\n{screen_text}\n```\n")
        except Exception as e:
            logger.warning(f"Failed to capture screen log: {e}")

        parts.append("이전 작업을 이어서 진행해주세요. (notepad, MANIFEST 등은 자동 로드됩니다)")
        return "\n".join(parts)

    def send_completion_notification(self, session_name: str, task_completion: Optional[TaskCompletion] = None):
        """Send work completion notification for a specific session with task details

        Args:
            session_name: The session to send notification for
            task_completion: Optional task completion details
        """
        try:
            # Check if this is a context limit notification
            current_state = self.last_state.get(session_name, SessionState.UNKNOWN)
            if current_state == SessionState.CONTEXT_LIMIT:
                self.send_context_limit_notification(session_name)
                return

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
                # Preserve existing wait time records across restarts.
                # Only reset if the session has no completion record — this prevents
                # bot restarts from wiping all wait time data.
                has_record = session_name in getattr(self.tracker, 'completion_times', {})
                if not has_record:
                    self.tracker.reset_session(session_name)
                else:
                    logger.info(f"📊 Preserved completion record for {session_name}")
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
                    
                    # --- 529 Overloaded auto-retry ---
                    current_screen = self.state_analyzer.get_screen_content(session_name)
                    is_overloaded = self.state_analyzer._detect_overloaded(current_screen or "")

                    if is_overloaded:
                        if session_name not in self.overload_retry_states:
                            # First detection: save last prompt and schedule first retry
                            saved = self.state_analyzer.extract_last_prompt(current_screen) or _FALLBACK_PROMPT
                            retry_state = OverloadRetryState(
                                session_name=session_name,
                                saved_prompt=saved,
                            )
                            retry_state.schedule_next()
                            self.overload_retry_states[session_name] = retry_state
                            logger.warning(
                                f"⚠️ {session_name}: API 529 overloaded detected. "
                                f"Retry in {retry_state.current_backoff}s (prompt: {saved[:60]!r})"
                            )
                        else:
                            retry_state = self.overload_retry_states[session_name]
                            if retry_state.is_ready():
                                retry_state.mark_retrying()
                                logger.info(
                                    f"🔁 {session_name}: Retry #{retry_state.retry_count} — "
                                    f"sending {retry_state.saved_prompt!r}"
                                )
                                try:
                                    subprocess.run(
                                        ["tmux", "send-keys", "-t", session_name,
                                         retry_state.saved_prompt, "Enter"],
                                        timeout=5, check=False
                                    )
                                except Exception as e:
                                    logger.warning(f"tmux send-keys failed for {session_name}: {e}")
                                retry_state.schedule_next()
                    elif session_name in self.overload_retry_states:
                        # Session recovered — clear retry state
                        self.overload_retry_states[session_name].mark_recovered()
                        del self.overload_retry_states[session_name]
                    # --- end overload retry ---

                    # --- stuck-after-agent auto-nudge ---
                    # Only check when IDLE (not WORKING) and not currently in overload retry
                    _current_state = self.last_state.get(session_name)
                    if (session_name not in self.overload_retry_states
                            and not is_overloaded
                            and _current_state not in (
                                SessionState.WORKING,
                                SessionState.WAITING_INPUT,
                            )):
                        now = time.time()
                        if now - self._stuck_check_at.get(session_name, 0) >= self._stuck_check_interval:
                            self._stuck_check_at[session_name] = now
                            path = session_manager.get_session_path(session_name)
                        else:
                            path = None
                        if path and self.state_analyzer.detect_stuck_after_agent(path, delay_seconds=45):
                            last_nudge = self._stuck_nudge_sent_at.get(session_name, 0)
                            # 300s cooldown between nudges for same session
                            if time.time() - last_nudge > 300:
                                logger.info(
                                    f"🔔 {session_name}: stuck after agent result — "
                                    f"sending nudge '마저해줘'"
                                )
                                try:
                                    subprocess.run(
                                        ["tmux", "send-keys", "-t", session_name,
                                         "마저해줘", "Enter"],
                                        timeout=5, check=False,
                                    )
                                    self._stuck_nudge_sent_at[session_name] = time.time()
                                except Exception as e:
                                    logger.warning(
                                        f"tmux send-keys (stuck nudge) failed "
                                        f"for {session_name}: {e}"
                                    )
                    # --- end stuck-after-agent nudge ---

                    # --- stuck-ca auto-nudge ---
                    # If /ca left critique-lock.json in EXECUTING state but session is idle,
                    # send "/ca" so Claude resumes from where it stopped.
                    if (session_name not in self.overload_retry_states
                            and not is_overloaded
                            and _current_state not in (
                                SessionState.WORKING,
                                SessionState.WAITING_INPUT,
                            )):
                        now = time.time()
                        if now - self._ca_check_at.get(session_name, 0) >= self._stuck_check_interval:
                            self._ca_check_at[session_name] = now
                            ca_path = session_manager.get_session_path(session_name)
                        else:
                            ca_path = None
                        if ca_path and self.state_analyzer.detect_stuck_ca(ca_path, delay_seconds=60):
                            last_ca_nudge = self._ca_nudge_sent_at.get(session_name, 0)
                            if time.time() - last_ca_nudge > 300:
                                logger.info(
                                    f"🔔 {session_name}: /ca stuck in EXECUTING — "
                                    f"sending resume nudge '/ca'"
                                )
                                try:
                                    subprocess.run(
                                        ["tmux", "send-keys", "-t", session_name,
                                         "/ca", "Enter"],
                                        timeout=5, check=False,
                                    )
                                    self._ca_nudge_sent_at[session_name] = time.time()
                                except Exception as e:
                                    logger.warning(
                                        f"tmux send-keys (ca nudge) failed "
                                        f"for {session_name}: {e}"
                                    )
                    # --- end stuck-ca nudge ---

                    # --- error auto-resume ---
                    # When Error Detected fires and session stays idle for 90s,
                    # automatically send "이어서 진행해줘" (mirrors what user does manually).
                    # Caps at 3 attempts to prevent infinite error loops.
                    # Skipped if overload retry is active (different handler).
                    _ERROR_RESUME_DELAY = 90    # seconds to wait before auto-resume
                    _ERROR_RESUME_MAX = 3       # max auto-resume attempts per error episode
                    if (session_name in self._error_detected_at
                            and session_name not in self.overload_retry_states):
                        elapsed = time.time() - self._error_detected_at[session_name]
                        count = self._error_auto_resume_count.get(session_name, 0)
                        curr_state = self.last_state.get(session_name)
                        if (elapsed >= _ERROR_RESUME_DELAY
                                and curr_state != SessionState.WORKING
                                and count < _ERROR_RESUME_MAX
                                and self.session_exists(session_name)):
                            logger.info(
                                f"⚡ {session_name}: auto-resuming after error "
                                f"(elapsed {elapsed:.0f}s, attempt #{count + 1}/{_ERROR_RESUME_MAX})"
                            )
                            try:
                                subprocess.run(
                                    ["tmux", "send-keys", "-t", session_name,
                                     "이어서 진행해줘", "Enter"],
                                    timeout=5, check=False
                                )
                                self._error_auto_resume_count[session_name] = count + 1
                                # Reset timer so next check waits another 90s
                                self._error_detected_at[session_name] = time.time()
                            except Exception as e:
                                logger.warning(
                                    f"tmux send-keys (error auto-resume) failed "
                                    f"for {session_name}: {e}"
                                )
                        elif count >= _ERROR_RESUME_MAX:
                            # Exhausted retries — stop trying, leave for user
                            logger.warning(
                                f"🛑 {session_name}: error auto-resume exhausted "
                                f"({_ERROR_RESUME_MAX} attempts) — manual intervention needed"
                            )
                            del self._error_detected_at[session_name]
                            del self._error_auto_resume_count[session_name]
                    # --- end error auto-resume ---

                    # --- working-stall detection ---
                    # WORKING 상태가 _stall_threshold 초 이상 유지되면 Telegram 알림.
                    # MCP 툴 호출 후 응답 없이 조용히 멈춘 경우를 감지.
                    _curr_state = self.last_state.get(session_name)
                    if (_curr_state == SessionState.WORKING
                            and session_name in self._working_since):
                        stall_elapsed = time.time() - self._working_since[session_name]
                        if stall_elapsed >= self._stall_threshold:
                            last_stall = self._stall_notified_at.get(session_name, 0)
                            if time.time() - last_stall > self._stall_notify_cooldown:
                                mins = stall_elapsed / 60
                                logger.warning(
                                    f"⚠️ {session_name}: WORKING {stall_elapsed:.0f}s 지속 — stall 의심"
                                )
                                self._stall_notified_at[session_name] = time.time()
                                try:
                                    msg = (
                                        f"⚠️ *{session_name}* 작업이 {mins:.1f}분째 진행 중\n"
                                        f"응답 없이 멈춘 것일 수 있습니다. 확인이 필요합니다.\n"
                                        f"(자동 재시작은 하지 않습니다 — 수동 확인 후 명령 전송)"
                                    )
                                    self.notifier.send_message(msg)
                                except Exception as e:
                                    logger.warning(f"stall notify failed for {session_name}: {e}")
                    # --- end working-stall detection ---

                    # Check for screen changes (updates activity time)
                    screen_changed = self.has_screen_changed(session_name)
                    
                    # Log activity changes for debugging
                    if screen_changed:
                        logger.debug(f"📺 Screen changed in {session_name}")
                    
                    
                    # Snapshot state BEFORE notification check (which updates last_state)
                    prev_state_snapshot = self.last_state.get(session_name)

                    # Check if we should send completion notification (state transition)
                    should_notify, task_completion = self.should_send_completion_notification(session_name)
                    if should_notify:
                        logger.info(f"🎯 Sending completion notification for {session_name}")
                        self.send_completion_notification(session_name, task_completion)
                        # Reset activity tracking on real completion
                        self.last_activity_time[session_name] = time.time()

                        # error auto-resume: record when Error Detected fires
                        if (task_completion and
                                "Error Detected" in str(task_completion.message)):
                            self._error_detected_at[session_name] = time.time()
                            self._error_auto_resume_count.setdefault(session_name, 0)
                            logger.info(
                                f"⚠️ {session_name}: Error Detected — "
                                f"will auto-resume in 90s if still idle "
                                f"(attempt #{self._error_auto_resume_count[session_name] + 1})"
                            )

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
                    # Use prev_state_snapshot (captured BEFORE should_send_completion_notification
                    # updates self.last_state) to detect actual state transitions
                    curr_state_now = self.last_state.get(session_name)
                    if prev_state_snapshot is not None and prev_state_snapshot != curr_state_now:
                        logger.info(f"🔄 {session_name}: {prev_state_snapshot} → {curr_state_now}")

                        # Log to debugger for analysis
                        self.debugger.log_state_change(
                            session_name, prev_state_snapshot, curr_state_now,
                            "Monitor loop state change"
                        )

                        # Update state in tracker for auto-completion detection
                        if hasattr(self.tracker, 'mark_state_transition'):
                            state_name = 'working' if curr_state_now in (SessionState.WORKING, SessionState.SCHEDULED) else 'waiting'
                            self.tracker.mark_state_transition(session_name, state_name)

                        # Clear error auto-resume state when session resumes working
                        if curr_state_now in (SessionState.WORKING, SessionState.SCHEDULED):
                            self._error_detected_at.pop(session_name, None)
                            self._error_auto_resume_count.pop(session_name, None)
                    
                    # e006: Update shared session state for web dashboard
                    current_state_val = self.last_state.get(session_name, SessionState.UNKNOWN)
                    self.shared_state.update_session(session_name, {
                        "state": current_state_val.value,
                        "last_activity": self.last_activity_time.get(session_name, 0),
                        "screen_hash": self.last_screen_hash.get(session_name, ""),
                        "notification_sent": self.notification_sent.get(session_name, False),
                    })
                    self.shared_state.flush_if_due(interval=3.0)

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
                # e006: Remove from shared state and flush
                self.shared_state.remove_session(session_name)
                self.shared_state.flush()
    
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