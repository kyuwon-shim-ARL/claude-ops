# 작업 상태 오탐지 문제 분석

## 📅 분석 정보
- **날짜**: 2025-09-12 12:00
- **요청**: esc to interrupt 패턴 오탐지 문제
- **유형**: bug-analysis
- **심각도**: HIGH

## 📊 분석 결과

### 🔴 핵심 문제

**"esc to interrupt" 텍스트가 화면에 남아있어 작업이 끝났는데도 계속 작업중으로 인식**

#### 실제 발견된 오탐지 사례
```
✻ Elucidating… (esc to interrupt)  ← 이 텍스트가 화면에 남아있음
─────────────────────────────────
 >                                  ← 실제로는 대기 상태
```

### 문제 발생 원인

#### 1. **과거 출력이 화면에 잔존**
- Claude가 작업 완료 후에도 이전 출력이 화면에 남아있음
- `esc to interrupt`가 포함된 라인이 스크롤되지 않고 계속 보임
- 현재 로직은 최근 10줄을 모두 검사하므로 과거 텍스트도 감지

#### 2. **컨텍스트 없는 단순 문자열 매칭**
```python
# 현재 문제가 있는 코드
if any(pattern in recent_content for pattern in self.working_patterns):
    return True  # "esc to interrupt" 텍스트만 있으면 무조건 작업중
```

#### 3. **시간적 컨텍스트 부재**
- 언제 출력된 텍스트인지 구분 못함
- 현재 활성 상태인지 과거 잔존물인지 판단 불가

### 📈 오탐지 패턴 분석

#### 자주 발생하는 상황
1. **긴 출력 후 대기**: Claude가 많은 출력 생성 후 멈춤
2. **도구 실행 완료**: Bash, Search 등 도구 실행 후
3. **분석 명령 후**: `/분석` 같은 명령 실행 중간에 표시

#### 오탐지 증거
- 화면 하단: `>` 프롬프트 (대기 상태)
- 화면 중간: `esc to interrupt` (과거 출력)
- 결과: 잘못된 "작업중" 판정

### 💡 해결 방안

#### 1. **즉시 적용 가능한 수정**

```python
def _detect_working_state(self, screen_content: str) -> bool:
    lines = screen_content.split('\n')
    
    # 마지막 몇 줄에 프롬프트가 있으면 대기 상태
    last_5_lines = '\n'.join(lines[-5:])
    if '\n>' in last_5_lines or '\n >' in last_5_lines:
        # 프롬프트가 있으면 대기 상태 (작업 안함)
        return False
    
    # 그 다음 working 패턴 체크
    recent_content = '\n'.join(lines[-10:])
    if any(pattern in recent_content for pattern in self.working_patterns):
        return True
    
    return False
```

#### 2. **중기 개선안: 활성 지표 구분**

```python
ACTIVE_WORKING_PATTERNS = [
    ("⠋", "⠙", "⠹", "⠸"),  # 회전하는 스피너
    "Running…",  # 진행형 표시
    "Thinking…",
    "Processing",
]

PASSIVE_INDICATORS = [
    "esc to interrupt",  # 단독으로는 신뢰 못함
    "ctrl+b",
]
```

#### 3. **장기 개선안: 타임스탬프 기반**
- 각 패턴 발견 시간 기록
- 5초 이상 변화 없으면 대기로 전환
- 화면 변화 추적으로 실시간성 판단

### 🔍 테스트 케이스 추가 필요

```python
def test_esc_interrupt_in_old_output():
    """과거 출력에 esc to interrupt가 있어도 프롬프트가 있으면 대기 상태"""
    screen = '''
    Old output with esc to interrupt
    Some other content
    ──────────────
     >
    '''
    assert not analyzer.is_working(screen)
```

## 💾 관련 파일
- 핵심 로직: `claude_ops/utils/session_state.py:255-332`
- 테스트: `tests/test_esc_interrupt_notification_bug.py`
- 관련 수정: commit `061aae4`

## 🔗 관련 분석
- [완료 시간 저장 문제](./2025-09-12-completion-time-tracking-issue.md)
- [대기시간 계산 메커니즘](./2025-09-12-wait-time-calculation-analysis.md)

## 🎯 액션 아이템

### 긴급 (즉시) - ✅ 완료
1. ✅ 프롬프트 우선 체크 로직 추가 - **구현됨**
2. ✅ "esc to interrupt" 단독 신뢰도 낮추기 - **구현됨**

### 중요 (1-2일)
1. 활성/수동 지표 분리
2. 테스트 케이스 보강
3. 스피너 애니메이션 감지

### 개선 (향후)
1. 타임스탬프 기반 추적
2. 머신러닝 기반 패턴 학습
3. 사용자 피드백 수집

## 🏁 결론

현재 "esc to interrupt" 텍스트만으로 작업 상태를 판단하는 것은 **과도한 단순화**입니다. 프롬프트 존재 여부를 우선 체크하고, 동적 지표(스피너, Running… 등)와 정적 텍스트를 구분해야 합니다.

**근본 원인**: 텍스트의 "현재성"을 판단하지 못함  
**해결됨**: 프롬프트가 있으면 대기 상태로 판정하는 로직 구현 완료

## 🎉 구현 완료 (2025-09-12)

### 적용된 수정사항
1. **프롬프트 우선 검사**: `_detect_working_state()` 메서드에서 작업 패턴 검사 전에 프롬프트 존재 여부를 먼저 확인
2. **포괄적 프롬프트 감지**: `>`, ` >`, `$ `, `❯ `, `>>>` 등 다양한 프롬프트 패턴 지원
3. **테스트 커버리지**: 9개 테스트 케이스로 다양한 시나리오 검증

### 검증 결과
- ✅ 보고된 false positive 시나리오 해결
- ✅ 기존 true positive 탐지 기능 유지  
- ✅ 다양한 프롬프트 형식에서 정확한 탐지
- ✅ 기존 시스템 호환성 유지

**파일**: `claude_ops/utils/session_state.py:255-333`  
**테스트**: `tests/test_esc_interrupt_false_positive_fix.py`