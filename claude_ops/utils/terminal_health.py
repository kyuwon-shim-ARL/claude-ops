"""Terminal Health Check and Recovery System"""

import logging
import re
import subprocess
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TerminalHealth:
    """Terminal health status"""
    session_name: str
    expected_width: int
    expected_height: int
    actual_width: Optional[int]
    actual_height: Optional[int]
    is_healthy: bool
    issues: List[str]
    screen_sample: str


class TerminalHealthChecker:
    """Check and fix terminal size issues in tmux sessions"""
    
    # Normal terminal dimensions range
    MIN_WIDTH = 80
    MIN_HEIGHT = 24
    IDEAL_WIDTH = 165
    IDEAL_HEIGHT = 73
    
    def __init__(self):
        self.vertical_text_pattern = re.compile(r'^.{1,3}$', re.MULTILINE)
        
    def capture_screen(self, session_name: str, lines: int = 30) -> str:
        """Capture tmux pane content"""
        try:
            result = subprocess.run(
                ['tmux', 'capture-pane', '-t', session_name, '-p'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return result.stdout
            return ""
        except Exception as e:
            logger.error(f"Failed to capture screen for {session_name}: {e}")
            return ""
    
    def get_pane_dimensions(self, session_name: str) -> Tuple[Optional[int], Optional[int]]:
        """Get actual pane dimensions"""
        try:
            result = subprocess.run(
                ['tmux', 'list-panes', '-t', session_name, '-F', '#{pane_width}x#{pane_height}'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                dimensions = result.stdout.strip().split('x')
                if len(dimensions) == 2:
                    return int(dimensions[0]), int(dimensions[1])
        except Exception as e:
            logger.error(f"Failed to get pane dimensions for {session_name}: {e}")
        return None, None
    
    def detect_vertical_text(self, screen_content: str) -> bool:
        """Detect if text is displayed vertically (one char per line)"""
        if not screen_content:
            return False
            
        lines = screen_content.split('\n')
        if len(lines) < 10:
            return False
            
        # Check if most lines are very short (1-3 chars)
        short_lines = sum(1 for line in lines if 0 < len(line.strip()) <= 3)
        total_lines = sum(1 for line in lines if line.strip())
        
        if total_lines > 0:
            ratio = short_lines / total_lines
            return ratio > 0.7  # 70% of lines are very short
        return False
    
    def detect_narrow_width(self, screen_content: str) -> bool:
        """Detect if terminal width is too narrow"""
        if not screen_content:
            return False
            
        lines = screen_content.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        if not non_empty_lines:
            return False
            
        # Check maximum line length
        max_length = max(len(line) for line in non_empty_lines)
        avg_length = sum(len(line) for line in non_empty_lines) / len(non_empty_lines)
        
        # If max length is very short or average is very low
        return max_length < 20 or avg_length < 10
    
    def detect_broken_layout(self, screen_content: str) -> bool:
        """Detect broken box drawing characters or layout issues"""
        if not screen_content:
            return False
            
        # Check for broken box patterns
        box_chars = ['╭', '╮', '╰', '╯', '│', '─', '┌', '┐', '└', '┘']
        
        # Count box characters
        box_count = sum(screen_content.count(char) for char in box_chars)
        
        # Check if box characters appear but layout seems broken
        if box_count > 0:
            lines = screen_content.split('\n')
            # Check if box chars appear isolated or in weird patterns
            for line in lines:
                if len(line.strip()) == 1 and line.strip() in box_chars:
                    return True
                    
        return False
    
    def check_health(self, session_name: str) -> TerminalHealth:
        """Comprehensive health check for a session"""
        width, height = self.get_pane_dimensions(session_name)
        screen_content = self.capture_screen(session_name)
        
        issues = []
        
        # Check dimensions
        if width and height:
            if width < self.MIN_WIDTH:
                issues.append(f"Width too narrow: {width} < {self.MIN_WIDTH}")
            if height < self.MIN_HEIGHT:
                issues.append(f"Height too small: {height} < {self.MIN_HEIGHT}")
        else:
            issues.append("Cannot determine pane dimensions")
        
        # Check content patterns
        if self.detect_vertical_text(screen_content):
            issues.append("Vertical text pattern detected")
            
        if self.detect_narrow_width(screen_content):
            issues.append("Narrow width content detected")
            
        if self.detect_broken_layout(screen_content):
            issues.append("Broken layout detected")
        
        # Get screen sample for debugging
        screen_lines = screen_content.split('\n')[:10]
        screen_sample = '\n'.join(screen_lines)
        
        return TerminalHealth(
            session_name=session_name,
            expected_width=self.IDEAL_WIDTH,
            expected_height=self.IDEAL_HEIGHT,
            actual_width=width,
            actual_height=height,
            is_healthy=len(issues) == 0,
            issues=issues,
            screen_sample=screen_sample
        )


class TerminalRecovery:
    """Recovery mechanisms for terminal issues"""
    
    @staticmethod
    def soft_reset(session_name: str) -> bool:
        """Soft reset: adjust terminal size without restart"""
        try:
            # Method 1: Send stty command
            cmds = [
                f"stty cols {TerminalHealthChecker.IDEAL_WIDTH} rows {TerminalHealthChecker.IDEAL_HEIGHT}",
                "reset",
                "clear"
            ]
            
            for cmd in cmds:
                subprocess.run(
                    ['tmux', 'send-keys', '-t', session_name, cmd, 'Enter'],
                    timeout=2
                )
                
            # Method 2: Refresh tmux client
            subprocess.run(['tmux', 'refresh-client', '-t', session_name], timeout=2)
            
            logger.info(f"Soft reset completed for {session_name}")
            return True
            
        except Exception as e:
            logger.error(f"Soft reset failed for {session_name}: {e}")
            return False
    
    @staticmethod
    def respawn_pane(session_name: str) -> bool:
        """Respawn pane - more aggressive but preserves session"""
        try:
            # Kill and respawn the pane
            subprocess.run(
                ['tmux', 'respawn-pane', '-t', session_name, '-k'],
                timeout=2
            )
            
            # Restart Claude in the correct directory
            subprocess.run(
                ['tmux', 'send-keys', '-t', session_name, 
                 f'cd /home/kyuwon/projects/{session_name.replace("claude_", "")}', 'Enter'],
                timeout=2
            )
            
            subprocess.run(
                ['tmux', 'send-keys', '-t', session_name, 'claude', 'Enter'],
                timeout=2
            )
            
            logger.info(f"Pane respawned for {session_name}")
            return True
            
        except Exception as e:
            logger.error(f"Respawn failed for {session_name}: {e}")
            return False
    
    @staticmethod
    def safe_restart_with_resume(session_name: str) -> bool:
        """Safe restart with conversation continuity"""
        try:
            # First try to get conversation ID (if possible)
            # This would need to be extracted from Claude's output
            
            # Send Ctrl+C to stop current operation
            subprocess.run(
                ['tmux', 'send-keys', '-t', session_name, 'C-c'],
                timeout=2
            )
            
            # Wait a moment
            import time
            time.sleep(2)
            
            # Exit Claude
            subprocess.run(
                ['tmux', 'send-keys', '-t', session_name, 'exit', 'Enter'],
                timeout=2
            )
            
            time.sleep(1)
            
            # Restart with resume
            subprocess.run(
                ['tmux', 'send-keys', '-t', session_name, 'claude --continue', 'Enter'],
                timeout=2
            )
            
            logger.info(f"Safe restart with resume completed for {session_name}")
            return True
            
        except Exception as e:
            logger.error(f"Safe restart failed for {session_name}: {e}")
            return False
    
    @staticmethod
    def fix_terminal(session_name: str, force_respawn: bool = False) -> Dict[str, any]:
        """Main recovery function with escalation strategy"""
        checker = TerminalHealthChecker()
        
        # Initial health check
        initial_health = checker.check_health(session_name)
        
        if initial_health.is_healthy:
            return {
                'success': True,
                'message': f"Terminal {session_name} is already healthy",
                'health': initial_health
            }
        
        recovery_attempts = []
        
        # Level 1: Soft reset
        if not force_respawn:
            logger.info(f"Attempting soft reset for {session_name}")
            if TerminalRecovery.soft_reset(session_name):
                import time
                time.sleep(3)  # Wait for changes to take effect
                
                # Re-check health
                health = checker.check_health(session_name)
                recovery_attempts.append("soft_reset")
                
                if health.is_healthy:
                    return {
                        'success': True,
                        'message': f"Terminal {session_name} fixed with soft reset",
                        'health': health,
                        'recovery_method': 'soft_reset'
                    }
        
        # Level 2: Respawn pane
        logger.info(f"Attempting pane respawn for {session_name}")
        if TerminalRecovery.respawn_pane(session_name):
            import time
            time.sleep(5)  # Wait for Claude to start
            
            # Final health check
            final_health = checker.check_health(session_name)
            recovery_attempts.append("respawn_pane")
            
            return {
                'success': final_health.is_healthy,
                'message': f"Terminal {session_name} respawned",
                'health': final_health,
                'recovery_method': 'respawn_pane',
                'recovery_attempts': recovery_attempts
            }
        
        # Recovery failed
        return {
            'success': False,
            'message': f"Failed to fix terminal {session_name}",
            'health': initial_health,
            'recovery_attempts': recovery_attempts
        }