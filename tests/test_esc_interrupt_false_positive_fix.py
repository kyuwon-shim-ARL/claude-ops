"""
Test Fix for "esc to interrupt" False Positive Detection

This test suite verifies that the fix for false positive detection works correctly,
specifically addressing the issue where "esc to interrupt" text remains on screen
from previous operations but Claude is actually at a prompt (not working).
"""

import pytest
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState


class TestEscInterruptFalsePositiveFix:
    """Test suite for false positive fix"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.analyzer = SessionStateAnalyzer()
    
    def test_prompt_overrides_esc_interrupt_pattern(self):
        """
        Test that prompt detection overrides "esc to interrupt" pattern.
        This is the core fix for false positives.
        """
        # Screen with old "esc to interrupt" text but currently at prompt
        screen_content = """
Previous output with working indicator
✻ Elucidating… (esc to interrupt)
Some other content
──────────────
>
        """
        
        # Should NOT detect as working because we're at a prompt
        assert not self.analyzer._detect_working_state(screen_content)
    
    def test_multiple_esc_interrupt_with_prompt(self):
        """
        Test that multiple "esc to interrupt" patterns are still overridden by prompt
        """
        screen_content = """
First task (esc to interrupt)
Second task with esc to interrupt pattern
✻ Processing… (esc to interrupt)
Another line with the pattern
──────────────
 >
        """
        
        # Should NOT detect as working despite multiple patterns
        assert not self.analyzer._detect_working_state(screen_content)
    
    def test_esc_interrupt_still_detected_without_prompt(self):
        """
        Test that "esc to interrupt" is still detected when there's no prompt
        """
        screen_content = """
Some output
✻ Currently working… (esc to interrupt)
More output
        """
        
        # Should detect as working when no prompt is present
        assert self.analyzer._detect_working_state(screen_content)
    
    def test_different_prompt_types_override_esc_interrupt(self):
        """
        Test that various prompt types override "esc to interrupt"
        """
        test_cases = [
            # Claude's edit prompt
            ("Old text (esc to interrupt)\n>", False),
            # Boxed prompt
            ("Text with esc to interrupt\n│ >", False),
            # Bash prompt
            ("esc to interrupt text\nuser@host:~/dir$ ", False),
            # Zsh prompt
            ("Working (esc to interrupt)\nuser@host ~/dir ❯ ", False),
            # Python prompt
            ("Code (esc to interrupt)\n>>> ", False),
        ]
        
        for screen_content, expected_working in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result == expected_working, f"Failed for: {repr(screen_content)}"
    
    def test_real_working_state_not_affected(self):
        """
        Test that genuine working states are still detected correctly
        NOTE: Conservative mode only detects "esc to interrupt" patterns
        """
        test_cases = [
            # Currently working without prompt - ONLY esc to interrupt is detected
            ("Running tests… (esc to interrupt)\nTest output", True),
            ("✻ Thinking… (esc to interrupt)", True),
            # Conservative mode: these are NOT detected (by design)
            ("Building project (ctrl+b to run in background)", False),
            ("Running tests...", False),
        ]
        
        for screen_content, expected in test_cases:
            result = self.analyzer._detect_working_state(screen_content)
            assert result == expected, f"Unexpected result for: {repr(screen_content)}"
    
    def test_edge_case_prompt_with_esc_interrupt_in_same_line(self):
        """
        Test edge case where prompt and esc interrupt might be on same line
        """
        # This should be treated as a prompt (not working)
        screen_content = "Previous (esc to interrupt) >"
        assert not self.analyzer._detect_working_state(screen_content)
    
    def test_empty_lines_dont_interfere(self):
        """
        Test that empty lines don't interfere with prompt detection
        """
        screen_content = """
Old output (esc to interrupt)


>

        """
        assert not self.analyzer._detect_working_state(screen_content)
    
    def test_case_sensitivity(self):
        """
        Test that pattern matching is case sensitive
        """
        # Different case should not match
        screen_content = "ESC TO INTERRUPT\n>"
        assert not self.analyzer._detect_working_state(screen_content)
        
        # Exact case should match when no prompt
        screen_content = "esc to interrupt"
        assert self.analyzer._detect_working_state(screen_content)
    
    def test_fix_resolves_reported_scenario(self):
        """
        Test the exact scenario reported in the analysis document
        """
        # This is the problematic screen from the analysis
        screen_content = """
✻ Elucidating… (esc to interrupt)
─────────────────────────────────
 >
        """
        
        # Before fix: would return True (false positive)
        # After fix: should return False (correct)
        assert not self.analyzer._detect_working_state(screen_content)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])