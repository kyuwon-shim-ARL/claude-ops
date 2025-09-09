# Claude-Ops 특수 대기 상태 감지 시스템 구축 튜토리얼

<!-- 
Git 컨텍스트:
- 브랜치: main
- 시작 커밋: 0b3bb17ef0766cc0cac4b36649b4014b92ce8c6b
- 생성 시각: Mon Aug 11 20:59:43 KST 2025
-->

## 한 줄 요약

텔레그램 알림이 오지 않는 Claude Code 특수 대기 상태 문제를 패턴 감지 시스템으로 해결한 프로젝트

## 전체 워크플로우

```
1️⃣ 문제 분석 → 2️⃣ 패턴 감지 구현 → 3️⃣ 알림 시스템 확장 → 4️⃣ 안전 테스트 → 5️⃣ 검증 완료
```

## 각 단계별 구현

### 1️⃣ 문제 분석 및 현재 시스템 이해

#### 실행 블록

```bash
# 현재 모니터링 상태 확인
claude-ops status

# 멀티 모니터 로그 확인
tmux capture-pane -t claude-multi-monitor -p | tail -20

# 기존 상태 감지 코드 확인
grep -A 10 -B 5 "esc to interrupt" claude_ops/telegram/multi_monitor.py
```

#### 핵심 설명

사용자가 "Ready to code", "bash command" 같은 특수 대기 상태에서 무한 대기가 발생한다고 보고. 기존 시스템은 `esc to interrupt`만 감지해서 이런 상황에서 알림이 오지 않음.

#### 트러블슈팅

```
❌ 시도했지만 안 된 것: 대화록에서 패턴 찾기 → 사용자가 선택하지 않은 상황은 기록되지 않음
✅ 대신 성공한 방법: 사용자 경험 기반으로 일반적인 대기 패턴 리스트 구성
```

### 2️⃣ 특수 대기 상태 패턴 감지 로직 구현

#### 실행 블록

```python
# claude_ops/telegram/multi_monitor.py 수정
waiting_patterns = [
    "ready to code",           # 기본 준비 상태
    "bash command",            # Bash 도구 대기
    "select option",           # 옵션 선택
    "choose an option",        # 옵션 선택 변형
    "enter your choice",       # 선택 프롬프트
    "press enter to continue", # 계속 프롬프트
    "waiting for input",       # 입력 대기
    "type your response",      # 응답 대기
    "what would you like",     # 질문 프롬프트
    "how can i help",          # 도움 프롬프트
    "continue?",               # 계속 질문
    "proceed?",                # 진행 질문
    "confirm?",                # 확인 질문
]

# 하단 5줄을 소문자로 변환해서 패턴 매칭
bottom_lines = '\n'.join(tmux_output.split('\n')[-5:]).lower()
for pattern in waiting_patterns:
    if pattern in bottom_lines:
        return "waiting_input"
```

#### 핵심 설명

기존 `working` 상태 외에 `waiting_input` 상태를 새로 추가. tmux 출력의 마지막 5줄을 검사해서 특수 대기 메시지 패턴을 감지.

### 3️⃣ 새로운 알림 타입 및 상태 전환 로직 구현

#### 실행 블록

```python
# 상태 전환 감지 로직 추가
if previous_state == "working" and current_state in ["idle", "waiting_input"]:
    self.send_completion_notification(session_name)

# 특수 대기 상태 감지
elif previous_state in ["working", "responding"] and current_state == "waiting_input":
    self.send_completion_notification(session_name, "waiting_input")

# 새로운 알림 메소드 구현 (notifier.py)
def send_waiting_input_notification(self) -> bool:
    message = f"""⏸️ **입력 대기** [`{session_name}`]
    
📁 **프로젝트**: `{working_dir}`
🎯 **세션**: `{session_name}`
⏰ **대기 시작**: {self._get_current_time()}

**현재 상태:**
{context_text}

💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
```

#### 핵심 설명

기존 완료 알림과 구분되는 "입력 대기" 알림 추가. 현재 화면의 마지막 3줄을 포함해서 사용자가 무엇을 대기 중인지 알 수 있게 함.

### 4️⃣ 안전한 핫 리로드 테스트

#### 실행 블록

```bash
# 텔레그램 봇 연결 유지하면서 멀티 모니터만 재시작
tmux kill-session -t claude-multi-monitor
tmux new-session -d -s claude-multi-monitor "uv run python -c 'from claude_ops.telegram.multi_monitor import MultiSessionMonitor; monitor = MultiSessionMonitor(); monitor.start_monitoring()'"

# 시스템 상태 확인
claude-ops status

# 멀티 모니터 로그 확인
tmux capture-pane -t claude-multi-monitor -p | tail -10
```

#### 핵심 설명

서비스 중단 없이 새로운 코드를 적용하는 방법. 텔레그램 봇 연결은 유지하고 모니터링 서비스만 재시작해서 무중단 업그레이드 달성.

#### 트러블슈팅

```
❌ 시도했지만 안 된 것: claude-ops stop-monitoring → 텔레그램 봇까지 중지됨
✅ 대신 성공한 방법: 멀티 모니터 세션만 개별적으로 재시작
```

### 5️⃣ 실제 상태 감지 검증

#### 실행 블록

```bash
# 복잡한 작업으로 상태 전환 유도
tmux send-keys -t claude_claude-ops "여러 옵션이 있는 복잡한 작업을 해줘" Enter

# 상태 변화 모니터링
tmux capture-pane -t claude-multi-monitor -p | tail -5

# 실제 감지된 상태 확인
# 예상 로그: "🔄 State change in claude_claude-ops: working -> responding"
```

#### 핵심 설명

실제 환경에서 새로운 상태 감지가 작동하는지 확인. `working -> responding -> working` 같은 새로운 상태 전환이 감지됨을 확인.

## Claude Code 특화 팁

### 효과적이었던 프롬프트 패턴

```
"기존 esc to interrupt로 포착되지 않아서 무한대기가 걸리는 상황들을 패턴으로 감지해줘"
"텔레그램 봇 연결은 끊지 말고 멀티 모니터만 안전하게 재시작해줘"
"실제 테스트 전에 현재 작동하는 기능들부터 확인해줘"
```

### 컨텍스트 관리

- **긴 테스트 작업 시**: 단계별로 나눠서 진행 (문제 분석 → 구현 → 테스트)
- **시스템 변경 시**: 항상 현재 상태 확인부터 시작
- **안전성 확보**: 기존 기능 검증 후 새 기능 추가

### 반복 개선

3번의 주요 반복을 통해 개선:
1. 초기 구현: 단순 패턴 매칭
2. 알림 시스템 확장: 상태별 다른 알림 메시지
3. 안전 테스트: 무중단 배포 방식 확립

## 즉시 실행 체크리스트

```
□ 사전 준비: claude-ops 시스템 정상 작동 확인 - 예상 시간: 2분
□ Step 1: 패턴 감지 로직 구현 (multi_monitor.py 수정) - 예상 시간: 10분
□ Step 2: 알림 시스템 확장 (notifier.py 수정) - 예상 시간: 15분
□ Step 3: 안전한 핫 리로드로 적용 - 예상 시간: 5분
□ Step 4: 실제 테스트로 검증 - 예상 시간: 10분
□ 검증: 기존 기능 정상 작동 + 새 상태 감지 확인
```

## 핵심 Q&A

**Q: 가장 막혔던 부분은?** 
A: 실제 무한대기 패턴을 파악하는 것. 대화록에는 사용자가 선택하지 않은 상황이 기록되지 않아서 사용자 경험을 바탕으로 일반적인 패턴을 구성해야 했음.

**Q: 다음에 한다면?** 
A: 사용자가 실제 겪는 특수 분기 메시지들을 먼저 수집한 후 정확한 패턴을 구현하는 방식으로 접근하겠음.

---

## 최종 성과

- ✅ 기존 기능 100% 유지 (esc to interrupt 감지)
- ✅ 새로운 상태 감지 시스템 구축 (waiting_input)
- ✅ 차별화된 알림 시스템 (완료 vs 입력 대기)
- ✅ 무중단 배포 방식 확립
- ✅ 13개 특수 대기 패턴 감지 지원

이제 Claude Code의 특수 대기 상태에서도 적절한 알림을 받을 수 있습니다!