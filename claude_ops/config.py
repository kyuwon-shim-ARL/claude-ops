"""
Unified Configuration Management for Claude-Ops

Handles environment variables, validation, and settings for all components:
- Telegram Bridge
- Notion Workflow
- Git Integration
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
    
    # Notion Configuration
    @property
    def notion_api_key(self) -> str:
        """Notion API key"""
        return os.getenv("NOTION_API_KEY", "")
    
    @property
    def notion_tasks_db_id(self) -> str:
        """Notion Tasks database ID"""
        return os.getenv("NOTION_TASKS_DB_ID", "")
    
    @property
    def notion_projects_db_id(self) -> str:
        """Notion Projects database ID"""
        return os.getenv("NOTION_PROJECTS_DB_ID", "")
    
    @property
    def notion_knowledge_hub_id(self) -> str:
        """Notion Knowledge Hub page ID"""
        return os.getenv("NOTION_KNOWLEDGE_HUB_ID", "")
    
    # GitHub Configuration
    @property
    def github_pat(self) -> str:
        """GitHub Personal Access Token"""
        return os.getenv("GITHUB_PAT", "")
    
    @property
    def github_repo_owner(self) -> str:
        """GitHub repository owner"""
        return os.getenv("GITHUB_REPO_OWNER", "")
    
    @property
    def github_repo_name(self) -> str:
        """GitHub repository name"""
        return os.getenv("GITHUB_REPO_NAME", "")
    
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
    
    def validate_notion_config(self) -> bool:
        """Validate notion-specific configuration"""
        return bool(self.notion_api_key and self.notion_tasks_db_id)
    
    def validate_github_config(self) -> bool:
        """Validate github-specific configuration"""
        return bool(self.github_pat and self.github_repo_owner and self.github_repo_name)
    
    def get_env_template(self) -> str:
        """Return complete .env template for all features"""
        return """# Claude-Ops Unified Configuration

# Telegram Bridge Settings
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=123456789,987654321

# Notion Workflow Settings
NOTION_API_KEY=your_notion_api_key_here
NOTION_TASKS_DB_ID=your_tasks_database_id
NOTION_PROJECTS_DB_ID=your_projects_database_id
NOTION_KNOWLEDGE_HUB_ID=your_knowledge_hub_page_id

# GitHub Integration Settings
GITHUB_PAT=your_github_personal_access_token
GITHUB_REPO_OWNER=your_github_username
GITHUB_REPO_NAME=your_repository_name

# System Settings (Optional)
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3
LOG_LEVEL=INFO

# Instructions:
# 1. Telegram: Get bot token from @BotFather, get user ID from bot messages
# 2. Notion: Create integration at https://www.notion.so/my-integrations
# 3. GitHub: Create PAT at https://github.com/settings/tokens
# 4. Replace all 'your_*_here' values with actual credentials
"""


# Backward compatibility alias
BridgeConfig = ClaudeOpsConfig