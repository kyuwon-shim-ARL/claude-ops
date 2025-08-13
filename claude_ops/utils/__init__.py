"""
Utility modules for Claude-Ops

Shared functionality across different components to ensure consistency
and prevent code duplication.
"""

# Import from the new unified session state module
from .session_state import (
    SessionStateAnalyzer,
    SessionState,
    StateTransition,
    session_state_analyzer,
    is_session_working,
    get_session_working_info
)

# Backward compatibility - redirect old imports to new module
from .session_state import session_state_analyzer as working_detector

__all__ = [
    # New unified interface
    'SessionStateAnalyzer',
    'SessionState', 
    'StateTransition',
    'session_state_analyzer',
    
    # Legacy compatibility
    'working_detector',
    'is_session_working',
    'get_session_working_info'
]