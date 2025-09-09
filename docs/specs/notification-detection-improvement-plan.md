# 🎯 알림 감지 시스템 개선 계획

**프로젝트**: Claude-Ops Notification Detection Enhancement  
**생성일**: 2025-09-09  
**버전**: 1.0.0  
**목적**: 조용히 완료되는 작업 및 엣지 케이스 알림 감지 개선

---

## 📋 현재 문제점 분석

### 1. **감지 못하는 케이스들**

#### A. 조용한 완료 (Quiet Completions)
```bash
# 예시: 정보 나열 후 조용히 끝나는 작업들
git log --oneline -10        # 로그 출력 후 끝
docker images                 # 이미지 목록 후 끝
npm list                      # 패키지 나열 후 끝
find . -name "*.py"          # 파일 검색 결과만
```
**문제**: WORKING 상태 없이 바로 결과만 표시하고 IDLE로 전환

#### B. 중간 길이 작업 (2-5초)
```bash
# 폴링 타이밍에 따라 놓치는 경우
npm run lint                  # 3초 작업
python quick_analysis.py      # 4초 작업
```
**문제**: 5초 폴링 사이에 시작하고 끝남

#### C. 백그라운드 작업
```bash
# 백그라운드로 실행되는 작업
nohup long_process.sh &
tmux send-keys -t other-session "command"
```
**문제**: 메인 세션에서 감지 불가

### 2. **오탐 케이스들**

#### A. 잘못된 완료 알림
- 작업 중인데 잠깐 IDLE처럼 보이는 순간에 알림
- 이전 화면의 "Running..." 텍스트로 인한 오탐

#### B. 중복 알림
- 같은 작업 완료에 대해 여러 번 알림
- 30초 쿨다운이 있지만 상태 전환이 빠른 경우 문제

---

## 🎯 개선 방안

### 1. **완료 패턴 감지 추가**

#### A. 명령 프롬프트 복귀 감지
```python
class SessionStateAnalyzer:
    def __init__(self):
        # 기존 패턴들...
        
        # 새로운: 완료 후 프롬프트 패턴
        self.prompt_patterns = [
            r'\$ $',                    # Bash prompt
            r'> $',                     # Shell prompt
            r'❯ $',                     # Zsh prompt
            r'>>> $',                   # Python prompt
            r'In \[\d+\]: $',          # IPython prompt
        ]
        
        # 완료 메시지 패턴
        self.completion_patterns = [
            "Successfully",
            "Completed", 
            "Done",
            "Finished",
            "✓",
            "✅",
            "Build succeeded",
            "Tests passed",
            "0 errors",
            "took \\d+\\.\\d+s",      # 실행 시간 표시
        ]
```

#### B. 출력량 기반 감지
```python
def detect_quiet_completion(self, session_name: str) -> bool:
    """조용한 완료 감지: 많은 출력 후 멈춤"""
    
    current_screen = self.get_current_screen_only(session_name)
    
    # 1. 최근 출력량 확인
    output_lines = len(current_screen.split('\n'))
    
    # 2. 마지막 줄이 프롬프트인지 확인
    last_line = current_screen.split('\n')[-1].strip()
    is_at_prompt = any(
        re.match(pattern, last_line) 
        for pattern in self.prompt_patterns
    )
    
    # 3. 화면 변화 중단 확인 (2회 연속 같은 화면)
    screen_hash = hashlib.md5(current_screen.encode()).hexdigest()
    is_stable = (
        session_name in self._last_screen_hash and
        self._last_screen_hash[session_name] == screen_hash
    )
    
    # 4. 조건 종합
    if output_lines > 10 and is_at_prompt and is_stable:
        return True  # 조용한 완료로 판단
    
    return False
```

### 2. **상태 전환 히스토리 추적**

```python
class StateTransitionTracker:
    """상태 전환 패턴을 추적하여 더 정확한 판단"""
    
    def __init__(self):
        self.state_history = {}  # session -> [(state, timestamp), ...]
        self.max_history = 10
        
    def record_state(self, session_name: str, state: SessionState):
        """상태 기록"""
        if session_name not in self.state_history:
            self.state_history[session_name] = []
            
        history = self.state_history[session_name]
        history.append((state, time.time()))
        
        # 최대 10개만 유지
        if len(history) > self.max_history:
            history.pop(0)
    
    def detect_completion_pattern(self, session_name: str) -> bool:
        """완료 패턴 감지"""
        if session_name not in self.state_history:
            return False
            
        history = self.state_history[session_name]
        if len(history) < 3:
            return False
            
        # 패턴: IDLE → (활동) → IDLE (2초 이상 유지)
        current_time = time.time()
        
        # 현재 IDLE이고
        if history[-1][0] == SessionState.IDLE:
            # 2초 이상 IDLE 유지
            if current_time - history[-1][1] >= 2:
                # 이전에 WORKING 또는 출력 활동이 있었다면
                for state, _ in history[-5:-1]:
                    if state == SessionState.WORKING:
                        return True  # 완료 패턴
                        
        return False
```

### 3. **디버깅 유틸리티 추가**

```python
class NotificationDebugger:
    """알림 시스템 디버깅 도구"""
    
    def __init__(self):
        self.debug_log = []
        self.enable_verbose = True
        
    def log_state_change(self, session: str, prev: SessionState, 
                        curr: SessionState, reason: str):
        """상태 변경 로깅"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'session': session,
            'transition': f"{prev} → {curr}",
            'reason': reason,
            'screen_snapshot': self._capture_screen_context(session)
        }
        
        self.debug_log.append(entry)
        
        if self.enable_verbose:
            logger.debug(f"🔍 {session}: {prev}→{curr} | {reason}")
    
    def _capture_screen_context(self, session: str) -> dict:
        """화면 컨텍스트 캡처"""
        screen = get_current_screen(session)
        return {
            'last_5_lines': screen.split('\n')[-5:],
            'screen_hash': hashlib.md5(screen.encode()).hexdigest(),
            'has_working_indicator': 'esc to interrupt' in screen,
            'has_prompt': any(p in screen for p in ['$ ', '> ', '❯ '])
        }
    
    def analyze_missed_notifications(self, session: str) -> list:
        """놓친 알림 분석"""
        missed = []
        
        for i in range(1, len(self.debug_log)):
            prev = self.debug_log[i-1]
            curr = self.debug_log[i]
            
            # 완료 패턴인데 알림 안 간 경우
            if (prev['transition'].startswith('WORKING') and 
                curr['transition'].endswith('IDLE') and
                not self._notification_sent_between(prev, curr)):
                
                missed.append({
                    'time': curr['timestamp'],
                    'reason': 'Completion not detected',
                    'context': curr['screen_snapshot']
                })
                
        return missed
```

### 4. **향상된 알림 트리거**

```python
def should_send_notification_enhanced(self, session_name: str) -> tuple[bool, str]:
    """향상된 알림 판단 로직"""
    
    current_state = self.get_session_state(session_name)
    previous_state = self.last_state.get(session_name)
    
    # 1. 기존 트리거 (WORKING → 완료)
    if previous_state == SessionState.WORKING and \
       current_state != SessionState.WORKING:
        return True, "작업 완료 (WORKING → IDLE)"
    
    # 2. 새로운: 조용한 완료 감지
    if self.detect_quiet_completion(session_name):
        if not self.notification_sent.get(session_name, False):
            return True, "조용한 작업 완료 감지"
    
    # 3. 새로운: 완료 메시지 패턴
    screen = self.get_current_screen_only(session_name)
    if any(pattern in screen for pattern in self.completion_patterns):
        # 최근 10초 내 알림 없었다면
        last_notif = self.last_notification_time.get(session_name, 0)
        if time.time() - last_notif > 10:
            return True, "완료 메시지 감지"
    
    # 4. 새로운: 상태 전환 패턴
    if self.transition_tracker.detect_completion_pattern(session_name):
        return True, "완료 패턴 감지 (활동 → 유휴)"
    
    # 5. 입력 대기 (기존)
    if current_state == SessionState.WAITING_INPUT and \
       previous_state != SessionState.WAITING_INPUT:
        return True, "사용자 입력 대기"
    
    return False, ""
```

---

## 🧪 테스트 시나리오

### 테스트 케이스 1: 조용한 완료
```python
def test_quiet_completion_detection():
    """git log 같은 조용한 완료 감지"""
    
    # Given: 명령 실행 전
    monitor = MultiSessionMonitor()
    session = "test_session"
    
    # When: git log 실행 후 완료
    simulate_command(session, "git log --oneline -10")
    time.sleep(2)  # 명령 완료 대기
    
    # Then: 완료 알림 발송 확인
    should_notify, reason = monitor.should_send_notification_enhanced(session)
    assert should_notify is True
    assert "조용한 작업 완료" in reason
```

### 테스트 케이스 2: 중간 길이 작업
```python  
def test_medium_duration_task():
    """3-4초 작업 감지"""
    
    # Given: 3초 작업
    monitor = MultiSessionMonitor()
    monitor.config.check_interval = 1  # 1초로 단축
    
    # When: 중간 길이 작업 실행
    simulate_command("session", "sleep 3 && echo Done")
    
    # Then: 완료 감지
    notifications = monitor.check_all_sessions()
    assert len(notifications) == 1
    assert "완료" in notifications[0]
```

### 테스트 케이스 3: 오탐 방지
```python
def test_no_false_positive_during_work():
    """작업 중 잘못된 알림 방지"""
    
    # Given: 긴 작업 진행 중
    monitor = MultiSessionMonitor()
    simulate_long_running_command("session", "npm run build")
    
    # When: 중간에 체크 (아직 작업 중)
    time.sleep(2)
    should_notify, _ = monitor.should_send_notification_enhanced("session")
    
    # Then: 알림 없어야 함
    assert should_notify is False
```

---

## 📊 구현 우선순위

### Phase 1: 즉시 구현 (1주)
1. ✅ 완료 메시지 패턴 감지 추가
2. ✅ 프롬프트 복귀 감지
3. ✅ 디버그 로깅 강화

### Phase 2: 단기 개선 (2주)
1. 🔄 조용한 완료 감지 로직
2. 🔄 상태 전환 히스토리 추적
3. 🔄 폴링 주기 동적 조정 (활동 시 1초, 유휴 시 5초)

### Phase 3: 장기 최적화 (1개월)
1. 📅 머신러닝 기반 패턴 학습
2. 📅 사용자별 커스텀 트리거 설정
3. 📅 웹 대시보드 디버깅 UI

---

## 🎯 성공 지표

### 정량적 지표
- **감지율**: 95% 이상 (현재 ~70%)
- **오탐율**: 5% 이하 (현재 ~15%)
- **응답시간**: 평균 3초 이내 (현재 5초)

### 정성적 지표
- 사용자 신뢰도 향상
- 디버깅 용이성 개선
- 시스템 투명성 증가

---

## 🔧 구현 체크리스트

- [ ] `session_state.py`에 완료 패턴 추가
- [ ] `multi_monitor.py`에 향상된 트리거 로직 구현
- [ ] `notification_debugger.py` 신규 생성
- [ ] 테스트 케이스 작성 (최소 10개)
- [ ] 문서화 업데이트
- [ ] 성능 벤치마크 실행

---

**다음 단계**: `/구현` 명령으로 Phase 1 구현 시작