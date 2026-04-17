# Experiment Log

## 2026-03-12: e001 시작
- **목표**: Context limit 자동 감지 + Telegram 알림
- **Branch**: worktree-context_limit
- **Status**: started
- **배경**: /sciomc 연구로 context limit 원인 분석 완료. /compact deadlock 문제 확인. exit → 새 세션 전략 채택.

## 2026-03-12: e002 시작
- **목표**: Context limit 시 자동 세션 재시작 + 핸드오프 프롬프트
- **Branch**: worktree-context_limit
- **Status**: started
- **의존성**: e001 (감지 로직 필요)

## 2026-03-12: T5 완료 (.omc gitignore)
- **.gitignore**에 `.omc/` 추가 완료
- **Status**: done

## 2026-03-12: e001 완료 (Context limit 감지)
- **session_state.py**: CONTEXT_LIMIT enum (priority 0), `_detect_context_limit()` 4패턴 감지
- **multi_monitor.py**: CONTEXT_LIMIT 알림 경로, InlineKeyboard (Restart/Ignore)
- **Architect**: APPROVED (security fix 적용 후)
- **Status**: done

## 2026-03-12: e002 완료 (One-click restart)
- **bot.py**: `_context_limit_restart_callback()` (Ctrl+C → /exit → fresh claude → handoff)
- **bot.py**: `_build_handoff_prompt()` (git status + .omc state)
- **Security**: list-form subprocess로 shell injection 방지
- **Architect**: APPROVED
- **Status**: done

## 2026-03-17: e007 시작
- **목표**: CTB State Detection Hardening — ⎿ Guard Fix + 회귀테스트 체계화
- **Issue**: #8
- **Branch**: main
- **Milestone**: none
- **Status**: started
- **배경**: antibiotic_platform 세션이 thinking 중인데 dashboard에서 idle로 오감지. ⎿ output guard가 parent line의 working 지표를 잘라냄. parent-line fix 적용 후 테스트 인프라 전반 정비 필요.

## 2026-03-17: e008 시작
- **목표**: Session State Structural Fix — collapse sub-output + glyph + test hardening
- **Issue**: #9
- **Branch**: main
- **Depends on**: e007
- **Status**: started
- **배경**: e007의 고정 윈도우(6줄) 접근이 근본적 한계. task list가 길어지면 working indicator가 윈도우 밖으로 밀려남. /sciomc 비평 결과 3가지 구조적 문제 확인: (1) sub-output collapse 필요, (2) ✶✻ 글리프 누락, (3) working_indicators 중복 리스트 drift 위험. 비평 수렴 후 실행.

## 2026-03-24: e012 시작
- **목표**: CTB Dashboard 감성 디자인 변환 + 아이젠하워 매트릭스 DnD
- **의존성**: e004 (Dashboard 프론트엔드)
- **Status**: started
- **배경**: /sciomc 연구로 Designer + Scientist + Critic 3단계 분석 완료. Phase 1(감성 CSS), Phase 2a(쿼드런트 UI), Phase 2b(DnD 인터랙션) 3단계 구현. Critic 비평 2회 수렴 후 실행.
- **Tasks**: T1-T6 (6개)

## 2026-03-24: e013 시작
- **목표**: CTB Dashboard DnD 버그 수정 + 라이트/다크 테마 토글
- **의존성**: e012 (감성 디자인 + 아이젠하워 매트릭스)
- **Status**: started
- **배경**: e012 구현 후 사용자 피드백: (1) DnD가 동작하지 않음 — debugger 에이전트가 5건 버그 확인 (stale event, touch-action, setPointerCapture, render guard, releasePointerCapture), (2) 다크 테마가 우중충함 — designer 에이전트가 라이트 크림 감성 팔레트 제안. Critic 비평으로 Bug4 fix 부작용(H1)과 Tailwind 전략(H2) 보완.
- **Tasks**: T1-T6 (6개)

## 2026-03-24: e014 시작
- **목표**: CTB Dashboard PC DnD 수정 + 라이트모드 강조 개선 + WORKING 최상단 재배치 복원
- **의존성**: e013 (DnD 버그 수정 + 테마 토글)
- **Status**: started
- **배경**: 사용자 피드백 3건: (1) PC에서 DnD 안됨 — 롱프레스 패턴이 마우스에 부적합, pointerType 분기 필요, (2) 라이트 모드 강조효과 미약 — CSS 변수 미설정 + glow opacity 부족, (3) 아이젠하워 매트릭스 도입 후 WORKING 최상단 재배치 풀림 — quadrant 내부 정렬 미적용. Critic 비평으로 H1-H3 식별, targeted fix 계획 수립.
- **Tasks**: T1-T5 (5개)

## 2026-03-24: e017 시작
- **목표**: 세션목표+프롬프트 표시 안정화 — work_context 범용 fallback + last_prompt persist
- **Issue**: #13
- **의존성**: e012 (감성 디자인 대시보드)
- **Status**: started
- **배경**: 사용자 피드백: (1) 세션목표(work_context)가 아예 안 보임 — 3단계 fallback 모두 OMC 전용 파일 의존, 일반 세션 None, (2) 마지막 프롬프트가 보이다 말다 함 — 캐시 TTL 1초 vs 폴링 3초 타이밍 불일치 + 과도한 필터링. Critic 비평 H1-H4, M1-M4 식별.
- **Tasks**: T1-T5 (5개)

## 2026-04-17: e023 시작
- **목표**: Ticket-Driven Nudge Suppression — 세션-티켓 레지스트리 도입
- **Issue**: #14
- **Branch**: main
- **Status**: started
- **비평**: 5개 HIGH, 5개 MEDIUM 반영 (H2: exp-workflow 등록 scope 포함, H5: Path4 guard 추가)
