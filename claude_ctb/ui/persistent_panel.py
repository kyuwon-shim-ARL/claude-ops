"""
텔레그램 InlineKeyboard 다단 액션 패널

InlineKeyboard 방식으로 메인 세션 패널과 세션별 액션 메뉴를 제공합니다.
사용자는 버튼 클릭으로 세션 선택 → 액션 수행의 다단 워크플로우 사용이 가능합니다.
"""

import logging
import subprocess
from typing import List, Dict, Optional, Any
from datetime import datetime
from ..utils.session_state import SessionStateAnalyzer, SessionState
from .ui_state_manager import ui_state_manager

logger = logging.getLogger(__name__)


class SessionInfo:
    """세션 정보 데이터 클래스"""
    
    def __init__(self, name: str, is_active: bool = False, 
                 last_activity: Optional[datetime] = None,
                 working_state: str = "unknown"):
        self.name = name
        self.is_active = is_active
        self.last_activity = last_activity or datetime.now()
        self.working_state = working_state
        self.display_name = self._get_display_name()
    
    def _get_display_name(self) -> str:
        """세션 표시 이름 생성 (claude_ 접두사 제거)"""
        if self.name.startswith('claude_'):
            return self.name[7:]  # 'claude_' 제거
        return self.name
    
    def get_status_icon(self) -> str:
        """세션 상태 아이콘 반환"""
        if self.is_active:
            return "⭐"  # 활성 세션 (최우선)
        elif self.working_state == "error":
            return "❌"  # 오류 상태
        elif self.working_state == "working":
            return "⚒️"  # 작업 중
        elif self.working_state == "waiting":
            return "⏸️"  # 입력 대기
        elif self.working_state == "idle":
            return "💤"  # 유휴 상태
        else:
            return "❓"  # 알 수 없음
    
    def get_button_text(self) -> str:
        """버튼에 표시될 텍스트 반환"""
        icon = self.get_status_icon()
        return f"{icon} {self.display_name}"


class PersistentSessionPanel:
    """InlineKeyboard 기반 다단 액션 패널 관리자"""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        InlineKeyboard 패널 관리자 초기화
        
        Args:
            bot_token: 텔레그램 봇 토큰
            chat_id: 채팅 ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.panel_message_id: Optional[int] = None
        self.sessions: Dict[str, SessionInfo] = {}
        self.active_session: Optional[str] = None
        self.state_analyzer = SessionStateAnalyzer()  # 실시간 세션 상태 감지
        
        # UI 상태 관리자와 액션 핸들러
        ui_state_manager.set_chat_id(chat_id)
        
        # 패널 설정
        self.max_sessions_per_row = 3  # InlineKeyboard는 더 많은 버튼 가능
        self.max_rows = 2
        self.max_sessions = self.max_sessions_per_row * self.max_rows  # 최대 6개 세션
    
    async def discover_sessions(self) -> List[str]:
        """
        Claude 세션들을 자동 발견
        
        Returns:
            List[str]: 발견된 세션 이름들
        """
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
                logger.info(f"Discovered {len(sessions)} Claude sessions: {sessions}")
                return sessions
            else:
                logger.warning("No Claude sessions found or tmux not available")
                return []
                
        except Exception as e:
            logger.error(f"Error discovering sessions: {e}")
            return []
    
    def update_session_info(self, session_name: str, is_active: bool = False,
                          working_state: str = "unknown") -> None:
        """
        세션 정보 업데이트
        
        Args:
            session_name: 세션 이름
            is_active: 활성 세션 여부
            working_state: 작업 상태 (working, waiting, idle, unknown)
        """
        if session_name not in self.sessions:
            self.sessions[session_name] = SessionInfo(session_name)
        
        session_info = self.sessions[session_name]
        session_info.is_active = is_active
        session_info.working_state = working_state
        session_info.last_activity = datetime.now()
        
        if is_active:
            # 이전 활성 세션 비활성화
            if self.active_session and self.active_session != session_name:
                if self.active_session in self.sessions:
                    self.sessions[self.active_session].is_active = False
            
            self.active_session = session_name
    
    def _detect_real_time_states(self) -> None:
        """실시간 세션 상태 감지 및 업데이트"""
        for session_name in self.sessions.keys():
            try:
                # SessionStateAnalyzer로 실제 상태 확인
                current_state = self.state_analyzer.get_state(session_name)
                
                # SessionState enum을 문자열로 변환
                if current_state == SessionState.WORKING:
                    working_state = "working"
                elif current_state == SessionState.WAITING_INPUT:
                    working_state = "waiting"
                elif current_state == SessionState.IDLE:
                    working_state = "idle"
                elif current_state == SessionState.ERROR:
                    working_state = "error"
                else:
                    working_state = "unknown"
                
                # 세션 정보 업데이트 (활성 상태는 유지)
                session_info = self.sessions[session_name]
                session_info.working_state = working_state
                session_info.last_activity = datetime.now()
                
            except Exception as e:
                logger.debug(f"Failed to detect state for {session_name}: {e}")
                # 실패 시 기본 상태 유지
    
    def _create_inline_keyboard(self) -> Dict[str, Any]:
        """
        인라인 키보드 생성
        
        Returns:
            Dict: 텔레그램 인라인 키보드 구조
        """
        # 세션을 최근 활동 순으로 정렬
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: (x[1].is_active, x[1].last_activity),
            reverse=True
        )
        
        # 최대 표시 개수 제한
        display_sessions = sorted_sessions[:self.max_sessions]
        
        # 키보드 버튼들 생성
        keyboard = []
        
        # 세션 버튼들을 행별로 배치
        for i in range(0, len(display_sessions), self.max_sessions_per_row):
            row = []
            for j in range(self.max_sessions_per_row):
                idx = i + j
                if idx < len(display_sessions):
                    session_name, session_info = display_sessions[idx]
                    button_text = session_info.get_button_text()
                    
                    row.append({
                        "text": button_text,
                        "callback_data": f"session:{session_name}"
                    })
            
            if row:
                keyboard.append(row)
        
        # 추가 제어 버튼들
        control_row = [
            {"text": "🔄 새로고침", "callback_data": "refresh"},
            {"text": "📊 상태", "callback_data": "status"},
            {"text": "⚙️ 설정", "callback_data": "settings"}
        ]
        keyboard.append(control_row)
        
        return {"inline_keyboard": keyboard}
    
    def _create_panel_text(self) -> str:
        """
        패널 메시지 텍스트 생성
        
        Returns:
            str: 패널 메시지 텍스트
        """
        current_time = datetime.now().strftime("%H:%M:%S")
        
        text = f"""🎛️ **Claude 세션 패널** ({current_time})

⭐ 활성  ⚒️ 작업중  ⏸️ 대기  💤 유휴  ❌ 오류  ❓ 알수없음

"""
        
        if not self.sessions:
            text += "세션을 검색하는 중..."
        else:
            # 활성 세션 정보 표시
            if self.active_session and self.active_session in self.sessions:
                active_info = self.sessions[self.active_session]
                text += f"**현재 활성:** {active_info.get_button_text()}\n"
            
            text += f"**총 세션:** {len(self.sessions)}개"
        
        return text
    
    async def send_initial_panel(self) -> Optional[int]:
        """
        초기 패널 메시지 전송
        
        Returns:
            Optional[int]: 메시지 ID (실패 시 None)
        """
        try:
            import requests
            
            # 세션 자동 발견
            session_names = await self.discover_sessions()
            
            # 세션 정보 초기화
            for session_name in session_names:
                self.update_session_info(session_name)
            
            # 패널 메시지 생성
            text = self._create_panel_text()
            keyboard = self._create_inline_keyboard()
            
            # 텔레그램으로 전송
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    message_id = result["result"]["message_id"]
                    self.panel_message_id = message_id
                    logger.info(f"Persistent panel sent successfully: message_id={message_id}")
                    return message_id
                else:
                    logger.error(f"Telegram API error: {result}")
                    return None
            else:
                logger.error(f"HTTP error sending panel: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending persistent panel: {e}")
            return None
    
    async def update_panel(self) -> bool:
        """
        기존 패널 업데이트
        
        Returns:
            bool: 업데이트 성공 여부
        """
        if not self.panel_message_id:
            logger.warning("No panel message ID available for update")
            return False
        
        try:
            import requests
            
            # 세션 정보 갱신
            session_names = await self.discover_sessions()
            
            # 새로운 세션들 추가
            for session_name in session_names:
                if session_name not in self.sessions:
                    self.update_session_info(session_name)
            
            # 없어진 세션들 제거
            existing_sessions = set(self.sessions.keys())
            current_sessions = set(session_names)
            removed_sessions = existing_sessions - current_sessions
            
            for session_name in removed_sessions:
                del self.sessions[session_name]
                if self.active_session == session_name:
                    self.active_session = None
            
            # 실시간 상태 감지 및 업데이트
            self._detect_real_time_states()
            
            # 패널 메시지 생성
            text = self._create_panel_text()
            keyboard = self._create_inline_keyboard()
            
            # 텔레그램으로 업데이트
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": self.panel_message_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info("Persistent panel updated successfully")
                    return True
                else:
                    logger.error(f"Telegram API error updating panel: {result}")
                    return False
            else:
                logger.error(f"HTTP error updating panel: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating persistent panel: {e}")
            return False
    
    async def handle_callback(self, callback_data: str) -> str:
        """
        콜백 버튼 처리
        
        Args:
            callback_data: 콜백 데이터
            
        Returns:
            str: 응답 메시지
        """
        try:
            if callback_data.startswith("session:"):
                session_name = callback_data.split(":", 1)[1]
                return await self._handle_session_selection(session_name)
            
            elif callback_data == "refresh":
                success = await self.update_panel()
                return "🔄 패널이 새로고침되었습니다!" if success else "❌ 새로고침 실패"
            
            elif callback_data == "status":
                return self._get_status_summary()
            
            elif callback_data == "settings":
                return self._get_settings_info()
            
            else:
                return f"❓ 알 수 없는 명령: {callback_data}"
                
        except Exception as e:
            logger.error(f"Error handling callback {callback_data}: {e}")
            return f"❌ 처리 중 오류 발생: {e}"
    
    async def _handle_session_selection(self, session_name: str) -> str:
        """
        세션 선택 처리
        
        Args:
            session_name: 선택된 세션 이름
            
        Returns:
            str: 응답 메시지
        """
        if session_name not in self.sessions:
            return f"❌ 세션을 찾을 수 없습니다: {session_name}"
        
        # 활성 세션으로 설정
        self.update_session_info(session_name, is_active=True)
        
        # 패널 업데이트
        await self.update_panel()
        
        session_info = self.sessions[session_name]
        return f"⭐ 활성 세션이 '{session_info.display_name}'로 변경되었습니다."
    
    def _get_status_summary(self) -> str:
        """상태 요약 정보 반환"""
        if not self.sessions:
            return "📊 등록된 세션이 없습니다."
        
        summary = "📊 **세션 상태 요약**\n\n"
        
        for session_name, session_info in self.sessions.items():
            icon = session_info.get_status_icon()
            activity_time = session_info.last_activity.strftime("%H:%M:%S")
            
            summary += f"{icon} {session_info.display_name} ({activity_time})\n"
        
        if self.active_session:
            active_display = self.sessions[self.active_session].display_name
            summary += f"\n⭐ **활성 세션:** {active_display}"
        
        return summary
    
    def _get_settings_info(self) -> str:
        """설정 정보 반환"""
        from ..utils.log_length_manager import get_current_log_length
        
        log_length = get_current_log_length()
        
        return f"""⚙️ **패널 설정**

📏 로그 길이: {log_length}줄
📱 최대 세션: {self.max_sessions}개
📊 행당 버튼: {self.max_sessions_per_row}개
🔄 업데이트: 자동

설정 변경은 CLI 도구를 사용하세요:
`python -m claude_ctb.cli.log_length_cli --help`"""


# 편의 함수들

async def create_persistent_panel(bot_token: str, chat_id: str) -> Optional[PersistentSessionPanel]:
    """
    편의 함수: 상시 패널 생성 및 전송
    
    Args:
        bot_token: 텔레그램 봇 토큰
        chat_id: 채팅 ID
        
    Returns:
        Optional[PersistentSessionPanel]: 생성된 패널 (실패 시 None)
    """
    try:
        panel = PersistentSessionPanel(bot_token, chat_id)
        message_id = await panel.send_initial_panel()
        
        if message_id:
            return panel
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error creating persistent panel: {e}")
        return None