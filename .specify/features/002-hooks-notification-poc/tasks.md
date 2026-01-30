# Tasks: Claude Code Hooks Notification POC

**Feature**: 002-hooks-notification-poc
**Date**: 2026-01-18
**Plan**: [plan.md](./plan.md)

---

## Phase 1: 환경 준비

### T001: 디렉토리 구조 생성
- [ ] `claude_ctb/hooks/` 디렉토리 생성
- [ ] `scripts/` 디렉토리 확인
- [ ] `logs/` 디렉토리 생성
- **Output**: 디렉토리 구조 완성

### T002: 의존성 확인
- [ ] `jq` 설치 확인 (`which jq`)
- [ ] 텔레그램 봇 토큰 환경변수 확인
- **Output**: 의존성 준비 완료

---

## Phase 2: Hook 스크립트 구현

### T003: notify_telegram.sh 작성
- [ ] stdin에서 JSON 읽기
- [ ] jq로 필요 필드 추출 (session_id, project_dir, hook_event_name)
- [ ] 텔레그램 메시지 전송 (curl)
- [ ] 비교용 로그 기록 (logs/hooks_events.jsonl)
- **File**: `claude_ctb/hooks/notify_telegram.sh`

### T004: 스크립트 실행 권한 및 테스트
- [ ] chmod +x 설정
- [ ] 수동 테스트 (echo JSON | ./notify_telegram.sh)
- **Output**: 스크립트 동작 확인

---

## Phase 3: Hooks 설정

### T005: setup_hooks.sh 작성
- [ ] 프로젝트 경로를 인자로 받음
- [ ] `.claude/settings.local.json` 생성/수정
- [ ] 기존 설정 백업
- [ ] Stop, Notification hooks 추가
- **File**: `scripts/setup_hooks.sh`

### T006: 테스트 프로젝트에 hooks 설정
- [ ] claude_ticket-aid 프로젝트에 적용
- [ ] 설정 파일 확인
- **Output**: 1개 프로젝트 hooks 활성화

---

## Phase 4: 비교 로깅 시스템

### T007: 기존 스크래핑 로깅 추가
- [ ] multi_monitor.py에 이벤트 로깅 추가
- [ ] logs/scraping_events.jsonl에 기록
- [ ] 형식: {timestamp, session_name, event_type, state}
- **File**: `claude_ctb/monitoring/multi_monitor.py` (수정)

### T008: 비교 분석 스크립트 작성
- [ ] hooks_events.jsonl 읽기
- [ ] scraping_events.jsonl 읽기
- [ ] 시간 기준으로 매칭
- [ ] 지연시간, 정확도 계산
- [ ] 리포트 출력
- **File**: `scripts/compare_results.py`

---

## Phase 5: 테스트 실행

### T009: 테스트 시나리오 T1-T2 (작업 완료)
- [ ] 짧은 작업 실행 후 완료
- [ ] 긴 작업 실행 후 완료
- [ ] 양쪽 알림 확인 및 로그 기록
- **Output**: T1, T2 결과

### T010: 테스트 시나리오 T3 (사용자 중단)
- [ ] 작업 중 Ctrl+C로 중단
- [ ] Hooks 미실행 확인
- [ ] Scraping 동작 확인
- **Output**: T3 결과

### T011: 테스트 시나리오 T4 (idle 60초)
- [ ] 입력 없이 60초 대기
- [ ] idle_prompt 알림 확인
- **Output**: T4 결과

### T012: 테스트 시나리오 T5-T6 (작업 중, 다중 세션)
- [ ] 작업 중 false positive 없음 확인
- [ ] 3개 세션 동시 완료 테스트
- **Output**: T5, T6 결과

---

## Phase 6: 결과 분석

### T013: 비교 리포트 생성
- [ ] compare_results.py 실행
- [ ] 정확도, 지연시간, FP/FN 비율 계산
- **Output**: 비교 리포트

### T014: 최종 결정 문서화
- [ ] Hooks vs Scraping 비교 표 작성
- [ ] 상위호환 여부 판단
- [ ] 다음 단계 권고사항
- **Output**: 결정 문서

---

## 진행 상태

| Phase | 상태 | 완료일 |
|-------|------|--------|
| Phase 1 | ⏳ 대기 | - |
| Phase 2 | ⏳ 대기 | - |
| Phase 3 | ⏳ 대기 | - |
| Phase 4 | ⏳ 대기 | - |
| Phase 5 | ⏳ 대기 | - |
| Phase 6 | ⏳ 대기 | - |

---

## 의존성

```
T001 → T002 → T003 → T004 → T005 → T006
                              ↓
T007 ─────────────────────→ T008
                              ↓
T009 → T010 → T011 → T012 → T013 → T014
```
