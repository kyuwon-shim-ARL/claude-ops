# PRD: Claude-Ops 작업 상태 감지 시스템 통합

**작성일:** 2025-08-13  
**작성자:** Claude & Kyuwon  
**상태:** In Progress  
**프로젝트:** Claude-Ops Session State Detection Unification

## 🔍 문제 분석: 어쩌다 이렇게 되었나?

### 1. **코드 중복의 연쇄 효과**

```
초기: 각 컴포넌트가 독립적으로 작업 감지 로직 구현
  ↓
중복 발생: monitor, notifier, working_detector 각각 다른 구현
  ↓
부분 수정: 한 곳만 수정하고 다른 곳은 누락
  ↓
불일치: 같은 상황에 대해 다른 판단
  ↓
버그: 잘못된 알림 타이밍
```

### 2. **현재 상황**

- **working_detector**: 최신 로직 (최근 20줄, 선택 프롬프트 감지)
- **notifier._is_work_running_from_content()**: 부분 통합
- **monitor.is_waiting_for_input()**: 구 로직 (전체 화면 검색)
- **monitor.is_working()**: working_detector 사용 (통합됨)

### 3. **DRY 원칙 위반의 결과**

- 같은 "작업 상태 판단" 기능이 3곳에 분산
- 수정 시 모든 곳을 찾아 변경해야 함 → 누락 발생
- 테스트도 각각 해야 함 → 복잡도 증가

---

## 📝 Executive Summary

### 1. **문제 정의**

**현재 문제:**
- 작업 상태 감지 로직이 여러 컴포넌트에 분산되어 있음
- 부분적 수정으로 인한 불일치 발생
- 동일 상황에 대해 다른 판단 결과
- 유지보수 어려움과 버그 발생

**영향:**
- 잘못된 타이밍의 알림 (작업 중인데 완료 알림)
- 누락된 알림 (완료되었는데 알림 안옴)
- 사용자 신뢰도 하락

### 2. **목표**

**Primary Goal:**
- 모든 작업 상태 감지를 단일 모듈로 통합

**Success Criteria:**
- [ ] 모든 컴포넌트가 동일한 로직 사용
- [ ] 한 곳 수정으로 전체 시스템 업데이트
- [ ] 100% 정확한 상태 감지
- [ ] 테스트 가능한 인터페이스

---

## 🛠 해결 방안

### Phase 1: 통합 모듈 설계

```python
# claude_ops/utils/session_state.py
from enum import Enum
from typing import Optional, Dict, Any

class SessionState(Enum):
    """Session state definitions"""
    WORKING = "working"           # 활발한 작업 진행 중
    WAITING_INPUT = "waiting"      # 사용자 입력 대기
    IDLE = "idle"                 # 유휴 상태
    ERROR = "error"               # 오류 상태
    UNKNOWN = "unknown"           # 알 수 없는 상태

class SessionStateAnalyzer:
    """Single source of truth for session state analysis"""
    
    def __init__(self):
        self.working_patterns = [
            "esc to interrupt",
            "Running…",
            "ctrl+b to run in background",
            "tokens · esc to interrupt)"
        ]
        
        self.input_waiting_patterns = [
            "Do you want to proceed?",
            "❯ 1.",
            "❯ 2.",
            "Choose an option:",
            "Select:",
            "Enter your choice:",
        ]
    
    def get_screen_content(self, session_name: str) -> Optional[str]:
        """Get tmux screen content with caching"""
        pass
    
    def is_working(self, session_name: str) -> bool:
        """작업 중 여부 - 최근 활동 기반"""
        pass
    
    def is_waiting_for_input(self, session_name: str) -> bool:
        """사용자 입력 대기 여부 - 프롬프트 감지"""
        pass
    
    def is_idle(self, session_name: str) -> bool:
        """유휴 상태 여부 - 활동 없음"""
        pass
    
    def get_state(self, session_name: str) -> SessionState:
        """종합 상태 반환 - 우선순위 기반"""
        pass
    
    def get_state_details(self, session_name: str) -> Dict[str, Any]:
        """상세 상태 정보 반환 - 디버깅용"""
        pass
```

### Phase 2: 기존 컴포넌트 리팩토링

#### 2.1 Monitor 리팩토링
```python
# claude_ops/telegram/multi_monitor.py
from ..utils.session_state import SessionStateAnalyzer, SessionState

class MultiSessionMonitor:
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
    
    def should_send_notification(self, session_name: str) -> bool:
        current_state = self.state_analyzer.get_state(session_name)
        previous_state = self.previous_states.get(session_name)
        
        # State transition based notification
        if previous_state == SessionState.WORKING and current_state != SessionState.WORKING:
            return True
        
        return False
```

#### 2.2 Notifier 리팩토링
```python
# claude_ops/telegram/notifier.py
from ..utils.session_state import SessionStateAnalyzer

class SmartNotifier:
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
    
    def send_work_completion_notification(self) -> bool:
        state = self.state_analyzer.get_state(self.config.session_name)
        
        if state == SessionState.WORKING:
            logger.info("Work still in progress, skipping notification")
            return False
        
        # Send notification...
```

### Phase 3: 상태 전이 관리

```python
# claude_ops/utils/state_tracker.py
class SessionStateTracker:
    """상태 변화 추적 및 알림 트리거"""
    
    def __init__(self):
        self.state_history: Dict[str, List[StateChange]] = {}
        self.state_analyzer = SessionStateAnalyzer()
    
    def track_state_change(self, session: str) -> Optional[StateTransition]:
        """상태 변화 감지 및 기록"""
        current_state = self.state_analyzer.get_state(session)
        previous_state = self.get_last_state(session)
        
        if current_state != previous_state:
            transition = StateTransition(
                session=session,
                from_state=previous_state,
                to_state=current_state,
                timestamp=datetime.now()
            )
            self.record_transition(transition)
            return transition
        
        return None
    
    def should_trigger_notification(self, transition: StateTransition) -> bool:
        """알림 트리거 여부 판단"""
        # Working -> Any other state = Completion notification
        if transition.from_state == SessionState.WORKING:
            return True
        
        # Idle -> Waiting = User input needed notification
        if transition.from_state == SessionState.IDLE and transition.to_state == SessionState.WAITING_INPUT:
            return True
        
        return False
```

---

## 📅 구현 계획

### Week 1: 통합 모듈 개발 (Day 1-3)
- [x] SessionState Enum 정의
- [x] SessionStateAnalyzer 클래스 구현
- [ ] 포괄적인 단위 테스트 작성
- [ ] 엣지 케이스 처리
- [ ] 성능 최적화 (캐싱 등)

### Week 2: 기존 시스템 마이그레이션 (Day 4-6)
- [ ] working_detector.py 기능 통합
- [ ] Monitor 컴포넌트 리팩토링
- [ ] Notifier 컴포넌트 리팩토링
- [ ] 통합 테스트
- [ ] 회귀 테스트

### Week 3: 안정화 및 배포 (Day 7+)
- [ ] 실제 환경 테스트
- [ ] 성능 모니터링
- [ ] 문서화 업데이트
- [ ] 배포 및 모니터링

---

## 🔧 기술 스펙

### 핵심 원칙

1. **Single Source of Truth**: 모든 상태 판단은 SessionStateAnalyzer에서
2. **Context-Aware**: 최근 활동 vs 전체 히스토리 구분
3. **Priority-Based**: 상태 우선순위 (WAITING_INPUT > WORKING > IDLE)
4. **Extensible**: 새로운 상태/패턴 추가 용이
5. **Testable**: 명확한 입력/출력, 모킹 가능

### 상태 정의 및 우선순위

```python
STATE_PRIORITY = {
    SessionState.ERROR: 0,         # 최우선 - 오류 상태
    SessionState.WAITING_INPUT: 1, # 사용자 응답 필요
    SessionState.WORKING: 2,       # 작업 진행 중
    SessionState.IDLE: 3,          # 유휴 상태
    SessionState.UNKNOWN: 4        # 알 수 없음
}
```

### 감지 로직

1. **Working Detection**:
   - 최근 20줄에서 working_patterns 검색
   - 과거 히스토리 무시

2. **Input Waiting Detection**:
   - 최근 10줄에서 selection prompts 검색
   - 우선순위 높음 (working보다 우선)

3. **Idle Detection**:
   - Working도 아니고 Waiting도 아닌 상태
   - 기본 상태

---

## 📊 위험 관리

### Risk Matrix

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 마이그레이션 중 서비스 중단 | High | Medium | 점진적 마이그레이션, 롤백 계획 |
| 새로운 버그 발생 | Medium | Medium | 포괄적 테스트, 단계별 배포 |
| 성능 저하 | Low | Low | 캐싱, 최적화 |
| 호환성 문제 | Medium | Low | 인터페이스 유지, 점진적 변경 |

### Rollback Plan

1. 기존 코드 백업 (git branch)
2. Feature flag로 새/구 로직 전환 가능
3. 단계별 롤백 가능한 구조

---

## 📈 성공 지표

### Quantitative Metrics

- **정확도**: 99%+ 정확한 상태 감지
- **일관성**: 100% 모든 컴포넌트 동일 결과
- **코드 중복**: 0% (완전 통합)
- **테스트 커버리지**: 95%+
- **응답 시간**: <100ms per state check

### Qualitative Metrics

- **유지보수성**: 단일 수정점
- **확장성**: 새 상태 추가 용이
- **가독성**: 명확한 코드 구조
- **신뢰성**: 예측 가능한 동작

---

## 🚀 Next Steps

1. **Immediate** (Today):
   - [x] PRD 작성 및 검토
   - [ ] session_state.py 기본 구조 구현
   - [ ] 기본 테스트 케이스 작성

2. **Short-term** (This Week):
   - [ ] 전체 모듈 구현
   - [ ] 기존 시스템 통합
   - [ ] 통합 테스트

3. **Long-term** (Next Week):
   - [ ] 프로덕션 배포
   - [ ] 모니터링 및 최적화
   - [ ] 문서화 완성

---

## 📚 References

- [DRY Principle](https://en.wikipedia.org/wiki/Don%27t_repeat_yourself)
- [Single Source of Truth](https://en.wikipedia.org/wiki/Single_source_of_truth)
- [State Pattern](https://refactoring.guru/design-patterns/state)
- Current Claude-Ops codebase analysis (2025-08-13)

---

*이 문서는 Claude-Ops 프로젝트의 작업 상태 감지 시스템을 통합하고 개선하기 위한 제품 요구사항 문서입니다.*