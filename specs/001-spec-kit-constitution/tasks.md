# Tasks: Claude-CTB System Reliability Improvements

**Input**: Design documents from `/home/kyuwon/claude-ops/specs/001-spec-kit-constitution/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/, quickstart.md

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Phase 3.1: Setup

- [x] T001 Create test directory structure for contract tests
  ```bash
  mkdir -p tests/contract tests/integration tests/unit
  ```

- [x] T002 Add environment variables to `.env.example` for new configuration
  ```bash
  # SESSION_RECONNECT_MAX_DURATION=300
  # SESSION_RECONNECT_INITIAL_BACKOFF=1
  # SESSION_RECONNECT_MAX_BACKOFF=30
  # TELEGRAM_RATE_LIMIT_ENABLED=true
  # TELEGRAM_BACKOFF_INITIAL=1
  # TELEGRAM_BACKOFF_MAX=60
  # COMMAND_CONFIRMATION_TIMEOUT=60
  # SESSION_SCREEN_HISTORY_LINES=200
  ```

- [x] T003 Create state persistence directory structure utility in `claude_ctb/utils/state_persistence.py`

## Phase 3.2: Contract Tests (TDD - MUST FAIL BEFORE IMPLEMENTATION)

⚠️ **CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

- [x] T004 [P] Contract test: Telegram inline keyboard creation and callback handling in `tests/contract/test_telegram_api_contract.py`
  - Test InlineKeyboardMarkup message sending
  - Test CallbackQuery reception with correct callback_data
  - Assert buttons functional for 60 seconds
  - Mock Telegram Bot API responses

- [x] T005 [P] Contract test: Telegram rate limit exception handling in `tests/contract/test_telegram_api_contract.py`
  - Mock RetryAfter exception with retry_after field
  - Assert exception includes 1-120 second retry window
  - Verify rate limits: 30 msg/sec burst, 20 msg/min sustained

- [x] T006 [P] Contract test: Message splitting with markdown preservation in `tests/contract/test_telegram_api_contract.py`
  - Test 8000-char message with code blocks
  - Assert all chunks ≤4000 chars
  - Assert no broken markdown tags across chunks
  - Verify line boundary preservation

- [x] T007 [P] Contract test: tmux session existence check accuracy in `tests/contract/test_tmux_contract.py`
  - Test `has-session` returns exit code 0 for existing session
  - Test `has-session` returns exit code 1 for non-existent session
  - Verify command completes within 1 second
  - Test idempotency (repeated checks don't affect state)

- [x] T008 [P] Contract test: tmux 200-line scrollback capture in `tests/contract/test_tmux_contract.py`
  - Create session with 250 lines of output
  - Run `tmux capture-pane -t {session} -p -S -200`
  - Assert returns exactly 200 most recent lines
  - Verify UTF-8 encoding preserved
  - Test command completes within 5 seconds

- [x] T009 [P] Contract test: tmux hash-based change detection in `tests/contract/test_tmux_contract.py`
  - Capture screen, compute MD5 hash
  - Send command to session
  - Capture screen again, compute hash
  - Assert hashes differ (change detected)
  - Assert same content → same hash (deterministic)

## Phase 3.3: Integration Tests (TDD - MUST FAIL BEFORE IMPLEMENTATION)

- [x] T010 [P] Integration test: Session disconnection with reconnection retry in `tests/integration/test_session_disconnection_flow.py`
  - Start monitoring with active session
  - Kill session (tmux kill-session)
  - Assert system detects disconnection within 5 seconds
  - Assert retry attempts logged with exponential backoff (1s, 2s, 4s, 8s, ...)
  - Assert failure notification sent after max_duration timeout
  - Assert other sessions continue monitoring normally

- [x] T011 [P] Integration test: Restart behavior skips missed events in `tests/integration/test_restart_notification_skip.py`
  - Start session in WAITING_INPUT state
  - Send notification for completion
  - Stop monitoring (kill bot process)
  - Restart monitoring
  - Assert NO duplicate notification sent
  - Send new command, assert new notification sent

- [x] T012 [P] Integration test: Rate limit queue with exponential backoff in `tests/integration/test_rate_limit_handling.py`
  - Configure aggressive rate limit (for testing)
  - Trigger burst of 10 rapid completions
  - Mock rate limit exception
  - Assert messages queued in memory
  - Assert exponential backoff applied (1s, 2s, 4s, ...)
  - Assert all messages eventually delivered (no loss)
  - Verify FIFO order preserved

- [x] T013 [P] Integration test: Dangerous command confirmation flow in `tests/integration/test_dangerous_command_confirm.py`
  - Send dangerous command (`sudo rm -rf /tmp/test`)
  - Assert inline keyboard displayed with Confirm/Cancel buttons
  - Test Cancel button → command not executed
  - Test Confirm button → command sent to tmux session
  - Test 61-second timeout → buttons no longer work, "Confirmation expired"

- [x] T014 [P] Integration test: 200-line screen history state detection in `tests/integration/test_state_detection_200_lines.py`
  - Create session with 250 lines of output (generate long history)
  - Send new command (triggers new "esc to interrupt")
  - Assert system captures last 200 lines
  - Assert state detection analyzes 200-line buffer
  - Assert no false positives from historical artifacts (old "esc to interrupt" beyond 200 lines)
  - Assert notification sent for new completion

## Phase 3.4: Unit Tests (Edge Cases)

- [ ] T015 [P] Unit test: SessionReconnectionState exponential backoff calculation in `tests/unit/test_reconnect_logic.py`
  - Test backoff sequence: 1s, 2s, 4s, 8s, 16s, 30s (max)
  - Test retry_count increments correctly
  - Test max_duration timeout enforcement
  - Test state transitions: RECONNECTING → SUCCESS/FAILED

- [ ] T016 [P] Unit test: PersistedSessionState file I/O in `tests/unit/test_state_persistence.py`
  - Test JSON serialization/deserialization
  - Test atomic file write (temp file + rename)
  - Test MD5 hash validation (32 hex characters)
  - Test load from non-existent file (returns None)

- [ ] T017 [P] Unit test: MessageQueueEntry exponential backoff in `tests/unit/test_exponential_backoff.py`
  - Test queue FIFO ordering
  - Test exponential backoff: delay = min(initial * 2^retry_count, max)
  - Test priority handling (HIGH vs NORMAL)
  - Test in-memory queue cleared on restart

- [ ] T018 [P] Unit test: PendingConfirmation timeout cleanup in `tests/unit/test_confirmation_timeout.py`
  - Test 60-second TTL enforcement
  - Test expired confirmations auto-cancelled
  - Test confirmation_id hash uniqueness
  - Test status transitions: PENDING → CONFIRMED/CANCELLED/EXPIRED

- [ ] T019 [P] Unit test: ScreenHistory 200-line parsing in `tests/unit/test_screen_history_parsing.py`
  - Test `tmux capture-pane -S -200` command construction
  - Test line count validation (≤200)
  - Test UTF-8 encoding handling
  - Test hash computation consistency
  - Test sessions with <200 lines (returns available lines)

- [ ] T020 [P] Unit test: Dangerous pattern detection in `tests/unit/test_dangerous_patterns.py`
  - Test DANGEROUS_PATTERNS regex matching
  - Test patterns: `rm -rf`, `sudo `, `chmod `, `chown `, etc.
  - Test false positives (e.g., "sudo" in sentence context)
  - Test command input length limit (10,000 chars)

- [ ] T045 [P] Unit test: Concurrent session completion handling in `tests/unit/test_concurrent_completions.py`
  - Test multiple sessions completing work simultaneously (within same 3-5s poll cycle)
  - Assert each session gets individual notification (no dropped notifications)
  - Assert notifications sent in correct order (session discovery order)
  - Test race condition: two sessions transition to WAITING_INPUT at same time
  - Verify no notification state corruption

- [ ] T046 [P] Unit test: Non-existent session validation in `tests/unit/test_session_validation.py`
  - Test command sent to non-existent session returns error
  - Assert user receives "Session not found" notification
  - Test session name validation (reject invalid characters)
  - Test recently-killed session handling (graceful failure)
  - Verify no crash when target session missing

## Phase 3.5: Core Implementation (ONLY after tests are failing)

- [x] T021 Implement SessionReconnectionState dataclass in `claude_ctb/utils/session_reconnect.py`
  - Define fields: session_name, disconnect_time, retry_count, next_retry_time, max_duration_seconds, current_backoff_seconds, status
  - Implement exponential backoff calculation method
  - Implement timeout check method
  - Add state transition validation

- [x] T022 Implement PersistedSessionState in `claude_ctb/utils/state_persistence.py`
  - Define dataclass fields: session_name, screen_hash, last_state, timestamp, notification_sent
  - Implement JSON serialization (to_dict, from_dict)
  - Implement atomic file write (tempfile + os.rename)
  - Implement load method with error handling

- [x] T023 Implement MessageQueueEntry dataclass in `claude_ctb/telegram/message_queue.py`
  - Define fields: message_id, chat_id, text, retry_count, next_retry_time, enqueue_time, priority
  - Implement UUID generation for message_id
  - Add queue ordering comparison methods

- [x] T024 Implement ExponentialBackoffQueue in `claude_ctb/telegram/message_queue.py`
  - Implement in-memory queue (list of MessageQueueEntry)
  - Implement enqueue method
  - Implement backoff calculation: delay = min(initial * 2^retry_count, max)
  - Implement async retry loop with scheduled retries

- [x] T025 Implement PendingConfirmation tracking dict in `claude_ctb/telegram/bot.py`
  - Add module-level dict: `pending_confirmations: Dict[str, PendingConfirmation]`
  - Implement confirmation_id hash generation (session + command + timestamp)
  - Implement timeout cleanup background task
  - Add expiration check on callback handling

- [x] T026 Enhance session_state.py for 200-line capture in `claude_ctb/utils/session_state.py`
  - Update `get_screen_content()` to use `tmux capture-pane -S -200`
  - Add line_count validation
  - Update hash computation to use 200-line buffer
  - Preserve existing state detection logic

- [ ] T027 Add reconnection retry logic to multi_monitor.py in `claude_ctb/monitoring/multi_monitor.py`
  - Detect session disconnection (has-session fails)
  - Create SessionReconnectionState instance
  - Implement retry loop with exponential backoff
  - Send failure notification after max_duration timeout
  - Maintain operation of other sessions during reconnection
  - NOTE: Partial implementation exists, needs completion

- [ ] T028 Implement restart state skip behavior in `claude_ctb/monitoring/multi_monitor.py`
  - Load PersistedSessionState on monitoring startup
  - Compare current screen_hash with persisted hash
  - Skip notification if hashes identical (no change)
  - Proceed with normal detection if hashes differ
  - Persist state after notifications sent

- [x] T029 Implement dangerous command confirmation flow in `claude_ctb/telegram/bot.py`
  - Add dangerous pattern detection in `validate_input()`
  - Create InlineKeyboardMarkup with Confirm/Cancel buttons
  - Send confirmation request message
  - Store PendingConfirmation with 60s TTL
  - Implement CallbackQueryHandler for button clicks

- [x] T030 Implement callback handler for confirmation buttons in `claude_ctb/telegram/bot.py`
  - Parse callback_data (format: "confirm:{session}:{cmd_hash}" or "cancel:{session}:{cmd_hash}")
  - Lookup PendingConfirmation by confirmation_id
  - Check expiration (60s timeout)
  - On CONFIRMED: send command to tmux session
  - On CANCELLED/EXPIRED: discard command, notify user
  - Remove from pending_confirmations dict

- [ ] T031 Integrate ExponentialBackoffQueue with notifier in `claude_ctb/telegram/notifier.py`
  - Wrap `send_message()` calls with retry logic
  - Catch `telegram.error.RetryAfter` exception
  - Enqueue failed messages to ExponentialBackoffQueue
  - Start background retry task
  - Log queue size and retry attempts

- [ ] T047 Add Telegram API error handling for non-rate-limit failures in `claude_ctb/telegram/notifier.py`
  - Catch `telegram.error.NetworkError` (connection failures)
  - Catch `telegram.error.TimedOut` (API timeout)
  - Catch `telegram.error.BadRequest` (invalid parameters)
  - Enqueue failed messages to ExponentialBackoffQueue
  - Log error type and retry attempt
  - Max 3 retries for non-rate-limit errors before user notification

- [x] T032 Add configuration for new environment variables in `claude_ctb/config.py`
  - Add SESSION_RECONNECT_MAX_DURATION (default: 300)
  - Add SESSION_RECONNECT_INITIAL_BACKOFF (default: 1)
  - Add SESSION_RECONNECT_MAX_BACKOFF (default: 30)
  - Add TELEGRAM_RATE_LIMIT_ENABLED (default: true)
  - Add TELEGRAM_BACKOFF_INITIAL (default: 1)
  - Add TELEGRAM_BACKOFF_MAX (default: 60)
  - ADD COMMAND_CONFIRMATION_TIMEOUT (default: 60)
  - Add SESSION_SCREEN_HISTORY_LINES (default: 200)

## Phase 3.6: Integration

- [ ] T033 Wire ExponentialBackoffQueue to multi_monitor notification system in `claude_ctb/monitoring/multi_monitor.py`
  - Replace direct `send_message` calls with queued sending
  - Handle rate limit exceptions
  - Log queue metrics

- [ ] T034 Wire SessionReconnectionState to session discovery loop in `claude_ctb/monitoring/multi_monitor.py`
  - Integrate reconnection detection with existing `discover_sessions()`
  - Maintain reconnection state across poll cycles
  - Clean up successful reconnections

- [ ] T035 Wire PersistedSessionState to notification delivery in `claude_ctb/telegram/notifier.py`
  - Save state after each notification sent
  - Load state on monitoring startup
  - Use hash comparison to skip duplicate notifications

- [ ] T036 Update bot command handlers to use confirmation flow in `claude_ctb/telegram/bot.py`
  - Integrate dangerous pattern check with existing `handle_message()`
  - Preserve reply-based session targeting
  - Ensure confirmation timeout cleanup runs

## Phase 3.7: Polish

- [ ] T037 [P] Add unit tests for configuration validation in `tests/unit/test_config_validation.py`
  - Test default values
  - Test environment variable parsing
  - Test validation (e.g., backoff values > 0)

- [ ] T038 [P] Add performance test for 200-line capture overhead in `tests/unit/test_screen_capture_performance.py`
  - Measure capture time for 200 lines
  - Assert < 100ms hash computation
  - Assert < 5s capture timeout
  - Test with 10+ concurrent sessions

- [ ] T039 [P] Add logging for reconnection attempts in `claude_ctb/utils/session_reconnect.py`
  - Log each retry attempt with backoff delay
  - Log success/failure outcomes
  - Log total reconnection duration

- [ ] T040 [P] Add logging for rate limit queue operations in `claude_ctb/telegram/message_queue.py`
  - Log messages enqueued
  - Log retry attempts with backoff
  - Log queue size and delivery latency

- [ ] T041 [P] Add logging for dangerous command detections in `claude_ctb/telegram/bot.py`
  - Log pattern matches
  - Log confirmation requests
  - Log user confirmations/cancellations/timeouts

- [ ] T042 Update CLAUDE.md with reliability improvements in `/home/kyuwon/claude-ctb/CLAUDE.md`
  - Document new environment variables
  - Document confirmation flow for dangerous commands
  - Document restart behavior (skip missed events)
  - Document 200-line screen history depth

- [ ] T043 Run manual quickstart validation in `specs/001-spec-kit-constitution/quickstart.md`
  - Execute all 5 test scenarios
  - Verify Session Disconnection Reconnection
  - Verify Restart State Skip
  - Verify Rate Limit Queue
  - Verify Dangerous Command Confirmation
  - Verify 200-Line Screen History Detection
  - Document results and any failures

- [ ] T044 Run full test suite and verify performance targets
  ```bash
  PYTHONPATH=. uv run pytest tests/ -v
  # Verify: <10s notification latency, <5% CPU per session
  ```

## Phase 3.8: Monitoring Session Health (FR-033/FR-034)

- [ ] T048 [P] Unit test: Monitoring session status check in `tests/unit/test_monitoring_status.py`
  - Test detection of active monitoring session (claude-monitor)
  - Test detection of missing monitoring session
  - Assert status check completes within 1 second
  - Test health check returns session count and uptime

- [ ] T049 Implement monitoring session health check in `claude_ctb/monitoring/multi_monitor.py`
  - Add `get_monitoring_status()` method
  - Check if claude-monitor tmux session exists and is responsive
  - Return status dict with session_count, uptime, last_check_time
  - Add initialization check before starting notification loops

- [ ] T050 Add /status command output for monitoring session state in `claude_ctb/telegram/bot.py`
  - Integrate monitoring health check into existing /status command
  - Display: "Monitoring: Active (6 sessions)" or "Monitoring: INACTIVE"
  - Show uptime and last check time
  - Alert user if monitoring session not running

## Dependencies

**Setup → Tests → Implementation → Integration → Polish**

- T001-T003 (Setup) must complete before all others
- T004-T014 (Contract/Integration Tests) must complete before T021-T032 (Implementation)
- T015-T020 (Unit Tests) can run parallel with T021-T032
- T021-T032 (Core Implementation) must complete before T033-T036 (Integration)
- T033-T036 (Integration) must complete before T037-T044 (Polish)

**Specific Dependencies**:
- T021 blocks T027 (reconnection logic needs SessionReconnectionState)
- T022 blocks T028 (restart behavior needs PersistedSessionState)
- T023-T024 block T031, T047 (queue implementation needed)
- T025 blocks T029-T030 (confirmation tracking needed)
- T026 blocks T014 (200-line capture needed for integration test)
- T032 blocks all implementation (config must exist first)
- T045 blocks T027 (multi_monitor must handle concurrent completions)
- T046 blocks T036 (bot must validate session existence)

## Parallel Execution Examples

**Contract Tests (T004-T009)** - All can run in parallel:
```bash
# Launch all contract tests together
pytest tests/contract/test_telegram_api_contract.py tests/contract/test_tmux_contract.py -v
```

**Integration Tests (T010-T014)** - All can run in parallel:
```bash
# Launch all integration tests together
pytest tests/integration/ -v
```

**Unit Tests (T015-T020, T045-T046)** - All can run in parallel:
```bash
# Launch all unit tests together
pytest tests/unit/test_reconnect_logic.py \
       tests/unit/test_state_persistence.py \
       tests/unit/test_exponential_backoff.py \
       tests/unit/test_confirmation_timeout.py \
       tests/unit/test_screen_history_parsing.py \
       tests/unit/test_dangerous_patterns.py \
       tests/unit/test_concurrent_completions.py \
       tests/unit/test_session_validation.py -v
```

**Polish Tests (T037-T041)** - Logging and performance tests can run in parallel:
```bash
pytest tests/unit/test_config_validation.py \
       tests/unit/test_screen_capture_performance.py -v
```

## Notes

- All test tasks (T004-T020, T045-T046) MUST fail initially (TDD requirement)
- Implementation tasks (T021-T036, T047) make tests pass
- Run `pytest -xvs` to see detailed test failures
- Use `pytest --tb=short` for concise failure reports
- Tests marked [P] are independent and can run in parallel
- Integration tasks (T033-T036) are sequential (order matters)
- Quickstart validation (T043) is manual end-to-end testing
- Performance target verification (T044) must pass before completion

## Success Criteria

- [ ] All 47 tasks completed
- [ ] All pytest tests pass
- [ ] Performance targets met (<10s latency, <5% CPU, <1s command response)
- [ ] Quickstart validation scenarios pass
- [ ] No constitutional violations introduced
- [ ] Code review checklist passed (see constitution.md)
