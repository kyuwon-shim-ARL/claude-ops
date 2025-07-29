# Next Session Context - Telegram-Claude Bridge 다중 세션 지원

## 🎯 다음 작업 목표
**Option 2 구현**: 작업 디렉토리 기반 tmux 세션 자동 분리

## 📊 현재 시스템 상태
- ✅ **완료**: 인라인 키보드 버튼 인터페이스 구현
- ✅ **완료**: Bot Commands Menu (/ 버튼) 통합
- ✅ **완료**: 알림 시스템 최적화 (선택지 박스 지원)
- ✅ **완료**: Git 커밋 완료 (commit: b830749)

## 🔧 현재 시스템 구조

### 핵심 파일들:
- `telegram_claude_bridge.py`: 메인 봇 파일 (인라인 키보드 완료)
- `send_smart_notification.sh`: 알림 스크립트 (bullet point 기반)
- `watch_claude_status.sh`: 모니터링 스크립트
- `.env`: 환경 변수 (TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS 등)

### 현재 제약사항:
- 단일 tmux 세션: `claude_session` 하드코딩
- 고정 실행 위치: `/home/kyuwon/claude-ops`
- 다중 프로젝트 지원 없음

## 🚀 구현 계획 (Option 2)

### 1. 세션 이름 동적 생성
```bash
# 현재: claude_session
# 개선: claude_$(basename $PWD)
# 예시: claude_project1, claude_ops, claude_research
```

### 2. 수정 필요 파일들
- `telegram_claude_bridge.py`: TMUX_SESSION 동적 설정
- `watch_claude_status.sh`: 디렉토리별 모니터링
- `send_smart_notification.sh`: 세션 이름 동적 처리

### 3. 환경변수 개선
```bash
# 기존
TMUX_SESSION="claude_session"

# 개선
TMUX_SESSION_PREFIX="claude"  # claude_$(dirname) 형태로 생성
```

## 🔄 현재 작동하는 기능들
1. **인라인 키보드**: Status, Log, Stop, Help 버튼
2. **Bot Commands Menu**: / 버튼으로 명령어 선택
3. **자동 알림**: 작업 완료 시 텔레그램 알림
4. **ESC 중단**: 텔레그램에서 작업 중단 가능
5. **실시간 로그**: 현재 Claude 화면 확인

## 📝 구현 세부사항

### A. 세션 이름 생성 로직
```python
import os
def get_session_name():
    current_dir = os.path.basename(os.getcwd())
    return f"claude_{current_dir}"
```

### B. 디렉토리별 상태 파일
```bash
# 현재: /tmp/claude_work_status
# 개선: /tmp/claude_work_status_$(basename $PWD)
```

### C. 모니터링 스크립트 개선
- 여러 세션 동시 모니터링
- 세션별 독립적인 상태 관리

## 🎉 완료된 주요 기능들
- ✅ 텔레그램 봇 인라인 키보드 (4개 버튼)
- ✅ 자동 메뉴 표시 (/start 시)
- ✅ Bot Commands Menu 통합
- ✅ 선택지 박스 알림 최적화
- ✅ ESC 작업 중단 기능
- ✅ 실시간 화면 모니터링

## 🔧 다음 세션에서 할 일
1. **세션 이름 동적 생성** 구현
2. **디렉토리별 모니터링** 설정
3. **다중 세션 지원** 테스트
4. **Git 커밋 및 문서 업데이트**

## 📚 참고 정보
- 현재 Git 브랜치: main
- 마지막 커밋: b830749 "Enhance Telegram-Claude Bridge with comprehensive button interface"
- 텔레그램 봇 정상 작동 중
- 모든 기존 기능 안정적으로 동작

---
*생성일: 2025-07-29*
*다음 세션에서 이 문서를 참고하여 Option 2 구현 계속 진행*