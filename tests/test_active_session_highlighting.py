"""
활성 세션 강조 표시 기능 테스트

상시 패널의 활성 세션 강조 및 실시간 상태 감지 기능을 테스트합니다.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Async 테스트를 위한 마크
pytestmark = pytest.mark.asyncio

from claude_ops.telegram.persistent_panel import (
    PersistentSessionPanel, 
    SessionInfo
)
from claude_ops.utils.session_state import SessionState


class TestActiveSessionHighlighting:
    """활성 세션 강조 표시 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        self.panel = PersistentSessionPanel("test_token", "test_chat_id")
    
    def test_active_session_priority_icon(self):
        """활성 세션이 다른 상태보다 우선하는지 테스트"""
        session = SessionInfo("claude_test", is_active=True, working_state="working")
        
        # 활성 세션은 작업 상태와 관계없이 ⭐ 아이콘
        assert session.get_status_icon() == "⭐"
        
        # 비활성 세션은 작업 상태에 따라 아이콘 결정
        session.is_active = False
        assert session.get_status_icon() == "⚒️"  # working state
    
    def test_error_state_priority(self):
        """오류 상태의 우선순위 테스트"""
        session = SessionInfo("claude_test", is_active=False, working_state="error")
        assert session.get_status_icon() == "❌"
        
        # 활성 세션은 오류 상태보다도 우선
        session.is_active = True
        assert session.get_status_icon() == "⭐"
    
    def test_all_state_icons(self):
        """모든 상태 아이콘 테스트"""
        session = SessionInfo("claude_test", is_active=False)
        
        state_icon_map = {
            "error": "❌",
            "working": "⚒️", 
            "waiting": "⏸️",
            "idle": "💤",
            "unknown": "❓"
        }
        
        for state, expected_icon in state_icon_map.items():
            session.working_state = state
            assert session.get_status_icon() == expected_icon
    
    def test_active_session_switching(self):
        """활성 세션 전환 테스트"""
        # 두 세션 추가
        self.panel.update_session_info("claude_session1", is_active=True)
        self.panel.update_session_info("claude_session2", is_active=False)
        
        # 첫 번째 세션이 활성
        assert self.panel.active_session == "claude_session1"
        assert self.panel.sessions["claude_session1"].is_active
        assert not self.panel.sessions["claude_session2"].is_active
        
        # 두 번째 세션으로 활성 전환
        self.panel.update_session_info("claude_session2", is_active=True)
        
        # 활성 세션 변경 확인
        assert self.panel.active_session == "claude_session2"
        assert not self.panel.sessions["claude_session1"].is_active
        assert self.panel.sessions["claude_session2"].is_active
    
    @patch.object(PersistentSessionPanel, '_detect_real_time_states')
    async def test_real_time_state_detection_called(self, mock_detect):
        """실시간 상태 감지가 호출되는지 테스트"""
        self.panel.panel_message_id = 12345
        
        # update_panel에서 실시간 상태 감지 호출 확인
        with patch.object(self.panel, 'discover_sessions', return_value=[]):
            with patch('requests.post') as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"ok": True}
                
                # 메서드 실행
                await self.panel.update_panel()
                
                # 실시간 상태 감지가 호출되었는지 확인
                mock_detect.assert_called_once()
    
    def test_real_time_state_mapping(self):
        """SessionState enum과 문자열 상태 매핑 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_test")
        
        # 각 SessionState에 대한 매핑 테스트
        state_mappings = [
            (SessionState.WORKING, "working"),
            (SessionState.WAITING_INPUT, "waiting"),
            (SessionState.IDLE, "idle"),
            (SessionState.ERROR, "error"),
            (SessionState.UNKNOWN, "unknown")
        ]
        
        for session_state, expected_string in state_mappings:
            with patch.object(self.panel.state_analyzer, 'get_state', return_value=session_state):
                # 실시간 상태 감지 실행
                self.panel._detect_real_time_states()
                
                # 상태가 올바르게 매핑되었는지 확인
                assert self.panel.sessions["claude_test"].working_state == expected_string
    
    def test_keyboard_layout_with_active_session(self):
        """활성 세션이 있는 키보드 레이아웃 테스트"""
        # 여러 세션 추가 (하나는 활성)
        self.panel.update_session_info("claude_session1", is_active=True, working_state="working")
        self.panel.update_session_info("claude_session2", is_active=False, working_state="idle")
        self.panel.update_session_info("claude_session3", is_active=False, working_state="waiting")
        
        keyboard = self.panel._create_inline_keyboard()
        
        # 키보드 구조 확인
        assert "inline_keyboard" in keyboard
        buttons = keyboard["inline_keyboard"]
        
        # 세션 버튼들 추출 (제어 버튼 제외)
        session_buttons = []
        for row in buttons[:-1]:  # 마지막 행은 제어 버튼
            session_buttons.extend(row)
        
        # 활성 세션이 ⭐ 아이콘으로 표시되는지 확인
        active_button_found = False
        for button in session_buttons:
            if "⭐" in button["text"]:
                active_button_found = True
                assert "session1" in button["text"]  # display name
        
        assert active_button_found, "활성 세션 버튼을 찾을 수 없습니다"
    
    def test_panel_text_active_session_info(self):
        """패널 텍스트에 활성 세션 정보 포함 테스트"""
        self.panel.update_session_info("claude_test_session", is_active=True)
        
        text = self.panel._create_panel_text()
        
        # 활성 세션 정보가 포함되어야 함
        assert "현재 활성:" in text
        assert "⭐ test_session" in text
        
        # 아이콘 범례 확인
        assert "⭐ 활성" in text
        assert "❌ 오류" in text  # 새로 추가된 오류 상태
    
    def test_session_sorting_active_first(self):
        """활성 세션이 키보드에서 우선 표시되는지 테스트"""
        # 여러 세션 추가 (나중에 추가된 세션을 활성으로)
        sessions = ["claude_a", "claude_b", "claude_c", "claude_d"]
        
        for session in sessions:
            self.panel.update_session_info(session, is_active=False)
        
        # 마지막 세션을 활성으로 설정
        self.panel.update_session_info("claude_d", is_active=True)
        
        keyboard = self.panel._create_inline_keyboard()
        
        # 첫 번째 버튼이 활성 세션인지 확인
        first_row = keyboard["inline_keyboard"][0]
        first_button = first_row[0]
        
        # 활성 세션(⭐)이 첫 번째 버튼에 와야 함
        assert "⭐" in first_button["text"]
        assert "d" in first_button["text"]
    
    async def test_callback_handling_with_active_session(self):
        """활성 세션 콜백 처리 테스트"""
        # 세션들 추가
        self.panel.update_session_info("claude_session1", is_active=True)
        self.panel.update_session_info("claude_session2", is_active=False)
        
        # 패널 업데이트 모킹
        with patch.object(self.panel, 'update_panel', return_value=True):
            # 다른 세션 선택 콜백 처리
            response = await self.panel.handle_callback("session:claude_session2")
            
            # 응답 메시지 확인
            assert "활성 세션이 'session2'로 변경되었습니다" in response
            
            # 활성 세션 변경 확인
            assert self.panel.active_session == "claude_session2"
            assert not self.panel.sessions["claude_session1"].is_active
            assert self.panel.sessions["claude_session2"].is_active


class TestIntegrationWithStateAnalyzer:
    """SessionStateAnalyzer 통합 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        self.panel = PersistentSessionPanel("test_token", "test_chat_id")
    
    @patch('claude_ops.telegram.persistent_panel.SessionStateAnalyzer')
    def test_state_analyzer_integration(self, mock_analyzer_class):
        """SessionStateAnalyzer 통합 테스트"""
        # SessionStateAnalyzer 인스턴스 모킹
        mock_analyzer = MagicMock()
        mock_analyzer_class.return_value = mock_analyzer
        
        # 새 패널 인스턴스 생성
        panel = PersistentSessionPanel("token", "chat_id")
        
        # SessionStateAnalyzer가 생성되었는지 확인
        assert panel.state_analyzer == mock_analyzer
        mock_analyzer_class.assert_called_once()
    
    def test_real_time_detection_error_handling(self):
        """실시간 감지 중 오류 처리 테스트"""
        # 세션 추가
        self.panel.update_session_info("claude_test")
        
        # state_analyzer.get_state가 예외를 발생시키도록 설정
        with patch.object(self.panel.state_analyzer, 'get_state', side_effect=Exception("Connection error")):
            # 예외가 발생해도 크래시하지 않아야 함
            self.panel._detect_real_time_states()
            
            # 세션이 여전히 존재하고 기본 상태를 유지해야 함
            assert "claude_test" in self.panel.sessions
            # 오류로 인해 상태가 변경되지 않아야 함