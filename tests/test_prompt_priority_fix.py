"""
Test suite for prompt detection priority fix
Tests that working indicators should have priority over prompt detection
"""

import pytest
from unittest.mock import patch
from claude_ops.utils.session_state import SessionStateAnalyzer, SessionState


class TestPromptPriorityFix:
    """Test cases to ensure working patterns have priority over prompts"""
    
    def test_working_indicator_overrides_prompt(self):
        """Working indicators should always override prompt detection"""
        analyzer = SessionStateAnalyzer()
        
        # Screen with both prompt AND working indicator
        screen = """
Running tests...
(esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        # Should detect as WORKING, not IDLE
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Working indicator should override prompt"
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen):
            state = analyzer.get_state("test_session")
            assert state == SessionState.WORKING, "State should be WORKING when indicators present"
    
    def test_building_with_prompt_visible(self):
        """Building process should be detected even with prompt"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Building project...
[████████████░░░░░░░] 60%
(esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Building should be detected as working"
    
    def test_running_command_with_prompt(self):
        """Running commands should be detected with prompt visible"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
$ npm install
added 234 packages in 12s
(Running… esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "'Running…' indicator should mean working"
    
    def test_spinner_with_prompt(self):
        """Spinner characters should indicate working despite prompt"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
⠋ Processing files...

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Spinner should indicate working state"
    
    def test_analyzing_with_prompt(self):
        """Analyzing indicator should work with prompt"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Analyzing codebase...
Found 15 issues
(esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Analyzing should be detected as working"
    
    def test_idle_with_prompt_only(self):
        """Prompt alone without indicators should be IDLE"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Task completed successfully.

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert not is_working, "No working indicators means idle"
    
    def test_old_boxed_prompt_with_working(self):
        """Old boxed prompt format with working indicator"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Running tests...
(esc to interrupt)

╭─────────────────────────────────────────────╮
│ >                                           │
╰─────────────────────────────────────────────╯"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Old format with working indicator should be WORKING"
    
    def test_priority_order_verification(self):
        """Verify that working patterns are checked before prompts"""
        analyzer = SessionStateAnalyzer()
        
        # Multiple working indicators with prompt
        screen = """
Building... 
Testing...
Installing...
Downloading...
(esc to interrupt)
(ctrl+b to run in background)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Multiple working indicators should definitely be WORKING"
    
    def test_edge_case_prompt_in_output(self):
        """Prompt character in output shouldn't affect working detection"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
Processing command: echo "use > for redirect"
(esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Working indicator present, should be WORKING"
    
    def test_git_operations_with_prompt(self):
        """Git operations commonly show prompt while working"""
        analyzer = SessionStateAnalyzer()
        
        screen = """
$ git push origin main
Enumerating objects: 45, done.
Counting objects: 100% (45/45), done.
Writing objects: 71% (32/45)
(Running… esc to interrupt)

───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        is_working = analyzer._detect_working_state(screen)
        assert is_working, "Git push in progress should be WORKING"


class TestStateDetectionPriority:
    """Test the complete state detection with proper priorities"""
    
    def test_state_priority_hierarchy(self):
        """Verify ERROR > WAITING_INPUT > WORKING > IDLE priority"""
        analyzer = SessionStateAnalyzer()
        
        # Case 1: Error overrides everything
        screen_error_and_working = """
Error: Build failed
(esc to interrupt)
───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen_error_and_working):
            state = analyzer.get_state("test")
            assert state == SessionState.ERROR, "ERROR should have highest priority"
        
        # Case 2: WAITING_INPUT overrides WORKING
        screen_waiting_and_working = """
Do you want to proceed?
Building...
───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen_waiting_and_working):
            # Clear cache to avoid interference from previous test
            analyzer.clear_cache()
            state = analyzer.get_state("test", use_cache=False)
            assert state == SessionState.WAITING_INPUT, "WAITING_INPUT should override WORKING"
        
        # Case 3: WORKING overrides IDLE (prompt)
        screen_working_and_prompt = """
Building project...
(esc to interrupt)
───────────────────────────────────────────────
 > 
───────────────────────────────────────────────"""
        
        with patch.object(analyzer, 'get_screen_content', return_value=screen_working_and_prompt):
            state = analyzer.get_state("test")
            assert state == SessionState.WORKING, "WORKING should override prompt (IDLE)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])