# Contract: tmux Session Management

**Feature**: 001-spec-kit-constitution
**Date**: 2025-10-01
**External Dependency**: tmux (terminal multiplexer)

## Purpose

Define expected behavior of tmux commands for session reconnection and screen history capture.

## Contract Operations

### 1. Session Existence Check

**Command**: `tmux has-session -t {session_name}`

**Expected Behavior**:
```bash
# Session exists
$ tmux has-session -t claude_my-project
$ echo $?
0

# Session does not exist
$ tmux has-session -t nonexistent
$ echo $?
1
```

**Contract Assertions**:
- Exit code 0 → session exists
- Exit code 1 → session does not exist
- Command completes within 1 second
- No output to stdout/stderr on success

**Failure Modes**:
- tmux server not running → exit code 1
- Invalid session name characters → exit code 1

---

### 2. Screen Content Capture (200 lines)

**Command**: `tmux capture-pane -t {session_name} -p -S -200`

**Flags**:
- `-t`: Target session name
- `-p`: Print to stdout (not to paste buffer)
- `-S -200`: Start 200 lines back in scrollback history

**Expected Output**:
```
Line 1 from history
Line 2 from history
...
Line 200 (most recent)
```

**Contract Assertions**:
- Output contains ≤200 lines (may be less for new sessions)
- Lines preserve original formatting (tabs, spaces)
- UTF-8 encoding
- Exit code 0 on success
- Command completes within 5 seconds

**Failure Modes**:
- Session doesn't exist → exit code 1, empty stdout
- tmux server not running → exit code 1
- Session has < 200 lines → returns available lines (valid)

---

### 3. Session Reconnection Retry

**Command Sequence**:
```bash
# Attempt 1
tmux has-session -t claude_my-project || exit_code=$?

# Wait backoff (1s, 2s, 4s, ...)
sleep $backoff_seconds

# Retry
tmux has-session -t claude_my-project || exit_code=$?
```

**Expected Behavior**:
- Transient failures (process paused) recover on retry
- Permanent failures (session killed) return exit code 1 consistently
- No side effects from repeated has-session checks

**Contract Assertions**:
- has-session is idempotent (no state changes)
- Repeated checks don't affect session state
- Session list doesn't include disconnected sessions

---

### 4. Screen Content Hash Comparison

**Operation**: Hash last 200 lines for change detection

**Process**:
```python
import hashlib

# Capture screen
screen_content = subprocess.run(
    f"tmux capture-pane -t {session_name} -p -S -200",
    shell=True, capture_output=True, text=True
).stdout

# Hash for comparison
screen_hash = hashlib.md5(screen_content.encode()).hexdigest()
```

**Contract Assertions**:
- Same screen content → same hash (deterministic)
- Different content → different hash (collision negligible)
- Hash computation < 100ms for 200 lines

---

## Error Handling

| Error | Exit Code | Cause | Expected Handling |
|-------|-----------|-------|-------------------|
| Session not found | 1 | Session killed/expired | Retry with backoff, then notify user |
| tmux server down | 1 | System issue | Log fatal error, exit monitoring |
| Invalid session name | 1 | Programming error | Validate session names on creation |
| Capture timeout | None | Hung session | Kill subprocess after 5s, mark session ERROR |

---

## Contract Test Requirements

Contract tests MUST verify:

1. **Session existence check accuracy**
   - Test: Create session, check existence, destroy session, check again
   - Assert: Exit codes correct (0 then 1)

2. **200-line scrollback capture**
   - Test: Fill session with 250 lines, capture with -S -200
   - Assert: Returns exactly 200 most recent lines

3. **Reconnection after transient failure**
   - Test: Suspend tmux server, resume, check session
   - Assert: has-session recovers after resume

4. **Hash-based change detection**
   - Test: Capture screen, send command, capture again
   - Assert: Hashes differ (change detected)

5. **UTF-8 encoding handling**
   - Test: Session with non-ASCII characters (Korean, emoji)
   - Assert: Capture preserves UTF-8, no mojibake

---

## Performance Requirements

| Operation | Max Duration | Rationale |
|-----------|--------------|-----------|
| has-session | 1 second | Blocking check, must be fast |
| capture-pane | 5 seconds | Large scrollback, timeout prevents hang |
| Hash computation | 100 ms | Runs every poll cycle (3-5s) |

---

## Dependencies

- tmux version 2.6+ (tested with 3.x)
- Linux kernel 4.x+ (RHEL 8 compatible)
- UTF-8 locale (`LANG=en_US.UTF-8`)

---

## Notes

- tmux manual: `man tmux`, search "capture-pane"
- Scrollback buffer size: default 2000 lines (configurable)
- Session names must match: `[a-zA-Z0-9._-]+`
- Existing implementation: `claude_ctb/utils/session_state.py`
