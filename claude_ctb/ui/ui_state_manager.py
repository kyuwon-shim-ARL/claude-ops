"""
UI 상태 관리 모듈

InlineKeyboard 다단 액션을 위한 UI 상태 추적 및 관리
"""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class UIState(Enum):
    """UI 상태 열거형"""
    MAIN_PANEL = "main"           # 메인 세션 목록 패널
    SESSION_ACTIONS = "actions"   # 세션별 액션 메뉴


class UIStateManager:
    """UI 상태 관리자"""
    
    def __init__(self, state_dir: str = "/tmp/claude-ops-ui"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / "ui_state.json"
        
        # 기본 상태
        self._current_state = UIState.MAIN_PANEL
        self._selected_session = None
        self._main_session = None
        self._chat_id = None
        
        # 상태 파일에서 로드
        self.load_state()
    
    @property
    def current_state(self) -> UIState:
        """현재 UI 상태"""
        return self._current_state
    
    @property
    def selected_session(self) -> Optional[str]:
        """현재 선택된 세션"""
        return self._selected_session
    
    @property
    def main_session(self) -> Optional[str]:
        """메인 세션 (⭐ 표시될 세션)"""
        return self._main_session
    
    @property
    def chat_id(self) -> Optional[str]:
        """현재 채팅 ID"""
        return self._chat_id
    
    def set_chat_id(self, chat_id: str):
        """채팅 ID 설정"""
        self._chat_id = chat_id
        self.save_state()
    
    def set_main_panel(self, chat_id: Optional[str] = None):
        """메인 패널 상태로 전환"""
        self._current_state = UIState.MAIN_PANEL
        self._selected_session = None
        if chat_id:
            self._chat_id = chat_id
        self.save_state()
        logger.info("UI state changed to MAIN_PANEL")
    
    def set_session_actions(self, session_name: str, chat_id: Optional[str] = None):
        """세션 액션 메뉴 상태로 전환"""
        self._current_state = UIState.SESSION_ACTIONS
        self._selected_session = session_name
        if chat_id:
            self._chat_id = chat_id
        self.save_state()
        logger.info(f"UI state changed to SESSION_ACTIONS for {session_name}")
    
    def set_main_session(self, session_name: str):
        """메인 세션 설정"""
        self._main_session = session_name
        self.save_state()
        logger.info(f"Main session set to {session_name}")
    
    def is_main_panel(self) -> bool:
        """메인 패널 상태인지 확인"""
        return self._current_state == UIState.MAIN_PANEL
    
    def is_session_actions(self) -> bool:
        """세션 액션 메뉴 상태인지 확인"""
        return self._current_state == UIState.SESSION_ACTIONS
    
    def get_state_info(self) -> Dict[str, Any]:
        """현재 상태 정보 반환"""
        return {
            "current_state": self._current_state.value,
            "selected_session": self._selected_session,
            "main_session": self._main_session,
            "chat_id": self._chat_id,
            "timestamp": datetime.now().isoformat()
        }
    
    def save_state(self):
        """상태를 파일에 저장"""
        try:
            state_data = {
                "current_state": self._current_state.value,
                "selected_session": self._selected_session,
                "main_session": self._main_session,
                "chat_id": self._chat_id,
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save UI state: {e}")
    
    def load_state(self):
        """파일에서 상태 로드"""
        try:
            if not self.state_file.exists():
                return
                
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 상태 복원
            state_value = state_data.get("current_state", "main")
            try:
                self._current_state = UIState(state_value)
            except ValueError:
                self._current_state = UIState.MAIN_PANEL
            
            self._selected_session = state_data.get("selected_session")
            self._main_session = state_data.get("main_session")
            self._chat_id = state_data.get("chat_id")
            
            logger.info(f"Loaded UI state: {self.get_state_info()}")
            
        except Exception as e:
            logger.error(f"Failed to load UI state: {e}")
            # 실패 시 기본 상태 유지
    
    def clear_state(self):
        """상태 초기화"""
        self._current_state = UIState.MAIN_PANEL
        self._selected_session = None
        self._main_session = None
        self._chat_id = None
        self.save_state()
        logger.info("UI state cleared")


# 전역 UI 상태 관리자 인스턴스
ui_state_manager = UIStateManager()