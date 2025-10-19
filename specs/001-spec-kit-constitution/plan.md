# Implementation Plan: Claude-CTB System Reliability Improvements

**Branch**: `001-spec-kit-constitution` | **Date**: 2025-10-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/spec.md`

## Summary

Improve Claude-CTB Telegram bridge reliability by addressing critical gaps in notification delivery, session state detection, error handling, and message processing. The system currently monitors Claude Code sessions via tmux and sends Telegram notifications, but requires enhancements to handle edge cases: session disconnections with configurable retry, restart behavior skipping missed events, rate limit handling with exponential backoff, dangerous command confirmations, and 200-line screen history analysis for accurate state detection.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: python-telegram-bot>=20.0, python-dotenv>=1.0.0, pytest>=8.4.1 (testing)
**Storage**: Filesystem-based state tracking (no database), tmux session persistence
**Testing**: pytest with contract, integration, and unit test coverage
**Target Platform**: Linux server (RHEL 8/compatible)
**Project Type**: Single project (Python CLI + bot daemon)
**Performance Goals**: <10s notification latency, 10+ concurrent sessions, <1s command response, <5% CPU per session
**Constraints**: Pure polling-based (no WebSockets/events), 4000-char Telegram message limit, tmux-dependent architecture
**Scale/Scope**: Single-user deployment, 1-10 concurrent Claude sessions, ~35 Python modules, ~26 test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify compliance with `.specify/memory/constitution.md`:

- [x] **Bridge-First Architecture**: Does NOT add workflow/prompt logic (delegates to claude-dev-kit) - ✅ Improvements maintain pure bridge model
- [x] **Polling-Based Reliability**: Maintains tmux polling, no event-based notification mechanisms - ✅ Enhancements preserve 3-5s polling architecture
- [x] **Session State Detection**: Uses `session_state.py` as single source of truth - ✅ Improvements enhance existing unified detection module
- [x] **Reply-Based Session Targeting**: Preserves reply-based command routing - ✅ No changes to targeting mechanism
- [x] **Test-Driven Development**: Tests written before implementation - ✅ All improvements will follow TDD (tests in Phase 1, implementation later)
- [x] **Conservative Detection**: Avoids false positive notifications - ✅ 200-line history analysis reinforces conservative approach
- [x] **Message Splitting**: Handles long messages without truncation - ✅ Enhancements maintain existing message_utils.py splitting logic

*No constitutional violations. All improvements align with existing principles.*

## Project Structure

### Documentation (this feature)
```
specs/001-spec-kit-constitution/
├── plan.md              # This file (/plan command output)
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
claude_ctb/
├── telegram/
│   ├── bot.py                      # Main bot, dangerous command confirmation
│   ├── notifier.py                 # Notification logic
│   └── message_utils.py            # Message splitting (existing)
├── monitoring/
│   ├── multi_monitor.py            # Multi-session polling, restart behavior
│   └── completion_event_system.py  # Event tracking
├── utils/
│   ├── session_state.py            # State detection (200-line history)
│   ├── wait_time_tracker_v2.py     # Session time tracking
│   └── session_reconnect.py        # NEW: Session reconnection logic
└── config.py                       # Configuration management

tests/
├── contract/
│   ├── test_telegram_api_contract.py      # Telegram Bot API contract tests
│   ├── test_tmux_contract.py              # tmux command contract tests
│   └── test_rate_limit_contract.py        # Rate limit behavior tests
├── integration/
│   ├── test_session_disconnection_flow.py # Session reconnection workflow
│   ├── test_restart_notification_skip.py  # Restart state handling
│   ├── test_dangerous_command_confirm.py  # Confirmation flow
│   └── test_state_detection_200_lines.py  # History depth integration
└── unit/
    ├── test_reconnect_logic.py            # Reconnection retry logic
    ├── test_exponential_backoff.py        # Rate limit backoff
    └── test_screen_history_parsing.py     # 200-line history parsing
```

**Structure Decision**: Single project (Python package). This is an existing system with established `claude_ctb/` package structure. Improvements will be integrated into existing modules (`telegram/`, `monitoring/`, `utils/`) with minimal new files. Test structure follows existing `tests/` organization with contract/integration/unit separation per constitution TDD requirements.

## Phase 0: Outline & Research

No NEEDS CLARIFICATION markers exist in Technical Context. All technology choices are established (Python 3.10+, python-telegram-bot, pytest, tmux). Research focuses on implementation patterns for the five clarified requirements.

### Research Topics

1. **Session Reconnection Patterns**
   - Decision: Configurable retry with exponential backoff + timeout
   - Rationale: Allows tuning for different network conditions, prevents infinite retry loops
   - Alternatives considered: Fixed retry count (rejected: less flexible), immediate failure (rejected: too aggressive)

2. **Restart State Management**
   - Decision: Persist last-known state hash, skip notifications if state unchanged across restart
   - Rationale: Prevents duplicate notifications, aligns with "skip missed events" clarification
   - Alternatives considered: Full event replay (rejected: violates clarification), state reset (rejected: loses context)

3. **Rate Limit Handling** (implements FR-028)
   - Decision: In-memory queue with exponential backoff (python-telegram-bot built-in retry + custom wrapper)
   - Rationale: Telegram limits are 30 msg/sec burst, 20 msg/min sustained; backoff prevents cascade failures
   - Alternatives considered: Disk-based queue (rejected: adds complexity), drop messages (rejected: violates FR-017)

4. **Dangerous Command Confirmation**
   - Decision: Telegram InlineKeyboardMarkup with "Confirm"/"Cancel" buttons, 60-second timeout
   - Rationale: Clear user intent, follows Telegram UX patterns, timeout prevents stale confirmations
   - Alternatives considered: Re-type command (rejected: poor UX), whitelist (rejected: too restrictive)

5. **Screen History Depth**
   - Decision: `tmux capture-pane -S -200` (last 200 lines from scrollback)
   - Rationale: Captures sufficient context for Claude Code output patterns, minimal performance overhead
   - Alternatives considered: Full scrollback (rejected: performance cost), last 50 lines (rejected: insufficient context per clarification)

**Output**: research.md created

## Phase 1: Design & Contracts

*Prerequisites: research.md complete* ✅

### 1. Data Model (`data-model.md`) ✅

Extracted 5 entities from feature spec requirements:

1. **SessionReconnectionState**: Tracks retry attempts with exponential backoff
   - Fields: session_name, disconnect_time, retry_count, next_retry_time, max_duration_seconds, current_backoff_seconds, status
   - State transitions: RECONNECTING → SUCCESS/FAILED

2. **PersistedSessionState**: Filesystem-persisted state for restart behavior
   - Fields: session_name, screen_hash, last_state, timestamp, notification_sent
   - Storage: `/tmp/claude-ctb/state/{session_name}.state`

3. **MessageQueueEntry**: In-memory rate limit queue
   - Fields: message_id, chat_id, text, retry_count, next_retry_time, enqueue_time, priority
   - Exponential backoff: delay = min(initial * 2^retry_count, max)

4. **PendingConfirmation**: Dangerous command confirmation tracking
   - Fields: confirmation_id, session_name, command, user_id, message_id, created_time, expires_time, status
   - 60-second TTL

5. **ScreenHistory** (enhanced): 200-line capture for state detection
   - Fields: session_name, content, line_count, capture_time, hash
   - Command: `tmux capture-pane -t {session} -p -S -200`

### 2. API Contracts (`contracts/`) ✅

**Telegram Bot API Contract** (`telegram-api-contract.md`):
- Send message with InlineKeyboard (dangerous command confirmation)
- Handle CallbackQuery (button clicks)
- Rate limit handling (RetryAfter exception)
- Message splitting verification (existing message_utils.py)

**tmux Contract** (`tmux-contract.md`):
- Session existence check (`has-session` exit codes)
- 200-line screen capture (`capture-pane -S -200`)
- Reconnection retry idempotency
- Hash-based change detection

### 3. Contract Tests (TDD - tests before implementation)

**Contract Test Files** (to be written in /tasks phase):
```
tests/contract/test_telegram_api_contract.py
tests/contract/test_tmux_contract.py
tests/contract/test_rate_limit_contract.py
```

Test assertions:
- Telegram inline keyboard creation and callback handling
- tmux 200-line capture returns correct line count
- Rate limit exceptions trigger queue with backoff
- Session reconnection retry behavior

### 4. Integration Test Scenarios (`quickstart.md`) ✅

5 manual validation scenarios:

1. **Session Disconnection Reconnection**: Kill session, verify retry attempts, verify failure notification after timeout
2. **Restart State Skip**: Restart monitoring, verify no duplicate notifications for unchanged sessions
3. **Rate Limit Queue**: Trigger burst notifications, verify queueing and exponential backoff
4. **Dangerous Command Confirmation**: Send `sudo` command, verify inline keyboard, test Confirm/Cancel/Timeout
5. **200-Line Screen History**: Session with long output, verify accurate state detection (no false positives)

**Full integration test**: All 5 improvements working together in multi-session scenario

### 5. Agent File Update (CLAUDE.md)

*Note: Skipping agent file update as this is a retrospective documentation project applying spec-kit to existing system. CLAUDE.md already contains comprehensive guidance.*

**Output**: data-model.md, contracts/, quickstart.md created ✅

## Phase 2: Task Planning Approach

*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:

1. **From Contracts** (2 contracts → 6-9 contract test tasks):
   - Telegram API contract → 3 test files (inline keyboard, callback, rate limit)
   - tmux contract → 3 test files (has-session, capture-pane, reconnection)
   - Each test file = 1 task marked [P] (parallel execution)

2. **From Data Model** (5 entities → 10-15 implementation tasks):
   - SessionReconnectionState → 2 tasks (data class + retry logic)
   - PersistedSessionState → 2 tasks (persistence + load/save)
   - MessageQueueEntry → 2 tasks (queue class + backoff logic)
   - PendingConfirmation → 2 tasks (tracking dict + timeout cleanup)
   - ScreenHistory → 2 tasks (capture enhancement + hash logic)

3. **From User Stories** (7 acceptance scenarios → 7-10 integration tests):
   - Each acceptance scenario → 1 integration test task [P]
   - Edge cases → additional unit tests (5-7 tasks)

4. **Implementation Tasks** (to make tests pass):
   - Enhance `session_state.py` for 200-line capture
   - Add reconnection logic to `multi_monitor.py`
   - Implement confirmation flow in `bot.py`
   - Add rate limit queue to `notifier.py`
   - Update `config.py` for new environment variables

**Ordering Strategy**:
- **Phase 3.1**: Setup (create `tests/contract/` directory, configure pytest)
- **Phase 3.2**: Contract tests (write tests, verify they fail) - [P] parallel execution
- **Phase 3.3**: Integration tests (write tests, verify they fail) - [P] parallel execution
- **Phase 3.4**: Unit tests (write edge case tests) - [P] parallel execution
- **Phase 3.5**: Core implementation (make tests pass)
- **Phase 3.6**: Integration (wire up components)
- **Phase 3.7**: Polish (performance testing, cleanup, quickstart validation)

**Estimated Output**: 40-50 numbered, ordered tasks in tasks.md

**Parallelization**:
- Test files independent → mark [P] (20-25 parallel test tasks)
- Implementation files mostly independent → mark [P] where safe
- Integration tasks sequential (wire-up dependencies)

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation

*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following TDD: tests first, implementation second)
**Phase 5**: Validation (run pytest, execute quickstart.md, performance validation)

## Complexity Tracking

*No constitutional violations identified. No complexity tracking required.*

All improvements align with existing principles:
- Pure bridge architecture maintained (no workflow logic)
- Polling-based reliability preserved
- Session state detection remains unified
- TDD process followed (tests before implementation)

## Critical Bugs Discovered & Fixed (2025-10-12)

During implementation validation, two critical blocking issues were discovered and resolved:

### Bug #1: Monitoring Session Not Running
**Symptom**: No notifications sent for any session completions (20+ minutes without alerts)
**Root Cause**: `claude-monitor` tmux session was not initialized/running despite Telegram bot being active
**Impact**: Complete notification system failure - monitoring threads never started
**Fix**: Manual initialization of monitoring session via `tmux new-session -d -s claude-monitor "uv run python -m claude_ctb.monitoring.multi_monitor"`
**Prevention**: Added FR-033 and FR-034 to spec.md requiring monitoring session status checks

### Bug #2: Invalid Method Call in multi_monitor.py
**Symptom**: `AttributeError: 'SmartNotifier' object has no attribute 'send_task_completion_notification'`
**Root Cause**: Line 290 in `multi_monitor.py` called non-existent method (only DEPRECATED version exists)
**Impact**: All notification attempts failed with exception, preventing completion alerts
**Fix**: Replaced task-specific notification branch with standard `send_work_completion_notification()` call
**Files Modified**: `claude_ctb/monitoring/multi_monitor.py:286-290`

### Bug #3: /summary Command Message Overflow
**Symptom**: Telegram API error "Message is too long" when 12+ sessions active
**Root Cause**: Incorrect parameter names passed to `safe_send_message()` (used `update=` and `message=` instead of `send_func=` and `text=`)
**Impact**: /summary command returned error message instead of session overview
**Fix**: Corrected method signature to use `send_func=update.message.reply_text` and `text=summary_message`
**Files Modified**: `claude_ctb/telegram/bot.py:1068-1072`

**Validation**: All three issues resolved, monitoring active with 6 sessions tracked, notifications working correctly

## Progress Tracking

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning approach described (/plan command)
- [ ] Phase 3: Tasks generated (/tasks command - NOT YET RUN)
- [x] Phase 4: Critical bugs discovered and fixed (see section above)
- [ ] Phase 5: Full implementation complete
- [ ] Phase 6: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS (all principles aligned)
- [x] Post-Design Constitution Check: PASS (no new violations)
- [x] All NEEDS CLARIFICATION resolved (5 clarifications documented)
- [x] Complexity deviations documented (none required)

**Artifacts Generated**:
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/plan.md` (this file)
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/research.md`
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/data-model.md`
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/contracts/telegram-api-contract.md`
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/contracts/tmux-contract.md`
- [x] `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/quickstart.md`

---

*Implementation plan complete. Ready for `/tasks` command.*

**Based on Constitution v1.0.0** - See `/home/kyuwon/claude-ops/.specify/memory/constitution.md`
