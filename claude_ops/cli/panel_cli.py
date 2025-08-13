"""
상시 패널 관리 CLI

텔레그램 상시 세션 패널을 명령줄에서 관리할 수 있는 도구입니다.
"""

import argparse
import asyncio
import sys
import os
from typing import Optional

from ..config import ClaudeOpsConfig
from ..telegram.persistent_panel import PersistentSessionPanel, create_persistent_panel


class PanelCLI:
    """패널 CLI 관리자"""
    
    def __init__(self):
        self.config = ClaudeOpsConfig()
        self.panel: Optional[PersistentSessionPanel] = None
    
    def _validate_config(self) -> bool:
        """설정 유효성 검증"""
        if not self.config.telegram_bot_token:
            print("❌ TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
            print("   .env 파일에서 TELEGRAM_BOT_TOKEN을 설정하세요.")
            return False
        
        if not self.config.telegram_chat_id:
            print("❌ TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
            print("   .env 파일에서 TELEGRAM_CHAT_ID를 설정하세요.")
            return False
        
        return True
    
    async def send_panel(self) -> None:
        """패널 전송"""
        if not self._validate_config():
            return
        
        print("📤 상시 패널을 전송하는 중...")
        
        panel = await create_persistent_panel(
            self.config.telegram_bot_token,
            self.config.telegram_chat_id
        )
        
        if panel:
            print(f"✅ 상시 패널이 성공적으로 전송되었습니다!")
            print(f"   메시지 ID: {panel.panel_message_id}")
            print(f"   발견된 세션: {len(panel.sessions)}개")
        else:
            print("❌ 상시 패널 전송 실패")
            sys.exit(1)
    
    async def update_panel(self, message_id: int) -> None:
        """패널 업데이트"""
        if not self._validate_config():
            return
        
        print(f"🔄 패널 (메시지 ID: {message_id})을 업데이트하는 중...")
        
        panel = PersistentSessionPanel(
            self.config.telegram_bot_token,
            self.config.telegram_chat_id
        )
        panel.panel_message_id = message_id
        
        success = await panel.update_panel()
        
        if success:
            print("✅ 상시 패널이 성공적으로 업데이트되었습니다!")
            print(f"   발견된 세션: {len(panel.sessions)}개")
        else:
            print("❌ 상시 패널 업데이트 실패")
            sys.exit(1)
    
    def show_sessions(self) -> None:
        """현재 세션 목록 표시"""
        print("🔍 Claude 세션 검색 중...")
        
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
                
                if sessions:
                    print(f"📊 발견된 Claude 세션: {len(sessions)}개\n")
                    for i, session in enumerate(sessions, 1):
                        display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                        print(f"  {i}. {session}")
                        print(f"     표시명: {display_name}")
                else:
                    print("📭 발견된 Claude 세션이 없습니다.")
            else:
                print("❌ tmux 세션 조회 실패")
                
        except Exception as e:
            print(f"❌ 세션 검색 중 오류 발생: {e}")
    
    def show_config(self) -> None:
        """현재 설정 표시"""
        print("⚙️ **현재 설정**\n")
        
        # 환경변수 확인
        env_file = ".env"
        if os.path.exists(env_file):
            print(f"📁 설정 파일: {env_file}")
        else:
            print(f"📁 설정 파일: {env_file} (없음)")
        
        # 봇 토큰 (마스킹)
        if self.config.telegram_bot_token:
            masked_token = self.config.telegram_bot_token[:10] + "..." + self.config.telegram_bot_token[-10:]
            print(f"🤖 봇 토큰: {masked_token}")
        else:
            print("🤖 봇 토큰: (설정되지 않음)")
        
        # 채팅 ID
        if self.config.telegram_chat_id:
            print(f"💬 채팅 ID: {self.config.telegram_chat_id}")
        else:
            print("💬 채팅 ID: (설정되지 않음)")
        
        # 작업 디렉토리
        print(f"📂 작업 디렉토리: {self.config.working_directory}")
        
        # 로그 길이
        from ..utils.log_length_manager import get_current_log_length
        log_length = get_current_log_length()
        print(f"📏 로그 길이: {log_length}줄")


async def main():
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="Claude-Ops 상시 패널 관리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 새 패널 전송
  python -m claude_ops.cli.panel_cli --send

  # 기존 패널 업데이트 (메시지 ID 필요)
  python -m claude_ops.cli.panel_cli --update 12345

  # 현재 세션 목록 확인
  python -m claude_ops.cli.panel_cli --list

  # 설정 정보 확인
  python -m claude_ops.cli.panel_cli --config

설정 요구사항:
  .env 파일에 다음 항목이 필요합니다:
  - TELEGRAM_BOT_TOKEN=your_bot_token_here
  - TELEGRAM_CHAT_ID=your_chat_id_here
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--send', '-s', action='store_true',
                      help='새 상시 패널 전송')
    group.add_argument('--update', '-u', type=int, metavar='MESSAGE_ID',
                      help='기존 패널 업데이트 (메시지 ID 필요)')
    group.add_argument('--list', '-l', action='store_true',
                      help='현재 Claude 세션 목록 표시')
    group.add_argument('--config', '-c', action='store_true',
                      help='현재 설정 정보 표시')
    
    args = parser.parse_args()
    
    cli = PanelCLI()
    
    try:
        if args.send:
            await cli.send_panel()
        elif args.update is not None:
            await cli.update_panel(args.update)
        elif args.list:
            cli.show_sessions()
        elif args.config:
            cli.show_config()
            
    except KeyboardInterrupt:
        print("\n🔚 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


def run_main():
    """동기 래퍼"""
    asyncio.run(main())


if __name__ == "__main__":
    run_main()