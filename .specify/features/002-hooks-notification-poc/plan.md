# Implementation Plan: Claude Code Hooks Notification POC

**Branch**: `002-hooks-notification-poc` | **Date**: 2026-01-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `./spec.md`

---

## Summary

Claude Code의 공식 Hooks 시스템(Stop, Notification)을 이용한 알림 방식이 기존 화면 스크래핑 방식 대비 정확도, 지연시간, 안정성 면에서 개선되는지 검증하는 POC 구현.

---

## Technical Context

**Language/Version**: Python 3.11, Bash
**Primary Dependencies**: python-telegram-bot (기존), jq (JSON 파싱)
**Storage**: 로그 파일 (비교 데이터 수집용)
**Testing**: 수동 비교 테스트 + 자동화 스크립트
**Target Platform**: Linux (Rocky 8)
**Project Type**: single
**Performance Goals**: 알림 지연 < 5초
**Constraints**: 기존 시스템과 병행 운영 필요
**Scale/Scope**: 10-20개 세션 동시 모니터링

---

## Constitution Check

*이 POC는 기존 시스템 대체가 아닌 비교 테스트이므로, 일부 원칙은 해당되지 않음*

- [x] **Bridge-First Architecture**: N/A (POC 범위)
- [ ] **Polling-Based Reliability**: ⚠️ Hooks는 이벤트 기반 - 이것이 더 나은지 검증 대상
- [x] **Session State Detection**: 기존 시스템 유지, hooks와 병행 테스트
- [x] **Reply-Based Session Targeting**: 기존 시스템 유지
- [x] **Test-Driven Development**: 비교 테스트 시나리오 먼저 정의
- [x] **Conservative Detection**: Hooks가 이를 보장하는지 검증 대상
- [x] **Message Splitting**: 기존 notifier 재사용

*Constitution 위반: Polling → Event 전환 가능성. 이는 POC로 검증 후 결정.*

---

## Project Structure

### Documentation (this feature)
```
.specify/features/002-hooks-notification-poc/
├── spec.md              # 완료
├── plan.md              # 이 파일
├── research.md          # Phase 0 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)
```
claude_ctb/
├── hooks/                    # NEW: Hooks 관련 코드
│   ├── notify_telegram.sh    # Stop/Notification hook용 스크립트
│   └── comparison_logger.py  # 비교 데이터 수집
├── monitoring/
│   └── multi_monitor.py      # 기존 스크래핑 (유지)
└── utils/
    └── session_state.py      # 기존 상태 감지 (유지)

scripts/
├── setup_hooks.sh            # 프로젝트별 hooks 설정 스크립트
└── compare_results.py        # 비교 분석 스크립트

logs/
├── hooks_events.jsonl        # Hooks 이벤트 로그
└── scraping_events.jsonl     # 스크래핑 이벤트 로그
```

**Structure Decision**: 기존 구조 유지, `hooks/` 디렉토리만 추가. 비교 테스트 후 결과에 따라 통합 또는 폐기.

---

## Phase 0: Outline & Research

### 연구 필요 항목

1. **Claude Code hooks 동작 확인**
   - Stop hook이 정확히 언제 실행되는지
   - 사용자 중단(Ctrl+C) 시 실행되는지 (문서상 NO)
   - stdin으로 전달되는 JSON 구조

2. **다중 세션 환경**
   - 각 프로젝트별 `.claude/settings.local.json` 설정 방법
   - 전역 설정 vs 프로젝트별 설정

3. **기존 시스템과의 통합**
   - 동시 실행 시 충돌 가능성
   - 이벤트 중복 처리

### 연구 결과 (research.md로 분리 가능)

**hooks 동작**:
- Stop: 응답 완료 시 실행, 사용자 중단 시 미실행
- Notification: idle_prompt (60초), permission_prompt
- stdin으로 JSON 전달: session_id, project_dir, hook_event_name 등

**설정 위치**:
- `~/.claude/settings.json`: 전역 설정
- `PROJECT/.claude/settings.local.json`: 프로젝트별 설정 (우선)

**Output**: research.md 작성 완료로 간주 (위 내용 기반)

---

## Phase 1: Design & Contracts

### 데이터 모델

```
HookEvent:
  - session_id: string
  - project_dir: string
  - event_type: "Stop" | "idle_prompt" | "permission_prompt"
  - timestamp: datetime
  - raw_json: dict

ScrapingEvent:
  - session_name: string
  - state: SessionState
  - timestamp: datetime
  - screen_hash: string

ComparisonResult:
  - event_id: string
  - hooks_detected: bool
  - hooks_timestamp: datetime?
  - scraping_detected: bool
  - scraping_timestamp: datetime?
  - latency_diff_ms: int
  - accuracy: "TP" | "FP" | "FN" | "TN"
```

### 컴포넌트 설계

1. **notify_telegram.sh** (Hook 스크립트)
   - stdin에서 JSON 읽기
   - 텔레그램 메시지 전송
   - 비교용 로그 기록

2. **comparison_logger.py** (비교 데이터 수집)
   - hooks/scraping 이벤트 동기화
   - 지연시간, 정확도 계산

3. **setup_hooks.sh** (설정 자동화)
   - 지정된 프로젝트에 hooks 설정 추가
   - 기존 설정 백업

4. **compare_results.py** (분석 스크립트)
   - 로그 파일 분석
   - 비교 리포트 생성

### 테스트 시나리오

| ID | 시나리오 | 예상 결과 |
|----|----------|----------|
| T1 | 짧은 작업 완료 | 양쪽 모두 감지 |
| T2 | 긴 작업 완료 | 양쪽 모두 감지 |
| T3 | 사용자 중단 | Hooks 미실행, Scraping 감지? |
| T4 | 60초 idle | Hooks idle_prompt 발생 |
| T5 | 작업 중 (no event) | 양쪽 모두 알림 없음 |
| T6 | 동시 3세션 완료 | 양쪽 모두 3개 알림 |

---

## Phase 2: Task Planning Approach

**Task Generation Strategy**:
1. 환경 준비 (디렉토리, 의존성)
2. Hook 스크립트 구현
3. 비교 로깅 시스템 구현
4. 테스트 프로젝트에 hooks 설정
5. 테스트 시나리오 실행
6. 결과 분석 및 리포트

**Ordering Strategy**:
- 순차 실행 (의존성 있음)
- 테스트는 수동 + 자동화 병행

**Estimated Output**: 12-15 tasks

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Event-based (vs Polling) | Hooks가 공식 지원 방식 | 비교 테스트가 목적, 폐기 가능 |

---

## Progress Tracking

**Phase Status**:
- [x] Phase 0: Research complete
- [x] Phase 1: Design complete
- [x] Phase 2: Task planning complete (approach described)
- [ ] Phase 3: Tasks generated
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS (with documented deviation)
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented
