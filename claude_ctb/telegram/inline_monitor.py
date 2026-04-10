"""
InlineKeyboard 기반 텔레그램 모니터링 시스템

기존 multi_monitor와 InlineKeyboard 다단 액션 패널을 통합한 모니터링 시스템
"""

import os
import time
import logging
import asyncio
import threading
from typing import Dict, Set, Optional
from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from ..utils.session_state import SessionStateAnalyzer, SessionState
from .notifier import SmartNotifier
from .inline_panel import InlineSessionPanel

logger = logging.getLogger(__name__)


class InlineMonitoringSystem:
    """InlineKeyboard 기반 통합 모니터링 시스템"""
    
    def __init__(self, config: ClaudeOpsConfig = None):
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.state_analyzer = SessionStateAnalyzer()
        
        # InlineKeyboard 패널
        self.panel: Optional[InlineSessionPanel] = None
        
        # 기존 모니터링 상태 추적
        self.last_screen_hash: Dict[str, str] = {}
        self.last_activity_time: Dict[str, float] = {}
        self.notification_sent: Dict[str, bool] = {}
        self.last_state: Dict[str, SessionState] = {}
        self.last_notification_time: Dict[str, float] = {}
        self.active_threads: Dict[str, threading.Thread] = {}
        self.thread_lock = threading.Lock()
        self.running = False
        self.timeout_seconds = 45
        
        # 패널 업데이트 간격
        self.panel_update_interval = 30  # 30초마다 패널 업데이트
        self.last_panel_update = 0
    
    async def initialize_panel(self) -> bool:
        """InlineKeyboard 패널 초기화"""
        try:
            if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
                logger.error("Telegram 설정이 없어 패널을 초기화할 수 없습니다.")
                return False
            
            # 패널 생성
            self.panel = InlineSessionPanel(
                self.config.telegram_bot_token, 
                self.config.telegram_chat_id
            )
            
            # 패널 시작
            success = await self.panel.start_panel()
            
            if success:
                logger.info(f"✅ InlineKeyboard 패널이 초기화되었습니다. (메시지 ID: {self.panel.panel_message_id})")
            else:
                logger.error("❌ InlineKeyboard 패널 초기화에 실패했습니다.")
            
            return success
            
        except Exception as e:
            logger.error(f"패널 초기화 중 오류: {e}")
            return False
    
    async def sync_panel_with_monitoring_data(self):
        """모니터링 데이터와 패널 동기화"""
        try:
            if not self.panel:
                return
            
            # 현재 발견된 세션들 가져오기
            current_sessions = set(session_manager.get_all_claude_sessions())
            
            # 패널에 세션 추가/업데이트
            for session_name in current_sessions:
                try:
                    # 세션 상태 감지
                    current_state = self.state_analyzer.get_state(session_name)
                    
                    # SessionState enum을 문자열로 변환
                    if current_state in (SessionState.WORKING, SessionState.SCHEDULED):
                        state_str = "working"
                    elif current_state == SessionState.WAITING_INPUT:
                        state_str = "waiting"
                    elif current_state == SessionState.IDLE:
                        state_str = "idle"
                    elif current_state in (SessionState.ERROR, SessionState.OVERLOADED, SessionState.CONTEXT_LIMIT):
                        state_str = "error"
                    else:
                        state_str = "unknown"
                    
                    # 패널에 세션 정보 업데이트
                    self.panel.update_session_info(session_name, working_state=state_str)
                    
                except Exception as e:
                    logger.debug(f"세션 {session_name} 상태 동기화 실패: {e}")
            
            # 없어진 세션들은 패널에서 제거
            panel_sessions = set(self.panel.sessions.keys())
            disappeared_sessions = panel_sessions - current_sessions
            
            for session_name in disappeared_sessions:
                if session_name in self.panel.sessions:
                    del self.panel.sessions[session_name]
                    logger.info(f"패널에서 사라진 세션 제거: {session_name}")
            
            # 패널 업데이트
            await self.panel.update_panel()
            
        except Exception as e:
            logger.error(f"패널 동기화 중 오류: {e}")
    
    def discover_sessions(self) -> Set[str]:
        """모든 활성 Claude 세션 발견"""
        return set(session_manager.get_all_claude_sessions())
    
    def get_status_file_for_session(self, session_name: str) -> str:
        """세션의 상태 파일 경로 가져오기"""
        return session_manager.get_status_file_for_session(session_name)
    
    def get_session_state(self, session_name: str) -> SessionState:
        """현재 세션 상태 가져오기"""
        return self.state_analyzer.get_state(session_name)
    
    def get_screen_content_hash(self, session_name: str) -> str:
        """화면 내용 해시 가져오기"""
        import subprocess
        import hashlib
        
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
                
            content = result.stdout.strip()
            return hashlib.md5(content.encode()).hexdigest()
            
        except Exception as e:
            logger.debug(f"Failed to get screen content hash for {session_name}: {e}")
            return ""
    
    def has_screen_changed(self, session_name: str) -> bool:
        """화면 내용 변경 여부 확인"""
        current_hash = self.get_screen_content_hash(session_name)
        
        if not current_hash:
            return False
            
        last_hash = self.last_screen_hash.get(session_name, "")
        
        if current_hash != last_hash:
            self.last_screen_hash[session_name] = current_hash
            self.last_activity_time[session_name] = time.time()
            return True
            
        return False
    
    def should_send_completion_notification(self, session_name: str) -> bool:
        """완료 알림 전송 여부 결정"""
        current_state = self.get_session_state(session_name)
        previous_state = self.last_state.get(session_name, SessionState.UNKNOWN)
        
        # 상태 업데이트
        self.last_state[session_name] = current_state
        
        # 작업 중이면 알림 플래그 리셋
        if current_state == SessionState.WORKING:
            self.notification_sent[session_name] = False
            self.last_activity_time[session_name] = time.time()
            return False
        
        # 중복 알림 방지
        if self.notification_sent.get(session_name, False):
            return False
        
        # 쿨다운 확인
        current_time = time.time()
        last_notification_time = self.last_notification_time.get(session_name, 0)
        
        if current_time - last_notification_time < 30:
            return False
        
        # 알림 조건: WORKING에서 완료되거나 WAITING_INPUT 상태
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
    
    def send_completion_notification(self, session_name: str):
        """완료 알림 전송"""
        try:
            original_session = session_manager.get_active_session()
            session_manager.switch_session(session_name)
            
            session_notifier = SmartNotifier(self.config)
            success = session_notifier.send_work_completion_notification()
            
            session_manager.switch_session(original_session)
            
            if success:
                logger.info(f"✅ Sent completion notification for session: {session_name}")
            else:
                logger.debug(f"⏭️ Skipped notification for session: {session_name}")
                
        except Exception as e:
            logger.error(f"Error sending completion notification for {session_name}: {e}")
    
    def monitor_session(self, session_name: str, status_file: str):
        """단일 세션 모니터링"""
        try:
            # 세션 추적 초기화
            with self.thread_lock:
                self.last_screen_hash[session_name] = ""
                self.last_activity_time[session_name] = time.time()
                self.notification_sent[session_name] = False
                self.last_state[session_name] = SessionState.UNKNOWN
                self.last_notification_time[session_name] = 0
            
            logger.info(f"📊 Started monitoring for {session_name}")
            
            while self.running:
                try:
                    # 세션 존재 확인
                    if not self.session_exists(session_name):
                        logger.info(f"📤 Session {session_name} no longer exists, stopping monitor")
                        break
                    
                    # 화면 변경 확인
                    screen_changed = self.has_screen_changed(session_name)
                    
                    # 완료 알림 확인
                    if self.should_send_completion_notification(session_name):
                        logger.info(f"🎯 Sending completion notification for {session_name}")
                        self.send_completion_notification(session_name)
                    
                    # 대기
                    time.sleep(self.config.check_interval)
                    
                except Exception as e:
                    logger.error(f"Error monitoring session {session_name}: {e}")
                    time.sleep(self.config.check_interval)
        
        finally:
            # 정리
            logger.info(f"🧹 Monitor thread for {session_name} is exiting")
            with self.thread_lock:
                for data_dict in [self.last_screen_hash, self.last_activity_time,
                                self.notification_sent, self.last_state, self.last_notification_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
                if session_name in self.active_threads:
                    del self.active_threads[session_name]
    
    def session_exists(self, session_name: str) -> bool:
        """세션 존재 여부 확인"""
        result = os.system(f"tmux has-session -t {session_name} 2>/dev/null")
        return result == 0
    
    def start_session_thread(self, session_name: str) -> bool:
        """세션 모니터링 스레드 시작"""
        with self.thread_lock:
            if session_name in self.active_threads:
                existing_thread = self.active_threads[session_name]
                if existing_thread.is_alive():
                    return False
                else:
                    del self.active_threads[session_name]
            
            status_file = self.get_status_file_for_session(session_name)
            logger.info(f"📊 Starting thread for session: {session_name}")
            
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
        """죽은 스레드 정리"""
        with self.thread_lock:
            dead_sessions = []
            for session_name, thread in self.active_threads.items():
                if not thread.is_alive():
                    dead_sessions.append(session_name)
            
            for session_name in dead_sessions:
                del self.active_threads[session_name]
                for data_dict in [self.last_screen_hash, self.last_activity_time,
                                self.notification_sent, self.last_state, self.last_notification_time]:
                    if session_name in data_dict:
                        del data_dict[session_name]
    
    async def start_monitoring(self):
        """모니터링 시작"""
        logger.info("🚀 Starting InlineKeyboard integrated monitoring...")
        self.running = True
        
        # InlineKeyboard 패널 초기화
        panel_success = await self.initialize_panel()
        if not panel_success:
            logger.warning("⚠️ 패널 초기화에 실패했지만 기본 모니터링은 계속합니다.")
        
        # 초기 세션들 발견 및 모니터링 스레드 시작
        active_sessions = self.discover_sessions()
        started_count = 0
        
        for session_name in active_sessions:
            if self.start_session_thread(session_name):
                started_count += 1
        
        if started_count == 0:
            logger.warning("❌ No Claude sessions found to monitor")
        else:
            logger.info(f"✅ Started monitoring {started_count} sessions: {list(active_sessions)}")
        
        # 메인 모니터링 루프
        while self.running:
            try:
                current_time = time.time()
                
                # 죽은 스레드 정리
                if current_time % 30 < 1:
                    self.cleanup_dead_threads()
                
                # 캐시 정리
                if current_time % 300 < 1:
                    self.state_analyzer.cleanup_expired_cache()
                
                # 패널 업데이트
                if (self.panel and 
                    current_time - self.last_panel_update > self.panel_update_interval):
                    
                    try:
                        await self.sync_panel_with_monitoring_data()
                        self.last_panel_update = current_time
                        logger.debug("🔄 Panel synchronized with monitoring data")
                    except Exception as e:
                        logger.error(f"패널 동기화 오류: {e}")
                
                # 새 세션 발견
                current_sessions = self.discover_sessions()
                monitored_sessions = set(self.active_threads.keys())
                new_sessions = current_sessions - monitored_sessions
                
                for session_name in new_sessions:
                    if self.session_exists(session_name):
                        if self.start_session_thread(session_name):
                            logger.info(f"🆕 New session detected and monitoring started: {session_name}")
                
                # 대기
                await asyncio.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("🛑 Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main monitoring loop: {e}")
                await asyncio.sleep(30)
        
        self.running = False
        logger.info("🏁 InlineKeyboard integrated monitoring stopped")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        logger.info("🛑 Stopping InlineKeyboard integrated monitoring...")
        self.running = False
        
        # 모든 스레드 정리
        with self.thread_lock:
            active_sessions = list(self.active_threads.keys())
        
        for session_name in active_sessions:
            thread = self.active_threads.get(session_name)
            if thread and thread.is_alive():
                thread.join(timeout=5)
        
        # 데이터 정리
        with self.thread_lock:
            self.active_threads.clear()
            self.last_screen_hash.clear()
            self.last_activity_time.clear()
            self.notification_sent.clear()
            self.last_state.clear()
            self.last_notification_time.clear()
        
        logger.info("✅ All monitoring stopped and cleaned up")


async def main():
    """메인 진입점"""
    try:
        config = ClaudeOpsConfig()
        monitor = InlineMonitoringSystem(config)
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Monitoring error: {e}")


if __name__ == "__main__":
    asyncio.run(main())