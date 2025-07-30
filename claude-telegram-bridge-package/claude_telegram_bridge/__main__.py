"""
Main entry point for claude-telegram-bridge package
"""

import sys
import logging
import argparse
import subprocess
import signal
import os
from typing import Optional

logger = logging.getLogger(__name__)


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, cleaning up...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import telegram
        import dotenv
        import requests
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Install with: pip install claude-telegram-bridge")
        return False


def create_default_env():
    """Create a default .env file if none exists"""
    if os.path.exists('.env'):
        print("✅ .env file already exists")
        return
        
    template = """# Claude-Telegram Bridge Configuration

# Required Settings
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=123456789,987654321

# Optional Settings  
TELEGRAM_CHAT_ID=your_chat_id_here
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3
LOG_LEVEL=INFO

# Instructions:
# 1. Get bot token from @BotFather on Telegram
# 2. Get your user ID by messaging the bot and checking:
#    https://api.telegram.org/bot<TOKEN>/getUpdates
# 3. Replace the values above with your actual credentials
"""
    
    with open('.env', 'w') as f:
        f.write(template)
    
    print("📝 Created .env template file")
    print("⚠️  Please edit .env with your actual Telegram credentials")


def start_both(background: bool = False) -> Optional[int]:
    """Start both bot and monitor"""
    if not check_dependencies():
        return 1
    
    try:
        from .monitor import main as monitor_main
        from .telegram_bot import main as bot_main
        
        print("🚀 Starting Claude-Telegram Bridge...")
        
        if background:
            # Start monitor in background
            monitor_process = subprocess.Popen([
                sys.executable, "-m", "claude_telegram_bridge", "monitor"
            ])
            print(f"👁️  Monitor started in background (PID: {monitor_process.pid})")
            
            # Start bot in foreground
            print("🤖 Starting Telegram Bot...")
            try:
                bot_main()
            finally:
                # Clean up monitor when bot exits
                try:
                    monitor_process.terminate()
                    monitor_process.wait(timeout=5)
                except (subprocess.TimeoutExpired, ProcessLookupError):
                    monitor_process.kill()
        else:
            # Start both in foreground (for development)
            import threading
            
            def run_monitor():
                monitor_main()
            
            monitor_thread = threading.Thread(target=run_monitor, daemon=True)
            monitor_thread.start()
            
            print("👁️  Monitor started")
            print("🤖 Starting Telegram Bot...")
            bot_main()
            
    except KeyboardInterrupt:
        print("\n⛔ Shutdown requested")
        return 0
    except Exception as e:
        logger.error(f"Error starting bridge: {str(e)}")
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog="claude-bridge",
        description="Claude-Telegram Bridge - Connect Claude Code with Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  claude-bridge start           # Start bot + monitor
  claude-bridge bot             # Start only bot
  claude-bridge monitor         # Start only monitor
  claude-bridge config          # Show configuration
  
Environment:
  Create a .env file with:
  TELEGRAM_BOT_TOKEN=your_token
  ALLOWED_USER_IDS=your_user_id
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "bot", "monitor", "config", "init"],
        help="Command to run (default: start)"
    )
    
    parser.add_argument(
        "--background", "-b",
        action="store_true",
        help="Run monitor in background when using 'start'"
    )
    
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="claude-telegram-bridge 1.0.0"
    )
    
    args = parser.parse_args()
    
    setup_signal_handlers()
    
    # Handle init command
    if args.command == "init":
        create_default_env()
        return 0
    
    if not check_dependencies():
        return 1
    
    try:
        if args.command == "start":
            return start_both(background=args.background) or 0
            
        elif args.command == "bot":
            from .telegram_bot import main as bot_main
            print("🤖 Starting Telegram Bot...")
            bot_main()
            
        elif args.command == "monitor":
            from .monitor import main as monitor_main
            print("👁️  Starting Claude Monitor...")
            monitor_main()
            
        elif args.command == "config":
            from .config import BridgeConfig
            try:
                config = BridgeConfig()
                print("✅ Configuration loaded successfully")
                print(f"📁 Working Directory: {config.working_directory}")
                print(f"🎯 Session Name: {config.session_name}")
                print(f"⏱️  Check Interval: {config.check_interval}s")
                print(f"👥 Allowed Users: {len(config.allowed_user_ids)} configured")
                print(f"🤖 Bot Token: {'✅ Set' if config.telegram_bot_token else '❌ Missing'}")
                print(f"💬 Chat ID: {'✅ Set' if config.telegram_chat_id else '🔍 Auto-detect'}")
            except Exception as e:
                print(f"❌ Configuration error: {e}")
                print("💡 Run 'claude-bridge init' to create a template .env file")
                return 1
                
    except KeyboardInterrupt:
        print("\n⛔ Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())