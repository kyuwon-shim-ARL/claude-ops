#!/usr/bin/env python3
"""
실시간 알림 모니터링 대시보드

사용법:
    python scripts/notification_monitor.py

기능:
- 실시간 상태 전환 추적
- 알림 누락 감지
- 각 세션별 상태 표시
"""

import sys
import time
import subprocess
from datetime import datetime
from collections import defaultdict

# Add project to path
sys.path.insert(0, '/home/kyuwon/claude-ops')

from claude_ctb.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ctb.session_manager import session_manager


class NotificationMonitor:
    """실시간 알림 모니터 대시보드"""

    def __init__(self):
        self.analyzer = SessionStateAnalyzer()
        self.last_states = {}
        self.completion_count = defaultdict(int)
        self.notification_count = defaultdict(int)

    def get_sessions(self):
        """활성 Claude 세션 목록"""
        return session_manager.get_all_claude_sessions()

    def check_session(self, session_name):
        """세션 상태 체크"""
        current_state = self.analyzer.get_state_for_notification(session_name)
        previous_state = self.last_states.get(session_name, SessionState.UNKNOWN)

        # 상태 전환 감지
        if previous_state != current_state:
            timestamp = datetime.now().strftime("%H:%M:%S")

            # 완료 감지
            if previous_state == SessionState.WORKING and current_state != SessionState.WORKING:
                self.completion_count[session_name] += 1
                print(f"\n🎯 [{timestamp}] {session_name}")
                print(f"   상태 전환: WORKING → {current_state.value.upper()}")
                print(f"   👉 여기서 알림이 가야 함!")

            # 입력 대기 감지
            elif current_state == SessionState.WAITING_INPUT and previous_state != SessionState.WAITING_INPUT:
                self.completion_count[session_name] += 1
                print(f"\n⏸️  [{timestamp}] {session_name}")
                print(f"   상태 전환: {previous_state.value.upper()} → WAITING_INPUT")
                print(f"   👉 입력 대기 알림이 가야 함!")

        self.last_states[session_name] = current_state
        return current_state

    def display_dashboard(self, sessions):
        """대시보드 출력"""
        print("\033[2J\033[H")  # 화면 클리어
        print("=" * 80)
        print(f"🔔 실시간 알림 모니터 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        print(f"📺 모니터링 중: {len(sessions)}개 세션")
        print()

        print(f"{'세션 이름':<40} {'현재 상태':<15} {'완료 감지':<10}")
        print("-" * 80)

        for session in sorted(sessions):
            state = self.last_states.get(session, SessionState.UNKNOWN)
            completions = self.completion_count[session]

            # 상태별 이모지
            state_emoji = {
                SessionState.WORKING: "⚙️ ",
                SessionState.WAITING_INPUT: "⏸️ ",
                SessionState.IDLE: "💤",
                SessionState.ERROR: "❌",
                SessionState.UNKNOWN: "❓"
            }

            emoji = state_emoji.get(state, "")
            display_name = session.replace('claude_', '')[:38]

            print(f"{display_name:<40} {emoji} {state.value:<13} {completions:>3}회")

        print()
        print("=" * 80)
        print("📊 통계:")
        print(f"   총 완료 감지: {sum(self.completion_count.values())}회")
        print()
        print("💡 Ctrl+C로 종료")

    def run(self):
        """메인 루프"""
        print("🚀 알림 모니터 시작...\n")

        try:
            while True:
                sessions = self.get_sessions()

                # 각 세션 상태 체크
                for session in sessions:
                    self.check_session(session)

                # 대시보드 표시 (3초마다)
                self.display_dashboard(sessions)

                time.sleep(3)

        except KeyboardInterrupt:
            print("\n\n✅ 모니터 종료")
            print(f"\n최종 통계:")
            print(f"   총 완료 감지: {sum(self.completion_count.values())}회")
            for session, count in sorted(self.completion_count.items()):
                if count > 0:
                    print(f"   {session}: {count}회")


if __name__ == "__main__":
    monitor = NotificationMonitor()
    monitor.run()
