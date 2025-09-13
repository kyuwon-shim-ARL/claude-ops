"""
Integration Test: False Positive Fix

This test demonstrates that the false positive issue reported by the user
has been resolved. It shows the before/after behavior of the fix.
"""

import pytest
from claude_ops.utils.session_state import SessionStateAnalyzer


def test_reported_false_positive_scenario():
    """
    Integration test for the exact false positive scenario reported by user.
    
    User reported: "오탐지인 경우 esc to interrupt 인 경우 찾음"
    This means false positives occurred when "esc to interrupt" was detected
    but Claude was actually idle at a prompt.
    """
    
    analyzer = SessionStateAnalyzer()
    
    # This is the problematic scenario from the analysis document:
    # Old "esc to interrupt" text remains on screen but Claude is at prompt
    problematic_screen = """
✻ Elucidating… (esc to interrupt)
─────────────────────────────────
 >
    """
    
    # BEFORE FIX: This would return True (false positive)
    # AFTER FIX: Should return False (correct detection)
    is_working = analyzer._detect_working_state(problematic_screen)
    
    # Should NOT be detected as working because we're at a prompt
    assert is_working == False, "False positive: detected working when at prompt"
    
    # Verify the fix works with variations
    test_cases = [
        # Multiple old patterns with current prompt
        ("First (esc to interrupt)\nSecond esc to interrupt\n >", False),
        
        # Different prompt styles with old patterns  
        ("Old (esc to interrupt)\nuser@host$ ", False),
        ("Work (esc to interrupt)\n>>> ", False),
        ("Task (esc to interrupt)\n│ >", False),
        
        # Still detects genuine working state
        ("Currently working (esc to interrupt)", True),
        ("✻ Processing… (esc to interrupt)", True),
    ]
    
    for screen_content, expected_working in test_cases:
        actual_working = analyzer._detect_working_state(screen_content)
        assert actual_working == expected_working, f"Failed for: {repr(screen_content)}"


def test_fix_improves_detection_accuracy():
    """
    Test that the fix improves overall detection accuracy by reducing false positives
    while maintaining true positive detection.
    """
    
    analyzer = SessionStateAnalyzer()
    
    # Cases that should NOT be detected as working (were false positives before)
    false_positive_cases = [
        "Old task (esc to interrupt)\n─────\n>",
        "Previous work esc to interrupt\n\n >", 
        "Completed (esc to interrupt)\nuser@host$ ",
        "✻ Done… (esc to interrupt)\n>>> ",
    ]
    
    # Cases that should STILL be detected as working (true positives)
    # NOTE: Conservative mode only detects "esc to interrupt"
    true_positive_cases = [
        "Currently running (esc to interrupt)",
        "✻ Analyzing… (esc to interrupt)",
        "Processing data esc to interrupt\nWorking...",
        # "Running…",  # Not detected in conservative mode (by design)
    ]
    
    # Verify false positives are eliminated
    false_positive_count = 0
    for case in false_positive_cases:
        if analyzer._detect_working_state(case):
            false_positive_count += 1
            
    assert false_positive_count == 0, f"Still has {false_positive_count} false positives"
    
    # Verify true positives are maintained  
    true_positive_count = 0
    for case in true_positive_cases:
        if analyzer._detect_working_state(case):
            true_positive_count += 1
            
    expected_true_positives = len(true_positive_cases)
    assert true_positive_count == expected_true_positives, f"Lost true positives: {true_positive_count}/{expected_true_positives}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])