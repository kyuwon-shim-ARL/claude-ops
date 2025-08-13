"""
Utility modules for Claude-Ops

Shared functionality across different components to ensure consistency
and prevent code duplication.
"""

from .working_detector import working_detector, is_session_working, get_session_working_info

__all__ = [
    'working_detector',
    'is_session_working', 
    'get_session_working_info'
]