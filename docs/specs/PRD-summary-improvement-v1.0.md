# PRD: /summary 커맨드 개선 v1.0

**작성일**: 2025-09-03  
**담당자**: Claude Code Assistant  
**분류**: Tactical (전술층) - UX 개선

---

## 📋 Executive Summary

Claude-Ops의 `/summary` 커맨드에서 발생하는 **대기시간 계산 오류**와 **비효율적인 정렬 순서** 문제를 해결하여 사용자 경험을 개선합니다. 현재 미래 타임스탬프 문제로 모든 세션이 "추정" 표시되며, 작업중 세션을 확인하기 위해 스크롤이 필요한 상황을 해결합니다.

## 🎯 Product Vision

**"Claude 세션 상태를 한 눈에 정확하게 파악할 수 있는 스마트한 요약 시스템"**

실시간으로 세션 상태를 모니터링하며, 작업 우선순위에 따라 직관적으로 정렬된 정보를 제공합니다.

## 🤔 Problem Statement

### 1. 대기시간 계산 부정확 (Critical)
- **현상**: 모든 세션이 "~추정~" 표시로 나타남
- **원인**: completion_times.json에 미래 타임스탬프 저장 (2025년 날짜)
- **영향**: 사용자가 실제 대기시간을 신뢰할 수 없음

### 2. 비효율적인 세션 정렬 (High)
- **현상**: 대기 세션들이 상단에, 작업중 세션들이 하단에 표시
- **문제**: 중요한 작업중 세션 확인을 위해 스크롤 필요
- **영향**: 반복적인 스크롤로 인한 사용성 저하

### 3. 사용자 혼동 (Medium)
- **현상**: "0초 대기" vs "진짜 작업중" 구분 어려움
- **문제**: 완료 vs 진행중 상태 시각적 구분 부족
- **영향**: 세션 상태 잘못 이해

## 🎯 Goals & Success Metrics

### Primary Goals

1. **정확한 대기시간 제공** (Critical)
   - 타임스탬프 검증 로직으로 미래 날짜 문제 해결
   - 정상 운영 시 "~추정~" 표시 0% 달성

2. **작업중 세션 우선 표시** (High)  
   - 새로운 정렬 로직: 작업중 → 대기(시간DESC)
   - 스크롤 없이 작업중 세션 즉시 확인 가능

### Success Metrics

| 지표 | 현재 | 목표 | 측정 방법 |
|------|------|------|-----------|
| 정확한 대기시간 표시율 | ~20% | 95%+ | Hook 기록 vs 추정 비율 |
| 작업중 세션 접근 시간 | 3-5초 | 1초 | 최상단 표시로 즉시 확인 |
| 사용자 만족도 | 3/5 | 4.5/5 | 정렬 순서 직관성 평가 |

## 👥 Target Users

### Primary Users
- **개발자**: 여러 Claude 세션을 동시 운영하는 파워 유저
- **프로젝트 매니저**: 팀의 세션 진행상황을 모니터링하는 관리자

### User Journey
1. `/summary` 명령어 실행
2. **작업중 세션**을 최상단에서 즉시 확인 ✨ NEW
3. **대기중 세션**을 대기시간 순으로 우선순위 파악  
4. 다음 작업할 세션 결정

## 🏗️ Technical Requirements

### Functional Requirements

#### FR-1: 타임스탬프 검증 및 보정
- **요구사항**: 미래 타임스탬프 자동 감지 및 보정
- **구현**: `WaitTimeTracker.validate_and_fix_timestamps()` 메서드
- **조건**: 현재 시간보다 미래이거나 24시간 초과 시 보정
- **보정 로직**: 현재 시점 기준 30분 전으로 설정

#### FR-2: 개선된 세션 정렬
- **요구사항**: 작업중 세션을 최상단에 표시
- **구현**: `get_all_sessions_with_status()` 정렬 로직 수정
- **정렬 순서**: 
  1. 작업중 세션들 (working)
  2. 대기중 세션들 (waiting, 대기시간 DESC)
  3. 세션명 오름차순 (안정성)

#### FR-3: 상태 시각적 구분
- **요구사항**: 작업중 vs 대기중 명확한 아이콘 구분
- **구현**: 🔨 (작업중) vs 🎯 (대기중) 이모지 사용
- **추가**: 추정 시간 시 "~추정~" 표시 유지

### Non-Functional Requirements

#### NFR-1: 성능
- **응답시간**: `/summary` 명령어 2초 이내 (현재 유지)
- **메모리**: 추가 메모리 사용량 < 1MB
- **처리량**: 초당 10회 요청 처리 가능

#### NFR-2: 호환성
- **하위 호환성**: 기존 `/summary` 출력 형식 유지
- **API 호환성**: 기존 메서드 시그니처 변경 금지
- **데이터 호환성**: 기존 JSON 파일 형식 유지

#### NFR-3: 신뢰성
- **타임스탬프 오류 처리**: 100% 케이스에서 graceful fallback
- **세션 감지**: 99% 이상 세션 상태 정확도 유지
- **오류 복구**: 자동 타임스탬프 보정으로 즉시 복구

## 🔧 Technical Implementation

### Architecture Overview

```
[Telegram Command] → [TelegramBridge.summary_command()]
                         ↓
                  [SessionSummaryHelper]
                         ↓
     [WaitTimeTracker] ← [SessionStateAnalyzer]
                         ↓
            [Improved Sorting Logic]
                         ↓
              [Enhanced Display Format]
```

### Core Components

#### 1. WaitTimeTracker Enhancement
```python
class WaitTimeTracker:
    def validate_and_fix_timestamps(self):
        """Fix future timestamps and invalid records"""
        
    def __init__(self):
        # Auto-run validation on startup
        self.validate_and_fix_timestamps()
```

#### 2. SessionSummaryHelper Update  
```python
class SessionSummaryHelper:
    def get_all_sessions_with_status(self):
        # New sorting key: working first, then waiting by time DESC
        all_sessions.sort(key=lambda x: (
            1 if x[3] == 'working' else 0,  # working 우선
            -x[1] if x[3] == 'waiting' else 0,  # waiting 시간순
            x[0]  # 안정성을 위한 이름순
        ))
```

### Data Model Changes

#### Before
```json
{
  "claude_projects": 1756888756.0,  // 미래 타임스탬프!
  "claude_claude-ops": 1756891750.6
}
```

#### After  
```json
{
  "claude_projects": 1725373750.0,  // 현재 기준 과거 타임스탬프
  "claude_claude-ops": 1725375550.0
}
```

## 🧪 Testing Strategy

### Unit Tests
- [ ] `validate_and_fix_timestamps()` 동작 테스트
- [ ] 정렬 로직 다양한 시나리오 테스트
- [ ] 타임스탬프 보정 경계값 테스트

### Integration Tests
- [ ] 실제 세션 데이터로 end-to-end 테스트
- [ ] `/summary` 명령어 전체 플로우 검증
- [ ] 성능 요구사항 검증

### User Acceptance Tests
- [ ] 개발자 사용성 테스트
- [ ] 정렬 순서 직관성 평가  
- [ ] 실제 운영 환경 검증

## 📅 Development Timeline

### Phase 1: Core Implementation (30분)
- [ ] `WaitTimeTracker.validate_and_fix_timestamps()` 구현
- [ ] `SessionSummaryHelper` 정렬 로직 개선
- [ ] 기본 단위 테스트 작성

### Phase 2: Testing & Validation (20분)
- [ ] 다양한 시나리오 테스트 실행
- [ ] 실제 세션으로 동작 검증
- [ ] 성능 테스트 수행

### Phase 3: Deployment (10분)
- [ ] 코드 리뷰 및 승인
- [ ] 배포 및 모니터링 설정
- [ ] 사용자 피드백 수집

**총 예상 시간: 1시간**

## 🚀 Launch Plan

### Rollout Strategy
1. **Alpha**: 개발자 로컬 환경 테스트
2. **Beta**: 실제 운영 환경 shadow testing  
3. **GA**: 전체 사용자 대상 배포

### Success Criteria
- ✅ 타임스탬프 보정으로 "~추정~" 표시 90% 감소
- ✅ 작업중 세션이 최상단에 표시되어 즉시 접근 가능
- ✅ 기존 기능 100% 호환성 유지

### Rollback Plan
- 기존 정렬 로직으로 즉시 롤백 가능
- 타임스탬프 백업 파일 보관
- 24시간 내 완전 복구 보장

## 🔍 Risk Assessment

### High Risk
- **타임스탬프 보정 오류**: 잘못된 보정으로 더 부정확해질 가능성
  - *완화책*: 보수적 보정 로직 + 상세 로깅

### Medium Risk  
- **정렬 로직 버그**: 예상과 다른 순서로 표시될 가능성
  - *완화책*: 철저한 테스트 케이스 + 즉시 롤백 가능

### Low Risk
- **성능 저하**: 정렬 로직 추가로 응답 시간 증가
  - *완화책*: 최적화된 정렬 알고리즘 사용

## 📈 Future Enhancements

### v1.1 (향후 고려사항)
- 세션별 우선순위 설정 기능
- 커스터마이징 가능한 정렬 옵션
- 세션 그룹핑 및 카테고리 기능

### v2.0 (장기 로드맵)
- 실시간 세션 상태 업데이트
- 시각적 대시보드 인터페이스  
- 다중 사용자 환경 지원

---

## 📝 Appendix

### Stakeholders
- **Product Owner**: Claude-Ops 메인테이너
- **Developers**: Python 개발팀
- **QA**: 테스트 엔지니어
- **Users**: Claude-Ops 사용자 커뮤니티

### References
- [기존 기획서](/home/kyuwon/claude-ops/docs/CURRENT/planning.md)
- [프로젝트 규칙](/home/kyuwon/claude-ops/docs/guides/project_rules.md)
- [시스템 아키텍처](/home/kyuwon/claude-ops/CLAUDE.md)

---

**문서 버전**: 1.0  
**최종 수정**: 2025-09-03 18:40  
**승인**: 대기중