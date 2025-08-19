"""
Telegram Bridge Module

Provides Telegram bot integration for Claude Code monitoring and control.
"""

from .bot import TelegramBridge
from ..monitoring.monitor import TelegramMonitor  
from .notifier import SmartNotifier

__all__ = [
    "TelegramBridge",
    "TelegramMonitor",
    "SmartNotifier"
]