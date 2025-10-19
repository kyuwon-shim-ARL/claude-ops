# Data Model: Claude-CTB System Reliability Improvements

**Feature**: 001-spec-kit-constitution
**Date**: 2025-10-01

## Entities

### 1. SessionReconnectionState

**Purpose**: Track reconnection attempts for disconnected tmux sessions

**Attributes**:
- `session_name` (string): tmux session identifier (e.g., "claude_my-project")
- `disconnect_time` (datetime): When disconnection was first detected
- `retry_count` (int): Number of reconnection attempts made
- `next_retry_time` (datetime): Scheduled time for next attempt
- `max_duration_seconds` (int): Configuration: maximum reconnection window
- `current_backoff_seconds` (int): Current backoff delay (exponential growth)
- `status` (enum): RECONNECTING | FAILED | SUCCESS

**Relationships**:
- Associated with one ClaudeCodeSession
- Referenced by MonitoringThread for retry logic

**Validation Rules**:
- `retry_count` >= 0
- `next_retry_time` > `disconnect_time`
- `current_backoff_seconds` <= max_backoff (30s)
- `disconnect_time` + `max_duration_seconds` defines absolute timeout

**State Transitions**:
```
RECONNECTING → SUCCESS (tmux session responds)
RECONNECTING → FAILED (max_duration exceeded)
FAILED → (terminal state, notification sent)
```

---

### 2. PersistedSessionState

**Purpose**: Track last-known session state across monitoring system restarts

**Attributes**:
- `session_name` (string): tmux session identifier
- `screen_hash` (string): MD5 hash of last 200 lines of screen content
- `last_state` (enum): ERROR | WAITING_INPUT | WORKING | IDLE | UNKNOWN
- `timestamp` (datetime): When state was last persisted
- `notification_sent` (bool): Whether notification was already sent for current state

**Storage**: Filesystem at `/tmp/claude-ctb/state/{session_name}.state` (JSON)

**Relationships**:
- One-to-one with ClaudeCodeSession
- Read on monitoring startup, written on state changes

**Validation Rules**:
- `screen_hash` matches MD5 format (32 hex characters)
- `timestamp` <= current time
- File persisted atomically (write to temp, rename)

**State Transitions**:
```
On restart:
- Load persisted state
- Compare screen_hash with current screen
- If identical → skip notification (no change)
- If different → proceed with detection logic
```

---

### 3. MessageQueueEntry

**Purpose**: Track queued Telegram messages during rate limit conditions

**Attributes**:
- `message_id` (string): Unique identifier (UUID)
- `chat_id` (int): Telegram chat ID
- `text` (string): Message content (≤4000 chars per chunk)
- `retry_count` (int): Number of send attempts
- `next_retry_time` (datetime): Scheduled retry timestamp
- `enqueue_time` (datetime): When message was first queued
- `priority` (enum): HIGH | NORMAL (notifications are HIGH)

**Storage**: In-memory queue (cleared on restart per clarification)

**Relationships**:
- Managed by ExponentialBackoffQueue
- Processed by Telegram message sending loop

**Validation Rules**:
- `text` length ≤ 4000 characters (Telegram limit with buffer)
- `retry_count` >= 0
- `next_retry_time` > current time (or immediate send)
- Exponential backoff: delay = min(initial_backoff * 2^retry_count, max_backoff)

**State Transitions**:
```
QUEUED → SENDING (retry time reached)
SENDING → SUCCESS (message sent)
SENDING → RETRYING (rate limit hit, increment retry_count)
```

---

### 4. PendingConfirmation

**Purpose**: Track dangerous commands awaiting user confirmation

**Attributes**:
- `confirmation_id` (string): Hash of (session_name + command + timestamp)
- `session_name` (string): Target tmux session
- `command` (string): Full command text
- `user_id` (int): Telegram user who sent command
- `message_id` (int): Telegram message ID with confirmation buttons
- `created_time` (datetime): When confirmation was requested
- `expires_time` (datetime): Timeout (created_time + 60s)
- `status` (enum): PENDING | CONFIRMED | CANCELLED | EXPIRED

**Storage**: In-memory dict (cleared on restart)

**Relationships**:
- One-to-one with Telegram InlineKeyboardMarkup callback
- Referenced by command execution logic

**Validation Rules**:
- `expires_time` = `created_time` + 60 seconds
- `command` matches DANGEROUS_PATTERNS regex
- Expired confirmations auto-cancelled (cleanup loop)

**State Transitions**:
```
PENDING → CONFIRMED (user clicks ✅)
PENDING → CANCELLED (user clicks ❌)
PENDING → EXPIRED (60s timeout)
CONFIRMED → (execute command)
CANCELLED/EXPIRED → (discard command)
```

---

### 5. ScreenHistory (Enhanced)

**Purpose**: Capture last 200 lines of tmux session screen for state detection

**Attributes**:
- `session_name` (string): tmux session identifier
- `content` (string): Raw screen text (last 200 lines)
- `line_count` (int): Actual number of lines captured
- `capture_time` (datetime): When screen was captured
- `hash` (string): MD5 hash of content for change detection

**Relationships**:
- Input to SessionStateAnalyzer
- Compared with PersistedSessionState.screen_hash

**Validation Rules**:
- `line_count` <= 200 (may be less for new sessions)
- `content` decoded as UTF-8
- Capture timeout 5 seconds (prevents hang)

**Processing**:
```python
# tmux command
tmux capture-pane -t {session_name} -p -S -200

# Flags:
# -p: output to stdout
# -S -200: start 200 lines back in scrollback
```

---

## Entity Relationships Diagram

```
ClaudeCodeSession (existing)
    ├─ 1:1 → PersistedSessionState (filesystem)
    ├─ 1:1 → SessionReconnectionState (in-memory, transient)
    └─ 1:N → ScreenHistory (captured per poll cycle)

MonitoringThread (existing)
    ├─ manages → SessionReconnectionState
    └─ reads → PersistedSessionState (on startup)

TelegramBot (existing)
    ├─ sends → MessageQueueEntry
    ├─ creates → PendingConfirmation
    └─ processes → InlineKeyboard callbacks

ExponentialBackoffQueue (new)
    └─ manages → MessageQueueEntry
```

---

## Data Flow

### 1. Session Disconnection Flow
```
1. MultiMonitor.monitor_session() → tmux has-session fails
2. Create SessionReconnectionState(retry_count=0)
3. Loop: wait backoff, retry tmux has-session
4. If success → delete SessionReconnectionState, resume monitoring
5. If timeout → send notification, mark FAILED
```

### 2. Restart State Skip Flow
```
1. MultiMonitor.start() → discover sessions
2. For each session → load PersistedSessionState from /tmp/claude-ctb/state/
3. Capture current ScreenHistory (200 lines)
4. Compare screen_hash with persisted hash
5. If identical → skip notification
6. If different → run state detection, send notification if WAITING_INPUT
```

### 3. Rate Limit Queue Flow
```
1. Notifier.send_message() → telegram.error.RetryAfter raised
2. Create MessageQueueEntry with backoff
3. ExponentialBackoffQueue.enqueue()
4. Background task: poll queue, retry when next_retry_time reached
5. On success → remove from queue
6. On failure → increment retry_count, reschedule with longer backoff
```

### 4. Dangerous Command Confirmation Flow
```
1. Bot.handle_message() → validate_input() detects pattern
2. Create PendingConfirmation with 60s TTL
3. Send InlineKeyboardMarkup with Confirm/Cancel buttons
4. User clicks button → callback_query_handler
5. Lookup PendingConfirmation by confirmation_id
6. If CONFIRMED → send command to tmux session
7. If CANCELLED/EXPIRED → discard, notify user
```

---

## Configuration Schema

New environment variables (`.env`):

```bash
# Session Reconnection
SESSION_RECONNECT_MAX_DURATION=300      # Max reconnection window (seconds)
SESSION_RECONNECT_INITIAL_BACKOFF=1     # Initial retry delay (seconds)
SESSION_RECONNECT_MAX_BACKOFF=30        # Maximum backoff delay (seconds)

# Rate Limiting
TELEGRAM_RATE_LIMIT_ENABLED=true        # Enable custom queue
TELEGRAM_BACKOFF_INITIAL=1              # Initial backoff (seconds)
TELEGRAM_BACKOFF_MAX=60                 # Max backoff (seconds)

# Dangerous Command Confirmation
COMMAND_CONFIRMATION_TIMEOUT=60         # Confirmation TTL (seconds)
DANGEROUS_PATTERNS_FILE=                # Optional: custom patterns file

# Screen History
SESSION_SCREEN_HISTORY_LINES=200        # Lines to capture (default 200)
```

---

## Summary

5 new/enhanced entities supporting the reliability improvements:
1. **SessionReconnectionState**: Exponential backoff retry logic
2. **PersistedSessionState**: Restart state skip behavior
3. **MessageQueueEntry**: Rate limit queue with backoff
4. **PendingConfirmation**: Dangerous command confirmation flow
5. **ScreenHistory**: Enhanced 200-line capture

All entities integrate with existing architecture (ClaudeCodeSession, MonitoringThread, TelegramBot) without breaking changes.
