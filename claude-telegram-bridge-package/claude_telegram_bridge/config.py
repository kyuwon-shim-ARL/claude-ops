"""
Configuration management for Claude-Telegram Bridge

Handles environment variables, validation, and default settings.
"""

import os
import logging
from typing import List, Optional
from dotenv import load_dotenv


class BridgeConfig:
    """Configuration manager for Claude-Telegram Bridge"""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration
        
        Args:
            env_file: Path to .env file (default: looks for .env in current directory)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
            
        self._validate_required_vars()
        self._setup_logging()
    
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
        """Current working directory"""
        return os.getcwd()
    
    @property
    def session_name(self) -> str:
        """Dynamic session name based on current directory"""
        dir_name = os.path.basename(self.working_directory)
        return f"{self.tmux_session_prefix}_{dir_name}"
    
    @property
    def status_file(self) -> str:
        """Path to status file"""
        return f"/tmp/claude_work_status_{os.path.basename(self.working_directory)}"
    
    def _validate_required_vars(self) -> None:
        """Validate required environment variables"""
        required_vars = [
            ("TELEGRAM_BOT_TOKEN", self.telegram_bot_token),
            ("ALLOWED_USER_IDS", self.allowed_user_ids)
        ]
        
        missing_vars = []
        for var_name, var_value in required_vars:
            if not var_value:
                missing_vars.append(var_name)
        
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                f"Please set them in your .env file or environment."
            )
    
    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def get_env_template(self) -> str:
        """Return .env template content"""
        return """# Claude-Telegram Bridge Configuration

# Telegram Bot Settings (Required)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=123456789,987654321

# Session Settings (Optional)
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3

# Logging (Optional)  
LOG_LEVEL=INFO

# Example:
# TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
# TELEGRAM_CHAT_ID=123456789
# ALLOWED_USER_IDS=985052105
"""