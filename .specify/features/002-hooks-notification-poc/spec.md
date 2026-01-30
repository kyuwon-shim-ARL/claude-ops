# Feature Specification: Claude Code Hooks Notification POC

**Feature Branch**: `002-hooks-notification-poc`
**Created**: 2026-01-18
**Status**: Draft
**Input**: User description: "Claude Code hooks 기반 알림 시스템을 기존 화면 스크래핑 방식과 비교 테스트하여 상위호환 여부 검증"

---

## 배경 및 목적

### 현재 상황
- 기존 방식: tmux 화면 스크래핑 + 패턴 매칭으로 Claude 세션 상태 감지
- 문제점:
  - 패턴 누락으로 인한 false positive/negative 빈번
  - `ctrl+c to interrupt` 패턴 누락 → 작업 중에도 완료 알림
  - `AskUserQuestion` 패턴 추가 → 작업 중에도 입력 대기 알림
  - 지속적인 패턴 유지보수 필요

### 대안
- Claude Code의 공식 Hooks 시스템 (2025년 6월 추가)
  - `Stop` hook: 응답 완료 시 실행
  - `Notification (idle_prompt)`: 60초 이상 입력 대기 시 실행

### 검증 필요 사항
- Hooks가 실제로 의도대로 동작하는지
- 기존 방식 대비 정확도, 지연시간, 안정성 비교
- 다중 세션 환경에서의 동작

---

## User Scenarios & Testing

### Primary User Story
사용자가 여러 Claude Code 세션을 동시에 운영하면서, 각 세션이 작업 완료 또는 입력 대기 상태가 되면 텔레그램으로 정확한 알림을 받고 싶다.

### Acceptance Scenarios

1. **Given** Claude 세션이 작업 중일 때,
   **When** 작업이 완료되면,
   **Then** 5초 이내에 텔레그램 알림이 도착해야 한다.

2. **Given** Claude 세션이 사용자 입력을 기다릴 때,
   **When** 60초가 경과하면,
   **Then** idle_prompt 알림이 텔레그램으로 도착해야 한다.

3. **Given** Claude 세션이 작업 중일 때,
   **When** 작업이 완료되지 않았으면,
   **Then** 알림이 발생하지 않아야 한다 (false positive 없음).

4. **Given** 3개 이상의 Claude 세션이 동시에 실행 중일 때,
   **When** 각각 다른 시점에 작업이 완료되면,
   **Then** 각 세션별로 개별 알림이 정확히 도착해야 한다.

### Edge Cases

- 세션이 갑자기 종료된 경우 어떻게 처리하는가?
- 사용자가 Ctrl+C로 작업을 중단한 경우 Stop hook이 실행되는가? (문서상 NO)
- 매우 짧은 작업 (1초 미만)도 감지되는가?
- 네트워크 지연으로 텔레그램 전송이 실패한 경우 재시도하는가?

---

## Requirements

### Functional Requirements

- **FR-001**: POC 시스템은 Claude Code Stop hook을 통해 작업 완료를 감지해야 한다.
- **FR-002**: POC 시스템은 Notification (idle_prompt) hook을 통해 입력 대기 상태를 감지해야 한다.
- **FR-003**: 각 hook 발생 시 텔레그램 메시지를 전송해야 한다.
- **FR-004**: 메시지에는 세션 이름, 프로젝트 경로, 이벤트 유형이 포함되어야 한다.
- **FR-005**: 기존 스크래핑 방식과 동시에 실행하여 비교 가능해야 한다.

### Non-Functional Requirements

- **NFR-001**: 알림 지연시간은 이벤트 발생 후 5초 이내여야 한다.
- **NFR-002**: false positive 비율은 0%여야 한다 (작업 중 알림 없음).
- **NFR-003**: false negative 비율은 0%여야 한다 (완료 시 알림 누락 없음).

### Key Entities

- **Hook Event**: session_id, project_dir, event_type (Stop/idle_prompt), timestamp
- **Notification**: session_name, message, sent_at, delivery_status

---

## 비교 테스트 기준

| 지표 | 측정 방법 | 목표 |
|------|----------|------|
| 정확도 | (정확한 알림 / 전체 이벤트) × 100 | 100% |
| 지연시간 | 이벤트 발생 ~ 알림 수신 | < 5초 |
| False Positive | 작업 중 잘못된 알림 수 | 0 |
| False Negative | 완료 시 누락된 알림 수 | 0 |
| 안정성 | 24시간 연속 운영 시 오류 | 0 |

---

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

---

## 제약사항 및 가정

### 제약사항
- Claude Code hooks는 각 프로젝트의 `.claude/settings.local.json`에 개별 설정 필요
- hooks 설정은 git에 커밋되지 않음 (local 설정)

### 가정
- Claude Code 버전이 hooks를 지원하는 최신 버전임
- 텔레그램 봇 토큰 및 채팅 ID는 기존 시스템과 동일하게 사용

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed
