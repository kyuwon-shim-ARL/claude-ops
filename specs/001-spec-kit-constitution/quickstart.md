# Quickstart Validation: Claude-CTB System Reliability Improvements

**Feature**: 001-spec-kit-constitution
**Date**: 2025-10-01
**Purpose**: Manual validation steps to verify all reliability improvements work end-to-end

## Prerequisites

- Claude-CTB installed and configured (`.env` with Telegram credentials)
- At least 2 Claude Code sessions running in tmux (`claude_test1`, `claude_test2`)
- Telegram bot accessible from mobile device

---

## Test Scenario 1: Session Disconnection Reconnection

**Objective**: Verify system retries tmux session reconnection with exponential backoff, then notifies user on failure

### Steps

1. **Setup**: Start monitoring with 2 active sessions
   ```bash
   tmux new-session -d -s claude_test1 -c /tmp
   tmux send-keys -t claude_test1 'claude' Enter

   tmux new-session -d -s claude_test2 -c /tmp
   tmux send-keys -t claude_test2 'claude' Enter

   python -m claude_ctb.telegram.bot
   ```

2. **Trigger disconnection**: Kill one session
   ```bash
   tmux kill-session -t claude_test1
   ```

3. **Observe**: Check monitoring logs
   ```bash
   tail -f /tmp/claude-ctb.log
   # Expected: "Session claude_test1 disconnected, retrying..."
   ```

4. **Verify retry attempts**: Wait 5 minutes (max reconnection duration)
   - Expected log entries: Multiple retry attempts with increasing backoff (1s, 2s, 4s, 8s...)

5. **Verify failure notification**: Check Telegram
   - Expected: Message "⚠️ Session claude_test1 failed to reconnect after 5 minutes"

**Success Criteria**:
- [x] System detects disconnection within 5 seconds (one poll cycle)
- [x] Retry attempts logged with exponential backoff
- [x] Failure notification sent after configured timeout
- [x] Other sessions (`claude_test2`) continue monitoring normally

---

## Test Scenario 2: Restart State Skip (No Duplicate Notifications)

**Objective**: Verify system skips notifications for unchanged sessions after restart

### Steps

1. **Setup**: Start session in waiting state
   ```bash
   tmux new-session -d -s claude_test -c /tmp
   tmux send-keys -t claude_test 'claude' Enter
   # Wait for Claude to show prompt (WAITING_INPUT state)
   ```

2. **Trigger notification**: Run a command, wait for completion
   ```bash
   tmux send-keys -t claude_test 'list files in current directory' Enter
   # Wait for completion, receive Telegram notification
   ```

3. **Stop monitoring**: Kill bot process
   ```bash
   pkill -f claude_ctb.telegram.bot
   ```

4. **Restart monitoring**: Start bot again
   ```bash
   python -m claude_ctb.telegram.bot
   ```

5. **Verify no duplicate**: Check Telegram
   - Expected: NO new notification for `claude_test` (screen unchanged)

6. **Send new command**: Verify detection still works
   ```bash
   tmux send-keys -t claude_test 'what is 2+2?' Enter
   # Wait for completion
   ```

7. **Verify new notification**: Check Telegram
   - Expected: New notification for completed command

**Success Criteria**:
- [x] No duplicate notification sent after restart for unchanged screen
- [x] New work completion triggers notification correctly
- [x] State file persisted at `/tmp/claude-ctb/state/claude_test.state`

---

## Test Scenario 3: Rate Limit Queue with Exponential Backoff

**Objective**: Verify messages queue and retry with backoff when rate limited

### Steps

1. **Setup**: Configure aggressive rate limit (for testing)
   ```bash
   # .env
   TELEGRAM_RATE_LIMIT_ENABLED=true
   TELEGRAM_BACKOFF_INITIAL=1
   ```

2. **Trigger burst**: Complete 10 commands rapidly
   ```bash
   for i in {1..10}; do
     tmux send-keys -t claude_test1 "echo test $i" Enter
     sleep 1
   done
   ```

3. **Monitor logs**: Check for rate limit handling
   ```bash
   tail -f /tmp/claude-ctb.log
   # Expected: "Rate limit hit, queueing message with backoff"
   ```

4. **Verify queue**: Check all messages eventually delivered
   - Expected: All 10 notifications arrive (may take 30-60 seconds with backoff)

5. **Verify order**: Confirm messages arrived in correct sequence
   - Expected: Notifications 1→10 in order (queue preserves FIFO)

**Success Criteria**:
- [x] Rate limit exceptions caught and handled
- [x] Messages queued in memory
- [x] Exponential backoff applied (1s, 2s, 4s, ...)
- [x] All messages eventually delivered (no loss)

---

## Test Scenario 4: Dangerous Command Confirmation

**Objective**: Verify dangerous commands require explicit confirmation before execution

### Steps

1. **Setup**: Active Claude session
   ```bash
   tmux new-session -d -s claude_test -c /tmp
   tmux send-keys -t claude_test 'claude' Enter
   ```

2. **Send dangerous command**: Via Telegram, reply to session with:
   ```
   sudo rm -rf /tmp/test
   ```

3. **Verify confirmation prompt**: Check Telegram
   - Expected: Message with inline keyboard "✅ Confirm" / "❌ Cancel"
   - Expected: Warning text showing full command

4. **Test cancellation**: Click "❌ Cancel"
   - Expected: Response "Command cancelled"
   - Expected: Command NOT sent to tmux session

5. **Send dangerous command again**: Same command
   ```
   sudo rm -rf /tmp/test
   ```

6. **Test confirmation**: Click "✅ Confirm"
   - Expected: Response "Command confirmed and sent to claude_test"
   - Expected: Command sent to tmux session (verify with `tmux capture-pane`)

7. **Test timeout**: Send dangerous command, wait 61 seconds without clicking
   - Expected: After 60s, buttons no longer work
   - Expected: Click shows "Confirmation expired"

**Success Criteria**:
- [x] Dangerous patterns detected (`sudo`, `rm -rf`, etc.)
- [x] Inline keyboard displayed with Confirm/Cancel
- [x] Cancel prevents command execution
- [x] Confirm executes command
- [x] 60-second timeout enforced

---

## Test Scenario 5: 200-Line Screen History Detection

**Objective**: Verify state detection analyzes last 200 lines, avoiding false positives from historical artifacts

### Steps

1. **Setup**: Session with long output history
   ```bash
   tmux new-session -d -s claude_test -c /tmp
   tmux send-keys -t claude_test 'claude' Enter

   # Generate 250 lines of output
   tmux send-keys -t claude_test 'print numbers 1 to 250' Enter
   # Wait for completion
   ```

2. **Send new command**: Trigger work
   ```bash
   tmux send-keys -t claude_test 'what is the capital of France?' Enter
   # Wait for completion (new "esc to interrupt" should appear)
   ```

3. **Verify detection**: Check logs
   ```bash
   grep "Analyzing last 200 lines" /tmp/claude-ctb.log
   ```

4. **Confirm notification**: Check Telegram
   - Expected: Notification for completed command (not confused by old "esc to interrupt" beyond 200 lines)

5. **Verify screen capture**: Manual check
   ```bash
   tmux capture-pane -t claude_test -p -S -200 | wc -l
   # Expected: 200 lines (or less if session < 200 lines old)
   ```

**Success Criteria**:
- [x] System captures last 200 lines of scrollback
- [x] State detection analyzes 200-line buffer
- [x] No false positives from historical artifacts (old "esc to interrupt")
- [x] Notification accuracy maintained

---

## Integration Test: Full Workflow

**Objective**: Verify all improvements work together in realistic multi-session scenario

### Steps

1. **Setup**: 3 Claude sessions, monitoring running
2. **Simulate work**: Complete tasks in sessions 1 & 2, verify notifications
3. **Kill session**: Disconnect session 3, verify reconnection attempts
4. **Rate limit**: Trigger burst notifications (10+ sessions completing work)
5. **Dangerous command**: Send `sudo` command during high load
6. **Restart**: Kill monitoring, restart, verify no duplicate notifications
7. **200-line history**: Session with long output, verify accurate detection

**Success Criteria**:
- All 5 improvements work simultaneously without conflicts
- Performance: <10s notification latency maintained
- No duplicate notifications
- No false positive state detections
- All confirmations processed correctly

---

## Validation Checklist

After completing all test scenarios:

- [ ] Session reconnection retry logic works with configurable backoff
- [ ] Restart skips missed events (no duplicates)
- [ ] Rate limit handling queues messages with exponential backoff
- [ ] Dangerous commands require confirmation (60s timeout)
- [ ] 200-line screen history prevents false positives
- [ ] All contract tests pass (Telegram API, tmux)
- [ ] Integration tests pass (multi-session workflow)
- [ ] Performance targets met (<10s latency, <5% CPU)

---

## Rollback Plan

If validation fails:

1. **Revert changes**: `git checkout main`
2. **Restart monitoring**: Existing system continues working
3. **Review logs**: Identify failure mode
4. **Fix and re-test**: Address issue, run quickstart again

---

## Notes

- Run validation in staging environment first (test Telegram bot)
- Keep sessions short (<100 lines) for faster testing
- Monitor CPU/memory during rate limit tests (performance check)
- Document any failures with logs and screenshots
