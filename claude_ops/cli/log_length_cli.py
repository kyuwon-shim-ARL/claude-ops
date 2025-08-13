"""
로그 길이 조절 CLI

동적 로그 길이를 명령줄에서 쉽게 조절할 수 있는 CLI 도구입니다.
"""

import argparse
import sys
from typing import Optional
from ..utils.log_length_manager import log_length_manager, LogLengthOption


def show_status() -> None:
    """현재 로그 길이 설정 상태 표시"""
    current = log_length_manager.get_current_length()
    options = log_length_manager.get_all_options()
    
    print(f"📊 현재 로그 길이: {current}줄")
    print(f"🔧 사용 가능한 옵션: {options}")
    print(f"📁 설정 파일: {log_length_manager.config_file}")


def set_length(length: int) -> None:
    """로그 길이 설정"""
    if length not in [100, 150, 200, 300]:
        print(f"❌ 잘못된 로그 길이: {length}")
        print("✅ 사용 가능한 옵션: 100, 150, 200, 300")
        sys.exit(1)
    
    success = log_length_manager.set_log_length(length)
    if success:
        print(f"✅ 로그 길이가 {length}줄로 설정되었습니다.")
    else:
        print(f"❌ 로그 길이 설정 실패")
        sys.exit(1)


def cycle_length() -> None:
    """로그 길이 순환 (100 → 150 → 200 → 300 → 100 → ...)"""
    old_length = log_length_manager.get_current_length()
    new_length = log_length_manager.increase_log_length()
    
    print(f"🔄 로그 길이: {old_length}줄 → {new_length}줄")


def reset_to_default() -> None:
    """기본 로그 길이(200줄)로 재설정"""
    old_length = log_length_manager.get_current_length()
    new_length = log_length_manager.reset_to_default()
    
    print(f"🔄 로그 길이를 기본값으로 재설정: {old_length}줄 → {new_length}줄")


def main() -> None:
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="Claude-Ops 로그 길이 조절 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python -m claude_ops.cli.log_length_cli --status              # 현재 설정 확인
  python -m claude_ops.cli.log_length_cli --set 300            # 300줄로 설정
  python -m claude_ops.cli.log_length_cli --cycle              # 순환 (100→150→200→300→100...)
  python -m claude_ops.cli.log_length_cli --reset              # 기본값(200줄)으로 재설정
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', '-s', action='store_true',
                      help='현재 로그 길이 설정 상태 표시')
    group.add_argument('--set', '-l', type=int, metavar='LENGTH',
                      help='로그 길이 설정 (100, 150, 200, 300 중 하나)')
    group.add_argument('--cycle', '-c', action='store_true',
                      help='로그 길이 순환 (100→150→200→300→100...)')
    group.add_argument('--reset', '-r', action='store_true',
                      help='기본 로그 길이(200줄)로 재설정')
    
    args = parser.parse_args()
    
    try:
        if args.status:
            show_status()
        elif args.set is not None:
            set_length(args.set)
        elif args.cycle:
            cycle_length()
        elif args.reset:
            reset_to_default()
            
    except KeyboardInterrupt:
        print("\n🔚 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()