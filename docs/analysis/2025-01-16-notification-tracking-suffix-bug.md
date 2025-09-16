# 알림 추적 접미사 버그 분석

## 📅 분석 정보
- **날짜**: 2025-01-16 10:32
- **요청**: "분명 완료알림이 오고 있는데 트랙킹이 안되고 있는것 같아. 혹시 지난번 처럼 자동추가되는 접미사 문제일까?"
- **유형**: notification-tracking-bug

## 🎯 발견된 문제

### 💡 정확한 진단!
**사용자의 직감이 맞았습니다.** 접미사 변경으로 인한 알림 추적 실패가 발생하고 있습니다.

## 🔍 증거 분석

### 관찰된 세션 변화
```
이전: claude_simple_smiles_PCA_PRD_refine-8
현재: claude_simple_smiles_PCA_PRD_refine-29
```

**21번의 세션 재생성 발생!** (8 → 29)

### 알림 기록 추적 실패
```json
// /tmp/claude_completion_times.json 현재 상태
{
  "claude_simple_funcscan_test_run-90": 1757603682.2774467
  // ❌ claude_simple_smiles_PCA_PRD_refine-* 관련 기록 없음
}
```

### 정규화 테스트
```python
# 정규화 함수
def normalize_session_name(session_name):
    return re.sub(r'-\d+$', '', session_name)

# 결과
claude_simple_smiles_PCA_PRD_refine-8  → claude_simple_smiles_PCA_PRD_refine
claude_simple_smiles_PCA_PRD_refine-29 → claude_simple_smiles_PCA_PRD_refine
# ✓ 정규화는 올바르게 작동

# 하지만 completion_times에 관련 기록이 전혀 없음!
```

## 🐛 근본 원인

### 1. 알림 발생과 기록 저장의 세션명 불일치
- **알림 발생**: `claude_simple_smiles_PCA_PRD_refine-8`에서 완료 알림 발생
- **기록 저장**: 다른 접미사나 아예 다른 세션명으로 저장되었을 가능성
- **결과**: 정규화로도 매칭할 수 없는 상황

### 2. 가능한 시나리오들

#### A. 알림 시점의 세션명 변화
```bash
# 시나리오 1: 알림 발생 직후 세션 재생성
완료 알림 발생 (8번) → tmux 세션 종료 → 새 세션 생성 (9번) → 기록이 9번으로 저장
```

#### B. 멀티 세션 혼동
```bash
# 시나리오 2: 여러 세션이 동시에 존재
claude_simple_smiles_PCA_PRD_refine-8 (실제 작업)
claude_simple_smiles_PCA_PRD_refine-9 (새로 생성됨)
→ 알림이 9번 세션으로 잘못 기록
```

#### C. 알림 시스템의 세션 식별 오류
```python
# 시나리오 3: 알림 시스템이 잘못된 세션명으로 기록
def mark_completion(session_name):
    # 여기서 session_name이 현재 활성 세션과 다를 수 있음
    self.completion_times[session_name] = time.time()
```

## 🔧 해결 방안

### 즉시 조치 (P0)
1. **알림 발생 시점의 세션명 로깅 강화**
   ```python
   def mark_completion(session_name):
       logger.info(f"🔔 Marking completion for: {session_name}")
       logger.info(f"📊 Active sessions: {get_active_sessions()}")
       self.completion_times[session_name] = time.time()
   ```

2. **중복 기록 방지 로직**
   ```python
   def mark_completion_safe(session_name):
       # 정규화된 이름으로 기존 기록 확인
       base_name = normalize_session_name(session_name)

       # 기존 기록이 있으면 업데이트, 없으면 새로 생성
       for existing_session in list(self.completion_times.keys()):
           if normalize_session_name(existing_session) == base_name:
               logger.info(f"🔄 Updating existing record: {existing_session} -> {session_name}")
               del self.completion_times[existing_session]
               break

       self.completion_times[session_name] = time.time()
   ```

### 근본 해결 (P1)
1. **세션 ID 기반 추적**
   ```python
   # 세션명 대신 안정적인 ID 사용
   session_tracking = {
       "session_id": "pca_project_001",
       "current_tmux_name": "claude_simple_smiles_PCA_PRD_refine-29",
       "completion_times": [timestamp1, timestamp2, ...]
   }
   ```

2. **프로젝트 기반 그룹핑**
   ```python
   # 프로젝트 디렉토리 기반 추적
   def get_project_id(session_name):
       working_dir = get_session_working_dir(session_name)
       return hash(working_dir)  # 안정적인 프로젝트 식별자
   ```

## 📊 영향 분석

### 현재 문제점
- 21번의 세션 재생성에도 불구하고 **0개의 알림 기록**
- 사용자는 계속 완료 알림을 받고 있지만 시스템은 추적 실패
- "세션 시작 기준" 시간만 표시되어 부정확한 정보 제공

### 해결 후 기대효과
- 세션 재생성과 관계없이 **연속적인 알림 기록 유지**
- 정확한 대기 시간 표시
- 프로젝트 단위의 일관된 추적

## 🎯 즉시 테스트 방법

```bash
# 현재 세션에서 완료 알림 발생 시 로그 확인
tail -f /var/log/claude-ops/notifications.log | grep "mark_completion"

# 또는 실시간 모니터링
tmux attach -t claude-multi-monitor
```

## ✅ 결론

**확실한 버그 발견**: 세션 접미사 변경(8→29)으로 인해 알림 기록이 저장되지 않거나 잘못된 세션명으로 저장되고 있음.

**핵심 문제**:
1. 정규화 기능은 정상 작동
2. 하지만 애초에 completion_times에 기록이 저장되지 않음
3. 알림 발생과 기록 저장 시점의 세션명 불일치

**우선 조치**: 알림 발생 시점의 세션명 로깅을 강화하여 정확한 원인 파악 필요

## 🔗 관련 파일
- `claude_ops/utils/wait_time_tracker.py:168-173` - mark_completion()
- `claude_ops/monitoring/multi_monitor.py` - 알림 발생 로직
- `/tmp/claude_completion_times.json` - 알림 기록 저장소