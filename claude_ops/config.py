"""
Unified Configuration Management for Claude-Ops

Handles environment variables, validation, and settings for:
- Telegram Bridge
- Session Management
- Claude Code automation
"""

import os
import logging
from typing import List, Optional
from dotenv import load_dotenv


class ClaudeOpsConfig:
    """Unified configuration manager for Claude-Ops system"""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize unified configuration
        
        Args:
            env_file: Path to .env file (default: looks for .env in current directory)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
            
        self._validate_required_vars()
        self._setup_logging()
    
    # Telegram Configuration
    @property
    def telegram_bot_token(self) -> str:
        """Telegram bot token"""
        return os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    @property
    def telegram_chat_id(self) -> str:
        """Telegram chat ID for notifications"""
        return os.getenv("TELEGRAM_CHAT_ID", "")
    
    @property
    def allowed_user_ids(self) -> List[int]:
        """List of allowed Telegram user IDs"""
        ids_str = os.getenv("ALLOWED_USER_IDS", "")
        if not ids_str:
            return []
        return [int(id.strip()) for id in ids_str.split(",") if id.strip()]
    
    
    # System Configuration
    @property
    def tmux_session_prefix(self) -> str:
        """Prefix for tmux session names"""
        return os.getenv("TMUX_SESSION_PREFIX", "claude")
    
    @property
    def check_interval(self) -> int:
        """Monitoring check interval in seconds"""
        return int(os.getenv("CHECK_INTERVAL", "3"))
    
    @property
    def working_directory(self) -> str:
        """Working directory for Claude sessions"""
        # Allow override via environment variable
        custom_dir = os.getenv("CLAUDE_WORKING_DIR")
        if custom_dir and os.path.exists(custom_dir):
            return custom_dir
        return os.getcwd()
    
    @property
    def session_name(self) -> str:
        """Get currently active session name from session manager"""
        try:
            from .session_manager import session_manager
            return session_manager.get_active_session()
        except ImportError:
            # Fallback to directory-based session name
            dir_name = os.path.basename(self.working_directory)
            return f"{self.tmux_session_prefix}_{dir_name}"
    
    @property
    def status_file(self) -> str:
        """Get status file for currently active session"""
        try:
            from .session_manager import session_manager
            active_session = session_manager.get_active_session()
            return session_manager.get_status_file_for_session(active_session)
        except ImportError:
            # Fallback to directory-based status file
            dir_name = os.path.basename(self.working_directory)
            return f"/tmp/claude_work_status_{dir_name}"
    
    def _validate_required_vars(self) -> None:
        """Validate required environment variables based on enabled features"""
        # Only validate if features are being used
        pass  # Flexible validation - only check when features are used
    
    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def validate_telegram_config(self) -> bool:
        """Validate telegram-specific configuration"""
        return bool(self.telegram_bot_token and self.allowed_user_ids)
    
    
    def get_env_template(self) -> str:
        """Return complete .env template for all features"""
        return """# Claude-Ops Configuration
# Copy this file to .env and fill in your actual values

# ==============================================
# ESSENTIAL SETTINGS (Required)
# ==============================================

# Telegram Bot Token
# Get this from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Your Telegram Chat ID  
# Get this by messaging your bot and visiting:
# https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
TELEGRAM_CHAT_ID=your_chat_id_here

# Allowed User IDs (comma-separated)
# These users can control the bot
# Find your user ID from the getUpdates response above
ALLOWED_USER_IDS=your_user_id_here

# ==============================================
# OPTIONAL SETTINGS (Defaults work fine)
# ==============================================

# Default working directory for Claude sessions
# If not set, uses current directory
# CLAUDE_WORKING_DIR=/path/to/your/projects

# How often to check Claude status (seconds)
# Default: 3
# CHECK_INTERVAL=3

# Logging level
# Options: DEBUG, INFO, WARNING, ERROR
# Default: INFO
# LOG_LEVEL=INFO
"""


# Backward compatibility alias
BridgeConfig = ClaudeOpsConfig