"""
Test suite for new Claude Code prompt UI format (horizontal lines instead of box)

Tests the detection of the new prompt format with horizontal lines
and ensures backward compatibility with the old boxed format.
"""

import pytest
from unittest.mock import patch
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState


class TestNewPromptUIFormat:
    """Test cases for new horizontal-line prompt format"""
    
    def test_old_boxed_prompt_still_works(self):
        """Ensure old boxed prompt format is still detected correctly"""
        analyzer = SessionStateAnalyzer()
        
        old_format = """
╭─────────────────────────────────────────────╮
│ >                                           │
╰─────────────────────────────────────────────╯
  ⏵⏵ accept edits on (shift+tab to cycle)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=old_format):
            state = analyzer.get_state("test_session")
            assert state == SessionState.IDLE, "Old boxed format should be detected as IDLE"
    
    def test_new_horizontal_line_prompt(self):
        """Test new horizontal line prompt format detection"""
        analyzer = SessionStateAnalyzer()
        
        new_format = """───────────────────────────────────────────────
 > 
───────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=new_format):
            state = analyzer.get_state("test_session")
            assert state == SessionState.IDLE, "New horizontal line format should be detected as IDLE"
    
    def test_single_prompt_character_detection(self):
        """Test that single '>' on its own line is properly detected"""
        analyzer = SessionStateAnalyzer()
        
        # Various formats with single '>'
        test_cases = [
            # Format 1: With leading space
            """ > """,
            # Format 2: No spaces
            """>""",
            # Format 3: With trailing space  
            """> """,
            # Format 4: Multiple spaces before
            """     >""",
        ]
        
        for screen in test_cases:
            is_working = analyzer._detect_working_state(screen)
            assert not is_working, f"Single '>' should not be detected as working: '{screen}'"
    
    def test_prompt_with_working_indicator(self):
        """Test that working indicators override prompt detection"""
        analyzer = SessionStateAnalyzer()
        
        # Even with new prompt format, if there's a working indicator, it's WORKING
        screen_working = """───────────────────────────────────────────────
 > 
───────────────────────────────────────────────
Running tests... (esc to interrupt)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen_working):
            state = analyzer.get_state("test_session")
            assert state == SessionState.WORKING, "Working indicator should override prompt"
    
    def test_horizontal_lines_dont_affect_detection(self):
        """Test that horizontal line characters don't interfere with detection"""
        analyzer = SessionStateAnalyzer()
        
        # Screen with horizontal lines but also working
        screen = """
Building project...
───────────────────────────────
Progress: 50%
───────────────────────────────
(esc to interrupt)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen):
            state = analyzer.get_state("test_session")
            assert state == SessionState.WORKING, "Horizontal lines shouldn't affect working detection"
    
    def test_various_horizontal_line_styles(self):
        """Test different styles of horizontal lines used in UI"""
        analyzer = SessionStateAnalyzer()
        
        line_styles = [
            "─" * 40,  # Light horizontal
            "━" * 40,  # Heavy horizontal
            "═" * 40,  # Double horizontal
            "▔" * 40,  # Upper block
            "▁" * 40,  # Lower block
        ]
        
        for line_style in line_styles:
            screen = f"""
{line_style}
 > 
{line_style}"""
            
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                assert state == SessionState.IDLE, f"Line style '{line_style[0]}' should not affect prompt detection"
    
    def test_prompt_in_text_vs_actual_prompt(self):
        """Distinguish between prompt character in text vs actual prompt"""
        analyzer = SessionStateAnalyzer()
        
        # Text containing '>' but not a prompt
        text_with_arrow = """
Here's how to redirect output:
  command > output.txt
  
Still processing...(esc to interrupt)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=text_with_arrow):
            analyzer.clear_cache("test_session")  # Clear cache
            state = analyzer.get_state("test_session", use_cache=False)
            assert state == SessionState.WORKING, "Arrow in text shouldn't be detected as prompt"
        
        # Actual prompt
        actual_prompt = """
Command completed.

 > """
        
        with patch.object(analyzer, 'get_screen_content', return_value=actual_prompt):
            analyzer.clear_cache("test_session")  # Clear cache
            state = analyzer.get_state("test_session", use_cache=False)
            assert state == SessionState.IDLE, "Actual prompt should be detected"
    
    def test_prompt_transition_detection(self):
        """Test detection during transition from working to prompt"""
        analyzer = SessionStateAnalyzer()
        
        # Just finished working, prompt appears
        transition_screen = """
✓ All tests passed (133/133)
✓ Mock usage: 27.3% (under 35% limit)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=transition_screen):
            state = analyzer.get_state("test_session")
            assert state == SessionState.IDLE, "Should detect IDLE after work completes"
    
    def test_multiline_prompt_area(self):
        """Test prompts that span multiple lines"""
        analyzer = SessionStateAnalyzer()
        
        multiline_prompt = """
───────────────────────────────────────────────
 
 > Type your message here
 
───────────────────────────────────────────────"""
        
        # Should still detect the prompt
        is_working = analyzer._detect_working_state(multiline_prompt)
        assert not is_working, "Multiline prompt area should not be detected as working"
    
    def test_empty_prompt_area(self):
        """Test empty prompt area (no '>' yet)"""
        analyzer = SessionStateAnalyzer()
        
        empty_prompt = """
───────────────────────────────────────────────
 
───────────────────────────────────────────────
  ⏵⏵ type to start"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=empty_prompt):
            state = analyzer.get_state("test_session")
            # Empty prompt area should be IDLE
            assert state == SessionState.IDLE, "Empty prompt area should be IDLE"


class TestBackwardCompatibility:
    """Ensure all prompt formats work correctly together"""
    
    def test_all_prompt_formats_detected(self):
        """Test that all known prompt formats are detected correctly"""
        analyzer = SessionStateAnalyzer()
        
        prompt_formats = [
            # Old boxed format
            """
╭─────────────────────────────────────────────╮
│ >                                           │
╰─────────────────────────────────────────────╯""",
            # New horizontal line format
            """
───────────────────────────────────────────────
 > 
───────────────────────────────────────────────""",
            # Simple prompt
            """> """,
            # Bash prompt
            """user@host:~/project$ """,
            # Python prompt
            """>>> """,
        ]
        
        for prompt in prompt_formats:
            with patch.object(analyzer, 'get_screen_content', return_value=prompt):
                state = analyzer.get_state("test_session")
                assert state in [SessionState.IDLE, SessionState.WAITING_INPUT], \
                    f"Prompt format not detected correctly:\n{prompt}"
    
    def test_format_changes_during_session(self):
        """Test handling when prompt format changes during a session"""
        analyzer = SessionStateAnalyzer()
        
        # Simulate format change from old to new
        screens = [
            # Start with old format
            """
╭─────────────────────────────────────────────╮
│ >                                           │
╰─────────────────────────────────────────────╯""",
            # Change to new format
            """
───────────────────────────────────────────────
 > 
───────────────────────────────────────────────""",
        ]
        
        for screen in screens:
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                assert state == SessionState.IDLE, "Format changes should be handled gracefully"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])