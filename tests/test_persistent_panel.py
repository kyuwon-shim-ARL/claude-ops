"""
상시 패널 테스트

텔레그램 상시 세션 패널의 기능을 테스트합니다.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

# Async 테스트를 위한 마크
pytestmark = pytest.mark.asyncio

from claude_ops.telegram.persistent_panel import (
    SessionInfo,
    PersistentSessionPanel,
    create_persistent_panel
)


class TestSessionInfo:
    """SessionInfo 테스트"""
    
    def test_session_info_creation(self):
        """세션 정보 생성 테스트"""
        session = SessionInfo("claude_test_session")
        
        assert session.name == "claude_test_session"
        assert session.display_name == "test_session"
        assert not session.is_active
        assert session.working_state == "unknown"
        assert isinstance(session.last_activity, datetime)
    
    def test_display_name_without_claude_prefix(self):
        """claude_ 접두사 제거 테스트"""
        session = SessionInfo("claude_my_project")
        assert session.display_name == "my_project"
        
        session = SessionInfo("other_session")
        assert session.display_name == "other_session"
    
    def test_status_icons(self):
        """상태 아이콘 테스트"""
        session = SessionInfo("test")
        
        # 기본 상태
        assert session.get_status_icon() == "❓"
        
        # 활성 세션
        session.is_active = True
        assert session.get_status_icon() == "⭐"
        
        # 작업 상태들 (활성이 우선)
        session.working_state = "working"
        assert session.get_status_icon() == "⭐"  # 활성이 우선
        
        # 활성이 아닐 때 작업 상태
        session.is_active = False
        assert session.get_status_icon() == "⚒️"
        
        session.working_state = "waiting"
        assert session.get_status_icon() == "⏸️"
        
        session.working_state = "idle"
        assert session.get_status_icon() == "💤"
    
    def test_button_text(self):
        """버튼 텍스트 생성 테스트"""
        session = SessionInfo("claude_test_project", is_active=True)
        expected = "⭐ test_project"
        assert session.get_button_text() == expected


class TestPersistentSessionPanel:
    """PersistentSessionPanel 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        self.panel = PersistentSessionPanel("fake_token", "fake_chat_id")
    
    @patch('subprocess.run')
    async def test_discover_sessions(self, mock_subprocess):
        """세션 발견 테스트"""
        # tmux 명령 성공 케이스
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="claude_session1\nclaude_session2\nclaude_session3\n"
        )
        
        sessions = await self.panel.discover_sessions()
        
        assert len(sessions) == 3
        assert "claude_session1" in sessions
        assert "claude_session2" in sessions
        assert "claude_session3" in sessions
    
    @patch('subprocess.run')
    async def test_discover_sessions_no_sessions(self, mock_subprocess):
        """세션이 없는 경우 테스트"""
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=""
        )
        
        sessions = await self.panel.discover_sessions()
        assert sessions == []
    
    @patch('subprocess.run')
    async def test_discover_sessions_error(self, mock_subprocess):
        """세션 발견 오류 테스트"""
        mock_subprocess.side_effect = Exception("Command failed")
        
        sessions = await self.panel.discover_sessions()
        assert sessions == []
    
    def test_update_session_info(self):
        """세션 정보 업데이트 테스트"""
        # 새 세션 추가
        self.panel.update_session_info("claude_new_session", is_active=True, working_state="working")
        
        assert "claude_new_session" in self.panel.sessions
        session = self.panel.sessions["claude_new_session"]
        assert session.is_active
        assert session.working_state == "working"
        assert self.panel.active_session == "claude_new_session"
        
        # 다른 세션을 활성화하면 이전 세션 비활성화
        self.panel.update_session_info("claude_other_session", is_active=True)
        
        assert not self.panel.sessions["claude_new_session"].is_active
        assert self.panel.sessions["claude_other_session"].is_active
        assert self.panel.active_session == "claude_other_session"
    
    def test_create_inline_keyboard(self):
        """인라인 키보드 생성 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_session1", is_active=True)
        self.panel.update_session_info("claude_session2", working_state="working")
        
        keyboard = self.panel._create_inline_keyboard()
        
        assert "inline_keyboard" in keyboard
        buttons = keyboard["inline_keyboard"]
        
        # 세션 버튼들이 있는지 확인
        session_buttons = buttons[0]  # 첫 번째 행
        assert len(session_buttons) <= self.panel.max_sessions_per_row
        
        # 제어 버튼들이 마지막 행에 있는지 확인
        control_buttons = buttons[-1]
        control_texts = [btn["text"] for btn in control_buttons]
        assert "🔄 새로고침" in control_texts
        assert "📊 상태" in control_texts
        assert "⚙️ 설정" in control_texts
    
    def test_create_panel_text(self):
        """패널 텍스트 생성 테스트"""
        self.panel.update_session_info("claude_test", is_active=True)
        
        text = self.panel._create_panel_text()
        
        assert "Claude 세션 패널" in text
        assert "⭐ 활성" in text
        assert "현재 활성:" in text
        assert "**총 세션:** 1개" in text
    
    async def test_handle_session_callback(self):
        """세션 선택 콜백 처리 테스트"""
        self.panel.update_session_info("claude_test_session")
        
        # 패널 업데이트 모킹
        with patch.object(self.panel, 'update_panel', return_value=True) as mock_update:
            response = await self.panel.handle_callback("session:claude_test_session")
            
            assert "활성 세션이 'test_session'로 변경되었습니다" in response
            assert self.panel.sessions["claude_test_session"].is_active
            mock_update.assert_called_once()
    
    async def test_handle_refresh_callback(self):
        """새로고침 콜백 처리 테스트"""
        with patch.object(self.panel, 'update_panel', return_value=True):
            response = await self.panel.handle_callback("refresh")
            assert "새로고침되었습니다" in response
    
    async def test_handle_status_callback(self):
        """상태 콜백 처리 테스트"""
        self.panel.update_session_info("claude_test", is_active=True)
        
        response = await self.panel.handle_callback("status")
        assert "세션 상태 요약" in response
        assert "활성 세션:" in response
    
    async def test_handle_settings_callback(self):
        """설정 콜백 처리 테스트"""
        response = await self.panel.handle_callback("settings")
        
        assert "패널 설정" in response
        assert "로그 길이:" in response
        assert "CLI 도구" in response
    
    async def test_handle_unknown_callback(self):
        """알 수 없는 콜백 처리 테스트"""
        response = await self.panel.handle_callback("unknown:action")
        assert "알 수 없는 명령" in response
    
    @patch('requests.post')
    async def test_send_initial_panel_success(self, mock_post):
        """초기 패널 전송 성공 테스트"""
        # 세션 발견 모킹
        with patch.object(self.panel, 'discover_sessions', return_value=["claude_test"]):
            # 텔레그램 API 응답 모킹
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "ok": True,
                "result": {"message_id": 12345}
            }
            mock_post.return_value = mock_response
            
            message_id = await self.panel.send_initial_panel()
            
            assert message_id == 12345
            assert self.panel.panel_message_id == 12345
            mock_post.assert_called_once()
    
    @patch('requests.post')
    async def test_send_initial_panel_failure(self, mock_post):
        """초기 패널 전송 실패 테스트"""
        with patch.object(self.panel, 'discover_sessions', return_value=[]):
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_post.return_value = mock_response
            
            message_id = await self.panel.send_initial_panel()
            assert message_id is None
    
    @patch('requests.post')
    async def test_update_panel_success(self, mock_post):
        """패널 업데이트 성공 테스트"""
        self.panel.panel_message_id = 12345
        
        with patch.object(self.panel, 'discover_sessions', return_value=["claude_test"]):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response
            
            success = await self.panel.update_panel()
            
            assert success
            mock_post.assert_called_once()
    
    async def test_update_panel_no_message_id(self):
        """메시지 ID 없이 패널 업데이트 테스트"""
        self.panel.panel_message_id = None
        
        success = await self.panel.update_panel()
        assert not success


class TestCreatePersistentPanel:
    """create_persistent_panel 함수 테스트"""
    
    @patch('claude_ops.telegram.persistent_panel.PersistentSessionPanel')
    async def test_create_persistent_panel_success(self, mock_panel_class):
        """패널 생성 성공 테스트"""
        mock_panel = MagicMock()
        mock_panel.send_initial_panel = AsyncMock(return_value=12345)
        mock_panel_class.return_value = mock_panel
        
        result = await create_persistent_panel("token", "chat_id")
        
        assert result == mock_panel
        mock_panel_class.assert_called_once_with("token", "chat_id")
        mock_panel.send_initial_panel.assert_called_once()
    
    @patch('claude_ops.telegram.persistent_panel.PersistentSessionPanel')
    async def test_create_persistent_panel_failure(self, mock_panel_class):
        """패널 생성 실패 테스트"""
        mock_panel = MagicMock()
        mock_panel.send_initial_panel = AsyncMock(return_value=None)
        mock_panel_class.return_value = mock_panel
        
        result = await create_persistent_panel("token", "chat_id")
        
        assert result is None


class TestIntegration:
    """통합 테스트"""
    
    @patch('subprocess.run')
    async def test_full_panel_workflow(self, mock_subprocess):
        """전체 패널 워크플로우 테스트"""
        # tmux 세션 발견 모킹
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="claude_session1\nclaude_session2\n"
        )
        
        panel = PersistentSessionPanel("token", "chat_id")
        
        # 세션 발견
        sessions = await panel.discover_sessions()
        assert len(sessions) == 2
        
        # 세션 정보 업데이트
        for session_name in sessions:
            panel.update_session_info(session_name)
        
        # 키보드 생성
        keyboard = panel._create_inline_keyboard()
        assert len(keyboard["inline_keyboard"]) > 0
        
        # 패널 텍스트 생성
        text = panel._create_panel_text()
        assert "**총 세션:** 2개" in text
        
        # 콜백 처리
        response = await panel.handle_callback("session:claude_session1")
        assert "활성 세션이" in response
        assert panel.active_session == "claude_session1"