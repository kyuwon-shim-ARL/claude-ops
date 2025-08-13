"""
InlineKeyboard 다단 액션 패널 데모 테스트

실제 환경에서 InlineKeyboard 패널의 동작을 테스트합니다.
"""

import asyncio
import logging
from claude_ops.telegram.inline_panel import InlineSessionPanel
from claude_ops.telegram.ui_state_manager import ui_state_manager
from claude_ops.config import ClaudeOpsConfig

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demo_inline_panel():
    """InlineKeyboard 패널 데모 실행"""
    try:
        # 설정 로드
        config = ClaudeOpsConfig()
        
        if not config.telegram_bot_token or not config.telegram_chat_id:
            print("❌ 텔레그램 설정이 없습니다. .env 파일을 확인하세요.")
            return
        
        print("🚀 InlineKeyboard 다단 액션 패널 데모 시작...")
        
        # 패널 생성
        panel = InlineSessionPanel(config.telegram_bot_token, config.telegram_chat_id)
        
        # 테스트용 세션들 추가
        print("📊 테스트 세션 추가 중...")
        panel.update_session_info("claude_PaperFlow", working_state="working")
        panel.update_session_info("claude_MC", working_state="idle")
        panel.update_session_info("claude_dev_kit", working_state="waiting")
        
        # 메인 세션 설정
        ui_state_manager.set_main_session("claude_PaperFlow")
        
        # 패널 시작
        print("🎛️ 패널 시작...")
        success = await panel.start_panel()
        
        if success:
            print(f"✅ InlineKeyboard 패널이 성공적으로 시작되었습니다!")
            print(f"📱 메시지 ID: {panel.panel_message_id}")
            print(f"🎯 UI 상태: {ui_state_manager.current_state.value}")
            print(f"⭐ 메인 세션: {ui_state_manager.main_session}")
            
            # 테스트 콜백들
            print("\n🔧 콜백 테스트:")
            
            # 1. 세션 선택 테스트
            print("1. 세션 선택 테스트...")
            response = await panel.handle_callback("session:claude_MC")
            print(f"   응답: {response[:100]}...")
            
            # 2. 메인 세션 설정 테스트
            print("2. 메인 세션 설정 테스트...")
            response = await panel.handle_callback("action:set_main:claude_MC")
            print(f"   응답: {response[:100]}...")
            
            # 3. 로그보기 테스트
            print("3. 로그보기 테스트...")
            response = await panel.handle_callback("action:logs:claude_PaperFlow")
            print(f"   응답: {response[:100]}...")
            
            # 4. 메인으로 돌아가기 테스트
            print("4. 메인으로 돌아가기 테스트...")
            response = await panel.handle_callback("action:back_to_main")
            print(f"   응답: {response}")
            
            print(f"\n🎉 최종 UI 상태: {ui_state_manager.current_state.value}")
            print(f"⭐ 최종 메인 세션: {ui_state_manager.main_session}")
            
        else:
            print("❌ 패널 시작에 실패했습니다.")
            
    except Exception as e:
        logger.error(f"데모 실행 중 오류: {e}")
        print(f"❌ 오류: {e}")


async def demo_session_actions():
    """세션 액션 핸들러 데모"""
    from claude_ops.telegram.session_action_handlers import session_action_handlers
    
    print("\n🛠️ 세션 액션 핸들러 데모:")
    
    # 실제 세션이 있는지 확인
    import subprocess
    result = subprocess.run(
        "tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^claude_' | head -1",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout.strip():
        session_name = result.stdout.strip()
        print(f"📋 테스트 세션: {session_name}")
        
        # 로그보기 테스트
        print("1. 로그보기 테스트...")
        success, message = session_action_handlers.show_logs(session_name)
        print(f"   성공: {success}")
        print(f"   메시지: {message[:200]}...")
        
    else:
        print("⚠️ 활성 Claude 세션이 없어 액션 테스트를 건너뜁니다.")


async def main():
    """메인 함수"""
    print("🎯 InlineKeyboard 다단 액션 패널 종합 데모")
    print("=" * 60)
    
    # 1. 패널 데모
    await demo_inline_panel()
    
    # 2. 액션 핸들러 데모
    await demo_session_actions()
    
    print("\n" + "=" * 60)
    print("✅ 모든 데모 완료!")


if __name__ == "__main__":
    asyncio.run(main())