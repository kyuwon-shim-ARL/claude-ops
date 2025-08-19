"""
Hook-based Notification Manager
Integrates Claude Code's built-in hook system with Claude-Ops notifications
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from .config import ClaudeOpsConfig
from .session_manager import session_manager
from .telegram.notifier import SmartNotifier

logger = logging.getLogger(__name__)


class HookManager:
    """Manages Claude Code hook integration for notifications"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.hook_script_path = self._get_hook_script_path()
        
    def _get_hook_script_path(self) -> str:
        """Get path to hook notification script"""
        script_dir = Path(__file__).parent.parent / "scripts"
        return str(script_dir / "hook-notification.sh")
    
    def _get_claude_settings_path(self) -> str:
        """Get path to Claude settings file"""
        # Try common locations for Claude settings
        possible_paths = [
            Path.home() / ".claude-settings.json",
            Path.home() / ".config" / "claude" / "settings.json",
            Path.cwd() / ".claude-settings.json"
        ]
        
        for path in possible_paths:
            if path.exists():
                return str(path)
        
        # Default to home directory
        return str(Path.home() / ".claude-settings.json")
    
    def setup_hooks(self) -> bool:
        """Setup Claude Code hooks for notifications"""
        try:
            settings_path = self._get_claude_settings_path()
            
            # Create hook configuration
            hook_config = {
                "hooks": {
                    "MainAgentStop": [
                        {
                            "command": self.hook_script_path,
                            "matcher": "*",
                            "timeout": 30,
                            "description": "Send notification when Claude finishes main work"
                        }
                    ],
                    "SubagentStop": [
                        {
                            "command": self.hook_script_path,
                            "matcher": "*",
                            "timeout": 30,
                            "description": "Send notification when Task tool completes"
                        }
                    ]
                }
            }
            
            # Check if settings file exists
            if os.path.exists(settings_path):
                # Load existing settings
                with open(settings_path, 'r') as f:
                    existing_settings = json.load(f)
                
                # Merge hook configuration
                if "hooks" in existing_settings:
                    existing_settings["hooks"].update(hook_config["hooks"])
                else:
                    existing_settings["hooks"] = hook_config["hooks"]
                
                hook_config = existing_settings
            
            # Write updated configuration
            with open(settings_path, 'w') as f:
                json.dump(hook_config, f, indent=2)
            
            # Make hook script executable
            os.chmod(self.hook_script_path, 0o755)
            
            logger.info(f"✅ Claude Code hooks configured: {settings_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to setup hooks: {e}")
            return False
    
    def remove_hooks(self) -> bool:
        """Remove Claude Code hook configuration"""
        try:
            settings_path = self._get_claude_settings_path()
            
            if not os.path.exists(settings_path):
                logger.info("No Claude settings file found")
                return True
            
            # Load existing settings
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            
            # Remove hooks section
            if "hooks" in settings:
                del settings["hooks"]
                
                # Write updated configuration
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                
                logger.info("✅ Claude Code hooks removed")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to remove hooks: {e}")
            return False
    
    def test_hook_notification(self, test_data: Optional[Dict[str, Any]] = None) -> bool:
        """Test hook notification system"""
        try:
            # Prepare test data
            if not test_data:
                test_data = {
                    "event": "MainAgentStop",
                    "session": session_manager.get_active_session() or "claude_test",
                    "timestamp": "2025-08-19T22:00:00Z"
                }
            
            # Run hook script with test data
            process = subprocess.Popen(
                [self.hook_script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(
                input=json.dumps(test_data),
                timeout=30
            )
            
            if process.returncode == 0:
                logger.info("✅ Hook notification test successful")
                return True
            else:
                logger.error(f"❌ Hook test failed: {stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Hook test timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Hook test error: {e}")
            return False
    
    def get_hook_status(self) -> Dict[str, Any]:
        """Get current hook configuration status"""
        settings_path = self._get_claude_settings_path()
        
        status = {
            "settings_file": settings_path,
            "settings_exists": os.path.exists(settings_path),
            "hook_script": self.hook_script_path,
            "script_exists": os.path.exists(self.hook_script_path),
            "script_executable": os.access(self.hook_script_path, os.X_OK) if os.path.exists(self.hook_script_path) else False,
            "hooks_configured": False,
            "active_hooks": []
        }
        
        try:
            if status["settings_exists"]:
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                
                if "hooks" in settings:
                    status["hooks_configured"] = True
                    status["active_hooks"] = list(settings["hooks"].keys())
        
        except Exception as e:
            logger.error(f"Error reading hook status: {e}")
        
        return status
    
    def enable_hybrid_mode(self) -> bool:
        """Enable hybrid monitoring (hooks + fallback monitoring)"""
        try:
            # Setup hooks first
            if not self.setup_hooks():
                return False
            
            # Create hybrid configuration
            hybrid_config_path = Path(__file__).parent.parent / "config" / "hybrid_monitoring.json"
            hybrid_config_path.parent.mkdir(exist_ok=True)
            
            hybrid_config = {
                "mode": "hybrid",
                "primary": "hooks",
                "fallback": "polling",
                "fallback_trigger_delay": 10,  # seconds
                "polling_interval": 5,  # reduced interval for fallback
                "hook_timeout": 30,
                "enabled_hooks": ["MainAgentStop", "SubagentStop"],
                "fallback_sessions": "all"
            }
            
            with open(hybrid_config_path, 'w') as f:
                json.dump(hybrid_config, f, indent=2)
            
            logger.info("✅ Hybrid monitoring mode enabled")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to enable hybrid mode: {e}")
            return False


def main():
    """CLI interface for hook management"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m claude_ops.hook_manager <command>")
        print("Commands: setup, remove, test, status, hybrid")
        return
    
    command = sys.argv[1].lower()
    hook_manager = HookManager()
    
    if command == "setup":
        success = hook_manager.setup_hooks()
        print("✅ Hooks setup complete" if success else "❌ Hooks setup failed")
    
    elif command == "remove":
        success = hook_manager.remove_hooks()
        print("✅ Hooks removed" if success else "❌ Hook removal failed")
    
    elif command == "test":
        success = hook_manager.test_hook_notification()
        print("✅ Hook test passed" if success else "❌ Hook test failed")
    
    elif command == "status":
        status = hook_manager.get_hook_status()
        print("🔍 Hook Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    
    elif command == "hybrid":
        success = hook_manager.enable_hybrid_mode()
        print("✅ Hybrid mode enabled" if success else "❌ Hybrid mode failed")
    
    else:
        print(f"❌ Unknown command: {command}")


if __name__ == "__main__":
    main()