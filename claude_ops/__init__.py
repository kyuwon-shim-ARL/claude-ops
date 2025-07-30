"""
Claude-Ops: Integrated Notion-Git-Claude-Telegram Workflow System

A comprehensive system that integrates:
- Notion task management
- Git branch management  
- Claude Code automation
- Telegram monitoring and control

This package provides a unified interface for research and development workflows.

Usage:
    # CLI
    claude-ops telegram start
    claude-ops notion task-start TID
    claude-ops workflow init
    
    # Programmatic  
    from claude_ops import TelegramBridge, WorkflowManager
    bridge = TelegramBridge()
    workflow = WorkflowManager()
"""

__version__ = "1.0.0"
__author__ = "Claude-Ops Team"
__description__ = "Integrated Notion-Git-Claude-Telegram workflow system"
__url__ = "https://github.com/kyuwon-shim-ARL/claude-ops"

# Import main components
from .telegram import TelegramBridge, TelegramMonitor, SmartNotifier
from .notion import WorkflowManager, TaskManager
from .config import ClaudeOpsConfig

__all__ = [
    "TelegramBridge",
    "TelegramMonitor", 
    "SmartNotifier",
    "WorkflowManager",
    "TaskManager",
    "ClaudeOpsConfig",
    "__version__",
    "__author__",
    "__description__",
]