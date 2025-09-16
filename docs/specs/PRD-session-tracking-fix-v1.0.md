# PRD: Session Tracking Fix v1.0

## 📋 Overview

### Problem Statement
세션 재생성 시 접미사 변경(예: -8 → -29)으로 인해 완료 알림 기록이 추적되지 않음. 정규화 기능은 있지만 애초에 기록이 제대로 저장되지 않는 문제.

### Solution
중복 방지 및 정규화를 고려한 안전한 기록 방식 구현

## 🎯 Goals & Success Criteria

### Goals
1. 세션 재생성과 무관하게 알림 기록 연속성 유지
2. 기존 기록과 충돌 없는 안전한 저장
3. 프로젝트 단위의 일관된 추적

### Success Criteria
- [ ] 세션 접미사가 변경되어도 이전 기록 유지
- [ ] 정규화된 세션명으로 기록 통합
- [ ] 알림 발생 시 로깅으로 추적 가능
- [ ] 90% 이상의 알림이 올바르게 기록됨

## 📊 Technical Design

### 1. Safe Marking Function
```python
def mark_completion_safe(self, session_name: str):
    """세션 정규화를 고려한 안전한 완료 기록"""
    current_time = time.time()
    base_name = self.normalize_session_name(session_name)
    
    # 로깅 강화
    logger.info(f"🔔 Marking completion for: {session_name}")
    logger.info(f"📊 Base name: {base_name}")
    
    # 기존 기록 확인 및 업데이트
    updated = False
    for existing_session in list(self.completion_times.keys()):
        if self.normalize_session_name(existing_session) == base_name:
            logger.info(f"🔄 Updating existing record: {existing_session} -> {session_name}")
            del self.completion_times[existing_session]
            updated = True
            break
    
    # 새 기록 추가
    self.completion_times[session_name] = current_time
    self._save_completions()
    
    action = "Updated" if updated else "Created"
    logger.info(f"✅ {action} completion record for {session_name} at {current_time}")
```

### 2. Enhanced Notification Handler
```python
# multi_monitor.py 수정
def send_completion_notification(self, session_name: str, wait_time: float):
    """완료 알림 발송 및 기록"""
    # 기존 알림 로직
    self.notifier.notify_completion(session_name, wait_time)
    
    # 안전한 기록 추가
    self.wait_tracker.mark_completion_safe(session_name)
```

### 3. Logging Enhancement
```python
# 알림 발생 추적을 위한 로깅
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/claude_notification_debug.log'),
        logging.StreamHandler()
    ]
)
```

## 🧪 Test Requirements

### Test 1: Suffix Change Tracking
```python
def test_completion_tracking_with_suffix_changes():
    """세션 접미사 변경 시에도 기록 유지"""
    tracker = WaitTimeTracker()
    
    # 첫 번째 세션에서 완료
    tracker.mark_completion_safe("claude_project-8")
    
    # 다른 접미사로 재생성된 세션에서 조회
    has_record = tracker.has_completion_record("claude_project-15")
    
    assert has_record is True
    wait_time = tracker.get_wait_time_since_completion("claude_project-15")
    assert wait_time < 10  # 최근 기록
```

### Test 2: Record Update on Same Project
```python
def test_record_update_for_same_project():
    """같은 프로젝트의 새 세션이 이전 기록을 대체"""
    tracker = WaitTimeTracker()
    
    # 초기 기록
    tracker.mark_completion_safe("claude_project-8")
    initial_count = len(tracker.completion_times)
    
    # 같은 프로젝트, 다른 접미사
    time.sleep(1)
    tracker.mark_completion_safe("claude_project-29")
    
    # 기록 개수는 동일 (대체됨)
    assert len(tracker.completion_times) == initial_count
    assert "claude_project-29" in tracker.completion_times
    assert "claude_project-8" not in tracker.completion_times
```

### Test 3: Logging Verification
```python
def test_completion_logging():
    """알림 기록 시 적절한 로그 생성"""
    with patch('logging.Logger.info') as mock_log:
        tracker = WaitTimeTracker()
        tracker.mark_completion_safe("claude_test-5")
        
        # 로그 호출 검증
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Marking completion for: claude_test-5" in log for log in log_calls)
        assert any("Base name: claude_test" in log for log in log_calls)
```

## 📐 Implementation Plan

### Phase 1: Core Fix (P0)
1. `mark_completion_safe()` 구현
2. `multi_monitor.py`에서 호출 변경
3. 로깅 강화

### Phase 2: Verification (P0)
1. 실제 세션에서 테스트
2. 로그 분석으로 동작 확인
3. 기존 기록과의 호환성 검증

### Phase 3: Future Improvements (P1)
1. 프로젝트 ID 기반 추적
2. 세션 그룹 관리
3. 통계 대시보드

## 🎯 Expected Outcome

### Before
- 세션 재생성 시 기록 손실
- "세션 시작 기준" 부정확한 표시
- 21번 재생성에 0개 기록

### After
- 세션 재생성과 무관하게 기록 유지
- 정확한 대기 시간 표시
- 모든 알림 추적 가능

## 📊 Success Metrics
- 알림 기록 성공률: 50% → 95%
- 세션 추적 정확도: ±80% → ±5%
- 사용자 만족도: 향상