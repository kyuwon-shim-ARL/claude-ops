"""
Claude Monitor Module

Python version of watch_claude_status.sh with improved monitoring logic.
"""

import os
import time
import logging
import subprocess
from typing import Optional
from ..config import ClaudeOpsConfig
from .notifier import SmartNotifier

logger = logging.getLogger(__name__)


class TelegramMonitor:
    """Monitor Claude session status and send notifications"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        """
        Initialize Claude monitor
        
        Args:
            config: Bridge configuration
        """
        self.config = config or ClaudeOpsConfig()
        self.notifier = SmartNotifier(self.config)
        self.previous_state = "idle"
        
    def get_tmux_output(self) -> Optional[str]:
        """Get tmux session output"""
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {self.config.session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Failed to capture tmux pane: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning("Tmux capture timed out")
            return None
        except Exception as e:
            logger.error(f"Error capturing tmux output: {str(e)}")
            return None
    
    def detect_current_state(self, tmux_output: str) -> str:
        """
        Detect current Claude state from tmux output
        
        Args:
            tmux_output: Full tmux session output
            
        Returns:
            Current state: 'working', 'typing', 'responding', or 'idle'
        """
        if not tmux_output:
            return "idle"
            
        # Get bottom lines for quick state detection
        bottom_lines = '\n'.join(tmux_output.split('\n')[-5:])
        
        # 1. Check if Claude is working (esc to interrupt)
        if "esc to interrupt" in tmux_output:
            return "working"
            
        # 2. Check if user is typing (input box with text)
        if ("╭.*╮" in bottom_lines and 
            "│ > [^ ]" in bottom_lines and 
            "auto-accept" in bottom_lines):
            return "typing"
            
        # 3. Check if Claude is responding (bullet points)
        if "●" in bottom_lines:
            return "responding"
            
        return "idle"
    
    def load_previous_state(self) -> str:
        """Load previous state from status file"""
        try:
            if os.path.exists(self.config.status_file):
                with open(self.config.status_file, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logger.warning(f"Could not read status file: {str(e)}")
        
        return "idle"
    
    def save_current_state(self, state: str) -> None:
        """Save current state to status file"""
        try:
            with open(self.config.status_file, 'w') as f:
                f.write(state)
        except Exception as e:
            logger.warning(f"Could not write status file: {str(e)}")
    
    def check_session_exists(self) -> bool:
        """Check if tmux session exists"""
        result = os.system(f"tmux has-session -t {self.config.session_name} 2>/dev/null")
        return result == 0
    
    async def send_notification(self, message: str) -> None:
        """Send notification via SmartNotifier"""
        try:
            await self.notifier.send_notification(message)
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
    
    def monitor_loop(self) -> None:
        """Main monitoring loop"""
        logger.info(f"Claude 상태 모니터링 시작 (세션: {self.config.session_name})")
        logger.info(f"체크 간격: {self.config.check_interval}초")
        
        # Initialize previous state
        self.previous_state = self.load_previous_state()
        
        while True:
            try:
                if not self.check_session_exists():
                    logger.debug(f"tmux 세션 '{self.config.session_name}'이 존재하지 않습니다")
                    time.sleep(10)  # Longer wait when session doesn't exist
                    continue
                
                # Get current tmux output
                tmux_output = self.get_tmux_output()
                if not tmux_output:
                    time.sleep(self.config.check_interval)
                    continue
                
                # Detect current state
                current_state = self.detect_current_state(tmux_output)
                
                # Check for state changes and send notifications
                if self.previous_state != current_state:
                    logger.info(f"상태 변화: {self.previous_state} → {current_state}")
                    
                    # Send notifications for specific transitions
                    if self.previous_state == "working" and current_state == "idle":
                        logger.info("✅ Claude 작업 완료 감지 - 알림 전송")
                        self.notifier.send_work_completion_notification()
                        
                    elif self.previous_state == "responding" and current_state == "idle":
                        logger.info("💬 Claude 응답 완료 감지 - 알림 전송")
                        self.notifier.send_response_completion_notification()
                    
                    # Update previous state
                    self.previous_state = current_state
                    self.save_current_state(current_state)
                
                time.sleep(self.config.check_interval)
                
            except KeyboardInterrupt:
                logger.info("모니터링이 사용자에 의해 중단되었습니다")
                break
            except Exception as e:
                logger.error(f"모니터링 중 오류 발생: {str(e)}")
                time.sleep(self.config.check_interval)


def main():
    """Main entry point for standalone monitoring"""
    try:
        config = BridgeConfig()
        monitor = ClaudeMonitor(config)
        monitor.monitor_loop()
    except KeyboardInterrupt:
        logger.info("모니터가 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"모니터 실행 중 오류: {str(e)}")


if __name__ == "__main__":
    main()