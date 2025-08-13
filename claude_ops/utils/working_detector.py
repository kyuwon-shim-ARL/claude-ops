"""
DEPRECATED: Legacy Working State Detection Utility

This module has been replaced by session_state.py for better consistency
and unified state management. Please use the new module instead.

This file is kept for backward compatibility only.
"""

import warnings
import logging

# Issue deprecation warning
warnings.warn(
    "working_detector.py is deprecated. Use claude_ops.utils.session_state instead.",
    DeprecationWarning,
    stacklevel=2
)

logger = logging.getLogger(__name__)

# Import everything from the new unified module
from .session_state import (
    session_state_analyzer,
    is_session_working,
    get_session_working_info
)

# Legacy compatibility - redirect to new implementation
working_detector = session_state_analyzer

# Keep the old interface for backward compatibility
class WorkingStateDetector:
    """
    DEPRECATED: Legacy wrapper around SessionStateAnalyzer
    
    This class is deprecated. Use SessionStateAnalyzer from session_state module instead.
    """
    
    def __init__(self):
        warnings.warn(
            "WorkingStateDetector is deprecated. Use SessionStateAnalyzer instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self._analyzer = session_state_analyzer
        
        # Expose old interface for compatibility
        self.working_patterns = self._analyzer.working_patterns
    
    def is_working(self, session_name: str) -> bool:
        """Legacy method - redirects to SessionStateAnalyzer.is_working()"""
        return self._analyzer.is_working(session_name)
    
    def _get_screen_content(self, session_name: str):
        """Legacy method - redirects to SessionStateAnalyzer.get_screen_content()"""
        return self._analyzer.get_screen_content(session_name)
    
    def _analyze_working_state(self, screen_content: str) -> bool:
        """Legacy method - redirects to SessionStateAnalyzer internal logic"""
        # Create a temporary analyzer to use the private method
        from .session_state import SessionState
        state = self._analyzer.get_state_from_content(screen_content) if hasattr(self._analyzer, 'get_state_from_content') else None
        
        # Fallback to working state check for compatibility
        return self._analyzer._detect_working_state(screen_content) if not self._analyzer._detect_input_waiting(screen_content) else False
    
    def get_working_indicators(self, session_name: str) -> dict:
        """Legacy method - converts new format to old format"""
        details = self._analyzer.get_state_details(session_name)
        
        # Convert to old format for backward compatibility
        return {
            "screen_length": details.get("screen_length", 0),
            "working_patterns_found": details.get("working_patterns_found", []),
            "final_decision": details.get("state") and details["state"].value == "working",
            "logic": details.get("analysis", {}).get("decision_logic", "")
        }


# Create legacy instance (will trigger deprecation warning)
working_detector = WorkingStateDetector()

# The actual working detector is now the session_state_analyzer
# But we keep this for any code that directly imports working_detector