#!/usr/bin/env python3
"""
Claude-Ops Basic Usage Examples

이 예제는 Claude-Ops의 핵심 기능들을 시연합니다:
1. 세션 상태 검출
2. 텔레그램 봇 기본 설정
3. 프롬프트 매크로 시스템
4. 다중 세션 모니터링
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from claude_ops.config import ClaudeOpsConfig
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ops.session_manager import session_manager
from claude_ops.prompt_loader import ClaudeDevKitPrompts
from claude_ops.telegram.notifier import SmartNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def example_1_session_state_detection():
    """예제 1: 세션 상태 검출 시스템"""
    print("🔍 예제 1: 세션 상태 검출 시스템")
    print("=" * 50)
    
    analyzer = SessionStateAnalyzer()
    
    # 현재 활성 세션들 검색
    sessions = session_manager.get_all_claude_sessions()
    print(f"📋 발견된 Claude 세션: {len(sessions)}개")
    
    for session in sessions:
        state = analyzer.get_state(session)
        is_working = analyzer.is_working(session)
        is_waiting = analyzer.is_waiting_for_input(session)
        
        print(f"  📌 {session}:")
        print(f"     상태: {state.value}")
        print(f"     작업중: {'✅' if is_working else '❌'}")
        print(f"     입력대기: {'✅' if is_waiting else '❌'}")
    
    print()

def example_2_prompt_loader():
    """예제 2: 프롬프트 매크로 시스템"""
    print("📝 예제 2: 프롬프트 매크로 시스템")
    print("=" * 50)
    
    prompts = ClaudeDevKitPrompts()
    prompts.load_prompts()
    
    available = prompts.get_available_prompts()
    print(f"🎯 로드된 프롬프트: {len(available)}개")
    
    for keyword in available:
        prompt_text = prompts.get_prompt(keyword)
        preview = prompt_text[:100] + "..." if len(prompt_text) > 100 else prompt_text
        print(f"  🔑 {keyword}: {preview}")
    
    # 워크플로우 조합 예제
    기획_prompt = prompts.get_prompt("@기획") 
    구현_prompt = prompts.get_prompt("@구현")
    combined = f"{기획_prompt}\n\n{구현_prompt}"
    print(f"\n🔄 조합 워크플로우 예제 '기획&구현':")
    print(f"   총 길이: {len(combined)} 문자")
    print(f"   프리뷰: {combined[:200]}...")
    
    print()

def example_3_configuration():
    """예제 3: 설정 관리"""
    print("⚙️ 예제 3: 설정 관리")
    print("=" * 50)
    
    config = ClaudeOpsConfig()
    
    print(f"📁 작업 디렉토리: {config.working_directory}")
    print(f"🕒 체크 간격: {config.check_interval}초")
    print(f"🤖 봇 설정됨: {'✅' if config.telegram_bot_token else '❌'}")
    print(f"💬 채팅 설정됨: {'✅' if config.telegram_chat_id else '❌'}")
    print(f"👥 허용된 사용자: {len(config.allowed_user_ids)}명")
    
    if config.session_name:
        print(f"🎯 현재 세션: {config.session_name}")
    
    print()

def example_4_notification_system():
    """예제 4: 스마트 알림 시스템 (텔레그램 토큰이 있을 때만)"""
    print("🔔 예제 4: 스마트 알림 시스템")
    print("=" * 50)
    
    config = ClaudeOpsConfig()
    
    if not config.telegram_bot_token:
        print("⚠️  텔레그램 봇 토큰이 설정되지 않아 시뮬레이션 모드로 실행")
        print("   실제 사용하려면 .env 파일에 TELEGRAM_BOT_TOKEN 설정 필요")
    
    notifier = SmartNotifier(config)
    
    # 현재 세션 상태 확인
    session_state = notifier._get_session_state()
    print(f"📊 현재 세션 상태: {session_state.value}")
    
    # 작업 실행 상태 확인  
    is_working = notifier._is_work_currently_running()
    print(f"🔄 현재 작업 실행중: {'✅' if is_working else '❌'}")
    
    print()

def example_5_integration_demo():
    """예제 5: 통합 워크플로우 데모"""
    print("🚀 예제 5: 통합 워크플로우 데모")
    print("=" * 50)
    
    # 1. 설정 로드
    config = ClaudeOpsConfig()
    print("✅ 설정 로드 완료")
    
    # 2. 세션 상태 분석
    analyzer = SessionStateAnalyzer()
    sessions = session_manager.get_all_claude_sessions()
    print(f"✅ {len(sessions)}개 세션 발견")
    
    # 3. 프롬프트 시스템 초기화
    prompts = ClaudeDevKitPrompts()
    prompts.load_prompts()
    print(f"✅ {len(prompts.get_available_prompts())}개 프롬프트 로드")
    
    # 4. 알림 시스템 준비
    notifier = SmartNotifier(config)
    print("✅ 알림 시스템 준비 완료")
    
    print("\n🎯 Claude-Ops 시스템이 정상 작동중입니다!")
    print(f"   현재 모니터링 세션: {config.session_name or '없음'}")
    
    if sessions:
        print("   활성 세션에서 다음 명령을 사용할 수 있습니다:")
        print("   - 텔레그램에서 /board - 세션 보드")
        print("   - 텔레그램에서 /remote - 프롬프트 매크로")
        print("   - 텔레그램에서 @기획, @구현, @안정화, @배포")
    
    print()

def run_all_examples():
    """모든 예제 실행"""
    print("🎉 Claude-Ops 기본 사용 예제")
    print("=" * 60)
    print()
    
    try:
        example_1_session_state_detection()
        example_2_prompt_loader()  
        example_3_configuration()
        example_4_notification_system()
        example_5_integration_demo()
        
        print("✅ 모든 예제가 성공적으로 완료되었습니다!")
        print()
        print("📚 다음 단계:")
        print("1. .env 파일에 텔레그램 봇 설정")
        print("2. 텔레그램에서 /start 명령으로 봇 활성화")  
        print("3. Claude Code 세션에서 /board로 다중 세션 관리")
        print("4. /remote로 프롬프트 매크로 활용")
        
    except Exception as e:
        logger.error(f"예제 실행 중 오류 발생: {str(e)}")
        print(f"❌ 오류 발생: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = run_all_examples()
    sys.exit(exit_code)