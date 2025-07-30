"""
Smart Notification Module

Python version of send_smart_notification.sh with improved logic and async support.
"""

import os
import asyncio
import logging
import subprocess
from typing import Optional
from .config import BridgeConfig

logger = logging.getLogger(__name__)


class SmartNotifier:
    """Smart notification system with context awareness"""
    
    def __init__(self, config: Optional[BridgeConfig] = None):
        """
        Initialize the smart notifier
        
        Args:
            config: Bridge configuration
        """
        self.config = config or BridgeConfig()
        
    def _send_telegram_notification(self, message: str) -> bool:
        """Send notification via Telegram"""
        try:
            try:
                import requests
            except ImportError:
                logger.error("requests library not available. Install with: pip install requests")
                return False
            
            # Use telegram API directly for notifications
            bot_token = self.config.telegram_bot_token
            chat_id = self.config.telegram_chat_id
            
            if not bot_token or not chat_id:
                logger.warning("Telegram credentials not configured for notifications")
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram notification sent successfully")
                return True
            else:
                logger.error(f"Failed to send Telegram notification: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending Telegram notification: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {str(e)}")
            return False
    
    def _check_notification_conditions(self) -> tuple[bool, str]:
        """Check if notification should be sent based on context"""
        try:
            # Check if tmux session exists
            result = subprocess.run(
                f"tmux has-session -t {self.config.session_name}",
                shell=True,
                capture_output=True
            )
            
            if result.returncode != 0:
                return False, "tmux session not found"
            
            # Get current tmux output to check context
            result = subprocess.run(
                f"tmux capture-pane -t {self.config.session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, "failed to capture tmux output"
            
            tmux_output = result.stdout
            
            # Basic context checks
            if not tmux_output.strip():
                return False, "empty tmux output"
            
            # Check if user might be actively typing
            bottom_lines = '\n'.join(tmux_output.split('\n')[-3:])
            if "│ > " in bottom_lines and len(bottom_lines.split('│ > ')[-1].strip()) > 0:
                return False, "user appears to be typing"
            
            return True, "conditions met"
            
        except subprocess.TimeoutExpired:
            logger.warning("Timeout checking notification conditions")
            return False, "timeout"
        except Exception as e:
            logger.error(f"Error checking notification conditions: {str(e)}")
            return False, f"error: {str(e)}"
    
    def send_notification_sync(self, message: str, force: bool = False) -> bool:
        """
        Send smart notification (synchronous version)
        
        Args:
            message: Notification message
            force: Skip context checks if True
            
        Returns:
            True if notification was sent successfully
        """
        logger.info(f"Smart notification request: {message}")
        
        # Add context information
        full_message = f"🤖 **Claude Status Update**\n\n{message}\n\n📁 **Project:** `{os.path.basename(self.config.working_directory)}`\n🎯 **Session:** `{self.config.session_name}`"
        
        # Check conditions unless forced
        if not force:
            should_send, reason = self._check_notification_conditions()
            if not should_send:
                logger.info(f"Skipping notification: {reason}")
                return False
        
        # Send notification
        success = self._send_telegram_notification(full_message)
        
        if success:
            logger.info("Smart notification sent successfully")
        else:
            logger.error("Failed to send smart notification")
            
        return success
    
    async def send_notification(self, message: str, force: bool = False) -> bool:
        """
        Send smart notification (async version)
        
        Args:
            message: Notification message
            force: Skip context checks if True
            
        Returns:
            True if notification was sent successfully
        """
        # Run synchronous version in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.send_notification_sync, message, force)
    
    def send_work_completion_notification(self) -> bool:
        """Send work completion notification with enhanced context"""
        return self.send_notification_sync("✅ **작업 완료**\n\nClaude가 작업을 완료했습니다. 결과를 확인해보세요.")
    
    def send_response_completion_notification(self) -> bool:
        """Send response completion notification"""
        return self.send_notification_sync("💬 **응답 완료**\n\nClaude가 응답을 완료했습니다.")
    
    def send_error_notification(self, error_message: str) -> bool:
        """Send error notification"""
        return self.send_notification_sync(f"❌ **오류 발생**\n\n{error_message}", force=True)


def main():
    """Main entry point for standalone notification sending"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m claude_bridge.notifier <message> [--force]")
        sys.exit(1)
    
    message = sys.argv[1]
    force = "--force" in sys.argv
    
    try:
        config = BridgeConfig()
        notifier = SmartNotifier(config)
        success = notifier.send_notification_sync(message, force=force)
        
        if success:
            print("Notification sent successfully")
            sys.exit(0)
        else:
            print("Failed to send notification")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error in notification main: {str(e)}")
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()