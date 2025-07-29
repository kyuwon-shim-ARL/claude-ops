"""
Main entry point for claude-bridge package
"""

import sys
import logging

logger = logging.getLogger(__name__)


def show_usage():
    """Show usage information"""
    print("""
🤖 Claude-Telegram Bridge

Usage:
  python -m claude_bridge <command>

Commands:
  bot       - Start Telegram bot
  monitor   - Start Claude monitor  
  config    - Show current configuration
  help      - Show this help message

Examples:
  python -m claude_bridge bot       # Start Telegram bot
  python -m claude_bridge monitor   # Start monitoring
  python -m claude_bridge config    # Show configuration
""")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        show_usage()
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "bot":
            from .telegram_bot import main as bot_main
            bot_main()
        elif command == "monitor":
            from .monitor import main as monitor_main
            monitor_main()
        elif command == "config":
            from .config import BridgeConfig
            config = BridgeConfig()
            print(f"Working Directory: {config.working_directory}")
            print(f"Session Name: {config.session_name}")
            print(f"Check Interval: {config.check_interval}s")
            print(f"Allowed Users: {len(config.allowed_user_ids)} configured")
        elif command == "help":
            show_usage()
        else:
            print(f"Unknown command: {command}")
            show_usage()
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()