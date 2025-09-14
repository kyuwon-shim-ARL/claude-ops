# Session Summary "추정" 표시 문제 분석

## 📅 분석 정보
- **날짜**: 2025-01-14 16:45
- **요청**: "세션 summary에서 최초 알림이 아니면 latest 알림 시간이 저장되어야 하는데 추정으로 나오는 이유"
- **유형**: data-persistence

## 📊 문제 분석

### 핵심 발견사항

#### 1. Session Name 변동성 문제 ✅ 확인됨
**현재 활성 세션들:**
```
cladue_PaperFlow-10          <- 오타 있음
claude_SMILES_property_webapp-4
claude_UMT_opt-16
claude_claude-dev-kit-1
claude_urban-microbiome-toolkit-5
claude_claude-ops-2
```

**저장된 completion_times:**
```json
{
  "claude_simple_funcscan_test_run-90": 1757603682.2774467
}
```

**session_history:**
```json
[
  "claude_session",
  "claude_meeting_minutes-9",
  "claude_simple_smiles_PCA-3",
  "claude_SMILES_property_webapp-4",
  "claude_simple_smiles_PCA_PRD_refine-8",
  "claude_claude-dev-kit-1",
  "claude_urban-microbiome-toolkit-5",
  "claude_claude-ops-2",
  "claude_UMT_opt-16"
]
```

### 문제의 진짜 원인

#### A. 세션 이름 불일치 (핵심 문제)
- **저장된 알림**: `claude_simple_funcscan_test_run-90`
- **현재 활성**: 해당 세션 없음 (이미 종료됨)
- **결과**: 새로운 세션들은 completion_times에 기록이 없어서 "추정" 표시

#### B. 세션 생성 패턴의 일관성 부족
1. **tmux new-session 사용 시**: `claude_project-name-숫자`
2. **숫자 접미사**: 랜덤하게 증가 (1, 2, 3... 또는 더 큰 수)
3. **세션 삭제/재생성**: 새로운 숫자 접미사 부여

#### C. 알림 시간 추적의 한계
```python
# wait_time_tracker.py
def has_completion_record(self, session_name: str) -> bool:
    has_completion = session_name in self.completion_times  # 정확한 이름 매칭 필요
    has_notification = session_name in self.last_notification_time
    return has_completion or has_notification
```

### 구체적 시나리오

#### 시나리오 1: 세션 재생성
```bash
# 이전 세션
tmux new-session -s claude_project-5
# → completion_times["claude_project-5"] = 1234567890

# 세션 종료 후 재시작
tmux new-session -s claude_project-8  # 다른 숫자!
# → completion_times에 "claude_project-8" 없음
# → "추정" 표시됨
```

#### 시나리오 2: 프로젝트 이름 변화
```bash
# 작업 진행하면서 세션명 변화
claude_simple_PCA-3       → claude_simple_smiles_PCA-3
claude_SMILES_webapp-4    → claude_SMILES_property_webapp-4
# → 세션명이 미세하게 변해서 기록 연결 실패
```

### 해결 방안

#### 1. 세션 이름 정규화 (단기)
```python
def normalize_session_name(session_name: str) -> str:
    """세션 이름을 기본 형태로 정규화"""
    # claude_project-name-숫자 → claude_project-name
    import re
    base_name = re.sub(r'-\d+$', '', session_name)
    return base_name

def has_completion_record_flexible(self, session_name: str) -> bool:
    """유연한 세션 이름 매칭"""
    base_name = normalize_session_name(session_name)

    # 정확한 매칭 우선
    if session_name in self.completion_times:
        return True

    # 기본 이름으로 매칭
    for stored_session in self.completion_times.keys():
        if normalize_session_name(stored_session) == base_name:
            return True

    return False
```

#### 2. 프로젝트 기반 추적 (중기)
```python
# 세션 이름 대신 프로젝트 디렉토리 기반 추적
def get_project_id(session_name: str) -> str:
    """세션의 프로젝트 ID 추출"""
    # working directory 기반으로 고유 식별
    working_dir = get_session_working_dir(session_name)
    return hashlib.md5(working_dir.encode()).hexdigest()[:8]
```

#### 3. 알림 이력 통합 관리 (장기)
```python
class NotificationHistory:
    def __init__(self):
        self.history = {
            "project_id": {
                "sessions": ["claude_project-1", "claude_project-2"],
                "last_notification": 1757603682.27,
                "total_notifications": 5
            }
        }
```

## 💡 권장 조치

### 즉시 구현 (P0)
1. **세션 이름 정규화**: 숫자 접미사 제거하여 매칭
2. **fallback 로직 개선**: 비슷한 이름 패턴 검색

### 단기 개선 (P1)
3. **프로젝트 디렉토리 기반**: working directory로 프로젝트 식별
4. **세션 연속성**: 같은 프로젝트의 새 세션 = 기존 기록 상속

### 장기 해결 (P2)
5. **통합 이력 관리**: 프로젝트 단위 알림 이력 DB
6. **세션 생성 표준화**: 일관된 naming convention

## 🎯 예상 효과

**Before:**
- 세션 재생성 → "추정" 표시
- 프로젝트명 변경 → 기록 손실

**After:**
- 세션 재생성 → 실제 시간 표시 유지
- 프로젝트 연속성 → 알림 이력 보존

## 📊 영향 범위
- **사용자 경험**: 정확한 대기 시간 정보 제공
- **시스템 신뢰도**: 일관된 데이터 추적
- **운영 효율성**: 세션 관리 간소화

## 🔗 관련 파일
- `claude_ops/utils/wait_time_tracker.py:198-207` - has_completion_record()
- `claude_ops/utils/session_summary.py:493-497` - 추정 표시 로직
- `/tmp/claude_completion_times.json` - 알림 시간 저장소
- `/tmp/claude_ops_active_session.json` - 세션 이력