"""
Claude-Telegram Bridge Package

A modular bridge system for connecting Claude Code with Telegram for monitoring and control.
This package provides real-time notifications, interactive bot controls, and session management.

Components:
- telegram_bot: Main Telegram bot with inline keyboard interface
- monitor: Claude session monitoring and status tracking  
- notifier: Smart notification system with context awareness
- config: Configuration management and environment setup

Installation:
    pip install claude-telegram-bridge

Usage:
    # Command line
    claude-bridge start
    
    # Programmatic
    from claude_telegram_bridge import BridgeConfig, ClaudeTelegramBot
    config = BridgeConfig()
    bot = ClaudeTelegramBot(config)
    bot.run()
"""

__version__ = "1.0.0"
__author__ = "Claude-Ops Team"
__email__ = "noreply@example.com"
__description__ = "A modular bridge system for connecting Claude Code with Telegram"
__url__ = "https://github.com/kyuwon-shim-ARL/claude-ops"

from .config import BridgeConfig
from .telegram_bot import ClaudeTelegramBot
from .monitor import ClaudeMonitor
from .notifier import SmartNotifier

__all__ = [
    "BridgeConfig",
    "ClaudeTelegramBot", 
    "ClaudeMonitor",
    "SmartNotifier",
    "__version__",
    "__author__",
    "__description__",
]