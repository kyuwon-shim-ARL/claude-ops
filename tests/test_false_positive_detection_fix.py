"""
Test for fixing false positive detection in Claude session state

This test reproduces and verifies the fix for the issue where
old "esc to interrupt" messages in scrollback cause false positives.
"""

import pytest
from unittest.mock import patch, MagicMock
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState


class TestFalsePositiveDetectionFix:
    """Test cases for preventing false positive working state detection"""
    
    def test_old_working_indicator_in_scrollback_should_not_trigger(self):
        """
        Test that old 'esc to interrupt' messages in scrollback buffer
        don't cause false positive working state detection
        """
        analyzer = SessionStateAnalyzer()
        
        # Simulate screen with old working indicator far up in scrollback
        # but with a clear prompt at the bottom
        screen_content = """
[Line 1 - old content]
[Line 2 - old content]
...
[Line 50 - old content]
...
[Line 60 - old content]
...
· Transfiguring… (esc to interrupt)    # Line 66 - OLD working indicator
[Line 67 - old content]
...
[Line 100 - old content]
...
[Line 150 - recent content]
  /보고                  # → 주간 보고서 자동 생성
  /연구 archive          # → 연구 최종 보고서 자동 생성

  🎉 핵심 장점

  1. 지능형 자동화: 작업 복잡도 자동 판단
  2. 명확한 분리: 개발 코드 vs 연구 분석
  3. 완전한 추적: 모든 연구 단계 자동 기록

╭─────────────────────────────────────────────────────────────────────────────────╮
│ >                                                                               │
╰─────────────────────────────────────────────────────────────────────────────────╯
  ⏵⏵ accept edits on (shift+tab to cycle)
"""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            with patch.object(analyzer, 'get_screen_content', return_value=screen_content):
                state = analyzer.get_state("test_session")
            
            # Should NOT be WORKING despite old "esc to interrupt" in scrollback
            assert state != SessionState.WORKING, \
                "Old working indicators in scrollback should not trigger working state"
            
            # Should be IDLE or WAITING_INPUT at the prompt
            assert state in [SessionState.IDLE, SessionState.WAITING_INPUT], \
                f"Expected IDLE or WAITING_INPUT at prompt, got {state}"
    
    def test_recent_working_indicator_still_triggers(self):
        """
        Test that recent/current 'esc to interrupt' messages still correctly
        trigger working state detection
        """
        analyzer = SessionStateAnalyzer()
        
        # Simulate active working screen
        screen_content = """
Running tests...
[1/10] test_example.py::test_one PASSED
[2/10] test_example.py::test_two PASSED
[3/10] test_example.py::test_three Running...

· Testing... (esc to interrupt)    # Recent/current working indicator
"""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            with patch.object(analyzer, 'get_screen_content', return_value=screen_content):
                state = analyzer.get_state("test_session")
            
            # Should correctly detect WORKING state for recent indicators
            assert state == SessionState.WORKING, \
                "Recent working indicators should trigger working state"
    
    def test_prompt_with_accept_edits_is_not_working(self):
        """
        Test that 'accept edits on' prompt is correctly identified as
        waiting for input, not working
        """
        analyzer = SessionStateAnalyzer()
        
        # Simulate Claude Code waiting for edit acceptance
        screen_content = """
Modified 1 file:
  - src/main.py

╭─────────────────────────────────────────────────────────────────────────────────╮
│ >                                                                               │
╰─────────────────────────────────────────────────────────────────────────────────╯
  ⏵⏵ accept edits on (shift+tab to cycle)
"""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            with patch.object(analyzer, 'get_screen_content', return_value=screen_content):
                state = analyzer.get_state("test_session")
            
            # Should be WAITING_INPUT or IDLE, not WORKING
            assert state != SessionState.WORKING, \
                "'accept edits' prompt should not be detected as working"
            
            # Preferably WAITING_INPUT since it's waiting for user action
            # But IDLE is also acceptable
            assert state in [SessionState.WAITING_INPUT, SessionState.IDLE], \
                f"Expected WAITING_INPUT or IDLE at edit prompt, got {state}"
    
    def test_multiple_old_indicators_dont_accumulate(self):
        """
        Test that multiple old working indicators in scrollback
        don't cause false positives
        """
        analyzer = SessionStateAnalyzer()
        
        # Simulate screen with old working indicators far from current view
        # All working indicators should be outside the 10-line detection window
        screen_content = """
[Very old task 1 - 20 lines up]
· Building... (esc to interrupt)    # Old indicator 1
[Task 1 completed]

[Very old task 2 - 15 lines up]  
· Testing... (esc to interrupt)     # Old indicator 2
[Task 2 completed]

[Old task 3 - 12 lines up]
· Installing... (esc to interrupt)  # Old indicator 3
[Task 3 completed]

Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7
Line 8
Line 9
Line 10
[Current screen - much later]
Session idle, waiting at prompt

user@host:~/project$ """
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            with patch.object(analyzer, 'get_screen_content', return_value=screen_content):
                state = analyzer.get_state("test_session")
            
            # Should be IDLE despite multiple old indicators
            assert state == SessionState.IDLE, \
                "Multiple old working indicators should not cause false positive"
    
    def test_boundary_case_indicator_at_edge_of_detection_window(self):
        """
        Test edge case where working indicator is right at the boundary
        of the detection window
        """
        analyzer = SessionStateAnalyzer()
        
        # Create content where line 10 from bottom has indicator (edge of proposed window)
        lines = []
        for i in range(30):
            if i == 19:  # This will be line 11 from bottom (just outside 10-line window)
                lines.append("· Processing... (esc to interrupt)")
            else:
                lines.append(f"Line {i+1}")
        
        # Add prompt at the end
        lines.extend([
            "",
            "user@host:~/project$ "
        ])
        
        screen_content = "\n".join(lines)
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen_content):
            with patch.object(analyzer, 'get_screen_content', return_value=screen_content):
                state = analyzer.get_state("test_session")
            
            # With improved logic (10-line window), should be IDLE
            # The indicator at line 11 from bottom should be ignored
            assert state == SessionState.IDLE, \
                "Working indicator outside detection window should be ignored"


class TestRegressionPrevention:
    """Ensure the fix doesn't break existing functionality"""
    
    def test_genuine_working_state_still_detected(self):
        """
        Verify that genuine working states are still properly detected
        after the fix
        """
        analyzer = SessionStateAnalyzer()
        
        test_cases = [
            # (screen_content, expected_state, description)
            ("Running tests... (esc to interrupt)\n", SessionState.WORKING, "Simple running state"),
            ("Building project...\n(esc to interrupt)", SessionState.WORKING, "Building state"),
            ("Installing packages... ctrl+b to run in background", SessionState.WORKING, "Installing state"),
            ("Compiling... Processing... Analyzing...", SessionState.WORKING, "Multiple indicators"),
        ]
        
        for content, expected, desc in test_cases:
            with patch.object(analyzer, 'get_current_screen_only', return_value=content):
                with patch.object(analyzer, 'get_screen_content', return_value=content):
                    state = analyzer.get_state("test_session")
                    assert state == expected, f"Failed: {desc} - Expected {expected}, got {state}"
    
    def test_transition_from_working_to_idle_still_triggers_notification(self):
        """
        Verify that the transition from WORKING to IDLE still triggers
        notifications correctly
        """
        from claude_ops.monitoring.multi_monitor import MultiSessionMonitor
        
        monitor = MultiSessionMonitor()
        session = "test_session"
        
        # Initialize session state
        monitor.last_state[session] = SessionState.WORKING
        monitor.notification_sent[session] = False
        monitor.last_notification_time[session] = 0
        
        # Mock the state analyzer to return IDLE (work completed)
        with patch.object(monitor.state_analyzer, 'get_state', return_value=SessionState.IDLE):
            with patch.object(monitor.state_analyzer, 'get_current_screen_only', return_value="user@host$ "):
                should_notify = monitor.should_send_completion_notification(session)
                
                # Should trigger notification for WORKING -> IDLE transition
                assert should_notify == True, \
                    "WORKING to IDLE transition should still trigger notification"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])