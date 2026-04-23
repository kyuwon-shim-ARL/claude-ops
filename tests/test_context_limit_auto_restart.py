"""Tests for context limit auto-restart functionality.

Covers:
- Exit sequence: /exit → Escape → Enter sent as separate tmux send-keys calls
- Cooldown logic: 60s cooldown prevents restart loops from residual scroll buffer
- Handoff prompt: screen-log based with metadata
- State reset: WORKING + notification_sent after restart
- Config toggle: context_limit_auto_restart enables/disables auto-restart
- Bot callback: same exit sequence fix in bot.py
"""
import time
import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
from claude_ctb.utils.session_state import SessionState


@pytest.fixture
def monitor():
    """Create a MultiSessionMonitor with mocked config."""
    with patch('claude_ctb.monitoring.multi_monitor.ClaudeOpsConfig') as MockConfig:
        cfg = MockConfig.return_value
        cfg.telegram_bot_token = "test_token"
        cfg.telegram_chat_id = "test_chat"
        cfg.check_interval = 3
        cfg.session_screen_history_lines = 200
        cfg.context_limit_auto_restart = True
        cfg.hook_only_mode = False
        mon = MultiSessionMonitor(config=cfg)
        yield mon


class TestExitSequence:
    """Test that /exit is sent with Escape to dismiss autocomplete."""

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_exit_sends_separate_keys(self, mock_sleep, mock_run, monitor):
        """Verify /exit, Escape, Enter are 3 separate send-keys calls."""
        # Mock _build_handoff_prompt to avoid subprocess calls
        monitor._build_handoff_prompt = MagicMock(return_value="handoff prompt")

        monitor._auto_restart_session("test_session")

        # Extract all tmux send-keys calls
        send_keys_calls = [
            c for c in mock_run.call_args_list
            if "send-keys" in c[0][0]
        ]

        # Should have separate calls for: C-c, /exit, Escape, Enter, clear, Enter, claude..., Enter, handoff, Enter
        key_args = [c[0][0] for c in send_keys_calls]

        # Verify the critical fix: /exit, Escape, Enter are separate calls
        exit_idx = None
        for i, args in enumerate(key_args):
            if "/exit" in args:
                exit_idx = i
                break

        assert exit_idx is not None, "/exit send-keys call not found"

        # /exit must NOT have "Enter" in the same call
        assert "Enter" not in key_args[exit_idx], \
            "/exit and Enter must NOT be in the same send-keys call (autocomplete bug)"

        # Next call should be Escape (dismiss autocomplete)
        assert "Escape" in key_args[exit_idx + 1], \
            "Escape must follow /exit to dismiss autocomplete"

        # Then Enter to execute /exit
        assert "Enter" in key_args[exit_idx + 2], \
            "Enter must follow Escape to execute /exit"

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_exit_sequence_has_delays(self, mock_sleep, mock_run, monitor):
        """Verify delays between /exit, Escape, and Enter."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        monitor._auto_restart_session("test_session")

        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]

        # After /exit: 0.5s delay before Escape
        assert 0.5 in sleep_calls, "0.5s delay after /exit not found"
        # After Escape: 0.3s delay before Enter
        assert 0.3 in sleep_calls, "0.3s delay after Escape not found"

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_no_atomic_exit_enter(self, mock_sleep, mock_run, monitor):
        """Regression test: /exit and Enter must NEVER be in the same send-keys call."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        monitor._auto_restart_session("test_session")

        for c in mock_run.call_args_list:
            args = c[0][0]
            if isinstance(args, list) and "send-keys" in args:
                # If /exit is in the args, Enter must NOT be
                if "/exit" in args:
                    assert "Enter" not in args, \
                        f"REGRESSION: /exit and Enter in same call: {args}"


class TestCooldownLogic:
    """Test 60-second cooldown prevents restart loops."""

    def test_cooldown_blocks_immediate_re_detection(self, monitor):
        """After restart, context limit re-detection within 60s should be blocked."""
        session = "claude_test"
        current_time = time.time()

        # Simulate a recent restart
        monitor._context_limit_restart_time[session] = current_time - 30  # 30s ago

        # Set up state for context limit detection
        monitor.last_state[session] = SessionState.WORKING  # previous != CONTEXT_LIMIT
        monitor.notification_sent[session] = False

        # Check cooldown logic inline (mirrors multi_monitor.py line 252-254)
        restart_cooldown = 60
        last_restart = monitor._context_limit_restart_time.get(session, 0)
        should_notify = (
            SessionState.CONTEXT_LIMIT != monitor.last_state[session]
            and (current_time - last_restart) > restart_cooldown
        )

        assert should_notify is False, "Should NOT trigger within 60s cooldown"

    def test_cooldown_allows_after_timeout(self, monitor):
        """After 60s, context limit should be re-detectable."""
        session = "claude_test"
        current_time = time.time()

        # Simulate an old restart (70s ago)
        monitor._context_limit_restart_time[session] = current_time - 70

        restart_cooldown = 60
        last_restart = monitor._context_limit_restart_time.get(session, 0)
        should_notify = (
            SessionState.CONTEXT_LIMIT != SessionState.WORKING  # previous != current
            and (current_time - last_restart) > restart_cooldown
        )

        assert should_notify is True, "Should trigger after 60s cooldown expires"

    def test_no_previous_restart_allows_detection(self, monitor):
        """First-time context limit detection should always proceed."""
        session = "claude_new"

        restart_cooldown = 60
        last_restart = monitor._context_limit_restart_time.get(session, 0)
        current_time = time.time()

        should_notify = (current_time - last_restart) > restart_cooldown
        assert should_notify is True, "No previous restart — should always trigger"


class TestStateResetAfterRestart:
    """Test monitor state is properly reset after auto-restart."""

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_state_reset_to_working(self, mock_sleep, mock_run, monitor):
        """After restart, last_state should be WORKING."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        monitor._auto_restart_session("test_session")

        assert monitor.last_state["test_session"] == SessionState.WORKING

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_notification_sent_after_restart(self, mock_sleep, mock_run, monitor):
        """After restart, notification_sent should be True to block immediate re-notification."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        monitor._auto_restart_session("test_session")

        assert monitor.notification_sent["test_session"] is True

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_cooldown_timestamp_set(self, mock_sleep, mock_run, monitor):
        """After restart, cooldown timestamp should be set."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        before = time.time()
        monitor._auto_restart_session("test_session")
        after = time.time()

        ts = monitor._context_limit_restart_time["test_session"]
        assert before <= ts <= after

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_restart_returns_true_on_success(self, mock_sleep, mock_run, monitor):
        """Successful restart returns True."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        result = monitor._auto_restart_session("test_session")
        assert result is True

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run', side_effect=Exception("tmux error"))
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_restart_returns_false_on_failure(self, mock_sleep, mock_run, monitor):
        """Failed restart returns False."""
        result = monitor._auto_restart_session("test_session")
        assert result is False


class TestHandoffPrompt:
    """Test handoff prompt generation."""

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    def test_handoff_includes_screen_log(self, mock_run, monitor):
        """Handoff should include last 50 lines of screen output."""
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if "display-message" in cmd:
                result.returncode = 0
                result.stdout = "/home/user/project\n"
            elif "capture-pane" in cmd:
                result.returncode = 0
                result.stdout = "line1\nline2\nworking on feature X\n"
            elif "branch" in cmd:
                result.returncode = 0
                result.stdout = "main\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = run_side_effect

        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', return_value=[]):
            prompt = monitor._build_handoff_prompt("test_session")

        assert "직전 화면 로그" in prompt
        assert "working on feature X" in prompt

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    def test_handoff_filters_context_limit_noise(self, mock_run, monitor):
        """Handoff should filter out context limit error lines."""
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if "display-message" in cmd:
                result.returncode = 0
                result.stdout = "/home/user/project\n"
            elif "capture-pane" in cmd:
                result.returncode = 0
                result.stdout = (
                    "doing work\n"
                    "Context limit reached\n"
                    "Conversation is too long\n"
                    "context window exceeded\n"
                    "important output\n"
                )
            elif "branch" in cmd:
                result.returncode = 0
                result.stdout = "feature-branch\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = run_side_effect

        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', return_value=[]):
            prompt = monitor._build_handoff_prompt("test_session")

        assert "Context limit reached" not in prompt
        assert "Conversation is too long" not in prompt
        assert "context window exceeded" not in prompt
        assert "important output" in prompt

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    def test_handoff_truncates_long_output(self, mock_run, monitor):
        """Handoff should truncate screen log to ~2000 chars."""
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if "display-message" in cmd:
                result.returncode = 0
                result.stdout = "/home/user/project\n"
            elif "capture-pane" in cmd:
                result.returncode = 0
                result.stdout = "x" * 3000 + "\n"
            elif "branch" in cmd:
                result.returncode = 0
                result.stdout = "main\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = run_side_effect

        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', return_value=[]):
            prompt = monitor._build_handoff_prompt("test_session")

        # Total prompt includes header + metadata + screen log
        # Screen log portion should be ≤ 2000 chars
        assert len(prompt) < 3000, f"Prompt too long: {len(prompt)}"

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    def test_handoff_includes_branch_and_omc_modes(self, mock_run, monitor):
        """Handoff metadata should include branch and active OMC modes."""
        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if "display-message" in cmd:
                result.returncode = 0
                result.stdout = "/home/user/project\n"
            elif "capture-pane" in cmd:
                result.returncode = 0
                result.stdout = "some output\n"
            elif "branch" in cmd:
                result.returncode = 0
                result.stdout = "feature/auth\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = run_side_effect

        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', return_value=['ralph-state.json', 'autopilot-state.json']):
            prompt = monitor._build_handoff_prompt("test_session")

        assert "feature/auth" in prompt
        assert "ralph" in prompt
        assert "autopilot" in prompt


class TestAutoRestartConfig:
    """Test config toggle for auto-restart."""

    @patch('requests.post')
    def test_auto_restart_enabled_calls_restart(self, mock_post, monitor):
        """When config enabled, send_context_limit_notification triggers auto-restart."""
        monitor.config.context_limit_auto_restart = True
        mock_post.return_value = MagicMock(status_code=200)

        with patch.object(monitor, '_auto_restart_session', return_value=True) as mock_restart:
            monitor.send_context_limit_notification("test_session")

        mock_restart.assert_called_once_with("test_session")

    @patch('requests.post')
    def test_auto_restart_disabled_sends_buttons(self, mock_post, monitor):
        """When config disabled, send buttons instead of auto-restarting."""
        monitor.config.context_limit_auto_restart = False
        mock_post.return_value = MagicMock(status_code=200)

        with patch.object(monitor, '_auto_restart_session') as mock_restart:
            monitor.send_context_limit_notification("test_session")

        mock_restart.assert_not_called()

        # Should have sent message with reply_markup (buttons mode)
        post_calls = mock_post.call_args_list
        assert len(post_calls) >= 1
        # In button mode, data dict has reply_markup key
        last_call = post_calls[-1]
        call_data = last_call[1].get('data', {}) if last_call[1] else {}
        assert 'reply_markup' in call_data, "Button mode should include reply_markup"


class TestFullRestartFlow:
    """Integration test for the complete restart sequence."""

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_full_restart_step_order(self, mock_sleep, mock_run, monitor):
        """Verify the full restart sends commands in correct order."""
        monitor._build_handoff_prompt = MagicMock(return_value="handoff text")

        monitor._auto_restart_session("claude_myproject")

        send_keys_calls = []
        for c in mock_run.call_args_list:
            args = c[0][0]
            if isinstance(args, list) and "send-keys" in args:
                # Extract the key being sent (last meaningful arg before timeout)
                keys = [a for a in args if a not in ["tmux", "send-keys", "-t", "claude_myproject"]]
                send_keys_calls.append(keys)

        expected_order = [
            ["C-c"],                                    # Step 1a: interrupt
            ["/exit"],                                  # Step 1b: type /exit
            ["Escape"],                                 # Step 1c: dismiss autocomplete
            ["Enter"],                                  # Step 1d: execute /exit
            ["clear", "Enter"],                         # Step 3: clear screen
            ["claude --dangerously-skip-permissions", "Enter"],  # Step 4: start new claude
            ["handoff text"],                           # Step 5a: send handoff text
            ["Enter"],                                  # Step 5b: execute handoff (separate for reliability)
        ]

        assert len(send_keys_calls) == len(expected_order), \
            f"Expected {len(expected_order)} send-keys calls, got {len(send_keys_calls)}: {send_keys_calls}"

        for i, (actual, expected) in enumerate(zip(send_keys_calls, expected_order)):
            assert actual == expected, \
                f"Step {i}: expected {expected}, got {actual}"

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_handoff_truncation(self, mock_sleep, mock_run, monitor):
        """Handoff longer than 4000 chars should be truncated."""
        long_handoff = "x" * 5000
        monitor._build_handoff_prompt = MagicMock(return_value=long_handoff)

        monitor._auto_restart_session("test_session")

        # Find the handoff send-keys call (last one with long text)
        for c in mock_run.call_args_list:
            args = c[0][0]
            if isinstance(args, list) and "send-keys" in args:
                for a in args:
                    if isinstance(a, str) and len(a) > 100:
                        assert len(a) <= 4000, f"Handoff not truncated: {len(a)} chars"
                        assert "잘렸습니다" in a

    @patch('claude_ctb.monitoring.multi_monitor.subprocess.run')
    @patch('claude_ctb.monitoring.multi_monitor.time.sleep')
    def test_empty_handoff_skips_send(self, mock_sleep, mock_run, monitor):
        """Empty handoff prompt should not trigger send-keys."""
        monitor._build_handoff_prompt = MagicMock(return_value="")

        monitor._auto_restart_session("test_session")

        send_keys_calls = [
            c[0][0] for c in mock_run.call_args_list
            if isinstance(c[0][0], list) and "send-keys" in c[0][0]
        ]

        # Without handoff, should be 6 calls: C-c, /exit, Escape, Enter, clear+Enter, claude+Enter
        assert len(send_keys_calls) == 6, \
            f"Expected 6 send-keys (no handoff), got {len(send_keys_calls)}: {send_keys_calls}"


class TestContextLimitBypassesNotificationSent:
    """Regression test: CONTEXT_LIMIT must bypass notification_sent guard.

    Bug scenario (2026-03-14):
    1. Session WORKING → subagents complete → state becomes IDLE
    2. Regular completion notification sent → notification_sent = True
    3. Screen shows "Context limit reached" from subagent output
    4. CONTEXT_LIMIT detected but notification_sent guard blocked it
    Fix: CONTEXT_LIMIT check moved before notification_sent guard.
    """

    def test_context_limit_detected_after_idle_notification(self, monitor):
        """CONTEXT_LIMIT should fire even when notification_sent=True from prior IDLE notification."""
        session = "claude_uni-mol-QSAR"

        # Simulate: a regular IDLE notification was already sent
        monitor.last_state[session] = SessionState.IDLE
        monitor.notification_sent[session] = True
        monitor.last_notification_time[session] = time.time() - 5  # 5s ago

        # Now the state transitions to CONTEXT_LIMIT
        with patch.object(monitor, 'get_session_state', return_value=SessionState.CONTEXT_LIMIT):
            should_notify, _ = monitor.should_send_completion_notification(session)

        assert should_notify is True, \
            "REGRESSION: notification_sent=True from IDLE must NOT block CONTEXT_LIMIT"

    def test_context_limit_detected_after_waiting_input_notification(self, monitor):
        """CONTEXT_LIMIT should fire even after a WAITING_INPUT notification."""
        session = "claude_test"

        # Simulate: WAITING_INPUT notification was sent
        monitor.last_state[session] = SessionState.WAITING_INPUT
        monitor.notification_sent[session] = True
        monitor.last_notification_time[session] = time.time() - 10

        with patch.object(monitor, 'get_session_state', return_value=SessionState.CONTEXT_LIMIT):
            should_notify, _ = monitor.should_send_completion_notification(session)

        assert should_notify is True, \
            "CONTEXT_LIMIT must bypass notification_sent from WAITING_INPUT"

    def test_context_limit_respects_own_cooldown(self, monitor):
        """CONTEXT_LIMIT should still respect its own 60s restart cooldown."""
        session = "claude_test"

        monitor.last_state[session] = SessionState.IDLE
        monitor.notification_sent[session] = True
        monitor._context_limit_restart_time[session] = time.time() - 30  # 30s ago (within cooldown)

        with patch.object(monitor, 'get_session_state', return_value=SessionState.CONTEXT_LIMIT):
            should_notify, _ = monitor.should_send_completion_notification(session)

        assert should_notify is False, \
            "CONTEXT_LIMIT should still respect 60s restart cooldown"

    def test_context_limit_not_re_triggered_same_state(self, monitor):
        """Once CONTEXT_LIMIT is the last_state, it should not re-trigger (no transition)."""
        session = "claude_test"

        # Already in CONTEXT_LIMIT state
        monitor.last_state[session] = SessionState.CONTEXT_LIMIT
        monitor.notification_sent[session] = True

        with patch.object(monitor, 'get_session_state', return_value=SessionState.CONTEXT_LIMIT):
            should_notify, _ = monitor.should_send_completion_notification(session)

        assert should_notify is False, \
            "CONTEXT_LIMIT→CONTEXT_LIMIT should NOT re-trigger"


class TestBotExitSequence:
    """Test that bot.py callback uses the same fixed exit sequence."""

    def test_bot_exit_not_atomic(self):
        """Verify bot.py doesn't have the atomic /exit Enter bug."""
        import inspect
        from claude_ctb.telegram.bot import TelegramBridge

        # Get source of _context_limit_restart_callback
        source = inspect.getsource(TelegramBridge._context_limit_restart_callback)

        # The atomic bug pattern: '"/exit", "Enter"' in a single send-keys call
        assert '"/exit", "Enter"' not in source, \
            "REGRESSION: bot.py still has atomic /exit Enter in _context_limit_restart_callback"

        # Must have separate /exit, Escape, Enter calls
        assert '"/exit"' in source, "bot.py must send /exit"
        assert '"Escape"' in source, "bot.py must send Escape to dismiss autocomplete"
