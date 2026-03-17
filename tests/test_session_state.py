"""
Unit tests for session state detection module

Tests the unified SessionStateAnalyzer to ensure reliable and consistent
state detection across all components.
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock
from datetime import datetime

from claude_ctb.utils.session_state import (
    SessionStateAnalyzer,
    SessionState,
    StateTransition
)
from conftest import load_fixture


class TestSessionState:
    """Test SessionState enum"""

    def test_state_enum_values(self):
        """Test that all required states are defined"""
        assert SessionState.ERROR.value == "error"
        assert SessionState.WAITING_INPUT.value == "waiting"
        assert SessionState.WORKING.value == "working"
        assert SessionState.IDLE.value == "idle"
        assert SessionState.UNKNOWN.value == "unknown"

    def test_state_priority(self):
        """Test state priority ordering"""
        analyzer = SessionStateAnalyzer()

        # CONTEXT_LIMIT should have highest priority (lowest number)
        assert analyzer.STATE_PRIORITY[SessionState.CONTEXT_LIMIT] == 0
        assert analyzer.STATE_PRIORITY[SessionState.ERROR] == 1
        assert analyzer.STATE_PRIORITY[SessionState.WAITING_INPUT] == 2
        assert analyzer.STATE_PRIORITY[SessionState.WORKING] == 3
        assert analyzer.STATE_PRIORITY[SessionState.IDLE] == 4
        assert analyzer.STATE_PRIORITY[SessionState.UNKNOWN] == 5


class TestStateTransition:
    """Test StateTransition class"""

    def test_transition_creation(self):
        """Test creating state transitions"""
        transition = StateTransition(
            session="test_session",
            from_state=SessionState.IDLE,
            to_state=SessionState.WORKING
        )

        assert transition.session == "test_session"
        assert transition.from_state == SessionState.IDLE
        assert transition.to_state == SessionState.WORKING
        assert isinstance(transition.timestamp, datetime)

    def test_transition_repr(self):
        """Test string representation"""
        transition = StateTransition(
            session="test",
            from_state=SessionState.IDLE,
            to_state=SessionState.WORKING
        )

        expected = "StateTransition(test: SessionState.IDLE → SessionState.WORKING)"
        assert str(transition) == expected


class TestSessionStateAnalyzer:
    """Test SessionStateAnalyzer class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = SessionStateAnalyzer()

    @patch('claude_ctb.utils.session_state.subprocess.run')
    def test_get_screen_content_success(self, mock_run):
        """Test successful screen content retrieval"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test screen content"
        mock_run.return_value = mock_result

        content = self.analyzer.get_screen_content("test_session", use_cache=False)

        assert content == "test screen content"
        mock_run.assert_called_once_with(
            "tmux capture-pane -t test_session -p -S -200",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

    @patch('claude_ctb.utils.session_state.subprocess.run')
    def test_get_screen_content_failure(self, mock_run):
        """Test screen content retrieval failure"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result

        content = self.analyzer.get_screen_content("test_session", use_cache=False)

        assert content is None

    def test_detect_working_state_true(self):
        """Test working state detection - positive cases.

        Each fixture must include surrounding context (❯ prompt, OMC bars)
        to exercise the 25-line recency window and narrow-window logic.
        """
        test_cases = [
            # esc to interrupt in recent lines
            "Some output\nMore lines\nesc to interrupt\n\n❯\n",
            # ctrl+c to interrupt
            "Output\nctrl+c to interrupt\n\n❯\n",
            # ctrl+b to run in background within narrow window before ❯
            "Previous output\nctrl+b to run in background\n❯\n",
            # Token streaming pattern in narrow window
            "Previous\n↓ 404 tokens\n❯\n",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result is True, f"Failed for: {repr(screen_content)}"

    def test_detect_working_state_false(self):
        """Test working state detection - negative cases"""
        test_cases = [
            "Just normal output\nNo working patterns\nComplete\n❯\n",
            "",  # Empty content
            # Old pattern pushed beyond 25 lines
            "Old command\n● Previous\n  ⎿  Running…\n" + "\n" * 25 + "Recent idle content\n❯\n",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result is False, f"Failed for: {repr(screen_content)}"

    def test_detect_input_waiting_true(self):
        """Test input waiting detection - positive cases"""
        test_cases = [
            "Some content\nDo you want to proceed?\n❯ 1. Yes\n  2. No",
            "Output\n❯ 1. Option A\n❯ 2. Option B",
            "Content\nChoose an option:\nSelect your choice",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_input_waiting(screen_content)
            assert result is True, f"Failed for: {screen_content}"

    def test_detect_input_waiting_false(self):
        """Test input waiting detection - negative cases"""
        test_cases = [
            "Normal output\nNo selection prompts\nRegular content",
            "",  # Empty content
            "Just text\nNothing special\nEnd",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_input_waiting(screen_content)
            assert result is False, f"Failed for: {screen_content}"

    def test_detect_error_state_true(self):
        """Test error state detection - positive cases (no working indicators)"""
        test_cases = [
            "Command output\nError: Something went wrong\nEnd",
            "Process\nFailed: Connection timeout\nResult",
            "Start\nException: Invalid input\nFinish",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_error_state(screen_content)
            assert result is True, f"Failed for: {screen_content}"

    def test_detect_error_state_false(self):
        """Test error state detection - negative cases"""
        test_cases = [
            "Normal successful output\nCompleted successfully\nDone",
            "",  # Empty content
            "Regular process\nNo errors\nFinished",
        ]

        for screen_content in test_cases:
            result = self.analyzer._detect_error_state(screen_content)
            assert result is False, f"Failed for: {screen_content}"

    def test_detect_error_state_suppressed_by_working(self):
        """Error patterns during active work should not trigger ERROR state."""
        # Claude is actively working and mentions 'Error:' in its analysis output
        screen = (
            "● Analyzing error handling patterns\n"
            "  Error: found in 5 files\n"
            "  esc to interrupt\n"
            "\n❯\n"
        )
        assert self.analyzer._detect_error_state(screen) is False

    @patch('claude_ctb.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_priority_resolution(self, mock_get_content):
        """Test state priority resolution when multiple states detected.

        Screen must have waiting patterns WITHOUT working indicators to
        trigger WAITING_INPUT (working guard in _detect_input_waiting).
        """
        mock_get_content.return_value = (
            "Previous output completed.\n"
            "\n"
            "Do you want to proceed?\n"
            "❯ 1. Yes\n"
            "  2. No\n"
        )

        state = self.analyzer.get_state("test_session")
        assert state == SessionState.WAITING_INPUT

    @patch('claude_ctb.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_idle(self, mock_get_content):
        """Test idle state when no specific patterns found"""
        mock_get_content.return_value = "Normal idle content\nNo special patterns\n❯\n"

        state = self.analyzer.get_state("test_session")
        assert state == SessionState.IDLE

    @patch('claude_ctb.utils.session_state.SessionStateAnalyzer.get_screen_content')
    def test_get_state_unknown(self, mock_get_content):
        """Test unknown state when screen content unavailable"""
        mock_get_content.return_value = None

        state = self.analyzer.get_state("test_session")
        assert state == SessionState.UNKNOWN

    @patch('claude_ctb.utils.session_state.SessionStateAnalyzer.get_state')
    def test_legacy_functions(self, mock_get_state):
        """Test legacy compatibility functions"""
        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_working("test") is True

        mock_get_state.return_value = SessionState.IDLE
        assert self.analyzer.is_working("test") is False

        mock_get_state.return_value = SessionState.WAITING_INPUT
        assert self.analyzer.is_waiting_for_input("test") is True

        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_waiting_for_input("test") is False

        mock_get_state.return_value = SessionState.IDLE
        assert self.analyzer.is_idle("test") is True

        mock_get_state.return_value = SessionState.WORKING
        assert self.analyzer.is_idle("test") is False


class TestGlobalFunctions:
    """Test global compatibility functions"""

    @patch('claude_ctb.utils.session_state.session_state_analyzer.is_working')
    def test_is_session_working(self, mock_is_working):
        """Test global is_session_working function"""
        mock_is_working.return_value = True

        from claude_ctb.utils.session_state import is_session_working
        result = is_session_working("test_session")

        assert result is True
        mock_is_working.assert_called_once_with("test_session")

    @patch('claude_ctb.utils.session_state.session_state_analyzer.get_state_details')
    def test_get_session_working_info(self, mock_get_details):
        """Test global get_session_working_info function"""
        mock_get_details.return_value = {
            "state": SessionState.WORKING,
            "screen_length": 1000,
            "working_patterns_found": ["Running…"],
            "analysis": {"decision_logic": "test logic"}
        }

        from claude_ctb.utils.session_state import get_session_working_info
        result = get_session_working_info("test_session")

        expected = {
            "screen_length": 1000,
            "working_patterns_found": ["Running…"],
            "final_decision": True,
            "logic": "test logic"
        }

        assert result == expected


class TestOutputGuard:
    """Tests for the ⎿ output guard and parent-line preservation.

    Bug context: antibiotic_platform session showed thinking with task-list
    sub-output (⎿) which caused the guard to cut the parent working indicator,
    misclassifying active thinking as IDLE.  Fixed by preserving the parent line.
    """

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def test_active_thinking_with_task_list(self):
        """Golden fixture: active ✢ thinking with ⎿ task list → WORKING.

        Regression for the antibiotic_platform idle-misdetection bug.
        """
        screen = load_fixture("thinking_with_task_list")
        assert self.analyzer._detect_working_state(screen) is True

    def test_completed_tool_output(self):
        """Golden fixture: completed tool with ⎿ result → IDLE."""
        screen = load_fixture("completed_tool_output")
        assert self.analyzer._detect_working_state(screen) is False

    def test_output_guard_first_line(self):
        """⎿ on first line of check window (no parent) → no crash, not working."""
        screen = (
            "  ⎿  Some previous output\n"
            "     More output lines\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_multiple_output_blocks(self):
        """Multiple ⎿ blocks: only last block's parent is preserved."""
        screen = (
            "✢ Old thinking… (5s · 100 tokens)\n"       # stale parent of first ⎿
            "  ⎿  Old task list item\n"                   # first ⎿ block
            "\n"
            "✢ Current work… (10s · ↓ 2k tokens)\n"      # parent of last ⎿
            "  ⎿  ◼ Active task\n"                        # last ⎿ block
            "     ◻ Pending task\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_omc_bar_between_working_and_output(self):
        """Golden fixture: OMC bar between working indicator and ⎿.

        The OMC bar filter removes [OMC#...] lines before the ⎿ scan,
        so the parent line (✢ thinking) should still be detected correctly.
        """
        screen = load_fixture("omc_bar_between_working_and_output")
        assert self.analyzer._detect_working_state(screen) is True

    def test_nested_output_parent_is_output_line(self):
        """When parent of ⎿ is itself a ⎿ line, it should not false-positive."""
        screen = (
            "  ⎿  Outer output\n"
            "  ⎿  Inner nested output\n"
            "     Some text\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_compacting_context_detected(self):
        """Compacting context should be detected as WORKING."""
        screen = (
            "Compacting context…\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True


class TestLineWrap:
    """Tests for tmux line-wrap handling of interrupt indicators."""

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def test_esc_to_interrupt_split_across_lines(self):
        """'esc to interrupt' split by tmux wrap should still be detected."""
        screen = (
            "Some output content\n"
            "  45s · 2.3k tokens · esc to inter\n"
            "rupt\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_ctrl_c_to_interrupt_split(self):
        """'ctrl+c to interrupt' split by tmux wrap."""
        screen = (
            "Output\n"
            "  10s · 500 tokens · ctrl+c to inter\n"
            "rupt\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_normal_lines_not_false_positive(self):
        """Joining adjacent lines should not create false interrupt matches."""
        screen = (
            "This is normal text about esc\n"
            "aping characters in shell\n"
            "\n"
            "❯\n"
        )
        # "esc" + "aping" joined = "escaping" — should NOT match "esc to interrupt"
        assert self.analyzer._detect_working_state(screen) is False


class TestIntegration:
    """Integration tests with real-world scenarios"""

    def test_real_world_scenario_git_commit(self):
        """Test detection with real git commit scenario"""
        screen_content = """
● Bash(git add .)
  ⎿  (No content)

● Bash(git commit -m "test commit")
  ⎿  [main abc1234] test commit
     1 file changed, 10 insertions(+)

● Bash(git push)
  ⎿  Running…

✢ Unravelling… (0s · ⚒ 113 tokens · esc to interrupt)

 >

  ⏵⏵ accept edits on (shift+tab to cycle)
"""

        analyzer = SessionStateAnalyzer()
        result = analyzer._detect_working_state(screen_content)
        assert result is True  # "esc to interrupt" present

    def test_real_world_scenario_user_prompt(self):
        """Test detection with real user prompt scenario"""
        screen_content = """
● Task completed successfully

Results:
- File created: config.json
- Dependencies installed
- Server configured

Do you want to proceed with deployment?
❯ 1. Yes
  2. No, and tell Claude what to do differently (esc)
"""

        analyzer = SessionStateAnalyzer()

        working = analyzer._detect_working_state(screen_content)
        waiting = analyzer._detect_input_waiting(screen_content)

        assert working is False
        assert waiting is True

    def test_real_world_golden_fixture_esc_to_interrupt(self):
        """Golden fixture: active session with 'esc to interrupt'."""
        screen = load_fixture("esc_to_interrupt_active")
        analyzer = SessionStateAnalyzer()
        assert analyzer._detect_working_state(screen) is True

    def test_real_world_scenario_telegram_message_too_long(self):
        """Test handling of very long screen content"""
        long_content = "● Processing large dataset\n"
        long_content += "Data analysis output:\n"
        long_content += "x" * 5000

        analyzer = SessionStateAnalyzer()
        state = analyzer._detect_working_state(long_content)
        assert isinstance(state, bool)

    def test_performance_large_screen_content(self):
        """Test performance with very large screen content"""
        import time

        large_content = ""
        for i in range(1000):
            large_content += f"Line {i}: Some output from long running process\n"

        # Add working pattern within last 25 lines with proper context
        large_content += "esc to interrupt\n\n❯\n"

        analyzer = SessionStateAnalyzer()

        start_time = time.time()
        result = analyzer._detect_working_state(large_content)
        end_time = time.time()

        assert result is True
        assert (end_time - start_time) < 0.1

    def test_concurrent_state_detection(self):
        """Test concurrent access to state analyzer"""
        import threading

        analyzer = SessionStateAnalyzer()
        results = []
        lock = threading.Lock()

        def check_state(session_name):
            with patch.object(analyzer, 'get_screen_content',
                              return_value="esc to interrupt\n\n❯\n"):
                state = analyzer.get_state(session_name, use_cache=False)
                with lock:
                    results.append((session_name, state))

        threads = []
        for i in range(5):
            thread = threading.Thread(target=check_state, args=(f"session_{i}",))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(results) == 5
        for session_name, state in results:
            assert state == SessionState.WORKING

    def test_state_transition_sequence(self):
        """Test realistic state transition sequence"""
        analyzer = SessionStateAnalyzer()

        states_sequence = [
            # Working: esc to interrupt in recent content
            ("Previous output\nesc to interrupt\n\n❯\n", SessionState.WORKING),
            # Waiting: no working indicators, prompt visible
            ("Task completed.\nDo you want to proceed?\n❯ 1. Yes\n", SessionState.WAITING_INPUT),
            # Idle: just a prompt, nothing else
            ("● All done\nTask finished successfully\n❯\n", SessionState.IDLE),
        ]

        for screen_content, expected_state in states_sequence:
            with patch.object(analyzer, 'get_screen_content',
                              return_value=screen_content):
                actual_state = analyzer.get_state("test_session", use_cache=False)
                assert actual_state == expected_state, \
                    f"Expected {expected_state}, got {actual_state} for: {repr(screen_content)}"

    def test_edge_case_empty_screen(self):
        """Test handling of empty screen content"""
        analyzer = SessionStateAnalyzer()

        with patch.object(analyzer, 'get_screen_content', return_value=""):
            state = analyzer.get_state("test_session")
            assert state == SessionState.IDLE

    def test_edge_case_null_screen(self):
        """Test handling of null screen content"""
        analyzer = SessionStateAnalyzer()

        with patch.object(analyzer, 'get_screen_content', return_value=None):
            state = analyzer.get_state("test_session")
            assert state == SessionState.UNKNOWN

    def test_edge_case_session_not_found(self):
        """Test handling of non-existent tmux session"""
        analyzer = SessionStateAnalyzer()

        with patch('claude_ctb.utils.session_state.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "session not found"
            mock_run.return_value = mock_result

            state = analyzer.get_state("nonexistent_session")
            assert state == SessionState.UNKNOWN


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_subprocess_timeout(self):
        """Test handling of subprocess timeout"""
        analyzer = SessionStateAnalyzer()

        with patch('claude_ctb.utils.session_state.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("tmux", 5)

            state = analyzer.get_state("test_session")
            assert state == SessionState.UNKNOWN

    def test_subprocess_exception(self):
        """Test handling of subprocess exceptions"""
        analyzer = SessionStateAnalyzer()

        with patch('claude_ctb.utils.session_state.subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            state = analyzer.get_state("test_session")
            assert state == SessionState.UNKNOWN

    def test_malformed_screen_content(self):
        """Test handling of malformed screen content"""
        analyzer = SessionStateAnalyzer()

        malformed_inputs = [
            "\x00\x01\x02",
            "ĉ̸̢̖͚̱̻͓͇̹̺̳̥̈́̾̃̀͒́̅̌̍̕",
            "\n" * 10000,
            "A" * 100000,
        ]

        for malformed_input in malformed_inputs:
            with patch.object(analyzer, 'get_screen_content',
                              return_value=malformed_input):
                state = analyzer.get_state("test_session")
                assert isinstance(state, SessionState)


if __name__ == "__main__":
    pytest.main([__file__])
