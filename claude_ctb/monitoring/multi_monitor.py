"""
Multi-Session Monitor for Claude Code

Monitors all Claude sessions simultaneously and sends notifications
when any session completes work.
"""

import glob
import os
import json
import time
import logging
import threading
import subprocess
import hashlib
from datetime import datetime, timezone
from typing import Dict, Set, Tuple, Optional
from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..utils.notification_debugger import get_debugger, NotificationEvent
from ..utils.task_completion_detector import task_detector, TaskCompletion, AlertPriority
from ..utils.session_reconnect import SessionReconnectionState  # T027: Reconnection tracking
from ..utils.overload_retry import OverloadRetryState, _FALLBACK_PROMPT  # 529 overloaded auto-retry
from ..utils.state_persistence import PersistedSessionState  # T028: Restart state persistence
from ..utils.progress_tracker import read_active_skill, parse_screen_progress, detect_stall as detect_progress_stall, SkillProgress
from ..telegram.notifier import SmartNotifier
from .completion_event_system import (
    CompletionEventBus, CompletionEventType, CompletionEvent,
    CompletionTimeRecorder
)
from ..telegram.message_queue import message_queue
from ..web_dashboard.shared_state import SharedSessionState
# Import improved tracker with state-based completion detection
try:
    from ..utils.wait_time_tracker_v2 import migrate_to_v2
    wait_tracker = migrate_to_v2()  # Auto-migrate on import
except ImportError:
    # Fallback to original tracker
    from ..utils.wait_time_tracker import wait_tracker

logger = logging.getLogger(__name__)


def _is_screen_progress_current(
    file_progress: Optional[SkillProgress],
    screen_content: str,
) -> bool:
    """screen_content가 현재 런의 것임을 검증.

    file_progress=None 또는 screen_content 공백: True 반환 (보수적 허용).
    그 외: file_progress.skill이 screen_content에 포함되어야 함.
    False 반환 시 screen_progress 무시, file_progress fallback 사용.
    """
    if not file_progress or not screen_content.strip():
        return True
    return file_progress.skill in screen_content


class MultiSessionMonitor:
    """Monitor multiple Claude Code sessions simultaneously"""

    _HOOK_EVENT_TTL = 30.0       # hook 이벤트 유효 기간 (초)
    _HOOK_EVENT_GC_TTL = 90.0    # hook 이벤트 GC 기간 (초)

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
        # 3-Phase 에스컬레이션: nudge(×3) → Escape(×1) → 수동 요청
        # C-c는 MCP tool call 등 정상적인 장기 작업을 죽일 수 있어 opt-in으로 변경.
        # STALL_ENABLE_CTRLC=1 환경변수로 활성화.
        self._working_since: Dict[str, float] = {}        # session -> WORKING 진입 시간
        self._stall_notified_at: Dict[str, float] = {}    # session -> 마지막 stall 알림 시간
        self._stall_nudge_count: Dict[str, int] = {}      # session -> 텍스트 nudge 횟수 (Phase 1)
        self._stall_escape_count: Dict[str, int] = {}     # session -> Escape 인터럽트 횟수 (Phase 2)
        self._stall_ctrlc_count: Dict[str, int] = {}      # session -> C-c 인터럽트 횟수 (Phase 3, opt-in)
        self._stall_threshold: float = float(os.getenv("STALL_THRESHOLD_SECONDS", "600"))  # 기본 10분
        self._stall_notify_cooldown: float = 300.0        # Phase 1 쿨다운 (5분)
        self._stall_interrupt_cooldown: float = 60.0      # Phase 2-3 쿨다운 (1분, 빠른 에스컬레이션)
        self._stall_max_nudges: int = 3                   # 최대 텍스트 nudge 횟수
        self._stall_max_escapes: int = 1                  # 최대 Escape 횟수
        # C-c는 기본 비활성(0). STALL_ENABLE_CTRLC=1 이면 2회 허용.
        self._stall_max_ctrlc: int = 2 if os.getenv("STALL_ENABLE_CTRLC") == "1" else 0
        self._post_ctrlc_at: Dict[str, float] = {}        # session -> C-c 전송 시각 (post-C-c resume용)
        self._stall_ctrlc_resume_timeout: float = 120.0   # WAITING 전환 대기 최대 시간

        # error auto-resume: auto-send "이어서 진행해줘" after Error Detected
        self._error_detected_at: Dict[str, float] = {}    # session -> when error was detected
        self._error_auto_resume_count: Dict[str, int] = {} # session -> resume attempt count

        # M13: Ticket-driven nudge suppression (e023)
        # Advisory dedup: session당 1회만 "티켓 완료" 알림 전송. 재시작 시 초기화는 설계 의도.
        self._ticket_done_notified: Dict[str, bool] = {}  # session -> notified flag

        # Progress stall detection: multi-stage skill이 중간에 멈췄을 때 감지
        # 3단계 에스컬레이션: nudge(×2) → Telegram(×1) → 침묵
        self._progress_nudge_count: Dict[str, int] = {}      # session -> nudge 횟수
        self._progress_nudge_sent_at: Dict[str, float] = {}  # session -> 마지막 nudge 시각
        self._progress_telegram_sent: Dict[str, bool] = {}   # session -> Telegram 알림 발송 여부
        self._progress_last_stage: Dict[str, int] = {}       # session -> 마지막 확인한 stage_num (리셋 감지용)
        self._progress_check_interval: float = 15.0          # 파일 I/O 빈도 제한 (15초)
        self._progress_check_at: Dict[str, float] = {}       # session -> 마지막 체크 시각

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
            elif session_name not in self._working_since:
                # 모니터 재시작 후 persisted state가 WORKING이면 previous_state도 WORKING이라
                # 위 분기가 실행되지 않아 _working_since가 초기화되지 않는 버그 수정.
                # 이 경우 재시작 시점을 기준으로 타이머 시작.
                self._working_since[session_name] = current_time
            return False, None
        else:
            # working-stall: WORKING 이탈 시 추적 제거
            self._working_since.pop(session_name, None)
            self._stall_notified_at.pop(session_name, None)
            self._stall_nudge_count.pop(session_name, None)
            self._stall_escape_count.pop(session_name, None)
            self._stall_ctrlc_count.pop(session_name, None)
            self._post_ctrlc_at.pop(session_name, None)

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

                # Check for incomplete workflow: [Stage N/M] where N < M
                try:
                    scrollback = self.state_analyzer.get_screen_content(session_name)
                    if scrollback:
                        recent = '\n'.join(scrollback.split('\n')[-100:])
                        stage_info = parse_screen_progress(recent)
                        if stage_info and stage_info[0] < stage_info[1]:
                            self.notifier.send_notification_sync(
                                f"⚠️ *{session_name}* Stage {stage_info[0]}/{stage_info[1]}에서 멈춤\n"
                                f"워크플로우 미완료 — /log로 확인 필요"
                            )
                            logger.warning(
                                f"⚠️ {session_name}: incomplete workflow "
                                f"Stage {stage_info[0]}/{stage_info[1]}"
                            )
                except Exception as e:
                    logger.debug(f"Incomplete workflow check failed for {session_name}: {e}")
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name} (duplicate or failed)")
                # Still mark completion if state changed (v2 tracker feature)
                if hasattr(self.tracker, 'mark_state_transition'):
                    self.tracker.mark_state_transition(session_name, 'waiting')

        except Exception as e:
            logger.error(f"Error sending completion notification for {session_name}: {e}")
    
    
    def _is_ticket_done_guard(self, session_name: str) -> bool:
        """Return True if the registered ticket for this session is done → suppress nudge.

        H9: Exceptions from is_ticket_done() → False (fail-open, nudge allowed).
        None return (session not registered) → tries auto-registration from session path,
        then re-checks. Still None after that → False (nudge allowed, default behaviour).
        """
        try:
            from ..utils.ticket_registry import is_ticket_done, auto_register_from_session_path
            result = is_ticket_done(session_name, self.state_dir)
            if result is None:
                # Not registered — try auto-registration from session working directory
                session_path = session_manager.get_session_path(session_name)
                if session_path and auto_register_from_session_path(
                    session_name, session_path, self.state_dir
                ):
                    result = is_ticket_done(session_name, self.state_dir)
            if result is not True:
                return False  # None (not registered) or False (open) → nudge allowed
            # Ticket is done — send dedup Telegram alert (session당 1회)
            if not self._ticket_done_notified.get(session_name):
                self._ticket_done_notified[session_name] = True
                try:
                    self.notifier.send_notification_sync(
                        f"✅ *{session_name}* 티켓 완료 — nudge 억제"
                    )
                except Exception:
                    pass
            return True
        except Exception as exc:
            logger.debug(
                "[ticket_registry] _is_ticket_done_guard error for %s: %s — returning False (nudge allowed)",
                session_name, exc,
            )
            return False  # fail-open

    def _check_progress_stall(self, session_name: str, curr_state: SessionState) -> None:
        """Detect multi-stage skill stall and escalate: nudge(×2) → Telegram(×1) → silence.

        Reads .omc/state/active-skill.json from the session's working directory
        and parses [Stage N/M] from screen content as fallback signal.
        Only triggers when session is IDLE (not WORKING/WAITING_INPUT).
        """
        now = time.time()

        # Rate-limit file I/O: check at most every 15 seconds
        if now - self._progress_check_at.get(session_name, 0) < self._progress_check_interval:
            return
        self._progress_check_at[session_name] = now

        # Get session working directory
        try:
            working_dir = session_manager.get_session_path(session_name)
        except Exception:
            return
        if not working_dir:
            return

        # Read file-based progress (v2 schema)
        file_progress = read_active_skill(working_dir)

        # Read screen-based progress (scrollback for stage pattern visibility)
        screen_content = self.state_analyzer.get_screen_content(session_name)
        # Limit to last 100 lines for freshness (avoid stale stage patterns from old runs)
        if screen_content:
            screen_lines = screen_content.split('\n')
            screen_for_stage = '\n'.join(screen_lines[-100:])
        else:
            screen_for_stage = None
        screen_progress = parse_screen_progress(screen_for_stage) if screen_for_stage else None
        screen_is_current = _is_screen_progress_current(file_progress, screen_for_stage or "")

        # Detect stall using dual-signal matrix
        is_stall = detect_progress_stall(
            file_progress=file_progress,
            screen_progress=screen_progress,
            session_state=curr_state.value,
            stall_threshold_seconds=300.0,
        )

        if not is_stall:
            return

        # Check stage change → reset counters
        # screen_progress is primary when screen is verified to be current run's output;
        # fall back to file_progress when screen is stale/residual from a different run.
        if screen_progress and screen_is_current:
            current_stage = screen_progress[0]
        elif file_progress:
            current_stage = file_progress.stage_num
        else:
            current_stage = 0
        last_stage = self._progress_last_stage.get(session_name, -1)
        if current_stage != last_stage:
            self._progress_last_stage[session_name] = current_stage
            self._progress_nudge_count[session_name] = 0
            self._progress_nudge_sent_at.pop(session_name, None)
            self._progress_telegram_sent[session_name] = False

        # Ticket done guard
        if self._is_ticket_done_guard(session_name):
            return

        # Recovery: if telegram already exhausted but screen has advanced past file stage,
        # the session is actually progressing — file just wasn't updated. Reset nudge state
        # so the next nudge cycle fires again. screen_is_current=True guards against residual
        # text from a different run triggering a spurious reset.
        # fall-through (no return): line below re-reads nudge_count=0/telegram_sent=False →
        # line 922+ `if nudge_count < 2:` block fires immediately.
        if (self._progress_telegram_sent.get(session_name, False)
                and file_progress and screen_progress and screen_is_current
                and file_progress.stage_num < screen_progress[0]):
            logger.info(
                f"🔄 {session_name}: stage mismatch recovery "
                f"(file={file_progress.stage_num} < screen={screen_progress[0]}), resetting nudge state"
            )
            self._progress_nudge_count[session_name] = 0
            self._progress_telegram_sent[session_name] = False
            self._progress_nudge_sent_at.pop(session_name, None)
            self._progress_last_stage.pop(session_name, None)

        nudge_count = self._progress_nudge_count.get(session_name, 0)
        last_nudge = self._progress_nudge_sent_at.get(session_name, 0)
        telegram_sent = self._progress_telegram_sent.get(session_name, False)

        # Build label for logging
        skill_name = file_progress.skill if file_progress else 'unknown'
        stage_label = file_progress.stage_label if file_progress else ''
        total = file_progress.total_stages if file_progress else (screen_progress[1] if screen_progress else '?')
        stage_info = f"Stage {current_stage}/{total}"
        if stage_label:
            stage_info += f" ({stage_label})"

        # Escalation: nudge(×2) → Telegram(×1) → silence
        if nudge_count < 2:
            # Cooldown check (first nudge is immediate, subsequent after 300s)
            if nudge_count > 0 and (now - last_nudge) < 300:
                return

            logger.info(f"🔔 {session_name}: progress stall at {stage_info} — nudge #{nudge_count + 1}/2")
            try:
                subprocess.run(
                    ["tmux", "send-keys", "-t", session_name, "이어서 진행해줘", "Enter"],
                    timeout=5, check=False,
                )
                self._progress_nudge_count[session_name] = nudge_count + 1
                self._progress_nudge_sent_at[session_name] = now
            except Exception as e:
                logger.warning(f"tmux send-keys (progress nudge) failed for {session_name}: {e}")

        elif not telegram_sent:
            # Cooldown after last nudge
            if (now - last_nudge) < 300:
                return

            # Calculate elapsed time
            if file_progress:
                elapsed_min = (datetime.now(timezone.utc) - file_progress.updated_at).total_seconds() / 60
            else:
                elapsed_min = 0

            logger.warning(f"⚠️ {session_name}: progress stall at {stage_info} — nudge exhausted, sending Telegram")
            try:
                self.notifier.send_notification_sync(
                    f"⚠️ *{session_name}*: {stage_info}에서 {elapsed_min:.0f}분째 정체\n"
                    f"스킬: {skill_name}\n"
                    f"액션: /log로 확인 또는 해당 세션에서 수동 입력"
                )
                self._progress_telegram_sent[session_name] = True
            except Exception as e:
                logger.warning(f"Telegram notification (progress stall) failed for {session_name}: {e}")

    def _check_resume_actions(self, session_name: str, curr_state: SessionState, prev_state: SessionState) -> None:
        """Check and trigger resume actions based on current session state.

        Called after should_send_completion_notification() so curr_state reflects
        the freshly updated last_state — eliminates 1-cycle stale lag.
        """
        is_overloaded = session_name in self.overload_retry_states
        _not_active = curr_state not in (SessionState.WORKING, SessionState.WAITING_INPUT)

        # --- stuck-after-agent auto-nudge ---
        if not is_overloaded and _not_active:
            now = time.time()
            if now - self._stuck_check_at.get(session_name, 0) >= self._stuck_check_interval:
                self._stuck_check_at[session_name] = now
                path = session_manager.get_session_path(session_name)
            else:
                path = None
            if path and self.state_analyzer.detect_stuck_after_agent(path, delay_seconds=45):
                if self._is_ticket_done_guard(session_name):
                    return  # 티켓 완료 — nudge 억제
                last_nudge = self._stuck_nudge_sent_at.get(session_name, 0)
                if time.time() - last_nudge > 300:
                    logger.info(f"🔔 {session_name}: stuck after agent result — sending nudge '마저해줘'")
                    try:
                        subprocess.run(
                            ["tmux", "send-keys", "-t", session_name, "마저해줘", "Enter"],
                            timeout=5, check=False,
                        )
                        self._stuck_nudge_sent_at[session_name] = time.time()
                    except Exception as e:
                        logger.warning(f"tmux send-keys (stuck nudge) failed for {session_name}: {e}")

        # --- stuck-ca auto-nudge ---
        if not is_overloaded and _not_active:
            now = time.time()
            if now - self._ca_check_at.get(session_name, 0) >= self._stuck_check_interval:
                self._ca_check_at[session_name] = now
                ca_path = session_manager.get_session_path(session_name)
            else:
                ca_path = None
            if ca_path and self.state_analyzer.detect_stuck_ca(ca_path, delay_seconds=60):
                if self._is_ticket_done_guard(session_name):
                    return  # 티켓 완료 — nudge 억제
                last_ca_nudge = self._ca_nudge_sent_at.get(session_name, 0)
                if time.time() - last_ca_nudge > 300:
                    logger.info(f"🔔 {session_name}: /ca stuck in EXECUTING — sending resume nudge '/ca'")
                    try:
                        subprocess.run(
                            ["tmux", "send-keys", "-t", session_name, "/ca", "Enter"],
                            timeout=5, check=False,
                        )
                        self._ca_nudge_sent_at[session_name] = time.time()
                    except Exception as e:
                        logger.warning(f"tmux send-keys (ca nudge) failed for {session_name}: {e}")

        # --- post-C-c resume ---
        # After C-c, if session transitions to WAITING_INPUT, send "이어서 진행해줘".
        if session_name in self._post_ctrlc_at:
            _ctrlc_elapsed = time.time() - self._post_ctrlc_at[session_name]
            if (curr_state == SessionState.WAITING_INPUT
                    and _ctrlc_elapsed < self._stall_ctrlc_resume_timeout):
                logger.info(
                    f"⚡ {session_name}: C-c 후 WAITING 전환 감지 ({_ctrlc_elapsed:.0f}s) — 자동 재개 전송"
                )
                try:
                    subprocess.run(
                        ["tmux", "send-keys", "-t", session_name, "이어서 진행해줘", "Enter"],
                        timeout=5, check=False,
                    )
                    self.notifier.send_notification_sync(
                        f"✅ *{session_name}* stall 복구 완료\n"
                        f"C-c 후 WAITING 전환 확인 — 자동 재개 전송"
                    )
                except Exception as e:
                    logger.warning(f"post-C-c resume failed for {session_name}: {e}")
                finally:
                    self._post_ctrlc_at.pop(session_name, None)
            elif (curr_state == SessionState.ERROR
                  or _ctrlc_elapsed >= self._stall_ctrlc_resume_timeout):
                self._post_ctrlc_at.pop(session_name, None)

        # --- error auto-resume ---
        # When session stays idle after error, auto-send "이어서 진행해줘". Max 3 attempts.
        _ERROR_RESUME_DELAY = 90
        _ERROR_RESUME_MAX = 3
        if session_name in self._error_detected_at and not is_overloaded:
            with self.thread_lock:
                _detected_at = self._error_detected_at.get(session_name, 0)
                _count = self._error_auto_resume_count.get(session_name, 0)
            elapsed = time.time() - _detected_at
            if (elapsed >= _ERROR_RESUME_DELAY
                    and curr_state != SessionState.WORKING
                    and _count < _ERROR_RESUME_MAX
                    and self.session_exists(session_name)):
                logger.info(
                    f"⚡ {session_name}: auto-resuming after error "
                    f"(elapsed {elapsed:.0f}s, attempt #{_count + 1}/{_ERROR_RESUME_MAX})"
                )
                try:
                    subprocess.run(
                        ["tmux", "send-keys", "-t", session_name, "이어서 진행해줘", "Enter"],
                        timeout=5, check=False,
                    )
                    with self.thread_lock:
                        self._error_auto_resume_count[session_name] = _count + 1
                        self._error_detected_at[session_name] = time.time()
                except Exception as e:
                    logger.warning(f"tmux send-keys (error auto-resume) failed for {session_name}: {e}")
            elif _count >= _ERROR_RESUME_MAX:
                logger.warning(
                    f"🛑 {session_name}: error auto-resume exhausted "
                    f"({_ERROR_RESUME_MAX} attempts) — manual intervention needed"
                )
                with self.thread_lock:
                    self._error_detected_at.pop(session_name, None)
                    self._error_auto_resume_count.pop(session_name, None)

        # --- progress stall detection (multi-stage skill) ---
        if not is_overloaded and _not_active:
            self._check_progress_stall(session_name, curr_state)

        # --- working-stall detection ---
        if self._is_ticket_done_guard(session_name):
            return  # 티켓 완료 — stall nudge 억제
        if curr_state == SessionState.WORKING and session_name in self._working_since:
            stall_elapsed = time.time() - self._working_since[session_name]
            if stall_elapsed >= self._stall_threshold:
                nudge_count = self._stall_nudge_count.get(session_name, 0)
                escape_count = self._stall_escape_count.get(session_name, 0)
                ctrlc_count = self._stall_ctrlc_count.get(session_name, 0)
                in_interrupt_phase = nudge_count >= self._stall_max_nudges
                cooldown = (self._stall_interrupt_cooldown if in_interrupt_phase
                            else self._stall_notify_cooldown)
                last_stall = self._stall_notified_at.get(session_name, 0)
                # hook 이벤트 체크 (Phase A: TTL 내 이벤트 있으면 확실히 working)
                if self._is_hook_supported(session_name) and self._check_hook_event(session_name):
                    logger.debug(f"⏸️ {session_name}: stall skip — hook event within TTL")
                    self._gc_hook_events(session_name)
                    return
                # GC (hook 지원 여부와 무관하게 오래된 파일 정리)
                self._gc_hook_events(session_name)
                # 멀티시그널 체크: bash child 또는 network 연결 있으면 stall 아님
                bash_child, net_est = self._check_stall_signals(session_name)
                if bash_child or net_est > 0:
                    logger.debug(
                        f"⏸️ {session_name}: stall skip — "
                        f"bash_child={bash_child}, net_est={net_est}"
                    )
                    self._log_stall_baseline(session_name, bash_child, net_est, curr_state.value, False)
                    return
                self._log_stall_baseline(session_name, bash_child, net_est, curr_state.value, False)
                if time.time() - last_stall > cooldown:
                    mins = stall_elapsed / 60
                    logger.warning(f"⚠️ {session_name}: WORKING {stall_elapsed:.0f}s 지속 — stall 의심")
                    self._stall_notified_at[session_name] = time.time()
                    try:
                        if nudge_count < self._stall_max_nudges:
                            subprocess.run(
                                ["tmux", "send-keys", "-t", session_name, "계속해줘", "Enter"],
                                timeout=5, check=False,
                            )
                            self._stall_nudge_count[session_name] = nudge_count + 1
                            msg = (
                                f"⚠️ *{session_name}* 작업이 {mins:.1f}분째 진행 중\n"
                                f"stall 감지 — 재개 신호 전송 "
                                f"({nudge_count + 1}/{self._stall_max_nudges}회)"
                            )
                        elif escape_count < self._stall_max_escapes:
                            subprocess.run(
                                ["tmux", "send-keys", "-t", session_name, "Escape"],
                                timeout=5, check=False,
                            )
                            self._stall_escape_count[session_name] = escape_count + 1
                            msg = (
                                f"🚨 *{session_name}* 작업이 {mins:.1f}분째 진행 중\n"
                                f"nudge {self._stall_max_nudges}회 무효 — "
                                f"Escape 인터럽트 전송 ({escape_count + 1}/{self._stall_max_escapes}회)"
                            )
                        elif ctrlc_count < self._stall_max_ctrlc:
                            subprocess.run(
                                ["tmux", "send-keys", "-t", session_name, "C-c"],
                                timeout=5, check=False,
                            )
                            self._stall_ctrlc_count[session_name] = ctrlc_count + 1
                            self._post_ctrlc_at[session_name] = time.time()
                            msg = (
                                f"🚨 *{session_name}* 작업이 {mins:.1f}분째 진행 중\n"
                                f"Escape 무효 — Ctrl+C 강제 인터럽트 전송 "
                                f"({ctrlc_count + 1}/{self._stall_max_ctrlc}회)\n"
                                f"hung 스킬/서브에이전트 강제 중단 시도 중"
                            )
                        else:
                            msg = (
                                f"🚨 *{session_name}* 자동 복구 실패\n"
                                f"작업 {mins:.1f}분, nudge {self._stall_max_nudges}회 + "
                                f"Escape {self._stall_max_escapes}회 + "
                                f"C-c {self._stall_max_ctrlc}회 모두 무효\n"
                                f"수동 확인이 필요합니다 (세션 재시작 권장)"
                            )
                        self.notifier.send_notification_sync(msg)
                        self._log_stall_baseline(session_name, bash_child, net_est, curr_state.value, True)
                    except Exception as e:
                        logger.warning(f"stall notify failed for {session_name}: {e}")

    def _get_claude_pid(self, session_name: str) -> Optional[int]:
        """tmux pane PID로부터 claude 프로세스 PID를 찾습니다."""
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", session_name, "-p", "#{pane_pid}"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            shell_pid = int(result.stdout.strip())
            try:
                import psutil
                shell_proc = psutil.Process(shell_pid)
                for child in shell_proc.children(recursive=False):
                    try:
                        cmdline = " ".join(child.cmdline())
                        if "claude" in cmdline.lower():
                            return child.pid
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except ImportError:
                ps_result = subprocess.run(
                    ["ps", "--ppid", str(shell_pid), "-o", "pid,args", "--no-headers"],
                    capture_output=True, text=True, timeout=3, check=False,
                )
                for line in ps_result.stdout.splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and "claude" in parts[1].lower():
                        return int(parts[0])
        except Exception:
            pass
        return None

    def _check_stall_signals(self, session_name: str) -> tuple:
        """Process tree + network 신호로 stall 여부를 보조 판단합니다.

        Returns:
            (bash_child: bool, net_est: int)
            bash_child=True이면 bash/sh/zsh 자식 프로세스 실행 중 (definitely working)
            net_est>0이면 api.anthropic.com과 ESTABLISHED 연결 있음 (LLM inference 중)
            실패 시 (False, 0) 반환 (보수적 폴백 — false negative 허용)
        """
        bash_child = False
        net_est = 0
        try:
            claude_pid = self._get_claude_pid(session_name)
            if claude_pid is None:
                return False, 0

            # bash child 탐지
            try:
                import psutil
                claude_proc = psutil.Process(claude_pid)
                for child in claude_proc.children(recursive=False):
                    try:
                        comm = child.name()
                        cmdline = child.cmdline()
                        if (comm in ("bash", "sh", "zsh")
                                and "-c" not in cmdline):
                            bash_child = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except ImportError:
                ps_result = subprocess.run(
                    ["ps", "--ppid", str(claude_pid), "-o", "comm,args", "--no-headers"],
                    capture_output=True, text=True, timeout=3, check=False,
                )
                for line in ps_result.stdout.splitlines():
                    parts = line.strip().split(None, 1)
                    if parts and parts[0] in ("bash", "sh", "zsh"):
                        args = parts[1] if len(parts) > 1 else ""
                        if "-c" not in args.split():
                            bash_child = True
                            break

            # 네트워크 감지 (api.anthropic.com:443 ESTABLISHED)
            net_est = self._get_net_established(claude_pid)

        except Exception as exc:
            logger.debug(f"_check_stall_signals error for {session_name}: {exc}")
        return bash_child, net_est

    def _check_hook_event(self, session_name: str) -> bool:
        """TTL 내 hook 이벤트 파일이 존재하면 True 반환 (stall skip 신호).

        Returns:
            True if a recent (within TTL) hook event exists for this session.
        """
        try:
            pattern = f"/tmp/ctb-events-{session_name}-*.json"
            now = time.time()
            for fpath in glob.glob(pattern):
                try:
                    if now - os.path.getmtime(fpath) > self._HOOK_EVENT_TTL:
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        event = json.load(f)
                    ts_str = event.get("timestamp_iso", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                        if now - ts.timestamp() <= self._HOOK_EVENT_TTL:
                            return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _gc_hook_events(self, session_name: str) -> None:
        """90s 초과 hook 이벤트 파일을 삭제합니다 (GC)."""
        try:
            now = time.time()
            for fpath in glob.glob(f"/tmp/ctb-events-{session_name}-*.json"):
                try:
                    if now - os.path.getmtime(fpath) > self._HOOK_EVENT_GC_TTL:
                        os.unlink(fpath)
                except Exception:
                    pass
        except Exception:
            pass

    def _is_hook_supported(self, session_name: str) -> bool:
        """이 세션이 hook 이벤트를 지원하는지 확인합니다."""
        flag_path = os.path.join(".omc", "state", "sessions", session_name, "hook_supported")
        return os.path.exists(flag_path)

    def _get_net_established(self, claude_pid: int) -> int:
        """claude 프로세스의 api.anthropic.com:443 ESTABLISHED 연결 수를 반환합니다."""
        try:
            result = subprocess.run(
                ["ss", "-tnp", f"pid,{claude_pid}"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            count = 0
            for line in result.stdout.splitlines():
                if "ESTAB" in line and ":443" in line:
                    count += 1
            if count > 0 or result.returncode == 0:
                return count
        except Exception:
            pass

        # /proc 폴백
        try:
            tcp_file = f"/proc/{claude_pid}/net/tcp6"
            if not os.path.exists(tcp_file):
                tcp_file = f"/proc/{claude_pid}/net/tcp"
            count = 0
            with open(tcp_file, "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[3] == "0A":
                        # ESTABLISHED(0x0A), 원격 포트 443 = 0x01BB
                        remote = parts[2]
                        remote_port = int(remote.split(":")[1], 16) if ":" in remote else 0
                        if remote_port == 443:
                            count += 1
            return count
        except Exception:
            pass
        return 0

    def _log_stall_baseline(
        self,
        session_name: str,
        bash_child_exists: bool,
        net_established: int,
        screen_state: str,
        stall_fired: bool,
    ) -> None:
        """Log stall check signals for baseline measurement."""
        try:
            log_dir = ".omc/logs"
            os.makedirs(log_dir, exist_ok=True)
            now = datetime.utcnow()
            log_path = os.path.join(log_dir, f"stall-baseline-{now.strftime('%Y-%m-%d')}.jsonl")
            entry = {
                "timestamp": now.isoformat() + "Z",
                "session_id": session_name,
                "bash_child_exists": bash_child_exists,
                "net_established": net_established,
                "screen_state": screen_state,
                "stall_fired": stall_fired,
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug(f"stall baseline log failed: {exc}")

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
                        # Session recovered — clear retry state and resume work
                        recovered_state = self.overload_retry_states[session_name]
                        recovered_state.mark_recovered()
                        del self.overload_retry_states[session_name]
                        # Notify and re-send saved prompt: retries during rate limit
                        # were blocked, so explicitly resume now that limit is lifted.
                        elapsed_min = recovered_state.elapsed / 60
                        resume_prompt = recovered_state.saved_prompt
                        logger.info(
                            f"✅ {session_name}: rate limit lifted after "
                            f"{elapsed_min:.1f}min — resuming with saved prompt"
                        )
                        try:
                            subprocess.run(
                                ["tmux", "send-keys", "-t", session_name,
                                 resume_prompt, "Enter"],
                                timeout=5, check=False,
                            )
                        except Exception as e:
                            logger.warning(
                                f"tmux send-keys (rate limit recovery) failed "
                                f"for {session_name}: {e}"
                            )
                        self.notifier.send_notification_sync(
                            f"✅ *{session_name}* Rate limit 해제\n"
                            f"{elapsed_min:.1f}분 경과 후 복구 — 작업 재개 신호 전송"
                        )
                    # --- end overload retry ---

                    # Check for screen changes
                    screen_changed = self.has_screen_changed(session_name)
                    if screen_changed:
                        logger.debug(f"📺 Screen changed in {session_name}")

                    # Snapshot state BEFORE notification check
                    prev_state_snapshot = self.last_state.get(session_name)

                    # Check completion notification — updates last_state
                    try:
                        should_notify, task_completion = self.should_send_completion_notification(session_name)
                    finally:
                        curr_state_now = self.last_state.get(session_name, SessionState.UNKNOWN)

                    if should_notify:
                        logger.info(f"🎯 Sending completion notification for {session_name}")
                        self.send_completion_notification(session_name, task_completion)
                        self.last_activity_time[session_name] = time.time()

                        # T028: Persist state after notification
                        current_hash = self.last_screen_hash.get(session_name, "")
                        self.save_persisted_state(
                            session_name,
                            current_hash,
                            curr_state_now,
                            notification_sent=True
                        )

                    # State change logging
                    if prev_state_snapshot is not None and prev_state_snapshot != curr_state_now:
                        logger.info(f"🔄 {session_name}: {prev_state_snapshot} → {curr_state_now}")
                        self.debugger.log_state_change(
                            session_name, prev_state_snapshot, curr_state_now,
                            "Monitor loop state change"
                        )
                        if hasattr(self.tracker, 'mark_state_transition'):
                            state_name = 'working' if curr_state_now in (SessionState.WORKING, SessionState.SCHEDULED) else 'waiting'
                            self.tracker.mark_state_transition(session_name, state_name)

                    # error auto-resume: set timer on WORKING→ERROR transition
                    if (prev_state_snapshot != SessionState.ERROR
                            and curr_state_now == SessionState.ERROR
                            and session_name not in self._error_detected_at):
                        with self.thread_lock:
                            self._error_detected_at[session_name] = time.time()
                            self._error_auto_resume_count.setdefault(session_name, 0)
                        logger.info(
                            f"⚠️ {session_name}: Error Detected — "
                            f"will auto-resume in 90s if still idle"
                        )

                    # Clear error auto-resume state when no longer in ERROR
                    if (session_name in self._error_detected_at
                            and curr_state_now != SessionState.ERROR):
                        self._error_detected_at.pop(session_name, None)
                        self._error_auto_resume_count.pop(session_name, None)

                    # Resume actions (stuck/stall/post-C-c/error/working-stall)
                    # Now uses fresh curr_state_now — no 1-cycle stale lag
                    self._check_resume_actions(session_name, curr_state_now, prev_state_snapshot)

                    # e006: Update shared session state for web dashboard
                    self.shared_state.update_session(session_name, {
                        "state": curr_state_now.value,
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

                # e023: Clean up ticket-done dedup flag
                self._ticket_done_notified.pop(session_name, None)

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