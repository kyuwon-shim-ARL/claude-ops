"""
Test specifications for notification system fixes
These tests are designed to FAIL until implementation is complete
"""

import pytest
from unittest.mock import Mock, patch
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState
from claude_ops.utils.session_summary import SessionSummaryHelper
from claude_ops.telegram.notifier import SmartNotifier


class TestEscInterruptPriority:
    """Test that 'esc to interrupt' has absolute priority over prompts"""

    def test_esc_interrupt_overrides_prompt(self):
        """
        User Story: When Claude is working on a task with todos,
        the system should recognize it's still working even if a prompt appears
        """
        # Given: Screen content with both "esc to interrupt" and prompt
        screen_content = """
● 완벽한 통찰입니다! 워크스페이스에서 시작하고 참조를 확장하는 방식이 훨씬 안전하고 체계적이네요!
✻ Designing workspace-first strategy… (esc to interrupt · ctrl+t to hide todos)

⎿  ☐ Design workspace-first Claude Code strategy
☐ Create workspace Git initialization
☐ Setup reference folder structure
☐ Document best practices

>
"""

        # When: State detection runs
        analyzer = SessionStateAnalyzer()
        # Mock the screen content retrieval
        from unittest.mock import patch
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            state = analyzer.get_state_for_notification("test_session")

        # Then: Should return WORKING, not IDLE
        assert state == SessionState.WORKING, f"Expected WORKING but got {state}"
        assert state != SessionState.IDLE, "Should NOT be IDLE when 'esc to interrupt' is present"

        # And: Verify the specific detection logic
        is_working = analyzer._detect_working_state(screen_content)
        assert is_working is True, "Should detect as working when 'esc to interrupt' is present"

    def test_todo_with_esc_interrupt_is_working(self):
        """
        User Story: When Claude shows TODO list with "esc to interrupt",
        it's actively working, not waiting for input
        """
        # Given: TODO list in progress with esc to interrupt
        screen_content = """
✻ Building feature… (esc to interrupt · ctrl+t to hide todos)

Todos:
☒ Analyze requirements
☐ Create implementation plan
☐ Write tests
☐ Implement feature

>
"""

        # When: Checking work state
        analyzer = SessionStateAnalyzer()
        # Mock the screen content retrieval
        from unittest.mock import patch
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            state = analyzer.get_state_for_notification("test_session")

        # Then: Must be WORKING state
        assert state == SessionState.WORKING, "TODO with 'esc to interrupt' means work in progress"
        assert state != SessionState.WAITING_INPUT, "Not waiting for input during TODO execution"

        # And: Should not trigger completion notification
        should_notify = (state != SessionState.WORKING)
        assert should_notify is False, "Should NOT send completion notification"


class TestSessionSummaryAccuracy:
    """Test that session summary shows accurate information"""

    def test_actual_notification_time_no_estimation_marker(self):
        """
        User Story: When a session has actually sent notifications,
        the summary should show the actual time without "추정" marker
        """
        # Given: Session with actual notification history
        summary_helper = SessionSummaryHelper()
        session_name = "claude_test_session"

        # Simulate actual notification was sent
        with patch.object(summary_helper.tracker, 'get_session_info') as mock_info:
            mock_info.return_value = {
                'wait_time': 300,  # 5 minutes
                'last_prompt': "Test prompt",
                'has_notification_record': True,  # Actual notification exists
                'last_notification_time': 1234567890
            }

            # When: Generating summary for this session
            summary = summary_helper._generate_single_session_summary(session_name)

            # Then: Should NOT contain "추정" marker
            assert "추정" not in summary, "Should not show '추정' when actual notification exists"
            assert "5분 대기)" in summary, "Should show actual wait time"
            assert "5분 대기 ~추정~)" not in summary, "Should NOT have estimation marker"

    def test_no_notification_shows_estimation_marker(self):
        """
        User Story: Only when no actual notifications exist
        should the summary show "추정" to indicate estimation
        """
        # Given: Session without notification history
        summary_helper = SessionSummaryHelper()
        session_name = "claude_new_session"

        with patch.object(summary_helper.tracker, 'get_session_info') as mock_info:
            mock_info.return_value = {
                'wait_time': 600,  # 10 minutes
                'last_prompt': "New task",
                'has_notification_record': False,  # No actual notification
                'last_notification_time': None
            }

            # When: Generating summary
            summary = summary_helper._generate_single_session_summary(session_name)

            # Then: Should contain "추정" marker
            assert "추정" in summary, "Should show '추정' when no actual notification exists"
            assert "10분 대기 ~추정~)" in summary, "Should have estimation marker"


class TestSimplifiedNotifications:
    """Test that notification system is simplified correctly"""

    def test_only_two_notification_types_exist(self):
        """
        User Story: System should only have work_complete and waiting_input notifications,
        no priority levels or other types
        """
        # Given: Notification manager
        from claude_ops.config import Config
        config = Config()
        notifier = SmartNotifier(config)

        # When: Checking available notification methods
        notification_methods = [
            method for method in dir(notifier)
            if method.startswith('send_') and 'notification' in method
        ]

        # Then: Only specific notification methods should exist
        expected_methods = [
            'send_work_completion_notification',
            'send_waiting_input_notification',
            'send_notification_sync'  # Base method
        ]

        for method in notification_methods:
            assert method in expected_methods, f"Unexpected notification method: {method}"

        # And: Priority-related methods should NOT exist
        assert not hasattr(notifier, 'send_critical_alert'), "Critical alerts should be removed"
        assert not hasattr(notifier, 'send_info_notification'), "Info notifications should be removed"
        assert not hasattr(notifier, 'send_task_completion_notification'), "Task completion with priorities should be removed"

    def test_no_priority_in_notification_messages(self):
        """
        User Story: Notification messages should be simple and clear,
        without priority indicators or levels
        """
        # Given: A work completion scenario
        from claude_ops.config import Config
        config = Config()
        notifier = SmartNotifier(config)

        with patch.object(notifier, '_send_telegram_notification') as mock_send:
            # When: Sending work completion notification
            notifier.send_work_completion_notification()

            # Then: Message should not contain priority indicators
            sent_message = mock_send.call_args[0][0] if mock_send.called else ""

            assert "CRITICAL" not in sent_message, "Should not contain CRITICAL"
            assert "HIGH" not in sent_message, "Should not contain HIGH priority"
            assert "INFO" not in sent_message, "Should not contain INFO level"
            assert "Priority:" not in sent_message, "Should not mention priority"


class TestBotCommandCleanup:
    """Test that unused bot commands are properly removed"""

    @pytest.mark.parametrize("removed_command", [
        "/detect_status",
        "/detect_trend",
        "/fix_terminal"
    ])
    def test_removed_commands_not_registered(self, removed_command):
        """
        User Story: When user tries to use removed commands,
        they should get an error message, not silent failure
        """
        from claude_ops.telegram.bot import TelegramBot

        # Given: Bot instance
        bot = TelegramBot()

        # When: Checking if command exists
        command_name = removed_command.replace('/', '')

        # Then: Command should not be in registered handlers
        assert not hasattr(bot, f'cmd_{command_name}'), f"{removed_command} should be removed"

        # And: Help text should not mention it
        help_text = bot.get_help_text()
        assert removed_command not in help_text, f"{removed_command} should not appear in help"

    def test_remaining_commands_still_work(self):
        """
        User Story: Essential commands should continue to work after cleanup
        """
        from claude_ops.telegram.bot import TelegramBot

        # Given: Bot instance
        bot = TelegramBot()

        # When: Checking essential commands
        essential_commands = [
            'sessions', 'new_project', 'board', 'restart',
            'stop', 'erase', 'status', 'log', 'fullcycle', 'help'
        ]

        # Then: All essential commands should exist
        for command in essential_commands:
            assert hasattr(bot, f'cmd_{command}'), f"Essential command /{command} should exist"


class TestIntegrationScenarios:
    """End-to-end integration tests for the complete fix"""

    def test_complete_workflow_no_false_notifications(self):
        """
        User Story: During a complete Claude work session with TODOs,
        no false completion notifications should be sent
        """
        # Given: A monitoring session for active Claude work
        from claude_ops.monitoring.multi_monitor import MultiSessionMonitor

        monitor = MultiSessionMonitor()
        session_name = "claude_test"

        # Screen progression during work
        screens = [
            # Step 1: Starting work
            "✻ Analyzing requirements... (esc to interrupt)",

            # Step 2: Working with TODOs
            """✻ Building feature… (esc to interrupt · ctrl+t to hide todos)

            Todos:
            ☒ Analyze requirements
            ☐ Create implementation plan

            >""",

            # Step 3: Still working despite prompt
            """● Implementing solution...
            ✻ Writing code… (esc to interrupt)

            >""",

            # Step 4: Actually complete (no esc to interrupt)
            """✅ Task completed successfully!

            All todos are done.

            >"""
        ]

        notifications_sent = []

        with patch.object(monitor, 'send_notification') as mock_notify:
            mock_notify.side_effect = lambda msg: notifications_sent.append(msg)

            # When: Processing each screen state
            for i, screen in enumerate(screens[:-1]):  # All except last
                with patch.object(monitor.state_analyzer, 'get_current_screen_only', return_value=screen):
                    state = monitor.state_analyzer.get_state_for_notification(session_name)

                    # Then: Should be WORKING for all screens with "esc to interrupt"
                    assert state == SessionState.WORKING, f"Step {i+1} should be WORKING"
                    assert len(notifications_sent) == 0, f"No notifications should be sent at step {i+1}"

            # When: Processing final screen (actually complete)
            with patch.object(monitor.state_analyzer, 'get_current_screen_only', return_value=screens[-1]):
                state = monitor.state_analyzer.get_state_for_notification(session_name)

                # Then: Should be IDLE only when truly complete
                assert state == SessionState.IDLE, "Should be IDLE when work is actually done"
                # Now a completion notification would be appropriate


# Test runner for validation
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])