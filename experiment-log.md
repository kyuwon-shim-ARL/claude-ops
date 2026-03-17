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
