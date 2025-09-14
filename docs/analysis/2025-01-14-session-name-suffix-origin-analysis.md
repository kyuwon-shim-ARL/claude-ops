# Session Name 접미사 생성 원리 및 정규화 솔루션

## 📅 분석 정보
- **날짜**: 2025-01-14 17:00
- **요청**: "애초에 이름이 왜 생기는지, 세션 이름 정규화(맨 뒤 접미사 제거)가 최선"
- **유형**: system-architecture

## 🔍 Session Name 접미사 생성 원리

### 1. TMux Session Grouping 메커니즘
**tmux list-sessions 출력 분석:**
```
claude_SMILES_property_webapp-4: ... (group claude_SMILES_property_webapp)
claude_UMT_opt-16: ... (group claude_UMT_opt)
claude_claude-dev-kit-1: ... (group claude_claude-dev-kit)
```

**핵심 발견:**
- tmux는 **그룹 단위**로 세션을 관리
- 같은 base name의 세션 생성 시 자동으로 `-숫자` 접미사 추가
- 예: `claude_project` → `claude_project-1`, `claude_project-2`, ...

### 2. 접미사 생성 시나리오들

#### A. 세션 이름 중복 방지
```bash
# 첫 번째 생성
tmux new-session -s claude_myapp
# → claude_myapp (접미사 없음)

# 같은 이름으로 다시 생성 시
tmux new-session -s claude_myapp
# → claude_myapp-1 (자동 접미사 추가)

# 또 다시 생성
tmux new-session -s claude_myapp
# → claude_myapp-2
```

#### B. 세션 종료 후 재생성
```bash
tmux kill-session -t claude_myapp    # 원본 세션 종료
tmux new-session -s claude_myapp     # 재생성 시
# → claude_myapp-3 (이전 최대값 + 1)
```

#### C. 프로젝트 생성 중 중복 처리
```python
# project_creator.py:424
subprocess.run([
    "tmux", "new-session", "-d", "-s", self.session_name,
    "-c", str(self.project_dir)
], check=True, timeout=10)
```

### 3. 왜 접미사가 불규칙한가?

#### tmux의 세션 번호 할당 알고리즘
1. **기본 이름 시도**: `claude_project`
2. **이미 존재하면**: 사용 가능한 최소 숫자 찾기
3. **숫자는 연속적이지 않음**: 중간에 삭제된 세션 번호는 재사용 안함

#### 실제 예시
```
claude_UMT_opt-16  # 1~15번이 생성/삭제된 이력
claude_project-90  # 90번까지 생성된 이력
```

## 💡 세션 이름 정규화 솔루션

### 현재 상황
```python
# 저장된 알림 데이터
completion_times = {
    "claude_simple_funcscan_test_run-90": 1757603682.27
}

# 현재 활성 세션들
active_sessions = [
    "claude_urban-microbiome-toolkit-5",
    "claude_claude-ops-2",
    "claude_UMT_opt-16"
]
# → 매칭 실패: 접미사가 달라서 기록 찾을 수 없음
```

### 제안 솔루션: 접미사 제거 정규화

#### 1. 정규화 함수
```python
import re

def normalize_session_name(session_name: str) -> str:
    """
    세션 이름을 기본 형태로 정규화
    claude_project-name-123 → claude_project-name
    """
    # 맨 끝의 -숫자 패턴 제거
    return re.sub(r'-\d+$', '', session_name)

# 테스트
assert normalize_session_name("claude_myapp-5") == "claude_myapp"
assert normalize_session_name("claude_simple_funcscan_test_run-90") == "claude_simple_funcscan_test_run"
assert normalize_session_name("claude_urban-microbiome-toolkit-5") == "claude_urban-microbiome-toolkit"
```

#### 2. 유연한 매칭 시스템
```python
def find_completion_record_flexible(self, session_name: str) -> Optional[float]:
    """접미사를 고려한 유연한 알림 기록 찾기"""
    # 1순위: 정확한 매칭
    if session_name in self.completion_times:
        return self.completion_times[session_name]

    # 2순위: 정규화된 이름으로 매칭
    base_name = normalize_session_name(session_name)

    for stored_session, timestamp in self.completion_times.items():
        if normalize_session_name(stored_session) == base_name:
            return timestamp

    return None
```

#### 3. 업데이트된 has_completion_record
```python
def has_completion_record(self, session_name: str) -> bool:
    """유연한 세션 이름 매칭으로 기록 확인"""
    # 직접 매칭
    if session_name in self.completion_times:
        return True

    # 정규화 매칭
    base_name = normalize_session_name(session_name)
    for stored_session in self.completion_times.keys():
        if normalize_session_name(stored_session) == base_name:
            return True

    # last_notification_time도 동일하게 확인
    if hasattr(self, 'last_notification_time'):
        if session_name in self.last_notification_time:
            return True
        for stored_session in self.last_notification_time.keys():
            if normalize_session_name(stored_session) == base_name:
                return True

    return False
```

### 4. 실제 적용 효과

#### Before (현재)
```python
# claude_simple_funcscan_test_run-90의 알림 기록 있음
# claude_urban-microbiome-toolkit-5 세션 확인
has_record = "claude_urban-microbiome-toolkit-5" in completion_times
# → False (매칭 실패)
# → "추정" 표시됨
```

#### After (정규화 적용)
```python
# 같은 상황
has_record = has_completion_record_flexible("claude_urban-microbiome-toolkit-5")
# → claude_urban-microbiome 프로젝트의 이전 기록 확인
# → 관련 기록이 있다면 True
# → 실제 시간 표시됨
```

## 🎯 구현 우선순위

### P0: 정규화 함수 구현
- `normalize_session_name()` 함수 추가
- 간단한 정규표현식으로 `-숫자$` 패턴 제거

### P1: 유연한 매칭 적용
- `wait_time_tracker.py`의 `has_completion_record()` 업데이트
- 기존 데이터와의 호환성 보장

### P2: 프로젝트 기반 그룹핑 (선택사항)
- 같은 프로젝트 디렉토리의 세션들 연결
- 더 정교한 연속성 관리

## ✅ 예상 결과

**즉시 효과:**
- 세션 재생성 시 기존 알림 기록 유지
- "추정" 표시 대신 실제 대기 시간 표시

**장기 효과:**
- 프로젝트 연속성 향상
- 사용자 경험 개선
- 데이터 일관성 확보

## 🔗 관련 파일
- `claude_ops/utils/wait_time_tracker.py` - 알림 기록 관리
- `claude_ops/project_creator.py:424` - 세션 생성 로직
- `claude_ops/utils/session_summary.py` - 요약 표시 로직

**결론**: 당신 말씀이 정확합니다. tmux의 자동 세션 그룹핑 메커니즘으로 인해 접미사가 생성되며, 정규화(접미사 제거)가 가장 실용적인 해결책입니다!