"""
Test edge cases for prompt detection logic

Tests scenarios where prompt-like patterns appear in content
but are not actual prompts.
"""

import pytest
from unittest.mock import patch
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState


class TestPromptDetectionEdgeCases:
    """Test cases for distinguishing real prompts from prompt-like text"""
    
    def test_user_typing_with_dollar_sign(self):
        """Test when user is typing text that contains '$ ' """
        analyzer = SessionStateAnalyzer()
        
        # User typing a command explanation
        screen = """
Running build process...
(esc to interrupt)

To fix this issue, run: git reset --hard HEAD~1
Then use: $ git push --force-with-lease
Still building..."""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Should still be WORKING despite '$ ' in content
                # Because "esc to interrupt" is present
                assert state == SessionState.WORKING, \
                    "Should detect as WORKING when 'esc to interrupt' is present"
    
    def test_code_example_with_prompts(self):
        """Test when showing code examples with prompt symbols"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Generating documentation...
(esc to interrupt)

## Usage Examples:
```bash
$ npm install
$ npm run dev
> Ready on http://localhost:3000
```
Still generating..."""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Should be WORKING because generation is ongoing
                assert state == SessionState.WORKING, \
                    "Code examples should not override working detection"
    
    def test_real_prompt_at_line_end(self):
        """Test detection of real prompt that ends a line"""
        analyzer = SessionStateAnalyzer()
        
        # Real prompt - line ends with prompt pattern
        screen = """
Build complete.
All tests passed.

user@host:~/project$ """
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Should be IDLE at real prompt
                assert state == SessionState.IDLE, \
                    "Real prompt at line end should be IDLE"
    
    def test_prompt_in_middle_of_line(self):
        """Test prompt pattern in middle of line (not real prompt)"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Processing files...
(esc to interrupt)

The command $ ls -la shows all files
Processing continues..."""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Should be WORKING - '$ ' in middle of line isn't a prompt
                assert state == SessionState.WORKING, \
                    "Prompt pattern in middle of line should not affect working state"
    
    def test_claude_code_edit_prompt_structure(self):
        """Test Claude Code's specific edit prompt structure"""
        analyzer = SessionStateAnalyzer()
        
        # Claude's edit prompt has specific box structure
        screen = """
Changes to be made:
- Update function
- Fix import

╭─────────────────────────────────────────────╮
│ >                                           │
╰─────────────────────────────────────────────╯
  ⏵⏵ accept edits on (shift+tab to cycle)"""
        
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Claude edit prompt should be WAITING_INPUT or IDLE
                assert state in [SessionState.IDLE, SessionState.WAITING_INPUT], \
                    "Claude edit prompt should not be WORKING"
    
    def test_multiline_command_input(self):
        """Test multiline command being typed"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
user@host:~/project$ docker run \\
  --name myapp \\
  -p 3000:3000 \\
  -v $(pwd):/app \\"""
        
        # User is in the middle of typing a multiline command
        with patch.object(analyzer, 'get_current_screen_only', return_value=screen):
            with patch.object(analyzer, 'get_screen_content', return_value=screen):
                state = analyzer.get_state("test_session")
                
                # Should be IDLE - user is at prompt typing
                assert state == SessionState.IDLE, \
                    "Multiline command input should be IDLE"


class TestImprovedPromptDetection:
    """Test improved prompt detection logic"""
    
    def test_prompt_must_be_at_line_end(self):
        """Verify that prompts are only detected at line ends"""
        
        test_cases = [
            # (line, should_be_prompt)
            ("user@host$ ", True),           # Real prompt
            ("user@host$ command", False),   # Command after prompt
            ("Run $ command", False),        # Dollar in middle
            ("> ", True),                    # Simple prompt
            ("Output > file", False),        # Greater-than in middle
            (">>> ", True),                  # Python prompt
            ("│ >", True),                   # Claude prompt (special case)
            ("│ > some text", False),        # Claude prompt with text
        ]
        
        for line, expected in test_cases:
            # This is what improved logic should do
            is_prompt = (
                line.endswith('$ ') or
                line.endswith('> ') or
                line.endswith('❯ ') or
                line == '>>>' or
                line == '>>> ' or
                line == '│ >' or  # Claude's special case
                line.endswith(']: ')  # IPython
            )
            
            assert is_prompt == expected, \
                f"Line '{line}' - Expected prompt={expected}, got {is_prompt}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])