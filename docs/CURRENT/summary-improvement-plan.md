# /summary 커맨드 개선 기획서

## 🎯 목표
1. **대기시간 계산 정확성 확보**: 타임스탬프 검증 및 fallback 개선
2. **사용자 경험 개선**: 작업중 세션을 우선 표시하여 즉시 확인 가능

## 📊 현재 문제점 분석

### 1. 대기시간 계산 오류
- **Root Cause**: completion_times.json의 미래 타임스탬프 (2025년 날짜)
- **증상**: 음수 대기시간으로 인한 fallback 메커니즘 작동
- **영향**: 모든 세션이 "~추정~" 표시로 나타남

### 2. 정렬 순서 불편함
- **현재**: [대기 세션들 (대기시간 DESC)] → [작업중 세션들]
- **문제**: 작업중 세션 확인을 위해 스크롤이 필요
- **개선**: [작업중 세션들] → [대기 세션들 (대기시간 DESC)]

## 🔧 해결책 설계

### 1. 타임스탬프 검증 및 보정 로직
```python
def validate_and_fix_timestamps(self):
    """미래 타임스탬프 검증 및 보정"""
    current_time = time.time()
    fixed_count = 0
    
    for session_name, timestamp in list(self.completion_times.items()):
        # 미래 타임스탬프 또는 24시간 초과 시 보정
        if timestamp > current_time or (current_time - timestamp) > 24*3600:
            # 현재 시점으로부터 합리적인 과거 시간으로 보정
            self.completion_times[session_name] = current_time - 1800  # 30분 전
            fixed_count += 1
    
    if fixed_count > 0:
        self._save_completions()
        logger.info(f"Fixed {fixed_count} invalid timestamps")
```

### 2. 개선된 정렬 로직
```python
def get_all_sessions_with_status_improved(self):
    """개선된 정렬: 작업중 우선, 그 다음 대기(대기시간 DESC)"""
    all_sessions = self._get_raw_session_data()
    
    # 새로운 정렬 로직:
    # 1순위: 작업중(working) 세션들을 맨 위로
    # 2순위: 대기(waiting) 세션들을 대기시간 내림차순으로
    # 3순위: 세션명 오름차순 (안정성)
    all_sessions.sort(key=lambda x: (
        1 if x[3] == 'working' else 0,  # working = 0 (위로), waiting = 1 (아래로) 
        -x[1] if x[3] == 'waiting' else 0,  # 대기 세션만 대기시간 내림차순
        x[0]  # 세션명 오름차순
    ))
    
    return all_sessions
```

## 📋 구현 계획 (MECE)

### Phase 1: 타임스탬프 보정 (Critical)
- [ ] WaitTimeTracker에 validate_and_fix_timestamps() 메서드 추가
- [ ] 시스템 초기화 시 자동 보정 실행
- [ ] 로깅으로 보정 과정 투명성 확보

### Phase 2: 정렬 로직 개선 (High Priority)  
- [ ] SessionSummaryHelper.get_all_sessions_with_status() 수정
- [ ] 새로운 정렬 키 적용: 작업중 → 대기(시간DESC) → 이름ASC
- [ ] 기존 메서드 호환성 유지

### Phase 3: 테스트 및 검증 (Medium Priority)
- [ ] 다양한 세션 상태 시나리오 테스트
- [ ] 정렬 순서 검증 테스트 
- [ ] 타임스탬프 보정 로직 테스트

## 🎯 성공 기준

### 기능적 요구사항
1. **정확한 대기시간**: "~추정~" 표시 0개 (정상 운영 시)
2. **올바른 정렬**: 작업중 세션이 최상단에 표시  
3. **사용성 향상**: 스크롤 없이 작업중 세션 즉시 확인 가능

### 비기능적 요구사항  
1. **호환성**: 기존 /summary 커맨드 동작 유지
2. **성능**: 응답 시간 < 2초 유지
3. **안정성**: 타임스탬프 문제 시 graceful fallback

## 📅 예상 소요 시간
- **구현**: 30분 (코드 수정)
- **테스트**: 20분 (시나리오 검증)  
- **검증**: 10분 (실제 세션으로 확인)

**총 예상 시간: 1시간**

---

**작성일**: 2025-09-03 18:35
**다음 단계**: Phase 1 구현 시작