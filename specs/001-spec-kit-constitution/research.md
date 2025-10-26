# Research: Claude-CTB System Reliability Improvements

**Feature**: 001-spec-kit-constitution
**Date**: 2025-10-01

## Overview

Research for implementing five critical reliability improvements based on clarified requirements. All technology choices are established (Python 3.10+, python-telegram-bot>=20.0, tmux, pytest). Focus is on implementation patterns and best practices.

## 1. Session Reconnection Patterns

### Decision
Configurable retry with exponential backoff + maximum duration timeout

### Rationale
- Transient tmux disconnections (process pauses, system load) require retry logic
- Network issues may be temporary; exponential backoff avoids thundering herd
- Maximum duration prevents infinite retry loops consuming resources
- Configuration allows tuning per deployment environment

### Implementation Approach
```python
# Configuration parameters (via .env)
SESSION_RECONNECT_MAX_DURATION=300  # 5 minutes default
SESSION_RECONNECT_INITIAL_BACKOFF=1  # 1 second
SESSION_RECONNECT_MAX_BACKOFF=30     # 30 seconds max

# Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s, 30s, ...
# Total attempts within 5 minutes: ~10-15 attempts
```

### Alternatives Considered
- **Fixed retry count** (e.g., 5 attempts): Rejected - doesn't account for varying network conditions
- **Immediate failure**: Rejected - too aggressive for transient issues
- **Infinite retry**: Rejected - resource exhaustion risk

### References
- python-telegram-bot uses similar backoff for API retries
- Kubernetes liveness probes use exponential backoff patterns

---

## 2. Restart State Management

### Decision
Persist last-known screen content hash, skip notifications if state unchanged across restart

### Rationale
- User clarification: "Skip missed events and only track new state changes after restart"
- Prevents duplicate notifications for work completed during downtime
- Hash comparison is lightweight and deterministic
- Aligns with existing `multi_monitor.py` hash-based change detection

### Implementation Approach
```python
# Store state in filesystem (e.g., /tmp/claude-ctb/state/)
# Per-session file: /tmp/claude-ctb/state/{session_name}.state
{
  "screen_hash": "md5_hash_of_last_200_lines",
  "last_state": "WAITING_INPUT",
  "timestamp": "2025-10-01T12:34:56Z"
}

# On restart:
# 1. Load persisted state for each discovered session
# 2. Compare current screen hash with persisted hash
# 3. If identical: skip notification (no change)
# 4. If different: proceed with normal detection logic
```

### Alternatives Considered
- **Full event replay**: Rejected - violates "skip missed events" clarification
- **State reset (treat as new)**: Rejected - loses context, may send duplicate notifications
- **Database storage**: Rejected - violates constitution (no database dependencies)

### References
- Existing `multi_monitor.py:get_screen_content_hash()` provides MD5-based change detection
- Systemd service restart patterns for stateful daemons

---

## 3. Rate Limit Handling

### Decision
In-memory message queue with exponential backoff retry (leveraging python-telegram-bot built-in + custom wrapper)

### Rationale
- Telegram Bot API limits: 30 messages/second burst, 20 messages/minute sustained
- python-telegram-bot v20.0+ has built-in rate limiter (NetworkRequestHandler)
- Custom wrapper adds queue persistence and exponential backoff for sustained overload
- In-memory queue sufficient (restart clears queue, aligns with "skip missed events")

### Implementation Approach
```python
# python-telegram-bot configuration
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

app = ApplicationBuilder()
    .token(token)
    .rate_limiter(rate_limiter=telegram.ext.RateLimiter())  # Built-in limiter
    .build()

# Custom exponential backoff wrapper
class ExponentialBackoffQueue:
    def __init__(self, initial_backoff=1, max_backoff=60):
        self.queue = []  # (message, retry_count, next_retry_time)
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

    async def send_with_retry(self, bot, chat_id, text):
        try:
            await bot.send_message(chat_id, text)
        except telegram.error.RetryAfter as e:
            backoff = min(self.initial_backoff * (2 ** retry_count), self.max_backoff)
            schedule_retry(message, retry_count + 1, time.time() + backoff)
```

### Alternatives Considered
- **Disk-based queue**: Rejected - adds complexity, filesystem I/O overhead
- **Drop messages**: Rejected - violates FR-017 ("without losing messages")
- **Block until success**: Rejected - blocks entire monitoring loop

### References
- python-telegram-bot v20.0 rate limiting: https://docs.python-telegram-bot.org/en/stable/telegram.ext.ratelimiter.html
- Telegram Bot API rate limits: https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this

---

## 4. Dangerous Command Confirmation

### Decision
Telegram InlineKeyboardMarkup with "Confirm"/"Cancel" buttons, 60-second timeout

### Rationale
- Clear user intent (explicit button click)
- Follows Telegram UX patterns (common in bots)
- Timeout prevents stale confirmations (user forgets, walks away)
- Non-blocking (doesn't interfere with other session operations)

### Implementation Approach
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Dangerous patterns (existing in bot.py:validate_input)
DANGEROUS_PATTERNS = ['rm -rf', 'sudo ', 'chmod ', ...]

# On detection:
keyboard = [
    [
        InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{session}:{cmd_hash}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{session}:{cmd_hash}")
    ]
]
reply_markup = InlineKeyboardMarkup(keyboard)
await update.message.reply_text(
    f"⚠️ Dangerous command detected:\n`{command}`\n\nConfirm execution?",
    reply_markup=reply_markup
)

# Store pending confirmation with 60s TTL
pending_confirmations[cmd_hash] = {
    "command": command,
    "session": session_name,
    "expires": time.time() + 60
}
```

### Alternatives Considered
- **Re-type command**: Rejected - poor UX, typo-prone
- **Whitelist approach**: Rejected - too restrictive, hampers legitimate use
- **Silent block**: Rejected - violates clarification (user chose confirmation)

### References
- Telegram Bot API InlineKeyboard: https://core.telegram.org/bots/api#inlinekeyboardmarkup
- Existing confirmation patterns in bot.py for session actions

---

## 5. Screen History Depth

### Decision
`tmux capture-pane -S -200` (last 200 lines from scrollback buffer)

### Rationale
- User clarification: "Last 200 lines sufficient"
- Claude Code output typically < 100 lines per response, 200 provides buffer
- tmux -S flag: start line offset from scrollback history
- Performance: 200 lines ≈ 10-20 KB text, negligible processing overhead

### Implementation Approach
```python
# Update session_state.py:get_screen_content()
def get_screen_content(session_name: str, lines: int = 200) -> str:
    """Get last N lines of tmux session screen including scrollback"""
    result = subprocess.run(
        f"tmux capture-pane -t {session_name} -p -S -{lines}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=5
    )
    return result.stdout if result.returncode == 0 else ""

# Current implementation uses -p (visible pane only, ~50 lines)
# New implementation adds -S -200 (scrollback 200 lines)
```

### Alternatives Considered
- **Full scrollback** (`-S -`): Rejected - performance cost, unbounded history
- **Last 50 lines** (current default): Rejected - insufficient per clarification
- **Dynamic sizing**: Rejected - unnecessary complexity, 200 lines sufficient

### References
- tmux capture-pane manual: `man tmux`, search "capture-pane"
- Existing implementation: `claude_ctb/utils/session_state.py:get_screen_content()`

---

---

## 6. API Compatibility During Refactoring (Post-Implementation Discovery)

### Problem Identified
During `claude_ops` → `claude_ctb` refactoring (commit 1b1abf3), improvements from bb6478c to v1 tracker were not propagated to v2, causing wait time tracking failures.

### Root Cause Analysis
1. **Dual version maintenance**: v1 (`wait_time_tracker.py`) and v2 (`wait_time_tracker_v2.py`) exist simultaneously
2. **v1-only fix**: commit bb6478c added `mark_completion_safe()` to v1 only (handles session suffix changes like `claude_project-5` → `claude_project-6`)
3. **Refactoring gap**: simple file moves (`claude_ops/` → `claude_ctb/`) didn't trigger cross-version sync
4. **Runtime failure**: system uses v2 (via `migrate_to_v2()`), but v2 lacks suffix handling → completion times not tracked

### Decision
Two-pronged solution:
1. **Immediate fix**: Port missing methods from v1 to v2
2. **Prevention**: Automated API compatibility checker

### Implementation Approach

#### Missing Methods (v1 → v2)
```python
# 1. Session suffix normalization
def normalize_session_name(session_name: str) -> str:
    """Remove trailing -\d+ suffix for continuity tracking"""
    return re.sub(r'-\d+$', '', session_name)

# 2. Suffix-aware completion marking
def mark_completion_safe(session_name: str):
    """Update existing record if base name matches"""
    base_name = normalize_session_name(session_name)
    # Replace old suffix record with new suffix

# 3. API compatibility aliases
def cleanup_old_sessions(max_age_hours=24):
    """Alias for cleanup_stale_data() - used by multi_monitor.py:584"""
    return cleanup_stale_data(max_age_hours)

def remove_session(session_name: str):
    """Alias for reset_session() - used by multi_monitor.py:503"""
    return reset_session(session_name)
```

#### Automated Compatibility Check
```bash
# scripts/check_api_compatibility.py
# - Extracts public methods from v1 and v2
# - Finds usages in codebase (grep-based)
# - Excludes self-references (v1 internal calls)
# - Exit code 0 (safe) or 1 (incompatible)
```

### Rationale
- **Suffix handling critical**: Claude sessions recreate with incremented suffixes on restart
- **Backwards compatibility**: Existing code calls `cleanup_old_sessions()` and `remove_session()`
- **Prevention > cure**: Automated check catches future API drift before deployment
- **CI/CD integration**: Script suitable for pre-commit hooks or GitHub Actions

### Alternatives Considered
- **Deprecate v1**: Rejected - requires extensive testing, higher risk
- **Manual review**: Rejected - error-prone, doesn't scale
- **Merge v1+v2**: Rejected - v2 has architectural improvements worth keeping

### References
- Original fix: commit bb6478c "fix: critical notification tracking with session suffix changes"
- Refactoring: commit 1b1abf3 "refactor: rename claude_ops to claude_ctb"
- Usage locations: `multi_monitor.py` lines 503 (remove_session), 584 (cleanup_old_sessions)

---

---

## 7. Restart State Skip Bug Fixes (Post-Deployment Discovery)

### Problems Identified (Critical)

**Bug 1: Permanent Notification Block**
- Symptom: "대기시간이 제대로 인식 안되는" - no completions tracked after restart
- Root cause: `notification_sent=True` persisted to disk, never reset
- Impact: `completion_times.json` stayed empty, wait time calculation impossible

**Bug 2: Restart False Positives**
- Symptom: "아무것도 안했는데 대기시간이 줄어있음" - false completions at restart
- Root cause: UNKNOWN → WAITING_INPUT treated as completion
- Impact: Sessions at prompt triggered completion events on restart

### Root Cause Analysis

**Bug 1 Timeline:**
1. Session completes work → `notification_sent=True` saved
2. System restarts → loads `notification_sent=True` from disk (line 357)
3. New work completes → screen changes but flag still True
4. No notification sent → no completion time recorded
5. Result: `completion_times.json` = {}, wait time tracking broken

**Bug 2 Timeline:**
1. System restart → all sessions start with `previous_state=UNKNOWN`
2. Idle session at prompt → `current_state=WAITING_INPUT`
3. Line 261 check: "any → WAITING_INPUT" triggers notification
4. UNKNOWN → WAITING_INPUT treated as completion ❌
5. Result: False positive completion, wait time reset for idle sessions

### Decision

Two-part fix addressing both bugs:

**Fix 1: Reset notification_sent on restart**
```python
# Line 359: Always start False, even if persisted True
self.notification_sent[session_name] = False
# Keep screen_hash for duplicate detection
```

**Fix 2: Ignore UNKNOWN transitions**
```python
# Line 262-265: Check previous state before notifying
if previous_state != SessionState.UNKNOWN:
    should_notify = True
```

### Implementation Approach

**Fix 1 Logic:**
- Persisted hash prevents duplicate of SAME completion (restart spam protection)
- Reset flag allows NEW completions after restart (fixes notification block)
- Behavior:
  - Screen unchanged → no notification ✅ (correct, same work)
  - Screen changed → notification sent ✅ (correct, new work)

**Fix 2 Logic:**
- Valid transitions that trigger notifications:
  - ✅ WORKING → WAITING_INPUT (actual completion)
  - ✅ IDLE → WAITING_INPUT (resumed work completed)
  - ❌ UNKNOWN → WAITING_INPUT (restart detection, not completion)

### Rationale

**Why both fixes needed:**
- Fix 1 alone: Notifications work, but restart causes spam
- Fix 2 alone: No spam, but notifications still blocked by flag
- Together: Clean restart + accurate detection

**Design principle:**
- Restart state skip should prevent DUPLICATE notifications
- But NOT prevent NEW work notifications
- Screen hash handles duplicates, flag shouldn't be persistent

### Alternatives Considered

- **Delete state files on restart**: Rejected - loses valuable hash data
- **Time-based expiry**: Rejected - completion timing varies widely
- **Manual reset command**: Rejected - requires user intervention

### Testing

Created test scenario:
1. Create state file with `notification_sent=True`
2. Restart monitor → verify flag reset to False
3. Session at prompt → verify no false positive
4. Actual work completes → verify notification sent

### References

- Bug 1 commit: 3e71111
- Bug 2 commit: b7fbbae
- Related feature: Phase 3.2 Restart State Skip (T010-T014)

---

## Summary

All research complete. No unknowns remain. Ready for Phase 1 (Design & Contracts).

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Session Reconnection | Exponential backoff + timeout | Handles transient failures, prevents resource exhaustion |
| Restart State | Hash-based skip logic | Prevents duplicate notifications, aligns with clarification |
| Rate Limiting | In-memory queue + backoff | Leverages built-in limiter, handles sustained overload |
| Dangerous Commands | InlineKeyboard confirmation | Clear intent, follows Telegram UX, non-blocking |
| Screen History | 200-line scrollback | Sufficient context per clarification, low overhead |
| API Compatibility | Port missing methods + automated check | Prevents refactoring regressions, ensures v1/v2 parity |
| Restart Bug Fixes | Reset flag + ignore UNKNOWN | Fixes notification block + false positives |
