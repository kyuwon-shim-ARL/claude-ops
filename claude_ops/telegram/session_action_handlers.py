"""
세션 액션 처리 모듈

세션별 액션 (메인세션 설정, 로그보기, Pause, Erase) 처리
"""

import subprocess
import logging
from typing import Optional, Tuple
from datetime import datetime
from ..utils.log_length_manager import get_current_log_length
from ..session_manager import session_manager
from .ui_state_manager import ui_state_manager

logger = logging.getLogger(__name__)


class SessionActionHandlers:
    """세션 액션 처리 핸들러"""
    
    def __init__(self):
        pass
    
    def set_main_session(self, session_name: str) -> Tuple[bool, str]:
        """
        메인 세션 설정 및 tmux 세션 전환
        
        Args:
            session_name: 설정할 세션명
            
        Returns:
            Tuple[bool, str]: (성공여부, 응답메시지)
        """
        try:
            # 세션 존재 확인
            if not self._session_exists(session_name):
                return False, f"❌ '{session_name}' 세션을 찾을 수 없습니다."
            
            # 현재 메인 세션과 동일한지 확인
            current_main = ui_state_manager.main_session
            if current_main == session_name:
                return True, f"ℹ️ '{self._get_display_name(session_name)}'은 이미 메인 세션입니다."
            
            # UI 상태 관리자에서 메인 세션 설정
            ui_state_manager.set_main_session(session_name)
            
            # session_manager를 통해 실제 tmux 세션 전환
            try:
                session_manager.switch_session(session_name)
                switch_success = True
                switch_msg = ""
            except Exception as e:
                switch_success = False
                switch_msg = f" (주의: tmux 세션 전환 실패 - {e})"
            
            display_name = self._get_display_name(session_name)
            
            response = f"""🏠 **메인 세션 변경 완료**

⭐ **새 메인 세션**: {display_name}
🕐 **변경 시간**: {self._get_current_time()}
{'✅ tmux 세션도 전환되었습니다.' if switch_success else '⚠️ UI에서만 메인 세션이 변경되었습니다.' + switch_msg}

💡 메인 패널에서 ⭐ 아이콘으로 표시됩니다."""

            logger.info(f"Main session changed to {session_name}")
            return True, response
            
        except Exception as e:
            error_msg = f"❌ 메인 세션 설정 중 오류가 발생했습니다: {e}"
            logger.error(f"Failed to set main session {session_name}: {e}")
            return False, error_msg
    
    def show_logs(self, session_name: str) -> Tuple[bool, str]:
        """
        세션 로그 표시
        
        Args:
            session_name: 로그를 볼 세션명
            
        Returns:
            Tuple[bool, str]: (성공여부, 응답메시지)
        """
        try:
            # 세션 존재 확인
            if not self._session_exists(session_name):
                return False, f"❌ '{session_name}' 세션을 찾을 수 없습니다."
            
            # 동적 로그 길이 가져오기
            log_length = get_current_log_length()
            
            # tmux로부터 로그 가져오기 (최신 내용부터)
            # -e: 전체 히스토리 끝에서부터
            # -S: 시작 위치 지정 (음수는 끝에서부터)
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -e -S -{log_length}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return False, f"❌ '{session_name}' 세션 로그를 가져올 수 없습니다."
            
            logs = result.stdout.strip()
            
            # 최신 내용이 아래에 오도록 라인 순서 유지
            # (tmux capture-pane은 이미 올바른 순서로 반환함)
            if not logs:
                logs = "(빈 화면)"
            
            # 너무 긴 로그는 자르기 (Telegram 4096자 제한)
            max_log_length = 3000  # 헤더와 푸터를 위한 여유공간
            if len(logs) > max_log_length:
                # 마지막 부분 우선으로 자르기
                logs = "...(로그 시작 부분 생략)...\n" + logs[-max_log_length:]
            
            display_name = self._get_display_name(session_name)
            
            response = f"""📜 **{display_name} 세션 로그**

🎛️ **세션**: `{session_name}`
📏 **로그 길이**: {log_length}줄
🕐 **확인 시간**: {self._get_current_time()}

```
{logs}
```

💡 로그 길이는 CLI로 조절할 수 있습니다:
`python -m claude_ops.cli.log_length_cli --cycle`"""

            logger.info(f"Retrieved logs for {session_name} ({len(logs)} chars)")
            return True, response
            
        except subprocess.TimeoutExpired:
            return False, f"❌ '{session_name}' 세션 로그 조회 시간 초과"
        except Exception as e:
            error_msg = f"❌ 로그 조회 중 오류가 발생했습니다: {e}"
            logger.error(f"Failed to show logs for {session_name}: {e}")
            return False, error_msg
    
    def send_pause(self, session_name: str) -> Tuple[bool, str]:
        """
        세션에 ESC 키 전송 (Pause)
        
        Args:
            session_name: 대상 세션명
            
        Returns:
            Tuple[bool, str]: (성공여부, 응답메시지)
        """
        try:
            # 세션 존재 확인
            if not self._session_exists(session_name):
                return False, f"❌ '{session_name}' 세션을 찾을 수 없습니다."
            
            # tmux로 ESC 키 전송
            result = subprocess.run(
                f"tmux send-keys -t {session_name} Escape",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, f"❌ '{session_name}' 세션에 ESC 키를 전송할 수 없습니다."
            
            display_name = self._get_display_name(session_name)
            
            response = f"""⏸️ **Pause 명령 전송**

🎛️ **대상 세션**: {display_name}
⌨️ **전송된 키**: ESC
🕐 **전송 시간**: {self._get_current_time()}

✅ ESC 키가 전송되었습니다. Claude 작업이 일시정지됩니다.

💡 작업을 재개하려면 해당 세션에서 계속 입력하세요."""

            logger.info(f"Sent ESC (pause) to {session_name}")
            return True, response
            
        except subprocess.TimeoutExpired:
            return False, f"❌ '{session_name}' 세션으로 ESC 키 전송 시간 초과"
        except Exception as e:
            error_msg = f"❌ Pause 명령 전송 중 오류가 발생했습니다: {e}"
            logger.error(f"Failed to send pause to {session_name}: {e}")
            return False, error_msg
    
    def send_erase(self, session_name: str) -> Tuple[bool, str]:
        """
        세션에 Ctrl+C 키 전송 (Erase)
        
        Args:
            session_name: 대상 세션명
            
        Returns:
            Tuple[bool, str]: (성공여부, 응답메시지)
        """
        try:
            # 세션 존재 확인
            if not self._session_exists(session_name):
                return False, f"❌ '{session_name}' 세션을 찾을 수 없습니다."
            
            # tmux로 Ctrl+C 키 전송
            result = subprocess.run(
                f"tmux send-keys -t {session_name} C-c",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, f"❌ '{session_name}' 세션에 Ctrl+C 키를 전송할 수 없습니다."
            
            display_name = self._get_display_name(session_name)
            
            response = f"""🗑️ **Erase 명령 전송**

🎛️ **대상 세션**: {display_name}
⌨️ **전송된 키**: Ctrl+C
🕐 **전송 시간**: {self._get_current_time()}

✅ Ctrl+C 키가 전송되었습니다. 현재 작업이 중단됩니다.

💡 새로운 작업을 시작하려면 해당 세션에서 명령어를 입력하세요."""

            logger.info(f"Sent Ctrl+C (erase) to {session_name}")
            return True, response
            
        except subprocess.TimeoutExpired:
            return False, f"❌ '{session_name}' 세션으로 Ctrl+C 키 전송 시간 초과"
        except Exception as e:
            error_msg = f"❌ Erase 명령 전송 중 오류가 발생했습니다: {e}"
            logger.error(f"Failed to send erase to {session_name}: {e}")
            return False, error_msg
    
    def _session_exists(self, session_name: str) -> bool:
        """세션 존재 여부 확인"""
        try:
            result = subprocess.run(
                f"tmux has-session -t {session_name}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _get_display_name(self, session_name: str) -> str:
        """세션 표시명 생성"""
        if session_name.startswith('claude_'):
            return session_name[7:]  # 'claude_' 접두사 제거
        return session_name
    
    def _get_current_time(self) -> str:
        """현재 시간 반환"""
        return datetime.now().strftime("%H:%M:%S")


# 전역 액션 핸들러 인스턴스
session_action_handlers = SessionActionHandlers()