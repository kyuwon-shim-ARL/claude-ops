# Claude-Ops 텔레그램 봇 수정 및 Reply 파싱 개선 튜토리얼

## 개요

Claude-Ops 시스템에서 텔레그램 입력 전송 기능이 작동하지 않는 문제와 Reply 기능 파싱 오류를 해결하는 과정입니다.

## 문제 증상

### 1. 텔레그램 입력 전송 미작동
```bash
# 텔레그램에서 메시지 전송 시 Claude 세션으로 전달되지 않음
```

### 2. Reply 파싱 오류
```bash
# 텔레그램 알림에 Reply로 답장 시 세션 타겟팅 실패
```

## 근본 원인 분석

### 1. 텔레그램 봇 미실행 문제

**원인**: `start_monitoring` 변경 시 텔레그램 봇 시작 로직이 누락

- **이전 구조**: `start_multi_monitoring.sh` → 모니터링 + 텔레그램 봇 동시 시작
- **변경 후**: 통합된 `start_monitoring()` 함수에서 모니터링만 시작, 텔레그램 봇 누락

### 2. Reply 파싱 패턴 불일치

**원인**: 알림 메시지 형식과 파싱 패턴 불일치

- **알림 메시지 형식**: `🎯 **세션**: \`session_name\``
- **기존 파싱 패턴**: `세션: \`([^`]+)\`` (마크다운 Bold 누락)

## 해결 과정

### 1단계: 텔레그램 봇 시작 로직 복구

#### 기존 누락된 텔레그램 봇 확인
```bash
# 텔레그램 봇 프로세스 확인
pgrep -f "telegram.*bot" || echo "No telegram bot found"

# 기존 텔레그램 브릿지 스크립트 발견
ls scripts/start_telegram_bridge.sh
```

#### start_monitoring() 함수 수정
```bash
# scripts/claude-ops.sh 수정
start_monitoring() {
    # ... 기존 모니터링 로직 ...
    
    # Also start telegram bot if not already running
    if ! tmux has-session -t telegram-bot 2>/dev/null; then
        printf "${GREEN}Starting Telegram Bot...${NC}\n"
        tmux new-session -d -s telegram-bot \
            "cd $(pwd) && uv run python -m claude_ops.telegram.bot"
        sleep 2
        
        if tmux has-session -t telegram-bot 2>/dev/null; then
            printf "${GREEN}✅ Telegram Bot started successfully${NC}\n"
        else
            printf "${YELLOW}⚠️  Telegram Bot failed to start${NC}\n"
        fi
    else
        printf "${GREEN}✅ Telegram Bot already running${NC}\n"
    fi
}
```

#### stop_monitoring() 함수 수정
```bash
stop_monitoring() {
    # ... 기존 모니터링 중지 로직 ...
    
    # Kill telegram bot session
    tmux kill-session -t telegram-bot 2>/dev/null && \
        printf "${GREEN}✅ Stopped telegram bot${NC}\n" || \
        printf "${YELLOW}ℹ️  Telegram bot not running${NC}\n"
}
```

### 2단계: Reply 파싱 패턴 수정

#### 현재 알림 메시지 형식 확인
```python
# claude_ops/telegram/notifier.py에서 확인
message = f"""✅ **작업 완료** [`{session_name}`]

📁 **프로젝트**: `{working_dir}`
🎯 **세션**: `{session_name}`
⏰ **완료 시간**: {self._get_current_time()}

{context}

💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
```

#### 파싱 패턴 개선
```python
# claude_ops/telegram/bot.py 수정
def extract_session_from_message(self, message_text: str) -> Optional[str]:
    patterns = [
        r'\*\*🎯 세션 이름\*\*: `([^`]+)`',  # From start command
        r'🎯 \*\*세션\*\*: `([^`]+)`',       # From notification (with markdown bold)
        r'세션: `([^`]+)`',                    # From notification (simple)
        r'\[([^]]+)\]',                        # From completion notification [session_name]
        r'(claude_[\w-]+)',                    # Any claude_xxx pattern (full match)
        r'claude_(\w+)',                       # Any claude_xxx pattern (name only)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message_text)
        if match:
            session_name = match.group(1)
            # If it already starts with 'claude_', return as-is
            if session_name.startswith('claude_'):
                return session_name
            # Otherwise, add 'claude_' prefix
            elif not session_name.startswith('claude'):
                session_name = f'claude_{session_name}'
                return session_name
            return session_name
    
    return None
```

### 3단계: 상태 표시 개선

#### status 명령어에 텔레그램 봇 상태 추가
```bash
show_status() {
    # ... 기존 상태 표시 ...
    
    if tmux has-session -t telegram-bot 2>/dev/null; then
        printf "  📱 Telegram bot: ${GREEN}Running${NC}\n"
    else
        printf "  📱 Telegram bot: ${RED}Stopped${NC}\n"
    fi
}
```

## 검증 및 테스트

### 1. 패턴 매칭 테스트

```python
# 테스트 스크립트로 패턴 검증
test_messages = [
    # Current notification format
    """✅ **작업 완료** [`claude_claude-ops`]
📁 **프로젝트**: `/home/kyuwon/claude-ops`
🎯 **세션**: `claude_claude-ops`
⏰ **완료 시간**: 13:40:30
Claude가 작업을 완료했습니다.
💡 **답장하려면** 이 메시지에 Reply로 응답하세요!""",
    
    # Alternative formats
    "[claude_PaperFlow] Work completed",
    "**🎯 세션 이름**: `claude_my-project`"
]

# 결과: 모든 패턴에서 정확한 세션명 추출 확인
```

### 2. 실제 Reply 테스트

```python
# 테스트 알림 전송
test_message = """✅ **작업 완료** [`claude_claude-ops`]
📁 **프로젝트**: `/home/kyuwon/claude-ops`
🎯 **세션**: `claude_claude-ops`
⏰ **완료 시간**: 13:45:00
🧪 **테스트 알림**: Reply 파싱 테스트용 메시지입니다.
💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
```

### 3. 봇 로그 확인

```bash
# 텔레그램 봇 로그에서 확인된 정상 동작
2025-08-01 13:45:24,919 - __main__ - INFO - 사용자 985052105로부터 입력 수신: 여기로 보내지나보자...
2025-08-01 13:45:24,919 - __main__ - INFO - 📍 Reply 기반 세션 타겟팅: claude_claude-ops
2025-08-01 13:45:24,930 - __main__ - INFO - 성공적으로 전송됨: 여기로 보내지나보자 -> claude_claude-ops
```

## 최종 동작 확인

### 통합 서비스 상태
```bash
claude-ops status

📊 Claude-Ops Status

Monitoring:
  ✅ Multi-session monitoring: Running
  📱 Telegram bot: Running

Claude Sessions:
  🎯 claude-multi-monitor  
  🎯 claude_PaperFlow
  🎯 claude_claude-ops
```

### 서비스 제어
```bash
# 모든 서비스 시작 (모니터링 + 텔레그램 봇)
claude-ops start-monitoring

# 모든 서비스 중지
claude-ops stop-monitoring
```

## 핵심 개선사항

1. **완전 통합**: 단일 명령어로 모든 필수 서비스 관리
2. **정확한 파싱**: 마크다운 Bold 형식을 포함한 모든 알림 메시지 파싱 지원
3. **안정적 타겟팅**: Reply 기반으로 정확한 세션 선택
4. **실시간 피드백**: 메시지 전송 결과 즉시 확인

## 지원되는 메시지 형식

1. **알림 메시지**: `🎯 **세션**: \`claude_session-name\``
2. **브래킷 형식**: `[claude_session-name]`
3. **시작 명령**: `**🎯 세션 이름**: \`claude_session-name\``
4. **본문 패턴**: 본문 내 `claude_session-name` 자동 인식

## 사용법

### 기본 사용
1. `claude-ops start-monitoring`로 모든 서비스 시작
2. 텔레그램에서 작업 완료 알림 수신
3. 알림 메시지에 Reply로 답장하여 해당 세션에 명령 전달

### 문제 해결
- **봇 미실행**: `claude-ops status`로 상태 확인 후 `claude-ops start-monitoring` 재실행
- **세션 타겟팅 실패**: 알림 메시지에 올바른 세션명이 포함되어 있는지 확인
- **연결 문제**: `tmux attach -t telegram-bot`로 봇 로그 직접 확인

이제 Claude-Ops의 텔레그램 통합이 완전히 복구되어 다중 세션 환경에서 정확한 Reply 기반 제어가 가능합니다.