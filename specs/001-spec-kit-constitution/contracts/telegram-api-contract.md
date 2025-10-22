# Contract: Telegram Bot API

**Feature**: 001-spec-kit-constitution
**Date**: 2025-10-01
**External Service**: Telegram Bot API (python-telegram-bot>=20.0 wrapper)

## Purpose

Define expected behavior of Telegram Bot API interactions for dangerous command confirmation and rate limit handling.

## Contract Endpoints

### 1. Send Message with InlineKeyboard

**Method**: `Bot.send_message()`

**Request**:
```python
await bot.send_message(
    chat_id=12345678,
    text="⚠️ Dangerous command detected:\n`sudo rm -rf /tmp`\n\nConfirm execution?",
    reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data="confirm:claude_test:abc123"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel:claude_test:abc123")
    ]]),
    parse_mode="Markdown"
)
```

**Expected Response**:
- Success: `Message` object with `message_id` field
- Rate limit error: `telegram.error.RetryAfter(retry_after=30)`
- Invalid chat: `telegram.error.BadRequest`

**Contract Assertions**:
- Message delivered within 5 seconds (network timeout)
- Inline keyboard buttons functional for 60 seconds
- Callback data preserved exactly (no truncation)

---

### 2. Handle Callback Query (Button Click)

**Method**: `CallbackQueryHandler`

**Event**:
```python
# User clicks button
callback_query = {
    "id": "callback_id_12345",
    "from": {"id": 12345678},
    "message": {"message_id": 98765},
    "data": "confirm:claude_test:abc123"  # Matches callback_data from send_message
}
```

**Expected Behavior**:
- `callback_query.data` matches original `callback_data` string
- `callback_query.answer()` acknowledges button click (removes loading spinner)
- Multiple clicks deliver same `callback_query.data` (idempotent)

**Contract Assertions**:
- Callback received within 1 second of button click
- `callback_query.data` string length ≤ 64 bytes
- Button disabled after first click (Telegram UI behavior)

---

### 3. Rate Limit Handling

**Method**: `Bot.send_message()` (any message)

**Rate Limit Response**:
```python
# Telegram raises RetryAfter exception
raise telegram.error.RetryAfter(retry_after=30)
```

**Expected Behavior**:
- Exception includes `retry_after` field (seconds to wait)
- Retry after specified duration succeeds (if rate compliant)
- python-telegram-bot v20.0 built-in rate limiter handles automatically

**Contract Assertions**:
- `retry_after` value is 1-120 seconds
- Retry after waiting succeeds (no further rate limit)
- Rate limits: 30 msg/sec burst, 20 msg/min sustained

---

### 4. Message Splitting (existing, verified)

**Method**: `message_utils.split_message()`

**Input**:
```python
long_text = "..." * 5000  # 5000+ chars
chunks = split_message(long_text, max_length=4000)
```

**Expected Output**:
- List of strings, each ≤ 4000 characters
- Splits preserve line boundaries (no mid-line breaks)
- Markdown formatting preserved (no broken code blocks)

**Contract Assertions**:
- All chunks < Telegram 4096 char limit (4000 buffer)
- Concatenating chunks reproduces original (minus whitespace)
- No chunk ends with incomplete markdown tag

---

## Error Handling

| Error Type | Cause | Expected Handling |
|------------|-------|-------------------|
| `RetryAfter` | Rate limit hit | Queue message, retry with exponential backoff |
| `BadRequest` | Invalid chat ID | Log error, skip notification |
| `NetworkError` | Connection failure | Retry with backoff (max 3 attempts) |
| `TimedOut` | API timeout | Retry with backoff (max 3 attempts) |
| `InvalidToken` | Bot token invalid | Fatal error, exit process |

---

## Contract Test Requirements

Contract tests MUST verify:

1. **Inline keyboard creation and callback handling**
   - Test: Send message with inline keyboard, simulate button click
   - Assert: Callback received with correct `callback_data`

2. **Rate limit exception handling**
   - Test: Mock `RetryAfter` exception
   - Assert: Message queued, retry scheduled with backoff

3. **Message splitting with markdown**
   - Test: Split 8000-char message with code blocks
   - Assert: All chunks valid markdown, no broken tags

4. **Callback timeout behavior**
   - Test: Send inline keyboard, wait >60 seconds
   - Assert: Stale callback rejected (expired confirmation)

---

## Dependencies

- `python-telegram-bot>=20.0`
- `telegram.ext.RateLimiter` (built-in rate limiting)
- Telegram Bot API v6.0+ (inline keyboard support)

---

## Notes

- Telegram Bot API docs: https://core.telegram.org/bots/api
- python-telegram-bot docs: https://docs.python-telegram-bot.org/en/stable/
- Rate limiting reference: https://core.telegram.org/bots/faq#my-bot-is-hitting-limits
