# 📖 Claude-Ops 사용 예시

Claude-Ops를 처음 사용하시나요? 실제 워크플로우를 통해 사용법을 빠르게 익혀보세요!

## 🚀 빠른 시작

```bash
# 예시 실행
uv run python examples/basic_usage.py
```

## 📋 포함된 시나리오

### 1. 🚀 새 프로젝트 시작하기
- Claude Code 세션 생성 및 연결
- 텔레그램을 통한 세션 확인
- claude-dev-kit의 `/기획` 명령어로 구조적 프로젝트 기획
- claude-dev-kit의 `/구현` 명령어로 체계적 개발 시작

### 2. 🎛️ 여러 프로젝트 동시 관리
- 다중 세션 실행 (Frontend, Backend, Mobile)
- `/board`를 통한 전체 현황 파악  
- Reply 기반 특정 세션 타겟팅
- claude-dev-kit 워크플로우 명령어 활용

### 3. 📱 원격 개발 워크플로우
- 집-외출-카페로 이어지는 연속 개발
- 텔레그램을 통한 진행상황 모니터링
- 원격에서 추가 지시 및 최종 마무리
- 장소에 관계없는 개발 연속성

## 🎯 핵심 명령어

### 세션 관리
```
/sessions   - 활성 세션 목록 및 전환
/board      - 세션 보드 (그리드 뷰)
/status     - 봇 및 시스템 상태
```

### 모니터링
```
/log        - Claude 화면 내용 보기 (기본 50줄)
/log 150    - 150줄까지 확장 보기
/stop       - Claude 작업 중단 (ESC)
/erase      - 현재 입력 지우기 (Ctrl+C)
```

### 워크플로우 명령어 (claude-dev-kit 제공)
```
/기획       - 구조적 기획 프롬프트
/구현       - DRY 원칙 기반 구현
/안정화     - 구조적 검증 및 테스트  
/배포       - 최종 배포 준비
/전체사이클 - 기획부터 배포까지 완전 사이클
```

## 🔧 환경 설정

### 1. 텔레그램 봇 설정
```bash
# .env 파일 생성
cp .env.example .env

# 필수 설정
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 2. 첫 번째 세션 시작
```bash
tmux new-session -s claude_test
claude
```

### 3. 텔레그램에서 확인
```
/start
/sessions
```

## 💡 실전 팁

### Reply 기능 활용
```
1. Claude 세션에서 작업 진행
2. 텔레그램 알림 메시지 수신
3. 해당 메시지에 Reply로 추가 명령
4. 자동으로 해당 세션에만 전송
```

### 효율적인 세션 명명
```bash
# 프로젝트별 명명
tmux new-session -s claude_ecommerce-frontend
tmux new-session -s claude_ecommerce-backend

# 기능별 명명  
tmux new-session -s claude_auth-service
tmux new-session -s claude_payment-api
```

### 워크플로우 명령어 활용
```
# 빠른 개발 사이클
/구현 새 기능 → /안정화

# 완전한 프로젝트 사이클
/전체사이클 새 프로젝트

# 품질 중심 마무리
/안정화 → /배포
```

## 🎪 고급 활용

### 세션 자동화
```bash
# 프로젝트 세션 일괄 생성 스크립트
projects=("frontend" "backend" "mobile")
for project in "${projects[@]}"; do
    tmux new-session -d -s "claude_$project"
    tmux send-keys -t "claude_$project" 'claude' Enter
done
```

### 알림 조건 활용
- 작업 완료 시 자동 알림
- 에러 발생 시 즉시 알림
- 대기 상태 전환 시 알림

### 원격 협업
```
1. 팀원별 전용 세션 생성
2. 공유 채팅방에서 진행상황 모니터링
3. 코드 리뷰 시 특정 세션 타겟팅
4. 통합 워크플로우로 일관성 유지
```

## 🚨 문제 해결

### 봇이 응답하지 않을 때
```bash
# 봇 프로세스 확인
ps aux | grep claude_ops

# 봇 재시작
pkill -f claude_ops
python -m claude_ops.telegram.bot
```

### 워크플로우 명령어가 작동하지 않을 때
- Claude Code에서 [claude-dev-kit](https://github.com/kyuwon-shim-ARL/claude-dev-kit)이 설치되어 있는지 확인
- 정확한 슬래시 커맨드 사용 (`/기획`, `/구현`, `/안정화`, `/배포`)
- Claude-Ops는 브리지 역할만 하며, 실제 명령어는 claude-dev-kit에서 처리됩니다

## 📚 더 알아보기

- **[QUICK_START.md](../QUICK_START.md)** - 빠른 설정 가이드
- **[README.md](../README.md)** - 전체 기능 개요
- **[claude-dev-kit](https://github.com/kyuwon-shim-ARL/claude-dev-kit)** - 워크플로우 명령어 제공

---

**Claude-Ops**: Pure Telegram Bridge for Claude Code Sessions