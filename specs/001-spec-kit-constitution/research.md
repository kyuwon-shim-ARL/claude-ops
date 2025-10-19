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

## Summary

All research complete. No unknowns remain. Ready for Phase 1 (Design & Contracts).

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Session Reconnection | Exponential backoff + timeout | Handles transient failures, prevents resource exhaustion |
| Restart State | Hash-based skip logic | Prevents duplicate notifications, aligns with clarification |
| Rate Limiting | In-memory queue + backoff | Leverages built-in limiter, handles sustained overload |
| Dangerous Commands | InlineKeyboard confirmation | Clear intent, follows Telegram UX, non-blocking |
| Screen History | 200-line scrollback | Sufficient context per clarification, low overhead |
