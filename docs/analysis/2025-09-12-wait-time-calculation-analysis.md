# `/summary` 대기시간 계산 메커니즘 분석

## 📅 분석 정보
- **날짜**: 2025-09-12 11:25
- **요청**: 지금 /summary 에서 대기시간 계산 무슨 방법으로 이뤄지고 있어?
- **유형**: technical-architecture
- **분석자**: Claude Code

## 📊 분석 결과

### 1. 대기시간 계산 아키텍처

#### 핵심 컴포넌트 구조
```
SessionSummaryHelper (session_summary.py)
    ↓
ImprovedWaitTimeTracker v2 (wait_time_tracker_v2.py)
    ↓
JSON 파일 저장소 (/tmp/claude_completion_times.json)
```

### 2. 대기시간 정의

**사용자 정의**: "세션이 마지막으로 작업을 완료한 이후 경과한 시간"

```python
# session_summary.py:47
wait_time, is_accurate = self.tracker.get_wait_time_since_completion(session_name)
```

### 3. 계산 메커니즘 상세

#### 3.1 Primary Method: Completion Time Tracking

**정확한 기록이 있는 경우 (is_accurate = True)**:

```python
# wait_time_tracker_v2.py:188-190
completion_time = self.completion_times[session_name]
wait_time = current_time - completion_time
return (wait_time, True)  # Accurate time
```

**작동 원리**:
1. 작업 완료 시점이 JSON 파일에 기록됨
2. 현재 시간 - 완료 시간 = 대기 시간
3. 정확도 플래그 True 반환

#### 3.2 Fallback Method: Intelligent Estimation

**기록이 없는 경우 (is_accurate = False)**:

```python
# wait_time_tracker_v2.py:206
def _get_intelligent_fallback(self, session_name: str) -> float:
```

**추정 알고리즘 (우선순위 순)**:

1. **tmux 세션 활동 시간 기반**:
   - tmux의 `session_activity` 타임스탬프 확인
   - 최근 활동(< 5분): 해당 시간 그대로 사용
   - 오래된 활동: 시간의 50%를 대기시간으로 추정

2. **화면 내용 패턴 분석**:
   - 완료 표시 발견 ('completed', 'done', '✓'): 7.5분 추정
   - 대기 표시 발견 ('waiting', 'ready', '>'): 30분 추정

3. **최종 폴백**: 15분 (중립적 추정값)

### 4. 자동 검증 및 복구 메커니즘

#### 4.1 타임스탬프 자동 검증
```python
# wait_time_tracker_v2.py:95
def _auto_validate(self):
    # 5분마다 자동 실행
    # 미래 타임스탬프 수정
    # 72시간 이상 오래된 기록 제거
```

#### 4.2 상태 전환 기반 자동 완료 기록
```python
# wait_time_tracker_v2.py:159-161
if old_state == "working" and new_state == "waiting":
    self.mark_completion(session_name, force=True)
```

### 5. UI 표시 방식

#### 5.1 정확한 시간 표시
```
🎯 **session_name** (15분 대기)
```

#### 5.2 추정 시간 표시 (투명성)
```
🎯 **session_name** (15분 대기 ~추정~)
```

### 6. 문제점 및 개선 사항

#### 현재 시스템의 강점
1. **자동 복구**: 놓친 알림도 상태 전환으로 복구
2. **투명성**: 추정값임을 명확히 표시
3. **지능적 폴백**: 다단계 추정 알고리즘
4. **자동 검증**: 비정상 타임스탬프 자동 수정

#### 잠재적 개선 영역
1. **Hook 설정 권장**: 정확한 시간 추적을 위해
2. **세션별 설정**: 세션별로 다른 추정 전략 적용 가능
3. **히스토리 기반 학습**: 과거 패턴으로 더 정확한 추정

### 7. 코드 흐름도

```mermaid
graph TD
    A[/summary 명령] --> B[SessionSummaryHelper]
    B --> C{세션 상태 확인}
    C -->|작업중| D[대기시간 계산 안함]
    C -->|대기중| E[get_wait_time_since_completion]
    E --> F{완료 기록 존재?}
    F -->|Yes| G[현재시간 - 완료시간]
    F -->|No| H[지능적 폴백]
    H --> I[tmux 활동 시간]
    H --> J[화면 패턴 분석]
    H --> K[기본값 15분]
    G --> L[정확한 시간 표시]
    I --> M[추정 시간 표시 ~추정~]
    J --> M
    K --> M
```

## 💾 관련 파일
- 핵심 로직: `claude_ops/utils/session_summary.py`
- 시간 추적: `claude_ops/utils/wait_time_tracker_v2.py`
- UI 구현: `claude_ops/telegram/bot.py`
- 데이터 저장: `/tmp/claude_completion_times.json`

## 🔗 관련 분석
- [세션 상태 감지 시스템](./session-state-detection.md)
- [알림 시스템 아키텍처](./notification-system-architecture.md)

## 💡 핵심 인사이트

1. **이중 추적 시스템**: 정확한 기록 + 지능적 추정의 하이브리드 접근
2. **투명성 우선**: 사용자에게 추정값임을 명확히 표시
3. **자동 복구**: 시스템 장애에도 대응 가능한 복원력
4. **실용적 설계**: Hook 없어도 작동하는 graceful degradation

## 🎯 결론

`/summary` 명령의 대기시간 계산은 **ImprovedWaitTimeTracker v2**를 통해 이루어지며, 정확한 완료 시간 기록이 있으면 그것을 사용하고, 없으면 tmux 세션 정보와 화면 패턴 분석을 통한 지능적 추정을 수행합니다. 시스템은 자동 검증과 복구 메커니즘을 갖추고 있어 안정적이며, 사용자에게 추정값 여부를 투명하게 표시합니다.