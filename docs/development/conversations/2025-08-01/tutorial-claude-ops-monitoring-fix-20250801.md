# Claude-CTB 모니터링 시작 오류 해결 튜토리얼

## 개요

Claude-CTB의 `start-monitoring` 명령어에서 2분 타임아웃 오류가 발생하는 문제를 해결하는 과정입니다.

## 문제 증상

```bash
claude-ctb start-monitoring
# 결과: Command timed out after 2m 0.0s
```

## 근본 원인 분석

1. **복잡한 스크립트 구조**: `claude-ctb.sh` → `start_multi_monitoring.sh` → tmux 세션 생성
2. **에러 핸들링 부족**: `set -e`로 인해 `pkill` 명령 실패 시 스크립트 중단
3. **환경변수 로딩 이슈**: `.env` 파일 파싱 중 오류 발생

## 해결 과정

### 1단계: 문제 진단

```bash
# 현재 tmux 세션 확인
tmux ls

# 모니터링 프로세스 확인
pgrep -f "multi_monitor"

# tmux 세션 존재 여부 확인
tmux has-session -t claude-multi-monitor 2>/dev/null && echo "Session exists" || echo "Session not found"
```

### 2단계: 스크립트 통합 및 단순화

기존의 복잡한 구조를 단순화하여 `claude-ctb.sh`의 `start_monitoring()` 함수에 모든 로직을 통합:

```bash
# Start monitoring
start_monitoring() {
    cd "$CLAUDE_OPS_DIR"
    
    # Check if already running
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "${YELLOW}Multi-session monitor is already running${NC}\n"
        return 0
    fi
    
    # Kill single-session monitor if running
    tmux kill-session -t claude-monitor 2>/dev/null || true
    
    # Kill any orphaned monitoring processes
    printf "${YELLOW}Checking for orphaned monitoring processes...${NC}\n"
    if pgrep -f "multi_monitor" > /dev/null 2>&1; then
        printf "${YELLOW}Found orphaned multi_monitor processes, cleaning up...${NC}\n"
        pkill -f "multi_monitor" || true
        sleep 2
    fi
    
    # Load environment and check required variables
    if [ ! -f .env ]; then
        printf "${RED}Error: .env file not found${NC}\n"
        return 1
    fi
    
    set -a
    source .env
    set +a
    
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        printf "${RED}Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env${NC}\n"
        return 1
    fi
    
    # Start the multi-session monitor in tmux
    printf "${GREEN}Starting Multi-Session Claude Code Monitor...${NC}\n"
    tmux new-session -d -s claude-multi-monitor \
        "cd $(pwd) && uv run python -m claude_ctb.telegram.multi_monitor"
    
    # Give tmux a moment to start
    sleep 3
    
    # Check if started successfully
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "${GREEN}✅ Multi-Session Monitor started successfully${NC}\n"
        printf "\n🎯 Now monitoring ALL Claude sessions simultaneously!\n\n"
        printf "Commands:\n"
        printf "  - View logs: tmux attach -t claude-multi-monitor\n"
        printf "  - Stop monitor: tmux kill-session -t claude-multi-monitor\n\n"
        printf "🚀 The monitor will automatically detect new sessions and send\n"
        printf "   notifications when ANY Claude Code task completes!\n"
        return 0
    else
        printf "${RED}❌ Failed to start Multi-Session Monitor${NC}\n"
        return 1
    fi
}
```

### 3단계: 검증

```bash
# 모니터링 서비스 시작
claude-ctb start-monitoring

# 상태 확인
claude-ctb status

# 예상 결과:
# ✅ Multi-session monitoring: Running
```

## 핵심 개선사항

1. **외부 스크립트 의존성 제거**: 모든 로직을 메인 스크립트에 통합
2. **에러 핸들링 강화**: `|| true` 구문으로 실패해도 계속 진행
3. **환경변수 로딩 개선**: `set -a; source .env; set +a` 방식 사용
4. **단계별 검증**: 각 단계마다 상태 확인 및 피드백 제공

## 추가 고려사항

- **로그 모니터링**: `tmux attach -t claude-multi-monitor`로 실시간 로그 확인 가능
- **서비스 재시작**: 문제 발생 시 `claude-ctb stop-monitoring` 후 재시작
- **환경변수 검증**: `.env` 파일의 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 설정 필수

## 관련 파일

- `scripts/claude-ctb.sh`: 메인 스크립트 (start_monitoring 함수)
- `claude_ctb/telegram/multi_monitor.py`: 모니터링 Python 모듈
- `.env`: 환경변수 설정 파일

## 재현 단계

1. 문제 상황 재현: `claude-ctb start-monitoring` (타임아웃 발생)
2. 스크립트 수정 적용
3. 테스트 실행: `claude-ctb start-monitoring` (정상 동작)
4. 상태 확인: `claude-ctb status`