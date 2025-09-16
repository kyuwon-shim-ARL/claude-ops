# 세션 대기시간 표시 불일치 분석

## 📅 분석 정보
- **날짜**: 2025-01-16 08:20
- **요청**: "claude_simple_smiles_PCA_PRD_refine-8 이 세션 보면 지금 알림 오고 주고받고있는데 왜 대기시간은 3시간이야?"
- **유형**: notification-timing-discrepancy

## 📊 현상 분석

### 관찰된 문제
- **세션명**: `claude_simple_smiles_PCA_PRD_refine-8`
- **현재 상태**: 활발히 알림 주고받는 중
- **표시된 대기시간**: 약 3시간
- **실제 세션 나이**: 91.2시간 (3일 19시간)

### 불일치 원인
**알림 기록이 없어서 발생한 문제입니다.**

## 🔍 근본 원인

### 1. 완료 알림 기록 부재
```json
// /tmp/claude_completion_times.json
{
  "claude_simple_funcscan_test_run-90": 1757603682.27,
  "claude_UMT_opt-26": 1757917283.00,
  "claude_KoreanClimateDiseasePaperReview-25": 1757978326.81
  // ❌ claude_simple_smiles_PCA_PRD_refine-8 없음
}
```

### 2. Fallback 메커니즘 동작
`claude_simple_smiles_PCA_PRD_refine-8` 세션에 대한 기록이 없어서:
1. `has_completion_record()` → False
2. `_get_fallback_wait_time()` 호출
3. tmux 세션 생성 시간 기반 계산
4. 91.2시간 → 표시 제한으로 "3시간"으로 표시

### 3. 왜 기록이 없을까?

#### 가능성 1: 장기 실행 세션
- 세션이 3일 이상 실행 중
- 한 번도 완료 알림이 발생하지 않음
- 계속 작업 중이거나 대기 상태 유지

#### 가능성 2: 시스템 재시작
- claude-ops 재시작 시 일부 알림 기록 손실
- 특히 장기 실행 세션의 경우 초기 알림 누락 가능

#### 가능성 3: 알림 시스템 미작동
- 해당 세션 생성 당시 알림 시스템이 꺼져있었을 가능성
- 또는 알림이 발생했지만 기록되지 않음

## 💡 해결 방안

### 즉시 조치 (수동)
```bash
# 현재 세션에 대한 완료 시간 수동 기록
python3 -c "
import json
import time
data = json.load(open('/tmp/claude_completion_times.json'))
data['claude_simple_smiles_PCA_PRD_refine-8'] = time.time()
json.dump(data, open('/tmp/claude_completion_times.json', 'w'))
print('✓ 알림 시간 기록됨')
"
```

### 장기 개선 방안

#### 1. 세션 시작 시간 추적 (이미 PRD 작성됨)
```python
# /tmp/claude_session_start_times.json
{
  "session_name": timestamp,
  ...
}
```

#### 2. 주기적 상태 스냅샷
- 매 시간마다 활성 세션 상태 기록
- 장기 실행 세션도 정확한 시간 추적

#### 3. 알림 기록 복구 로직
```python
def recover_missing_records():
    """오래된 세션의 누락된 기록 복구"""
    for session in active_sessions:
        if not has_completion_record(session):
            # 세션 나이가 1일 이상이면 현재 시간 기록
            if get_session_age(session) > 86400:
                mark_completion(session)
```

## 📈 영향 분석

### 현재 영향
- **사용자 혼란**: 활발한 세션인데 "3시간 대기"로 표시
- **정확도 문제**: 실제 91시간 vs 표시 3시간
- **신뢰성 저하**: 시스템 정보의 신뢰도 하락

### 개선 후 효과
- 모든 세션의 정확한 시간 표시
- 장기 실행 세션도 올바른 추적
- 사용자 신뢰도 향상

## 🎯 권장 조치

### P0: 긴급
1. 해당 세션 알림 기록 수동 추가
2. 다른 장기 실행 세션 확인

### P1: 중요
1. 세션 시작 시간 추적 구현
2. 주기적 상태 스냅샷 구현

### P2: 개선
1. 알림 기록 복구 자동화
2. 대시보드에 실제 세션 나이 표시

## ✅ 결론

**문제**: `claude_simple_smiles_PCA_PRD_refine-8` 세션이 91시간(3일 19시간) 동안 실행 중이지만, 완료 알림 기록이 없어서 대기 시간이 부정확하게 표시됨

**원인**: `/tmp/claude_completion_times.json`에 해당 세션 기록 부재

**해결**:
1. 즉시: 수동으로 알림 시간 기록
2. 장기: 세션 시작 시간 추적 시스템 구현 (PRD 이미 작성됨)

이는 장기 실행 세션의 일반적인 문제로, 시스템 개선이 필요합니다.

## 🔗 관련 파일
- `/tmp/claude_completion_times.json` - 알림 시간 저장
- `claude_ops/utils/wait_time_tracker.py` - 시간 계산 로직
- `docs/specs/PRD-session-time-tracking-v1.0.md` - 개선 계획