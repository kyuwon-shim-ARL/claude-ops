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
        assert analyzer.STATE_PRIORITY[SessionState.OVERLOADED] == 2
        assert analyzer.STATE_PRIORITY[SessionState.WAITING_INPUT] == 3
        assert analyzer.STATE_PRIORITY[SessionState.WORKING] == 4
        assert analyzer.STATE_PRIORITY[SessionState.IDLE] == 5
        assert analyzer.STATE_PRIORITY[SessionState.SCHEDULED] == 6
        assert analyzer.STATE_PRIORITY[SessionState.UNKNOWN] == 7


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

    def test_compacting_conversation_detected(self):
        """Compacting conversation (with spinner glyph) should be detected as WORKING."""
        screen = (
            "✢ Compacting conversation… (1m 12s)\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_precompact_hooks_detected(self):
        """Running PreCompact hooks should be detected as WORKING."""
        screen = (
            "Running PreCompact hooks…\n"
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


class TestCollapseSubOutput:
    """Unit tests for _collapse_sub_output() — T1 of e008."""

    def setup_method(self):
        self.collapse = SessionStateAnalyzer._collapse_sub_output

    def test_basic_sub_output_removed(self):
        """⎿ line is discarded, initiator kept."""
        lines = ["● Tool(args)", "  ⎿  output line", "❯"]
        assert self.collapse(lines) == ["● Tool(args)", "❯"]

    def test_blank_ends_sub_output_block(self):
        """Blank line terminates sub-output; blank itself is kept."""
        lines = ["● Tool", "  ⎿  out", "     cont", "", "❯"]
        assert self.collapse(lines) == ["● Tool", "", "❯"]

    def test_deep_indent_continuation_discarded(self):
        """Lines with leading >= 5 spaces inside sub-output are discarded."""
        lines = ["● T", "  ⎿  line1", "     line2", "     line3", "❯"]
        assert self.collapse(lines) == ["● T", "❯"]

    def test_low_indent_ends_sub_output(self):
        """Non-blank line with < 5 leading spaces exits sub-output mode."""
        lines = ["● T1", "  ⎿  sub", "     c", "● T2"]
        assert self.collapse(lines) == ["● T1", "● T2"]

    def test_eof_inside_sub_output(self):
        """Sub-output at end of input — no terminator."""
        lines = ["● T", "  ⎿  line1", "     line2"]
        assert self.collapse(lines) == ["● T"]

    def test_four_space_indent_exits_sub_output(self):
        """4-space indent is < 5, so it exits sub-output and is kept."""
        lines = ["● T", "  ⎿  out", "    four"]
        assert self.collapse(lines) == ["● T", "    four"]

    def test_five_space_indent_stays_in_sub_output(self):
        """5-space indent is >= 5, so it stays in sub-output and is discarded."""
        lines = ["● T", "  ⎿  out", "     five"]
        assert self.collapse(lines) == ["● T"]

    def test_consecutive_sub_output_blocks(self):
        """Two ⎿ blocks separated by blank, both collapsed."""
        lines = [
            "● Tool1", "  ⎿  out1", "     c1", "",
            "● Tool2", "  ⎿  out2", "     c2", "",
            "✶ Spinner"
        ]
        assert self.collapse(lines) == ["● Tool1", "", "● Tool2", "", "✶ Spinner"]

    def test_nested_sub_output(self):
        """Two consecutive ⎿ lines — both discarded."""
        lines = ["● T", "  ⎿  first", "  ⎿  second", "❯"]
        assert self.collapse(lines) == ["● T", "❯"]

    def test_empty_input(self):
        """Empty list returns empty list."""
        assert self.collapse([]) == []

    def test_no_sub_output(self):
        """Lines without ⎿ pass through unchanged."""
        lines = ["line1", "line2", "line3"]
        assert self.collapse(lines) == ["line1", "line2", "line3"]


class TestWideWindowAndOMCSignals:
    """Tests for collapse-based detection and OMC-specific signals.

    These cover real-world scenarios where sub-output blocks are arbitrarily
    long and OMC background task signals need special handling.
    """

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def test_long_task_list_pushes_indicator_beyond_6_lines(self):
        """Working indicator above 6 lines from prompt must still be detected.

        Real scenario: OMC task list with 10+ sub-items pushes the
        '● Creating… (↓ 4.3k tokens)' line far above the ❯ prompt.
        """
        screen = (
            "● Creating experiment tickets… (6m 46s · ↓ 4.3k tokens)\n"
            "  ⎿  ✔ Phase A1: SOTA-expand\n"
            "     ✔ Phase A2: Fetch missing abstracts\n"
            "     ✔ Phase A3: L1 abstract analysis\n"
            "     ✔ Phase A4: Positioning analysis\n"
            "     ✔ Phase A5: Gap identification\n"
            "     ◼ Phase B1: Initialize exp-workflow\n"
            "     ◻ Phase B2: Critic review\n"
            "     ◻ Phase B3: Final plan\n"
            "     ◻ Phase C1: Execute converged plans\n"
            "     ◻ Phase C2: Validation\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_spinner_glyph_variants_with_tokens(self):
        """Claude Code uses various spinner glyphs: ·✢✳✶✻✽●⏺.

        Token patterns like '↓ 24.6k tokens' must be detected regardless
        of which glyph is used.
        """
        for glyph in ['·', '✢', '✳', '✶', '✻', '✽', '●', '⏺']:
            screen = (
                f"● Some tool output\n"
                f"  ⎿  result\n"
                f"\n"
                f"{glyph} Working… (5m · ↓ 12.3k tokens)\n"
                f"\n"
                f"❯\n"
            )
            assert self.analyzer._detect_working_state(screen) is True, \
                f"Failed for glyph {glyph}"

    def test_omc_background_task_running(self):
        """⏵⏵ line with '(running)' indicates active background agent."""
        screen = (
            "Some previous output\n"
            "✻ Worked for 57s\n"
            "\n"
            "❯\n"
            "───\n"
            "  [OMC#4.5.1] | session:1m\n"
            "  ⏵⏵ bypass permissions on · Task name (running)\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_omc_background_no_running_is_idle(self):
        """⏵⏵ without '(running)' is NOT a working signal."""
        screen = (
            "Task completed.\n"
            "✻ Worked for 57s\n"
            "\n"
            "❯\n"
            "───\n"
            "  [OMC#4.5.1] | session:1m\n"
            "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_past_tense_worked_for_is_idle(self):
        """'Worked for 57s' (past tense) must NOT be detected as working."""
        screen = (
            "  Best regards,\n"
            "  Kyuwon\n"
            "\n"
            "✻ Worked for 57s\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_stale_scrollback_not_detected_as_working(self):
        """Stale working indicators in scrollback must not cause false positives.

        After a tool completes and Claude writes response text, the old
        spinner line (with token count) remains in scrollback. The collapse
        + 2-non-blank-line window must exclude it.
        """
        screen = (
            "✶ Old analysis… (15m · ↓ 30k tokens)\n"
            "  ⎿  ✔ Step 1 done\n"
            "     ✔ Step 2 done\n"
            "\n"
            "● Here is the analysis:\n"
            "\n"
            "The model shows significant improvement from 0.75 to 0.92.\n"
            "Key factors: better tokenization, larger batch size.\n"
            "Recommendation: proceed with the larger model.\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_100_sub_items_still_detected(self):
        """Working indicator must be found regardless of sub-output length.

        Validates the structural fix: collapse removes sub-output before
        windowing, so even 100 task items don't push the indicator out.
        """
        lines = ["● Creating tickets… (6m · ↓ 4.3k tokens)", "  ⎿  ✔ Task 1"]
        for i in range(2, 101):
            lines.append(f"     ✔ Task {i}")
        lines.extend(["", "❯", ""])
        assert self.analyzer._detect_working_state("\n".join(lines)) is True

    def test_real_world_piu_v2_pattern(self):
        """Real PIU-v2 session: many tool outputs then spinner with tokens."""
        screen = (
            "● Bash(gh issue close 10)\n"
            "  ⎿  ✓ Closed issue #10\n"
            "\n"
            "● plugin:runpod-mcp:runpod - list_pods (MCP)\n"
            "  ⎿  ID: spf0ifdqo18vq5\n"
            "     Name: piu-v2\n"
            "     Status: EXITED\n"
            "\n"
            "  Searching for 4 patterns\n"
            "  ⎿  \"scripts/*train*\"\n"
            "\n"
            "✶ Boondoggling… (22m 49s · ↑ 8.2k tokens · thought for 4s)\n"
            "\n"
            "───\n"
            "❯\n"
            "───\n"
            "  [OMC#4.5.1] | thinking | session:22m\n"
            "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    # --- T4: 2-non-blank boundary tests ---

    def test_spinner_as_only_nonblank_before_prompt(self):
        """Single non-blank line (spinner) before ❯ → WORKING."""
        screen = "\n\n✶ Thinking… (↓ 404 tokens)\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is True

    def test_spinner_at_second_nonblank_not_detected(self):
        """Past-tense completion at 2nd-to-last non-blank → NOT working.

        When Claude finishes, the active spinner ('Working…') changes to
        past-tense ('Worked for 5m 8s') — the ellipsis disappears. So a
        past-tense line above response text is correctly stale/IDLE.
        """
        screen = (
            "✶ Worked for 5m (↓ 10k tokens)\n"
            "\n"
            "Some response text\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_active_spinner_with_ui_dialog_below_is_working(self):
        """Active spinner with Claude Code UI dialog between it and prompt → WORKING.

        P1d catches this: the ellipsis (…) in raw recent lines is a definitive
        active-work signal regardless of inline UI elements below the spinner.
        """
        screen = (
            "✢ Percolating… (4m 40s · ↑ 3.3k tokens)\n"
            "\n"
            "● How is Claude doing this session? (optional)\n"
            "  1: Bad    2: Fine   3: Good   0: Dismiss\n"
            "\n"
            "❯\n"
            "───────────────────────────────────────────────────\n"
            "  [OMC#4.5.1] | session:30m | ctx:42% | 🔧9\n"
            "  ⏵⏵ bypass permissions on\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    def test_spinner_at_third_nonblank_excluded(self):
        """Spinner is 3rd-from-last non-blank (outside [-2:] window) → IDLE."""
        screen = (
            "✶ Old work… (5m · ↓ 10k tokens)\n"
            "\n"
            "Response line A\n"
            "\n"
            "Response line B\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is False

    def test_all_blank_before_prompt_is_idle(self):
        """Zero non-blank lines after collapse → IDLE."""
        screen = "  ⎿  orphan output\n     cont\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is False

    # --- T2 verification: structural regex with all glyphs ---

    def test_structural_regex_all_glyphs(self):
        """All _TOOL_GLYPHS (·✢✳✶✻✽●⏺) match the structural verb regex."""
        for glyph in ['·', '✢', '✳', '✶', '✻', '✽', '●', '⏺']:
            screen = f"{glyph} Running tests\n\n❯\n"
            assert self.analyzer._detect_working_state(screen) is True, \
                f"Structural regex missed glyph {glyph}"

    # --- T: Generic ellipsis pattern (random verbs) ---

    def test_random_verb_with_ellipsis_is_working(self):
        """Random verb with … (ellipsis) must be detected as WORKING.

        Claude Code uses random verbs: Swooping…, Stewing…, Cogitating…, etc.
        The ellipsis (U+2026) is the key indicator of active work.
        """
        for verb in ['Swooping', 'Stewing', 'Cogitating', 'Elucidating', 'Boondoggling']:
            screen = f"✶ {verb}\u2026 (1h 51m 11s)\n\n❯\n"
            assert self.analyzer._detect_working_state(screen) is True, \
                f"Random verb '{verb}…' should be WORKING"

    def test_random_verb_with_ellipsis_no_parens_is_working(self):
        """Random verb with … but NO parenthesized info still WORKING."""
        screen = "✶ Swooping\u2026\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is True

    def test_random_verb_with_tokens_and_thinking_is_working(self):
        """Full status line with tokens and thinking marker."""
        screen = "✶ Swooping\u2026 (1h 51m 11s · ↓ 9.2k tokens · thinking)\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is True

    def test_past_tense_cogitated_for_is_idle(self):
        """'Cogitated for 5m 8s' (past tense, no …) must NOT be WORKING."""
        screen = "✻ Cogitated for 5m 8s\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is False

    def test_past_tense_cogitated_long_duration_is_idle(self):
        """'Cogitated for 26m 55s' (past tense) must NOT be WORKING."""
        screen = "✻ Cogitated for 26m 55s\n\n❯\n"
        assert self.analyzer._detect_working_state(screen) is False

    def test_past_tense_various_verbs_are_idle(self):
        """Various past-tense completion forms must all be IDLE."""
        for verb in ['Worked', 'Cogitated', 'Thought', 'Processed']:
            screen = f"✻ {verb} for 57s\n\n❯\n"
            assert self.analyzer._detect_working_state(screen) is False, \
                f"Past-tense '{verb} for' should NOT be WORKING"

    def test_completion_with_background_tasks_is_working(self):
        """Completion line + 'background tasks still running' = still WORKING."""
        screen = (
            "✻ Cogitated for 5m 8s, background tasks still running\n"
            "\n"
            "❯\n"
        )
        # "background tasks still running" string pattern should trigger WORKING
        assert self.analyzer._detect_working_state(screen) is True

    def test_churned_with_background_tasks_is_working(self):
        """Real-world: '✻ Churned for 47s · 2 background tasks still running' = WORKING.

        Main work is done but background tasks are pending results.
        The 'background tasks still running' string must take priority over
        the past-tense completion guard.
        """
        screen = (
            "✻ Churned for 47s \xb7 2 background tasks still running (\u2193 to manage)\n"
            "\n"
            "❯\n"
        )
        assert self.analyzer._detect_working_state(screen) is True

    # --- T7: collapse path performance test ---

    def test_performance_collapse_500_blocks(self):
        """500 tool blocks must collapse+detect in < 50ms."""
        import time
        lines = []
        for i in range(500):
            lines.extend([f"● Tool{i}(args)", f"  ⎿  output{i}", f"     cont{i}", ""])
        lines.extend(["✶ Working… (↓ 5k tokens)", "", "❯", ""])
        screen = "\n".join(lines)

        t0 = time.time()
        result = self.analyzer._detect_working_state(screen)
        elapsed = time.time() - t0

        assert result is True
        assert elapsed < 0.05, f"Collapse too slow: {elapsed:.3f}s"


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


class TestExtractLastPrompt:
    """
    Regression: extract_last_prompt was missing from SessionStateAnalyzer.
    Called by multi_monitor.py 529 overload retry but caused AttributeError,
    silently disabling auto-retry for all sessions.
    Found by /qa on 2026-04-09
    Report: fix(session-state): add extract_last_prompt to SessionStateAnalyzer
    """

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def test_extracts_prompt_after_chevron(self):
        screen = "some output\n❯ 재시도해줘\n  ⎿  API Error: 529 overloaded_error"
        assert self.analyzer.extract_last_prompt(screen) == "재시도해줘"

    def test_extracts_last_prompt_when_multiple_chevrons(self):
        screen = "❯ 이전 프롬프트\nsome output\n❯ 마지막 프롬프트"
        assert self.analyzer.extract_last_prompt(screen) == "마지막 프롬프트"

    def test_returns_none_on_empty_content(self):
        assert self.analyzer.extract_last_prompt("") is None
        assert self.analyzer.extract_last_prompt(None) is None

    def test_returns_none_when_no_chevron(self):
        screen = "just some output\nno prompt here"
        assert self.analyzer.extract_last_prompt(screen) is None

    def test_ignores_bare_chevron_with_no_text(self):
        screen = "❯ \n❯ actual prompt"
        assert self.analyzer.extract_last_prompt(screen) == "actual prompt"

    def test_multiline_screen_with_529_error(self):
        # Reproduces the exact claude_misc scenario
        screen = (
            "❯ 왜 이렇게 나 많이 필요한거야? 주요 선택기준에 따라 MECE하면서도\n"
            " 구조의 위계가 한눈에 보이게 정리해줘.\n"
            '  ⎿  API Error: 529 {"type":"error","error":{"type":"overloaded_error"}}\n'
            "❯ \n"
            "──────────────────────────────\n"
        )
        result = self.analyzer.extract_last_prompt(screen)
        assert result == "왜 이렇게 나 많이 필요한거야? 주요 선택기준에 따라 MECE하면서도"


class TestDetectStuckAfterAgent:
    """Tests for detect_stuck_after_agent — fires nudge when JSONL ends with
    unanswered tool_result (Claude got results but hasn't responded yet)."""

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def _write_jsonl(self, path, entries):
        """Write JSONL entries to a file."""
        import json
        path.write_text('\n'.join(json.dumps(e) for e in entries))

    def _assistant_tool_use(self):
        return {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash"}]}}

    def _tool_result(self):
        return {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}

    def _assistant_text(self):
        return {"message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}

    def _make_proj(self, tmp_path, monkeypatch, entries, age_seconds):
        """Create project dir + JSONL and patch expanduser/time."""
        import time as _time
        # encoded("/fake/path") == "-fake-path"; expanduser returns tmp_path
        # so project_dir = tmp_path / "-fake-path"
        proj = tmp_path / "-fake-path"
        proj.mkdir(parents=True)
        jsonl = proj / "session.jsonl"
        self._write_jsonl(jsonl, entries)
        mtime = jsonl.stat().st_mtime
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) if "~" in p else p)
        monkeypatch.setattr("time.time", lambda: mtime + age_seconds)
        return jsonl

    def test_stuck_returns_true(self, tmp_path, monkeypatch):
        """JSONL ends with tool_result > last_assistant — genuinely stuck."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_tool_use(), self._tool_result()], age_seconds=60)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is True

    def test_too_fresh_returns_false(self, tmp_path, monkeypatch):
        """JSONL age < 45s — Claude is still processing, not stuck."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_tool_use(), self._tool_result()], age_seconds=10)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is False

    def test_assistant_responded_returns_false(self, tmp_path, monkeypatch):
        """Assistant replied after tool_result — not stuck."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_tool_use(), self._tool_result(), self._assistant_text()],
                        age_seconds=60)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is False

    def test_no_tool_use_in_assistant_returns_false(self, tmp_path, monkeypatch):
        """Tool result present but prior assistant had no tool_use — not stuck."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_text(), self._tool_result()], age_seconds=60)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is False

    def test_empty_session_path_returns_false(self):
        assert self.analyzer.detect_stuck_after_agent("") is False
        assert self.analyzer.detect_stuck_after_agent(None) is False

    def test_nonexistent_project_dir_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) if "~" in p else p)
        assert self.analyzer.detect_stuck_after_agent("/no/such/path") is False

    def test_long_cogitation_within_new_max_age(self, tmp_path, monkeypatch):
        """JSONL age=2100s (35min cogitation) — within new max_age=3600, should detect."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_tool_use(), self._tool_result()], age_seconds=2100)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is True

    def test_beyond_max_age_returns_false(self, tmp_path, monkeypatch):
        """JSONL age=4000s — beyond max_age=3600, should skip."""
        self._make_proj(tmp_path, monkeypatch,
                        [self._assistant_tool_use(), self._tool_result()], age_seconds=4000)
        assert self.analyzer.detect_stuck_after_agent("/fake/path") is False


class TestExtractWorkflowPhase:
    """Tests for extract_workflow_phase() — 8 cases per ticket CTB-GLANCEABLE T1."""

    def setup_method(self):
        self.analyzer = SessionStateAnalyzer()

    def test_error_state_returns_error(self):
        """ERROR state always returns 'error' regardless of content."""
        content = "Some output\n❯\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.ERROR)
        assert result == "error"

    def test_awaiting_approval_pattern(self):
        """WAITING_INPUT + approval pattern → awaiting_approval."""
        content = "Claude 진행할까요?\nA) 예\nB) 아니오\n❯\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WAITING_INPUT)
        assert result == "awaiting_approval"

    def test_awaiting_approval_wins_over_completion(self):
        """Conflict: both approval and completion patterns present → awaiting_approval wins."""
        content = "작업 완료. 진행할까요? A) 계속 B) 중단\n❯\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WAITING_INPUT)
        assert result == "awaiting_approval"

    def test_reporting_completion_pattern(self):
        """WAITING_INPUT + completion keyword → reporting_completion."""
        content = "All tasks finished successfully.\n❯\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WAITING_INPUT)
        assert result == "reporting_completion"

    def test_executing_pattern(self):
        """WORKING + Edit/Write/Bash tool call → executing."""
        content = "● Edit(src/app.py)\n  Running tests...\nesc to interrupt\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WORKING)
        assert result == "executing"

    def test_planning_pattern(self):
        """WORKING + TodoWrite → planning."""
        content = "● TodoWrite([{task: implement feature}])\nesc to interrupt\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WORKING)
        assert result == "planning"

    def test_exploring_pattern(self):
        """WORKING + Read/Grep/Glob → exploring."""
        content = "● Grep(pattern='def extract', path='.')\nesc to interrupt\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WORKING)
        assert result == "exploring"

    def test_no_matching_pattern_returns_none(self):
        """WORKING with unrecognized content → None."""
        content = "Thinking...\nesc to interrupt\n"
        result = self.analyzer.extract_workflow_phase(content, SessionState.WORKING)
        assert result is None

    def test_none_screen_content_returns_none(self):
        """None screen_content always returns None."""
        result = self.analyzer.extract_workflow_phase(None, SessionState.WAITING_INPUT)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
