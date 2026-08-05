"""A completion notification must arrive even when its Markdown is broken.

Field incident (2026-08-05): 11 of 11 completion notifications in 24h were
rejected by Telegram with

    Bad Request: can't parse entities: Can't find end of the entity
    starting at byte offset 1091

Nothing was delivered. Notification bodies embed text scraped from the session
screen -- prompts, replies, tool output -- so a lone `*`, `_` or backtick is
routine, and `parse_mode: Markdown` makes Telegram refuse the whole message.
The 400 handler treated that as permanent ("bad requests won't succeed"), but
this particular 400 succeeds immediately without parse_mode: worse formatting
beats a notification that never arrives.
"""

from unittest.mock import MagicMock, patch

import pytest

from claude_ctb.config import ClaudeOpsConfig
from claude_ctb.telegram.notifier import SmartNotifier

PARSE_ERROR = (
    '{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse '
    'entities: Can\'t find end of the entity starting at byte offset 1091"}'
)


@pytest.fixture
def notifier():
    cfg = MagicMock(spec=ClaudeOpsConfig)
    cfg.telegram_bot_token = "test_token"
    cfg.telegram_chat_id = "test_chat"
    cfg.session_name = "claude_demo"
    cfg.telegram_rate_limit_enabled = False
    return SmartNotifier(cfg)


def _resp(status, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.json.return_value = {}
    return r


def test_parse_error_is_retried_as_plain_text(notifier):
    """The message must still be delivered, unformatted."""
    body = "✅ *claude_demo* done\n\nan unbalanced *asterisk"
    with patch("requests.post", side_effect=[_resp(400, PARSE_ERROR), _resp(200)]) as post:
        assert notifier._send_telegram_notification(body) is True

    assert post.call_count == 2, "a parse failure must be retried without Markdown"
    retry = post.call_args_list[1].kwargs["data"]
    assert "parse_mode" not in retry, "the retry must not ask Telegram to parse again"
    assert retry["text"] == body, "the text itself must survive the retry"


def test_the_first_attempt_still_asks_for_markdown(notifier):
    """Formatting is the default; plain text is only the fallback."""
    with patch("requests.post", return_value=_resp(200)) as post:
        notifier._send_telegram_notification("✅ *claude_demo* done")
    assert post.call_args_list[0].kwargs["data"]["parse_mode"] == "Markdown"


def test_a_plain_text_retry_that_also_fails_reports_failure(notifier):
    with patch("requests.post", side_effect=[_resp(400, PARSE_ERROR), _resp(400, "nope")]):
        assert notifier._send_telegram_notification("boom") is False


def test_unrelated_400s_are_not_retried(notifier):
    """Only the parse failure is recoverable this way — do not hammer the API."""
    bad_chat = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'
    with patch("requests.post", return_value=_resp(400, bad_chat)) as post:
        assert notifier._send_telegram_notification("hi") is False
    assert post.call_count == 1


def test_success_is_not_retried(notifier):
    with patch("requests.post", return_value=_resp(200)) as post:
        assert notifier._send_telegram_notification("hi") is True
    assert post.call_count == 1
