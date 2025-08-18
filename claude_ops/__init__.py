"""
Claude-Ops: Telegram-Claude Bridge System

A streamlined system that integrates:
- Claude Code session management
- Telegram monitoring and control
- Session state detection
- Smart notifications

This package provides a unified interface for Claude development workflows via Telegram.

Usage:
    # Direct execution
    python -m claude_ops.telegram.bot
    
    # Programmatic  
    from claude_ops import TelegramBridge, SmartNotifier
    bridge = TelegramBridge()
    notifier = SmartNotifier()
"""

__version__ = "2.0.0"
__author__ = "Claude-Ops Team"
__description__ = "Telegram-Claude Bridge System"
__url__ = "https://github.com/kyuwon-shim-ARL/claude-ops"

# Import main components
from .telegram import TelegramBridge, TelegramMonitor, SmartNotifier
from .config import ClaudeOpsConfig
from .session_manager import SessionManager, session_manager

__all__ = [
    "TelegramBridge",
    "TelegramMonitor", 
    "SmartNotifier",
    "ClaudeOpsConfig",
    "SessionManager",
    "session_manager",
    "__version__",
    "__author__",
    "__description__",
]