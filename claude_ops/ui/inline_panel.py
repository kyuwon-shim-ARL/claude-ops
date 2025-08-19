"""
텔레그램 InlineKeyboard 다단 액션 패널

InlineKeyboard 방식으로 메인 세션 패널과 세션별 액션 메뉴를 제공합니다.
사용자는 버튼 클릭으로 세션 선택 → 액션 수행의 다단 워크플로우 사용이 가능합니다.
"""

import logging
import asyncio
import subprocess
import requests
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from ..utils.session_state import SessionStateAnalyzer, SessionState
from .ui_state_manager import ui_state_manager, UIState
from .session_action_handlers import session_action_handlers

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


class InlineSessionPanel:
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
                logger.debug("No Claude sessions found or tmux error")
                return []
                
        except Exception as e:
            logger.error(f"Error discovering sessions: {e}")
            return []
    
    def update_session_info(self, session_name: str, is_active: bool = False, working_state: str = "unknown"):
        """
        세션 정보 업데이트
        
        Args:
            session_name: 세션 이름
            is_active: 활성 세션 여부
            working_state: 작업 상태
        """
        if is_active and self.active_session != session_name:
            # 기존 활성 세션 비활성화
            if self.active_session and self.active_session in self.sessions:
                self.sessions[self.active_session].is_active = False
            
            # 새 활성 세션 설정
            self.active_session = session_name
        
        # 세션 정보 업데이트 또는 생성
        if session_name in self.sessions:
            session_info = self.sessions[session_name]
            session_info.is_active = is_active
            session_info.working_state = working_state
            session_info.last_activity = datetime.now()
        else:
            self.sessions[session_name] = SessionInfo(
                name=session_name,
                is_active=is_active,
                working_state=working_state
            )
    
    def _detect_real_time_states(self):
        """실시간 세션 상태 감지 및 업데이트"""
        try:
            for session_name in list(self.sessions.keys()):
                try:
                    # SessionStateAnalyzer를 사용하여 실시간 상태 감지
                    current_state = self.state_analyzer.get_state(session_name)
                    
                    # SessionState enum을 문자열로 변환
                    if current_state == SessionState.WORKING:
                        state_str = "working"
                    elif current_state == SessionState.WAITING_INPUT:
                        state_str = "waiting"
                    elif current_state == SessionState.IDLE:
                        state_str = "idle"
                    elif current_state == SessionState.ERROR:
                        state_str = "error"
                    else:
                        state_str = "unknown"
                    
                    # 세션 정보 업데이트 (활성 상태는 그대로 유지)
                    self.update_session_info(
                        session_name,
                        is_active=self.sessions[session_name].is_active,
                        working_state=state_str
                    )
                    
                except Exception as e:
                    logger.debug(f"Error detecting state for {session_name}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in real-time state detection: {e}")
    
    def _create_main_panel_text(self) -> str:
        """메인 패널 텍스트 생성"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 메인 세션 정보
        main_session_text = "없음"
        if ui_state_manager.main_session:
            main_session_info = self.sessions.get(ui_state_manager.main_session)
            if main_session_info:
                main_session_text = f"⭐ {main_session_info.display_name}"
        
        # 세션 개수
        total_sessions = len(self.sessions)
        working_count = sum(1 for s in self.sessions.values() if s.working_state == "working")
        
        text = f"""📊 **Claude-Ops 세션 관리** ({current_time})

🏠 **현재 메인**: {main_session_text}
🎛️ **총 세션**: {total_sessions}개 (작업중: {working_count}개)

💡 **사용법**: 세션 버튼 클릭 → 액션 선택

**아이콘 범례**:
⭐ 메인  ⚒️ 작업중  ⏸️ 대기  💤 유휴  ❌ 오류  ❓ 알수없음"""
        
        return text
    
    def _create_session_action_text(self, session_name: str) -> str:
        """세션 액션 메뉴 텍스트 생성"""
        session_info = self.sessions.get(session_name)
        if not session_info:
            return f"❌ '{session_name}' 세션 정보를 찾을 수 없습니다."
        
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # 상태 텍스트 생성
        state_texts = {
            "working": "⚒️ 작업 중",
            "waiting": "⏸️ 입력 대기",
            "idle": "💤 유휴 상태",
            "error": "❌ 오류 상태",
            "unknown": "❓ 알 수 없음"
        }
        status_text = state_texts.get(session_info.working_state, "❓ 알 수 없음")
        
        # 메인 세션 여부
        is_main = ui_state_manager.main_session == session_name
        main_text = " (현재 메인)" if is_main else ""
        
        text = f"""🎯 **{session_info.display_name} 세션 액션**{main_text}

📊 **현재 상태**: {status_text}
🎛️ **세션명**: `{session_name}`
🕐 **확인 시간**: {current_time}

💡 원하는 액션을 선택하세요"""
        
        return text
    
    def _create_main_panel_keyboard(self) -> Dict[str, Any]:
        """메인 패널 InlineKeyboard 생성"""
        keyboard = {"inline_keyboard": []}
        
        # 세션 버튼들 (메인 세션 우선)
        sessions = list(self.sessions.values())
        
        # 메인 세션을 맨 앞으로 정렬
        main_session_name = ui_state_manager.main_session
        if main_session_name:
            sessions.sort(key=lambda s: (s.name != main_session_name, s.display_name))
        else:
            sessions.sort(key=lambda s: s.display_name)
        
        # 세션을 최대 표시 개수로 제한
        sessions = sessions[:self.max_sessions]
        
        # 세션 버튼을 행으로 분할
        for i in range(0, len(sessions), self.max_sessions_per_row):
            row = []
            for session in sessions[i:i + self.max_sessions_per_row]:
                button = {
                    "text": session.get_button_text(),
                    "callback_data": f"session:{session.name}"
                }
                row.append(button)
            keyboard["inline_keyboard"].append(row)
        
        # 제어 버튼 행
        control_row = [
            {"text": "🔄 새로고침", "callback_data": "action:refresh"},
            {"text": "📊 전체상태", "callback_data": "action:status"},
            {"text": "⚙️ 설정", "callback_data": "action:settings"}
        ]
        keyboard["inline_keyboard"].append(control_row)
        
        return keyboard
    
    def _create_session_action_keyboard(self, session_name: str) -> Dict[str, Any]:
        """세션 액션 메뉴 InlineKeyboard 생성"""
        keyboard = {"inline_keyboard": []}
        
        # 첫 번째 행: 메인 세션 설정, 로그 보기
        first_row = [
            {"text": "🏠 메인세션 설정", "callback_data": f"action:set_main:{session_name}"},
            {"text": "📜 로그보기", "callback_data": f"action:logs:{session_name}"}
        ]
        keyboard["inline_keyboard"].append(first_row)
        
        # 두 번째 행: Pause, Erase
        second_row = [
            {"text": "⏸️ Pause (ESC)", "callback_data": f"action:pause:{session_name}"},
            {"text": "🗑️ Erase (Ctrl+C)", "callback_data": f"action:erase:{session_name}"}
        ]
        keyboard["inline_keyboard"].append(second_row)
        
        # 세 번째 행: 돌아가기
        back_row = [
            {"text": "◀️ 메인으로 돌아가기", "callback_data": "action:back_to_main"}
        ]
        keyboard["inline_keyboard"].append(back_row)
        
        return keyboard
    
    async def handle_callback(self, callback_data: str) -> str:
        """
        InlineKeyboard 콜백 처리
        
        Args:
            callback_data: 콜백 데이터
            
        Returns:
            str: 응답 메시지
        """
        try:
            parts = callback_data.split(":", 2)
            action_type = parts[0]
            
            if action_type == "session":
                # 세션 선택 → 액션 메뉴로 전환
                session_name = parts[1]
                ui_state_manager.set_session_actions(session_name, self.chat_id)
                
                # 패널 업데이트
                await self.update_panel()
                
                session_info = self.sessions.get(session_name)
                display_name = session_info.display_name if session_info else session_name
                return f"🎯 {display_name} 세션의 액션 메뉴로 전환되었습니다."
                
            elif action_type == "action":
                action_name = parts[1]
                
                if action_name == "refresh":
                    await self.refresh_sessions()
                    await self.update_panel()
                    return "🔄 세션 목록을 새로고침했습니다."
                    
                elif action_name == "status":
                    return await self._handle_status_action()
                    
                elif action_name == "settings":
                    return await self._handle_settings_action()
                    
                elif action_name == "back_to_main":
                    ui_state_manager.set_main_panel(self.chat_id)
                    await self.update_panel()
                    return "◀️ 메인 패널로 돌아갔습니다."
                    
                elif action_name.startswith("set_main") and len(parts) == 3:
                    session_name = parts[2]  # "action:set_main:session_name"
                    success, message = session_action_handlers.set_main_session(session_name)
                    if success:
                        # 메인 패널로 돌아가서 업데이트
                        ui_state_manager.set_main_panel(self.chat_id)
                        await self.update_panel()
                    return message
                    
                elif action_name.startswith("logs") and len(parts) == 3:
                    session_name = parts[2]  # "action:logs:session_name"
                    success, message = session_action_handlers.show_logs(session_name)
                    return message
                    
                elif action_name.startswith("pause") and len(parts) == 3:
                    session_name = parts[2]  # "action:pause:session_name"
                    success, message = session_action_handlers.send_pause(session_name)
                    return message
                    
                elif action_name.startswith("erase") and len(parts) == 3:
                    session_name = parts[2]  # "action:erase:session_name"
                    success, message = session_action_handlers.send_erase(session_name)
                    return message
            
            return f"❓ 알 수 없는 콜백: {callback_data}"
            
        except Exception as e:
            logger.error(f"Error handling callback {callback_data}: {e}")
            return f"❌ 콜백 처리 중 오류가 발생했습니다: {e}"
    
    async def _handle_status_action(self) -> str:
        """전체 상태 액션 처리"""
        try:
            sessions = await self.discover_sessions()
            
            if not sessions:
                return "📊 **전체 상태**\n\n❌ 활성 Claude 세션이 없습니다."
            
            # 상태별 세션 분류
            working_sessions = []
            idle_sessions = []
            waiting_sessions = []
            error_sessions = []
            unknown_sessions = []
            
            for session in sessions:
                try:
                    state = self.state_analyzer.get_state(session)
                    display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                    
                    if state == SessionState.WORKING:
                        working_sessions.append(display_name)
                    elif state == SessionState.WAITING_INPUT:
                        waiting_sessions.append(display_name)
                    elif state == SessionState.IDLE:
                        idle_sessions.append(display_name)
                    elif state == SessionState.ERROR:
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
            
            current_time = datetime.now().strftime("%H:%M:%S")
            response = f"""📊 **전체 시스템 상태** ({current_time})

🎛️ **총 세션**: {len(sessions)}개

{status_summary}

💡 개별 세션 관리는 세션 버튼을 클릭하세요."""
            
            return response
            
        except Exception as e:
            return f"📊 **상태 확인 실패**\n\n❌ 오류: {e}"
    
    async def _handle_settings_action(self) -> str:
        """설정 액션 처리"""
        try:
            from ..utils.log_length_manager import get_current_log_length
            log_length = get_current_log_length()
            sessions = await self.discover_sessions()
            
            current_time = datetime.now().strftime("%H:%M:%S")
            response = f"""⚙️ **시스템 설정** ({current_time})

📏 **로그 길이**: {log_length}줄
🎛️ **모니터링 세션**: {len(sessions)}개
🖥️ **패널 방식**: InlineKeyboard (다단 액션)

**📱 CLI 도구 사용법:**

로그 길이 조절:
`python -m claude_ops.cli.log_length_cli --cycle`
`python -m claude_ops.cli.log_length_cli --set 300`

패널 관리:
`python -m claude_ops.cli.panel_cli --config`
`python -m claude_ops.cli.panel_cli --list`

💡 설정 변경 후 🔄 새로고침으로 상태를 확인하세요."""
            
            return response
            
        except Exception as e:
            return f"⚙️ **설정 확인 실패**\n\n❌ 오류: {e}"
    
    async def refresh_sessions(self):
        """세션 목록 새로고침"""
        try:
            # 현재 세션들 발견
            current_sessions = await self.discover_sessions()
            
            # 기존 세션 중 없어진 것들 제거
            existing_sessions = set(self.sessions.keys())
            current_sessions_set = set(current_sessions)
            
            removed_sessions = existing_sessions - current_sessions_set
            for session_name in removed_sessions:
                del self.sessions[session_name]
                if self.active_session == session_name:
                    self.active_session = None
                logger.info(f"Removed disappeared session: {session_name}")
            
            # 새로운 세션들 추가
            for session_name in current_sessions:
                if session_name not in self.sessions:
                    self.update_session_info(session_name, working_state="unknown")
                    logger.info(f"Added new session: {session_name}")
            
            # 실시간 상태 업데이트
            self._detect_real_time_states()
            
            logger.info(f"Refreshed sessions: {len(current_sessions)} total")
            
        except Exception as e:
            logger.error(f"Error refreshing sessions: {e}")
    
    async def update_panel(self) -> bool:
        """패널 업데이트"""
        try:
            # 실시간 상태 감지
            self._detect_real_time_states()
            
            # 현재 UI 상태에 따라 적절한 패널 생성
            if ui_state_manager.is_main_panel():
                text = self._create_main_panel_text()
                keyboard = self._create_main_panel_keyboard()
            elif ui_state_manager.is_session_actions():
                selected_session = ui_state_manager.selected_session
                if not selected_session:
                    # 선택된 세션이 없으면 메인으로 돌아가기
                    ui_state_manager.set_main_panel(self.chat_id)
                    text = self._create_main_panel_text()
                    keyboard = self._create_main_panel_keyboard()
                else:
                    text = self._create_session_action_text(selected_session)
                    keyboard = self._create_session_action_keyboard(selected_session)
            else:
                # 알 수 없는 상태면 메인으로 리셋
                ui_state_manager.set_main_panel(self.chat_id)
                text = self._create_main_panel_text()
                keyboard = self._create_main_panel_keyboard()
            
            # 패널 메시지 전송 또는 업데이트
            if self.panel_message_id:
                # 기존 메시지 업데이트
                success = await self._edit_message(text, keyboard)
                if not success:
                    # 업데이트 실패 시 새 메시지 전송
                    self.panel_message_id = await self._send_message(text, keyboard)
            else:
                # 새 메시지 전송
                self.panel_message_id = await self._send_message(text, keyboard)
            
            return self.panel_message_id is not None
            
        except Exception as e:
            logger.error(f"Error updating panel: {e}")
            return False
    
    async def _send_message(self, text: str, keyboard: Dict[str, Any]) -> Optional[int]:
        """새 메시지 전송"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard)
            }
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    message_id = result["result"]["message_id"]
                    logger.info(f"Sent new panel message: {message_id}")
                    return message_id
            
            logger.error(f"Failed to send message: {response.text}")
            return None
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    async def _edit_message(self, text: str, keyboard: Dict[str, Any]) -> bool:
        """기존 메시지 업데이트"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": self.panel_message_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard)
            }
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.debug(f"Updated panel message: {self.panel_message_id}")
                    return True
                else:
                    logger.warning(f"Failed to edit message: {result}")
            
            logger.error(f"Failed to edit message: {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return False
    
    async def start_panel(self) -> bool:
        """패널 시작"""
        try:
            # 세션 발견 및 초기화
            await self.refresh_sessions()
            
            # UI 상태를 메인 패널로 설정
            ui_state_manager.set_main_panel(self.chat_id)
            
            # 초기 패널 생성
            success = await self.update_panel()
            
            if success:
                logger.info(f"InlineKeyboard panel started successfully: message_id={self.panel_message_id}")
            else:
                logger.error("Failed to start InlineKeyboard panel")
            
            return success
            
        except Exception as e:
            logger.error(f"Error starting panel: {e}")
            return False


# 편의 함수들
async def create_inline_panel(bot_token: str, chat_id: str) -> InlineSessionPanel:
    """InlineKeyboard 패널 생성 및 시작"""
    panel = InlineSessionPanel(bot_token, chat_id)
    await panel.start_panel()
    return panel