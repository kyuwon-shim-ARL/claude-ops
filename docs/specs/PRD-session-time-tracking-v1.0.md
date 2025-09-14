# PRD: Claude Session Time Tracking Improvement v1.0

## 📋 Overview

### Problem Statement
현재 7개 이상의 Claude 세션이 "추정" 시간으로 표시되며, 사용자에게 혼란스러운 "Hook 미설정" 메시지가 표시됨. 실제로는 첫 알림 전 상태이거나 알림 기록이 없는 경우임.

### Solution
tmux 세션 생성 시간과 Claude 세션 시작 시간을 정확히 추적하여, 첫 알림 전에도 정확한 대기 시간을 표시

## 🎯 Goals & Success Criteria

### Goals
1. 모든 세션에 대해 정확한 대기 시간 표시
2. "추정" 표시를 최소화
3. 사용자가 이해하기 쉬운 메시지 제공

### Success Criteria
- [ ] 새로 생성된 세션도 즉시 정확한 시간 표시
- [ ] "Hook 미설정" 메시지 제거
- [ ] tmux 세션 시작 시간을 정확히 추적
- [ ] Claude 프로세스 시작 시간도 선택적으로 추적

## 📊 Current State Analysis

### 현재 구현 (_get_fallback_wait_time)
```python
# 현재: tmux 세션 생성 시간의 80%만 사용 (보수적 추정)
session_age = current_time - created_timestamp
estimated_wait = session_age * 0.8  # 80% 추정
estimated_wait = max(300.0, estimated_wait)  # 최소 5분
```

### 문제점
1. **보수적 추정**: 실제 대기 시간보다 적게 표시
2. **최소값 강제**: 5분 미만은 모두 5분으로 표시
3. **Claude 시작 시간 미추적**: tmux 세션 != Claude 실행 시간

## 🚀 Proposed Solution

### 1. Session Start Time Tracking
```python
class SessionTimeTracker:
    """각 세션의 정확한 시작 시간 추적"""

    def __init__(self):
        self.session_start_times = {}  # {session_name: timestamp}
        self.storage_path = "/tmp/claude_session_start_times.json"
        self.load_start_times()

    def record_session_start(self, session_name: str):
        """새 세션 시작 시 기록"""
        self.session_start_times[session_name] = time.time()
        self.save_start_times()

    def get_accurate_wait_time(self, session_name: str) -> tuple[float, str]:
        """정확한 대기 시간 계산"""
        # 1순위: 완료 알림 기록
        if self.has_completion_record(session_name):
            return self.get_time_since_completion(session_name), "completion"

        # 2순위: Claude 시작 시간 (정확)
        if session_name in self.session_start_times:
            wait_time = time.time() - self.session_start_times[session_name]
            return wait_time, "session_start"

        # 3순위: tmux 생성 시간 (보완)
        tmux_time = self.get_tmux_creation_time(session_name)
        if tmux_time:
            return time.time() - tmux_time, "tmux_creation"

        # 4순위: 최소 추정값
        return 300.0, "estimated"
```

### 2. Claude Process Detection
```python
def detect_claude_start(session_name: str) -> Optional[float]:
    """Claude 프로세스 실제 시작 시점 감지"""
    # Option 1: claude 명령어 실행 감지
    cmd = f"tmux capture-pane -t {session_name} -p | grep -m1 'claude\\|Claude Code'"

    # Option 2: 특정 프롬프트 패턴 감지
    patterns = [
        "Human:",
        "Assistant:",
        "What would you like to",
        "I'll help you"
    ]

    # Option 3: Process ID 추적
    # ps aux | grep "claude.*{session_name}"
```

### 3. Message Improvement
```python
# Before
"⚠️ _추정_ 표시: Hook 미설정으로 7개 세션 시간 추정"

# After - 상황별 메시지
if source == "completion":
    indicator = ""  # 정확한 시간
elif source == "session_start":
    indicator = " (세션 시작 기준)"
elif source == "tmux_creation":
    indicator = " (tmux 생성 기준)"
else:
    indicator = " (추정)"
```

## 🧪 Test Scenarios

### Test 1: New Session Time Tracking
```python
def test_new_session_gets_accurate_time():
    """새 세션 생성 시 즉시 정확한 시간 추적"""
    # Given: 새 Claude 세션 생성
    session_name = "claude_test_project-1"
    tracker = SessionTimeTracker()

    # When: 세션 시작 기록
    tracker.record_session_start(session_name)
    time.sleep(10)

    # Then: 정확한 대기 시간 반환
    wait_time, source = tracker.get_accurate_wait_time(session_name)
    assert 9.5 < wait_time < 10.5
    assert source == "session_start"
```

### Test 2: Fallback Chain
```python
def test_fallback_priority_chain():
    """우선순위에 따른 fallback 동작"""
    tracker = SessionTimeTracker()

    # Case 1: Completion record exists
    tracker.completion_times["session1"] = time.time() - 100
    wait_time, source = tracker.get_accurate_wait_time("session1")
    assert source == "completion"

    # Case 2: Session start time exists
    tracker.session_start_times["session2"] = time.time() - 200
    wait_time, source = tracker.get_accurate_wait_time("session2")
    assert source == "session_start"

    # Case 3: Only tmux time available
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.stdout = "session3: ... (created ...)"
        wait_time, source = tracker.get_accurate_wait_time("session3")
        assert source == "tmux_creation"
```

### Test 3: Message Display
```python
def test_user_friendly_messages():
    """사용자 친화적 메시지 표시"""
    helper = SessionSummaryHelper()

    # No more "Hook 미설정" message
    summary = helper.generate_summary()
    assert "Hook 미설정" not in summary

    # Clear time source indicators
    assert "(세션 시작 기준)" in summary or "(정확)" in summary
    assert "~추정~" only appears for truly estimated times
```

## 📐 Implementation Plan

### Phase 1: Core Tracking (P0)
1. SessionTimeTracker 클래스 구현
2. project_creator.py에서 세션 생성 시 시간 기록
3. wait_time_tracker.py 개선

### Phase 2: Message Update (P0)
1. "Hook 미설정" 메시지 제거
2. 시간 소스별 명확한 표시

### Phase 3: Claude Detection (P1)
1. Claude 프로세스 시작 감지
2. 더 정확한 시간 추적

## 🎯 Expected Outcome

### Before
- 7개 세션 "추정" 표시
- "Hook 미설정으로..." 혼란스러운 메시지
- 부정확한 대기 시간

### After
- 모든 세션 정확한 시간 표시
- "(세션 시작 기준)" 등 명확한 표시
- 실제 대기 시간과 일치

## 📊 Success Metrics
- 추정 표시 세션 수: 7개 → 0개
- 시간 정확도: ±20% → ±5%
- 사용자 이해도: 향상

## 🔗 Related Files
- `claude_ops/utils/wait_time_tracker.py` - 시간 추적 로직
- `claude_ops/utils/session_summary.py` - 메시지 표시
- `claude_ops/project_creator.py` - 세션 생성 시점
- `/tmp/claude_session_start_times.json` - 시작 시간 저장 (신규)