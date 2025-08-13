"""
InlineKeyboard 다단 액션 패널 통합 테스트

UI 상태 관리, 세션 액션, InlineKeyboard 패널의 전체 워크플로우를 테스트합니다.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

# Async 테스트를 위한 마크
pytestmark = pytest.mark.asyncio

from claude_ops.telegram.inline_panel import InlineSessionPanel, SessionInfo
from claude_ops.telegram.ui_state_manager import ui_state_manager, UIState
from claude_ops.telegram.session_action_handlers import session_action_handlers
from claude_ops.utils.session_state import SessionState


class TestInlinePanelIntegration:
    """InlineKeyboard 패널 통합 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        # UI 상태 초기화 (패널 생성 전에)
        ui_state_manager.clear_state()
        self.panel = InlineSessionPanel("test_token", "test_chat_id")
    
    def test_panel_initialization(self):
        """패널 초기화 테스트"""
        assert self.panel.bot_token == "test_token"
        assert self.panel.chat_id == "test_chat_id"
        assert self.panel.sessions == {}
        assert self.panel.active_session is None
        assert ui_state_manager.chat_id == "test_chat_id"
    
    async def test_session_discovery(self):
        """세션 발견 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "claude_session1\nclaude_session2\nclaude_session3\n"
        
        with patch('subprocess.run', return_value=mock_result):
            sessions = await self.panel.discover_sessions()
            
        assert len(sessions) == 3
        assert "claude_session1" in sessions
        assert "claude_session2" in sessions
        assert "claude_session3" in sessions
    
    def test_session_info_creation(self):
        """세션 정보 생성 테스트"""
        session_info = SessionInfo("claude_test_session", is_active=True, working_state="working")
        
        assert session_info.name == "claude_test_session"
        assert session_info.display_name == "test_session"  # claude_ 접두사 제거
        assert session_info.is_active is True
        assert session_info.working_state == "working"
        assert session_info.get_status_icon() == "⭐"  # 활성 세션
        assert session_info.get_button_text() == "⭐ test_session"
    
    def test_session_info_status_icons(self):
        """세션 상태 아이콘 테스트"""
        test_cases = [
            (False, "error", "❌"),
            (False, "working", "⚒️"),
            (False, "waiting", "⏸️"),
            (False, "idle", "💤"),
            (False, "unknown", "❓"),
            (True, "error", "⭐"),  # 활성 세션은 상태와 관계없이 ⭐
        ]
        
        for is_active, working_state, expected_icon in test_cases:
            session_info = SessionInfo("claude_test", is_active=is_active, working_state=working_state)
            assert session_info.get_status_icon() == expected_icon
    
    def test_session_info_update(self):
        """세션 정보 업데이트 테스트"""
        # 첫 번째 세션 추가
        self.panel.update_session_info("claude_session1", is_active=True, working_state="working")
        
        assert len(self.panel.sessions) == 1
        assert self.panel.active_session == "claude_session1"
        assert self.panel.sessions["claude_session1"].is_active is True
        
        # 두 번째 세션 추가 (활성 세션 변경)
        self.panel.update_session_info("claude_session2", is_active=True, working_state="idle")
        
        assert len(self.panel.sessions) == 2
        assert self.panel.active_session == "claude_session2"
        assert self.panel.sessions["claude_session1"].is_active is False  # 이전 활성 세션 비활성화
        assert self.panel.sessions["claude_session2"].is_active is True
    
    def test_real_time_state_detection(self):
        """실시간 상태 감지 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_test")
        
        # 모킹된 상태 분석기 설정
        with patch.object(self.panel.state_analyzer, 'get_state', return_value=SessionState.WORKING):
            self.panel._detect_real_time_states()
            
        # 세션 상태가 업데이트되었는지 확인
        assert self.panel.sessions["claude_test"].working_state == "working"
    
    def test_main_panel_text_creation(self):
        """메인 패널 텍스트 생성 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_session1", working_state="working")
        self.panel.update_session_info("claude_session2", working_state="idle")
        
        # 메인 세션 설정
        ui_state_manager.set_main_session("claude_session1")
        
        text = self.panel._create_main_panel_text()
        
        assert "Claude-Ops 세션 관리" in text
        assert "⭐ session1" in text  # 메인 세션 표시
        assert "총 세션**: 2개" in text
        assert "작업중: 1개" in text
        assert "아이콘 범례" in text
    
    def test_session_action_text_creation(self):
        """세션 액션 텍스트 생성 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_test_session", working_state="working")
        
        text = self.panel._create_session_action_text("claude_test_session")
        
        assert "test_session 세션 액션" in text
        assert "⚒️ 작업 중" in text
        assert "claude_test_session" in text
        assert "원하는 액션을 선택하세요" in text
    
    def test_main_panel_keyboard_creation(self):
        """메인 패널 키보드 생성 테스트"""
        # 여러 세션 추가
        self.panel.update_session_info("claude_session1", working_state="working")
        self.panel.update_session_info("claude_session2", working_state="idle")
        self.panel.update_session_info("claude_session3", working_state="waiting")
        
        # 메인 세션 설정 (우선 정렬 테스트)
        ui_state_manager.set_main_session("claude_session2")
        
        # 메인 세션을 활성 세션으로도 설정해야 ⭐ 아이콘이 표시됨
        self.panel.update_session_info("claude_session2", is_active=False, working_state="idle")  # 메인 세션으로 다시 업데이트
        
        keyboard = self.panel._create_main_panel_keyboard()
        
        assert "inline_keyboard" in keyboard
        buttons = keyboard["inline_keyboard"]
        
        # 마지막 행은 제어 버튼들
        control_row = buttons[-1]
        control_texts = [btn["text"] for btn in control_row]
        assert "🔄 새로고침" in control_texts
        assert "📊 전체상태" in control_texts
        assert "⚙️ 설정" in control_texts
        
        # 세션 버튼들 확인 (메인 세션이 우선 정렬되어야 함)
        session_buttons = []
        for row in buttons[:-1]:  # 제어 버튼 행 제외
            session_buttons.extend(row)
        
        # 첫 번째 버튼이 메인 세션인지 확인 (메인 세션은 정렬에서 우선이지만 아이콘은 working_state에 따라)
        first_button = session_buttons[0]
        # session2가 idle 상태이므로 💤 아이콘이어야 함
        assert "💤" in first_button["text"] or "session2" in first_button["text"]
        assert first_button["callback_data"] == "session:claude_session2"
    
    def test_session_action_keyboard_creation(self):
        """세션 액션 키보드 생성 테스트"""
        keyboard = self.panel._create_session_action_keyboard("claude_test_session")
        
        assert "inline_keyboard" in keyboard
        buttons = keyboard["inline_keyboard"]
        
        # 3개 행이어야 함
        assert len(buttons) == 3
        
        # 첫 번째 행: 메인세션 설정, 로그보기
        first_row = buttons[0]
        assert len(first_row) == 2
        assert first_row[0]["text"] == "🏠 메인세션 설정"
        assert first_row[0]["callback_data"] == "action:set_main:claude_test_session"
        assert first_row[1]["text"] == "📜 로그보기"
        assert first_row[1]["callback_data"] == "action:logs:claude_test_session"
        
        # 두 번째 행: Pause, Erase
        second_row = buttons[1]
        assert len(second_row) == 2
        assert second_row[0]["text"] == "⏸️ Pause (ESC)"
        assert second_row[0]["callback_data"] == "action:pause:claude_test_session"
        assert second_row[1]["text"] == "🗑️ Erase (Ctrl+C)"
        assert second_row[1]["callback_data"] == "action:erase:claude_test_session"
        
        # 세 번째 행: 돌아가기
        third_row = buttons[2]
        assert len(third_row) == 1
        assert third_row[0]["text"] == "◀️ 메인으로 돌아가기"
        assert third_row[0]["callback_data"] == "action:back_to_main"
    
    async def test_callback_session_selection(self):
        """세션 선택 콜백 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_test_session")
        
        # update_panel 모킹
        with patch.object(self.panel, 'update_panel', return_value=True):
            response = await self.panel.handle_callback("session:claude_test_session")
        
        assert "test_session 세션의 액션 메뉴로 전환되었습니다" in response
        assert ui_state_manager.current_state == UIState.SESSION_ACTIONS
        assert ui_state_manager.selected_session == "claude_test_session"
    
    async def test_callback_refresh_action(self):
        """새로고침 액션 콜백 테스트"""
        with patch.object(self.panel, 'refresh_sessions', return_value=None):
            with patch.object(self.panel, 'update_panel', return_value=True):
                response = await self.panel.handle_callback("action:refresh")
        
        assert "세션 목록을 새로고침했습니다" in response
    
    async def test_callback_back_to_main(self):
        """메인으로 돌아가기 콜백 테스트"""
        # 먼저 세션 액션 상태로 설정
        ui_state_manager.set_session_actions("claude_test", "test_chat_id")
        
        with patch.object(self.panel, 'update_panel', return_value=True):
            response = await self.panel.handle_callback("action:back_to_main")
        
        assert "메인 패널로 돌아갔습니다" in response
        assert ui_state_manager.current_state == UIState.MAIN_PANEL
        assert ui_state_manager.selected_session is None
    
    async def test_callback_set_main_session(self):
        """메인 세션 설정 콜백 테스트"""
        # 세션 먼저 추가
        self.panel.update_session_info("claude_test")
        
        # session_action_handlers.set_main_session 모킹
        with patch.object(session_action_handlers, 'set_main_session', return_value=(True, "메인 세션 설정 완료")):
            with patch.object(self.panel, 'update_panel', return_value=True):
                response = await self.panel.handle_callback("action:set_main:claude_test")
        
        assert "메인 세션 설정 완료" in response
        assert ui_state_manager.current_state == UIState.MAIN_PANEL  # 메인 패널로 돌아가야 함
    
    async def test_callback_logs_action(self):
        """로그보기 액션 콜백 테스트"""
        with patch.object(session_action_handlers, 'show_logs', return_value=(True, "로그 내용")):
            response = await self.panel.handle_callback("action:logs:claude_test")
        
        assert "로그 내용" in response
    
    async def test_callback_pause_action(self):
        """Pause 액션 콜백 테스트"""
        with patch.object(session_action_handlers, 'send_pause', return_value=(True, "ESC 키 전송됨")):
            response = await self.panel.handle_callback("action:pause:claude_test")
        
        assert "ESC 키 전송됨" in response
    
    async def test_callback_erase_action(self):
        """Erase 액션 콜백 테스트"""
        with patch.object(session_action_handlers, 'send_erase', return_value=(True, "Ctrl+C 키 전송됨")):
            response = await self.panel.handle_callback("action:erase:claude_test")
        
        assert "Ctrl+C 키 전송됨" in response
    
    async def test_refresh_sessions(self):
        """세션 새로고침 테스트"""
        # 초기 세션들 설정
        self.panel.update_session_info("claude_session1")
        self.panel.update_session_info("claude_session2")
        self.panel.active_session = "claude_session1"
        
        # discover_sessions 모킹 (session2만 남음)
        with patch.object(self.panel, 'discover_sessions', return_value=["claude_session2", "claude_session3"]):
            with patch.object(self.panel, '_detect_real_time_states'):
                await self.panel.refresh_sessions()
        
        # session1은 제거되고, session3은 추가되어야 함
        assert "claude_session1" not in self.panel.sessions
        assert "claude_session2" in self.panel.sessions
        assert "claude_session3" in self.panel.sessions
        assert self.panel.active_session is None  # 활성 세션이 제거되었으므로 None
    
    @patch('requests.post')
    async def test_send_message(self, mock_post):
        """메시지 전송 테스트"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_response
        
        message_id = await self.panel._send_message("Test message", {"inline_keyboard": []})
        
        assert message_id == 12345
        mock_post.assert_called_once()
        
        # 호출 인수 확인
        call_args = mock_post.call_args
        assert call_args[1]["json"]["chat_id"] == "test_chat_id"
        assert call_args[1]["json"]["text"] == "Test message"
        assert call_args[1]["json"]["parse_mode"] == "Markdown"
    
    @patch('requests.post')
    async def test_edit_message(self, mock_post):
        """메시지 편집 테스트"""
        self.panel.panel_message_id = 12345
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response
        
        success = await self.panel._edit_message("Updated message", {"inline_keyboard": []})
        
        assert success is True
        mock_post.assert_called_once()
        
        # 호출 인수 확인
        call_args = mock_post.call_args
        assert call_args[1]["json"]["chat_id"] == "test_chat_id"
        assert call_args[1]["json"]["message_id"] == 12345
        assert call_args[1]["json"]["text"] == "Updated message"
    
    @patch('requests.post')
    async def test_update_panel_main_state(self, mock_post):
        """메인 패널 상태에서 패널 업데이트 테스트"""
        # 새 메시지 전송 모킹
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_response
        
        # 세션 추가
        self.panel.update_session_info("claude_test")
        
        # 메인 패널 상태로 설정
        ui_state_manager.set_main_panel("test_chat_id")
        
        success = await self.panel.update_panel()
        
        assert success is True
        assert self.panel.panel_message_id == 12345
        
        # 메시지 전송이 호출되었는지 확인
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "Claude-Ops 세션 관리" in call_args[1]["json"]["text"]
    
    @patch('requests.post')
    async def test_update_panel_session_actions_state(self, mock_post):
        """세션 액션 상태에서 패널 업데이트 테스트"""
        # 새 메시지 전송 모킹
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_response
        
        # 세션 추가
        self.panel.update_session_info("claude_test_session")
        
        # 세션 액션 상태로 설정
        ui_state_manager.set_session_actions("claude_test_session", "test_chat_id")
        
        success = await self.panel.update_panel()
        
        assert success is True
        
        # 세션 액션 패널이 생성되었는지 확인
        call_args = mock_post.call_args
        assert "test_session 세션 액션" in call_args[1]["json"]["text"]
    
    @patch('requests.post')
    async def test_start_panel(self, mock_post):
        """패널 시작 테스트"""
        # 메시지 전송 모킹
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_response
        
        # 세션 발견 모킹
        with patch.object(self.panel, 'discover_sessions', return_value=["claude_test"]):
            success = await self.panel.start_panel()
        
        assert success is True
        assert self.panel.panel_message_id == 12345
        assert ui_state_manager.current_state == UIState.MAIN_PANEL
        assert len(self.panel.sessions) == 1


class TestUIStateIntegration:
    """UI 상태 관리 통합 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        ui_state_manager.clear_state()
    
    def test_ui_state_transitions(self):
        """UI 상태 전환 테스트"""
        # 초기 상태는 메인 패널
        assert ui_state_manager.is_main_panel() is True
        assert ui_state_manager.is_session_actions() is False
        
        # 세션 액션으로 전환
        ui_state_manager.set_session_actions("claude_test", "test_chat")
        assert ui_state_manager.is_main_panel() is False
        assert ui_state_manager.is_session_actions() is True
        assert ui_state_manager.selected_session == "claude_test"
        
        # 메인 패널로 돌아가기
        ui_state_manager.set_main_panel("test_chat")
        assert ui_state_manager.is_main_panel() is True
        assert ui_state_manager.is_session_actions() is False
        assert ui_state_manager.selected_session is None
    
    def test_main_session_management(self):
        """메인 세션 관리 테스트"""
        assert ui_state_manager.main_session is None
        
        # 메인 세션 설정
        ui_state_manager.set_main_session("claude_test")
        assert ui_state_manager.main_session == "claude_test"
        
        # 메인 세션 변경
        ui_state_manager.set_main_session("claude_other")
        assert ui_state_manager.main_session == "claude_other"


class TestSessionActionHandlersIntegration:
    """세션 액션 핸들러 통합 테스트"""
    
    def test_session_action_handlers_exist(self):
        """세션 액션 핸들러가 올바르게 임포트되는지 테스트"""
        # 핸들러 메서드들이 존재하는지 확인
        assert hasattr(session_action_handlers, 'set_main_session')
        assert hasattr(session_action_handlers, 'show_logs')
        assert hasattr(session_action_handlers, 'send_pause')
        assert hasattr(session_action_handlers, 'send_erase')
    
    @patch('subprocess.run')
    def test_session_exists_check(self, mock_run):
        """세션 존재 확인 테스트"""
        mock_run.return_value.returncode = 0  # 세션 존재
        
        success, message = session_action_handlers.set_main_session("claude_test")
        
        # session_exists가 호출되었는지 확인
        mock_run.assert_called()
        
        # 실제 동작은 모킹되어 있으므로 호출만 확인