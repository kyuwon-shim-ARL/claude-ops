"""/log (and its line-count siblings, and the inline-keyboard log callbacks)
must refuse a bash-only (@ctb_shell-marked) session rather than capture its
pane -- that pane can hold a password or an API key mid-typing, and these
are exactly the paths that would otherwise put it in a Telegram message.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from claude_ctb.telegram.bot import TelegramBridge
from claude_ctb.config import ClaudeOpsConfig
from telegram import Update, Message, User, Chat


class _Base(unittest.TestCase):
    def setUp(self):
        mock_config = MagicMock(spec=ClaudeOpsConfig)
        mock_config.telegram_bot_token = "t"
        mock_config.telegram_chat_id = "c"
        mock_config.session_name = "claude_demo_sh"
        self.bot = TelegramBridge(mock_config)

        user = MagicMock(spec=User)
        user.id = 1
        user.is_bot = False

        message = MagicMock(spec=Message)
        message.from_user = user
        message.reply_to_message = None
        message.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = user
        update.message = message
        self.update = update
        self.message = message
        self.context = MagicMock()
        self.context.args = []

        self.bot.check_user_authorization = MagicMock(return_value=True)


class TestLogCommandRefusesShell(_Base):
    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=True)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_log_command_refuses_a_shell_session_without_capturing(self, mock_run, _is_shell):
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.bot.log_command(self.update, self.context))
        mock_run.assert_not_called()
        self.message.reply_text.assert_awaited()
        (text,), _ = self.message.reply_text.call_args
        assert "bash" in text or "셸" in text or "허용" in text

    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=False)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_log_command_still_works_for_an_ordinary_session(self, mock_run, _is_shell):
        import asyncio
        import subprocess as sp
        mock_run.return_value = sp.CompletedProcess(args=[], returncode=0, stdout="hello\n", stderr="")
        asyncio.get_event_loop().run_until_complete(self.bot.log_command(self.update, self.context))
        mock_run.assert_called()


class TestLogWithLinesRefusesShell(_Base):
    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=True)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_log50_refuses_a_shell_session(self, mock_run, _is_shell):
        import asyncio
        asyncio.get_event_loop().run_until_complete(self.bot.log50_command(self.update, self.context))
        mock_run.assert_not_called()
        self.message.reply_text.assert_awaited()


class TestCallbackLogPathsRefuseShell(_Base):
    @patch("claude_ctb.telegram.bot._tmux", return_value=0)
    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=True)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_session_log_callback_refuses_a_shell_session(self, mock_run, _is_shell, _tmux):
        import asyncio
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        asyncio.get_event_loop().run_until_complete(
            self.bot._session_log_callback(query, self.context, "claude_demo_sh"))
        mock_run.assert_not_called()
        query.edit_message_text.assert_awaited()

    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=True)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_quick_log_callback_refuses_a_shell_session(self, mock_run, _is_shell):
        import asyncio
        query = MagicMock()
        query.edit_message_text = AsyncMock()
        asyncio.get_event_loop().run_until_complete(
            self.bot._quick_log_callback(query, self.context, 50, "claude_demo_sh"))
        mock_run.assert_not_called()
        query.edit_message_text.assert_awaited()

    @patch("claude_ctb.telegram.bot._tmux", return_value=0)
    @patch("claude_ctb.session_manager.session_manager.is_shell_session", return_value=True)
    @patch("claude_ctb.telegram.bot.subprocess.run")
    def test_get_session_log_content_refuses_a_shell_session(self, mock_run, _is_shell, _tmux):
        import asyncio
        text = asyncio.get_event_loop().run_until_complete(
            self.bot._get_session_log_content("claude_demo_sh"))
        mock_run.assert_not_called()
        assert "bash" in text or "셸" in text


if __name__ == "__main__":
    unittest.main()
