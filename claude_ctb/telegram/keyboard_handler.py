"""
텔레그램 키보드 입력 처리 모듈

하단 상시 키보드에서 오는 텍스트 메시지를 분석하고 적절한 동작을 수행합니다.
"""

import logging
import re
from typing import Optional
from ..utils.session_state import SessionStateAnalyzer
from ..utils.log_length_manager import get_current_log_length
from .notifier import SmartNotifier

logger = logging.getLogger(__name__)


class KeyboardHandler:
    """키보드 입력 처리 핸들러"""
    
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
        
        # 키보드 버튼 패턴 매핑
        self.button_patterns = {
            # 세션 버튼 패턴 (아이콘 + 세션명)
            r'^[⭐💤⚒️⏸️❌❓]\s*(.+)$': self.handle_session_selection,
            
            # 제어 버튼 패턴
            r'^🔄\s*새로고침$': self.handle_refresh,
            r'^📊\s*상태$': self.handle_status,
            r'^⚙️\s*설정$': self.handle_settings,
        }
    
    def process_keyboard_input(self, message_text: str, notifier: SmartNotifier) -> bool:
        """
        키보드 입력 처리
        
        Args:
            message_text: 텔레그램에서 받은 메시지 텍스트
            notifier: 응답 전송용 노티파이어
            
        Returns:
            bool: 처리 여부
        """
        message_text = message_text.strip()
        
        # 각 패턴과 매칭 시도
        for pattern, handler in self.button_patterns.items():
            match = re.match(pattern, message_text)
            if match:
                try:
                    response = handler(match, message_text)
                    if response:
                        # 즉시 응답 전송
                        notifier.send_notification_sync(response, force=True)
                        logger.info(f"Processed keyboard input: {message_text} -> {response[:50]}...")
                        return True
                except Exception as e:
                    logger.error(f"Error handling keyboard input '{message_text}': {e}")
                    error_response = f"❌ 처리 중 오류가 발생했습니다: {e}"
                    notifier.send_notification_sync(error_response, force=True)
                    return True
        
        return False  # 키보드 입력이 아님
    
    def handle_session_selection(self, match: re.Match, original_text: str) -> str:
        """세션 선택 처리"""
        session_display_name = match.group(1).strip()
        
        # 표시명을 실제 세션명으로 변환
        session_name = self._find_session_by_display_name(session_display_name)
        
        if not session_name:
            return f"❌ '{session_display_name}' 세션을 찾을 수 없습니다."
        
        # 세션 상태 확인
        try:
            current_state = self.state_analyzer.get_state(session_name)
            is_working = self.state_analyzer.is_working(session_name)
            
            # 상태 아이콘 결정
            if current_state.name == "WORKING":
                status_icon = "⚒️"
                status_text = "작업 중"
            elif current_state.name == "WAITING_INPUT":
                status_icon = "⏸️"
                status_text = "입력 대기"
            elif current_state.name == "IDLE":
                status_icon = "💤"
                status_text = "유휴 상태"
            elif current_state.name == "ERROR":
                status_icon = "❌"
                status_text = "오류 상태"
            else:
                status_icon = "❓"
                status_text = "알 수 없음"
            
            response = f"""🎯 **세션 선택: {session_display_name}**

{status_icon} **현재 상태**: {status_text}
🎛️ **세션명**: `{session_name}`
⏰ **확인 시간**: {self._get_current_time()}

💡 이 세션으로 전환하려면 해당 tmux 세션에 접속하세요."""
            
            return response
            
        except Exception as e:
            return f"❌ '{session_display_name}' 세션 상태 확인 실패: {e}"
    
    def handle_refresh(self, match: re.Match, original_text: str) -> str:
        """새로고침 처리"""
        try:
            # 모든 Claude 세션 발견
            sessions = self._discover_sessions()
            
            if not sessions:
                return "📊 **세션 새로고침**\n\n❌ 활성 Claude 세션이 없습니다."
            
            # 각 세션 상태 확인
            session_status = []
            for session in sessions:
                try:
                    state = self.state_analyzer.get_state(session)
                    display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                    
                    if state.name == "WORKING":
                        icon = "⚒️"
                    elif state.name == "WAITING_INPUT":
                        icon = "⏸️"
                    elif state.name == "IDLE":
                        icon = "💤"
                    elif state.name == "ERROR":
                        icon = "❌"
                    else:
                        icon = "❓"
                    
                    session_status.append(f"{icon} {display_name}")
                    
                except Exception:
                    session_status.append(f"❓ {display_name} (오류)")
            
            status_text = '\n'.join(session_status)
            
            response = f"""🔄 **세션 새로고침** ({self._get_current_time()})

📊 **발견된 세션**: {len(sessions)}개

{status_text}

💡 버튼을 다시 클릭하면 최신 상태를 확인할 수 있습니다."""
            
            return response
            
        except Exception as e:
            return f"🔄 **새로고침 실패**\n\n❌ 오류: {e}"
    
    def handle_status(self, match: re.Match, original_text: str) -> str:
        """상태 확인 처리"""
        try:
            sessions = self._discover_sessions()
            log_length = get_current_log_length()
            
            if not sessions:
                return "📊 **시스템 상태**\n\n❌ 활성 Claude 세션이 없습니다."
            
            # 상태별 세션 분류
            working_sessions = []
            idle_sessions = []
            waiting_sessions = []
            error_sessions = []
            unknown_sessions = []
            
            # Import summary helper for wait times
            from ..utils.session_summary import summary_helper
            
            for session in sessions:
                try:
                    state = self.state_analyzer.get_state(session)
                    display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                    
                    # Get wait time if applicable
                    wait_time = summary_helper.get_session_wait_time(session)
                    if wait_time:
                        wait_str = f" ({summary_helper.format_wait_time(wait_time)})"
                    else:
                        wait_str = ""
                    
                    if state.name == "WORKING":
                        working_sessions.append(display_name)
                    elif state.name == "WAITING_INPUT":
                        waiting_sessions.append(f"{display_name}{wait_str}")
                    elif state.name == "IDLE":
                        idle_sessions.append(f"{display_name}{wait_str}")
                    elif state.name == "ERROR":
                        error_sessions.append(display_name)
                    else:
                        unknown_sessions.append(display_name)
                        
                except Exception:
                    unknown_sessions.append(display_name)
            
            # 상태 요약 생성
            status_lines = []
            
            if working_sessions:
                status_lines.append(f"⚒️ **작업 중**: {', '.join(working_sessions)}")
            if waiting_sessions:
                status_lines.append(f"⏸️ **입력 대기**: {', '.join(waiting_sessions)}")
            if idle_sessions:
                status_lines.append(f"💤 **유휴**: {', '.join(idle_sessions)}")
            if error_sessions:
                status_lines.append(f"❌ **오류**: {', '.join(error_sessions)}")
            if unknown_sessions:
                status_lines.append(f"❓ **알 수 없음**: {', '.join(unknown_sessions)}")
            
            status_summary = '\n'.join(status_lines) if status_lines else "모든 세션이 정상 상태입니다."
            
            response = f"""📊 **시스템 상태** ({self._get_current_time()})

🎛️ **총 세션**: {len(sessions)}개
📏 **로그 길이**: {log_length}줄

{status_summary}

💡 세션 버튼을 클릭하면 개별 상태를 확인할 수 있습니다."""
            
            return response
            
        except Exception as e:
            return f"📊 **상태 확인 실패**\n\n❌ 오류: {e}"
    
    def handle_settings(self, match: re.Match, original_text: str) -> str:
        """설정 확인 처리"""
        try:
            log_length = get_current_log_length()
            sessions = self._discover_sessions()
            
            response = f"""⚙️ **시스템 설정** ({self._get_current_time()})

📏 **로그 길이**: {log_length}줄
🎛️ **모니터링 세션**: {len(sessions)}개
🔄 **상시 패널**: 활성화됨 (하단 키보드)

**📱 CLI 도구 사용법:**

로그 길이 조절:
`python -m claude_ctb.cli.log_length_cli --cycle`
`python -m claude_ctb.cli.log_length_cli --set 300`

패널 관리:
`python -m claude_ctb.cli.panel_cli --config`
`python -m claude_ctb.cli.panel_cli --list`

💡 설정 변경 후 🔄 새로고침으로 상태를 확인하세요."""
            
            return response
            
        except Exception as e:
            return f"⚙️ **설정 확인 실패**\n\n❌ 오류: {e}"
    
    def _find_session_by_display_name(self, display_name: str) -> Optional[str]:
        """표시명으로 실제 세션명 찾기"""
        try:
            sessions = self._discover_sessions()
            
            for session in sessions:
                session_display = session.replace('claude_', '') if session.startswith('claude_') else session
                if session_display == display_name:
                    return session
                    
            return None
            
        except Exception:
            return None
    
    def _discover_sessions(self) -> list[str]:
        """Claude 세션 발견"""
        import subprocess
        
        try:
            result = subprocess.run(
                "tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^claude_' || true",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
                return sessions
            else:
                return []
                
        except Exception:
            return []
    
    def _get_current_time(self) -> str:
        """현재 시간 반환"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")


# 전역 핸들러 인스턴스
keyboard_handler = KeyboardHandler()