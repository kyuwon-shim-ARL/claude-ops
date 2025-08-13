"""
Unified Working State Detection Utility

This module provides a single source of truth for detecting Claude Code working states
across all components (monitor, notifier, etc.) to prevent logic duplication and 
inconsistencies.

## Design Principles:
- Single Responsibility: Only working state detection
- DRY: One implementation used everywhere  
- Extensible: Easy to add new patterns
- Testable: Clear interface for unit testing
"""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WorkingStateDetector:
    """Unified working state detection for Claude Code sessions"""
    
    def __init__(self):
        """Initialize the working state detector with pattern definitions"""
        # Patterns that indicate active work in progress
        self.working_patterns = [
            "esc to interrupt",           # Standard working indicator
            "Running…",                   # Background task execution
            "ctrl+b to run in background", # Background task hint
            "tokens · esc to interrupt)", # Token counting with interrupt
        ]
        
        # Patterns that indicate work is complete despite working indicators
        self.finished_patterns = [
            "accept edits",       # Edit completion state
            "Spelunking…",        # File exploration complete  
            "Forging…",           # Tool execution complete
            "Envisioning…",       # Planning complete
            "⏵⏵ accept",         # General completion prompt
        ]
    
    def is_working(self, session_name: str) -> bool:
        """
        Determine if Claude is currently working in the given session
        
        Args:
            session_name: Name of the tmux session to check
            
        Returns:
            True if work is in progress, False if idle or complete
        """
        try:
            screen_content = self._get_screen_content(session_name)
            if not screen_content:
                return False
                
            return self._analyze_working_state(screen_content)
            
        except Exception as e:
            logger.debug(f"Failed to detect working state for {session_name}: {e}")
            return False
    
    def _get_screen_content(self, session_name: str) -> Optional[str]:
        """Get current screen content from tmux session"""
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return result.stdout
            return None
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout getting screen content for {session_name}")
            return None
        except Exception as e:
            logger.warning(f"Error getting screen content for {session_name}: {e}")
            return None
    
    def _analyze_working_state(self, screen_content: str) -> bool:
        """Analyze screen content to determine working state"""
        # Check for any working indicators
        has_working_pattern = any(
            pattern in screen_content for pattern in self.working_patterns
        )
        
        if not has_working_pattern:
            return False
        
        # Check for finished patterns that override working indicators
        has_finished_pattern = any(
            pattern in screen_content for pattern in self.finished_patterns
        )
        
        # If finished patterns are present, work is complete
        if has_finished_pattern:
            return False
            
        # Work is in progress
        return True
    
    def get_working_indicators(self, session_name: str) -> dict:
        """
        Get detailed information about working indicators (for debugging)
        
        Returns:
            Dict with detected patterns and analysis results
        """
        try:
            screen_content = self._get_screen_content(session_name)
            if not screen_content:
                return {"error": "No screen content available"}
            
            found_working = [p for p in self.working_patterns if p in screen_content]
            found_finished = [p for p in self.finished_patterns if p in screen_content]
            
            return {
                "screen_length": len(screen_content),
                "working_patterns_found": found_working,
                "finished_patterns_found": found_finished,
                "final_decision": self._analyze_working_state(screen_content),
                "logic": f"working={bool(found_working)}, finished={bool(found_finished)}, result={not bool(found_finished) if found_working else False}"
            }
            
        except Exception as e:
            return {"error": str(e)}


# Global singleton instance for easy import
working_detector = WorkingStateDetector()


def is_session_working(session_name: str) -> bool:
    """
    Convenience function for checking if a session is working
    
    Args:
        session_name: Name of the tmux session
        
    Returns:
        True if session is working, False otherwise
    """
    return working_detector.is_working(session_name)


def get_session_working_info(session_name: str) -> dict:
    """
    Convenience function for getting detailed working state info
    
    Args:
        session_name: Name of the tmux session
        
    Returns:
        Dict with detailed working state analysis
    """
    return working_detector.get_working_indicators(session_name)