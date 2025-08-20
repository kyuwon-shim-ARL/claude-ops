#!/usr/bin/env python3
"""
Claude-Ops Usage Examples

간단한 사용 시나리오를 통해 Claude-Ops의 핵심 워크플로우를 보여줍니다.
"""

import os
import sys
from pathlib import Path

# Add project root to path  
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def scenario_1_new_project():
    """시나리오 1: 새 프로젝트 시작하기"""
    print("🚀 **시나리오 1: 새 프로젝트 시작하기**")
    print("=" * 50)
    print()
    print("📋 상황: 새로운 웹 애플리케이션 프로젝트를 시작합니다")
    print()
    print("1️⃣ Claude Code 세션 시작:")
    print("   tmux new-session -s claude_my-webapp")
    print("   claude  # Claude Code 실행")
    print()
    print("2️⃣ 텔레그램에서 세션 확인:")
    print("   /sessions  # ← claude_my-webapp 표시됨")
    print()
    print("3️⃣ 구조적 기획 시작:")
    print("   @기획 React + Node.js 웹 애플리케이션")
    print("   # ↑ 자동으로 상세한 기획 프롬프트로 확장됨")
    print()
    print("4️⃣ 기획 완료 후 구현:")
    print("   @구현 사용자 인증 시스템")
    print()
    print("✅ 결과: 구조화된 프로젝트 기획 → 체계적 구현")
    print()

def scenario_2_multi_project():
    """시나리오 2: 여러 프로젝트 동시 관리"""
    print("🎛️ **시나리오 2: 여러 프로젝트 동시 관리**")
    print("=" * 50)
    print()
    print("📋 상황: Frontend, Backend, Mobile 3개 프로젝트를 동시 진행")
    print()
    print("1️⃣ 여러 세션 동시 실행:")
    print("   tmux new-session -d -s claude_frontend")
    print("   tmux new-session -d -s claude_backend") 
    print("   tmux new-session -d -s claude_mobile")
    print()
    print("2️⃣ 텔레그램에서 전체 현황 파악:")
    print("   /board  # ← 모든 세션을 그리드 뷰로 확인")
    print()
    print("3️⃣ 특정 프로젝트에 집중:")
    print("   [Frontend 세션 알림에 Reply]")
    print("   → \"API 연동 부분 구현해줘\"")
    print("   # ↑ Frontend 세션에만 명령 전송")
    print()
    print("4️⃣ 통합 워크플로우:")
    print("   @구현&안정화  # ← 구현 + 테스트까지 한번에")
    print()
    print("✅ 결과: 여러 프로젝트 진행상황 실시간 모니터링")
    print()

def scenario_3_remote_workflow():
    """시나리오 3: 원격 개발 워크플로우"""
    print("📱 **시나리오 3: 원격 개발 워크플로우**")
    print("=" * 50)
    print()
    print("📋 상황: 집에서 작업 시작 → 외출 중 → 카페에서 마무리")
    print()
    print("🏠 집에서 작업 시작:")
    print("   1. Claude Code로 API 개발 시작")
    print("   2. @구현 RESTful API 엔드포인트")
    print("   3. 외출 전 진행상황 확인")
    print()
    print("🚶‍♂️ 외출 중 모니터링:")
    print("   1. 텔레그램 알림: \"API 구현 완료!\"")
    print("   2. /log 100  # ← 마지막 100줄 코드 확인")
    print("   3. \"이제 테스트 코드 작성해줘\" (Reply)")
    print()
    print("☕ 카페에서 최종 확인:")
    print("   1. @안정화  # ← 코드 구조 및 테스트 검증")
    print("   2. @배포    # ← 최종 배포 준비")
    print("   3. 집 도착 전에 모든 작업 완료!")
    print()
    print("✅ 결과: 장소에 관계없이 연속적인 개발 워크플로우")
    print()

def show_telegram_commands():
    """주요 텔레그램 명령어 요약"""
    print("📱 **주요 텔레그램 명령어**")
    print("=" * 50)
    print()
    print("🎛️ **세션 관리:**")
    print("   /sessions   - 활성 세션 목록 및 전환")
    print("   /board      - 세션 보드 (그리드 뷰)")
    print("   /status     - 봇 및 시스템 상태")
    print()
    print("📺 **모니터링 & 제어:**")
    print("   /log        - Claude 화면 내용 보기 (기본 50줄)")
    print("   /log 150    - 150줄까지 확장 보기") 
    print("   /stop       - Claude 작업 중단 (ESC)")
    print("   /erase      - 현재 입력 지우기 (Ctrl+C)")
    print()
    print("🎯 **워크플로우 사용법:**")
    print("   필요시 직접 슬래시 커맨드를 입력하세요:")
    print("   /기획       - 구조적 기획 및 계획 수립")
    print("   /구현       - DRY 원칙 기반 체계적 구현")
    print("   /안정화     - 구조적 지속가능성 검증")
    print("   /배포       - 최종 검증 및 배포")
    print()
    print("🆕 **프로젝트 생성:**")
    print("   /new_project - 새 Claude 프로젝트 생성")
    print()

def show_next_steps():
    """다음 단계 안내"""
    print("📚 **다음 단계**")
    print("=" * 50)
    print()
    print("1️⃣ **환경 설정 확인:**")
    print("   - .env 파일에 TELEGRAM_BOT_TOKEN 설정")
    print("   - 텔레그램에서 봇과 대화 시작")
    print()
    print("2️⃣ **첫 번째 세션 시작:**")
    print("   tmux new-session -s claude_test")
    print("   claude")
    print()
    print("3️⃣ **텔레그램에서 확인:**")
    print("   /start")
    print("   /sessions")
    print()
    print("4️⃣ **첫 번째 워크플로우 체험:**")
    print("   /기획 간단한 계산기 앱")
    print()
    print("🎉 **성공!** 이제 Claude-Ops의 모든 기능을 활용할 수 있습니다!")
    print()

def main():
    """메인 실행 함수"""
    print("📖 **Claude-Ops 사용 예시 가이드**")
    print("=" * 60)
    print()
    print("Claude-Ops를 처음 사용하시나요? 아래 3가지 시나리오를 통해")
    print("실제 사용법을 빠르게 익혀보세요!")
    print()
    
    # 3가지 핵심 시나리오
    scenario_1_new_project()
    scenario_2_multi_project() 
    scenario_3_remote_workflow()
    
    # 명령어 요약 및 다음 단계
    show_telegram_commands()
    show_next_steps()
    
    print("💡 **Tip:** 각 시나리오는 실제 상황을 기반으로 작성되었습니다.")
    print("    자신의 프로젝트에 맞게 응용해보세요!")

if __name__ == "__main__":
    main()