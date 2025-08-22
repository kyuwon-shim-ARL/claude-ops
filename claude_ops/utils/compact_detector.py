"""
Compact Prompt Detector for Claude-Ops

Detects when Claude suggests running /compact command and captures the prompt
for easy execution via Telegram bot.
"""

import re
import logging
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class CompactPromptDetector:
    """Detects and extracts /compact command suggestions from Claude"""
    
    def __init__(self):
        # Patterns that indicate Claude is suggesting /compact
        self.suggestion_patterns = [
            r"이제\s+[`']?/compact[`']?\s*(?:를|을)?\s*실행",
            r"Now\s+run\s+[`']?/compact[`']?",
            r"[`']?/compact[`']?\s*명령(?:어)?를?\s*실행",
            r"다음\s+명령(?:어)?(?:를|들을)?\s*(?:순서대로\s+)?실행",  # More flexible
            r"[`']?/compact.*?[`']?\s*(?:를|을)?\s*실행",  # Any /compact variation
            r"Please\s+run\s+[`']?/compact[`']?",
            r"Execute\s+[`']?/compact[`']?",
            r"[`']?/compact[`']?\s+command",
            r"다음\s+단계를?\s*수행",  # Common Korean pattern
        ]
        
        # Patterns to extract the actual command with options
        self.command_patterns = [
            r"[`']?(/compact[^`'\n]*?)[`']",  # /compact with options in backticks
            r"```\s*(/compact.*?)\s*```",  # In code block
            r"^\s*(/compact.*?)$",  # On its own line
        ]
        
        # Cache to avoid duplicate notifications
        self._notification_cache: Dict[str, datetime] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
    
    def detect_suggestion(self, screen_content: str) -> bool:
        """
        Check if screen content contains a /compact suggestion
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            bool: True if /compact suggestion detected
        """
        if not screen_content:
            return False
        
        # Check each pattern
        for pattern in self.suggestion_patterns:
            if re.search(pattern, screen_content, re.IGNORECASE | re.MULTILINE):
                logger.info(f"Detected /compact suggestion with pattern: {pattern}")
                return True
        
        return False
    
    def extract_commands(self, screen_content: str) -> List[str]:
        """
        Extract all /compact commands from the content
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            List[str]: List of /compact commands found
        """
        commands = []
        
        # Look for commands in the last 50 lines (recent context)
        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-50:])
        
        for pattern in self.command_patterns:
            matches = re.findall(pattern, recent_content, re.MULTILINE)
            for match in matches:
                if match and match.strip().startswith('/compact'):
                    command = match.strip()
                    if command not in commands:
                        commands.append(command)
        
        # If no specific command found but suggestion detected, add basic /compact
        if not commands and self.detect_suggestion(recent_content):
            commands.append('/compact')
        
        return commands
    
    def extract_zed_guide(self, screen_content: str) -> Optional[str]:
        """
        Extract ZED-based guide prompt that comes with /compact suggestion
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            Optional[str]: ZED guide prompt if found
        """
        # Look in recent content
        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-200:])  # Look at more lines for guide
        
        # First try to find ZED code block
        zed_match = re.search(r'```zed\n(.*?)```', recent_content, re.DOTALL | re.MULTILINE)
        if zed_match:
            return zed_match.group(1).strip()
        
        # Look for structured content after /compact mention
        if '/compact' in recent_content:
            # Find lines that mention /compact
            compact_lines = []
            for i, line in enumerate(lines[-200:]):
                if '/compact' in line:
                    compact_lines.append(i)
            
            # Check content after each /compact mention
            for compact_idx in compact_lines:
                # Get lines after /compact
                after_lines = lines[-200 + compact_idx:]
                
                # Look for structured content indicators
                guide_lines = []
                in_structured_content = False
                empty_line_count = 0
                
                for line in after_lines[1:]:  # Skip the /compact line
                    # Check if this line starts structured content
                    if not in_structured_content:
                        if (line.strip().startswith('##') or 
                            line.strip().startswith('- ') or
                            line.strip().startswith('•') or
                            '다음 내용' in line or
                            '다음 문서' in line or
                            'following' in line.lower()):
                            in_structured_content = True
                            if not ('다음' in line or 'following' in line.lower()):
                                guide_lines.append(line)
                    else:
                        # We're in structured content
                        if not line.strip():
                            empty_line_count += 1
                            # Stop after 2 consecutive empty lines
                            if empty_line_count >= 2:
                                break
                        else:
                            empty_line_count = 0
                            guide_lines.append(line)
                
                # Return if we found substantial content
                if len(guide_lines) > 3:
                    content = '\n'.join(guide_lines).strip()
                    # Ensure it has structure markers
                    if '##' in content or ('- ' in content and len(guide_lines) > 5):
                        return content
        
        # Fallback: Look for any section headers after recent /compact
        section_pattern = r'##\s+[^\n]+\n((?:.*\n)*?)(?=\n##|\Z)'
        sections = re.findall(section_pattern, recent_content, re.MULTILINE)
        if sections and '/compact' in recent_content:
            # Combine all sections found
            combined = '\n'.join(['## ' + re.search(r'##\s+([^\n]+)', recent_content).group(1)] + 
                                 [s.strip() for s in sections if s.strip()])
            if len(combined) > 100:
                return combined
        
        return None
    
    def should_notify(self, session_name: str, screen_content: str) -> bool:
        """
        Check if we should send a notification for this command
        (Avoid duplicate notifications based on content hash)
        
        Args:
            session_name: Name of the tmux session
            screen_content: Current screen content
            
        Returns:
            bool: True if notification should be sent
        """
        import hashlib
        
        # Create a hash of the relevant content (last 100 lines)
        lines = screen_content.split('\n')
        relevant_content = '\n'.join(lines[-100:])
        content_hash = hashlib.md5(relevant_content.encode()).hexdigest()
        
        cache_key = f"{session_name}:{content_hash}"
        now = datetime.now()
        
        # Clean expired cache entries (increase TTL to 30 minutes)
        expired_keys = [
            key for key, timestamp in self._notification_cache.items()
            if (now - timestamp).total_seconds() > 1800  # 30 minutes
        ]
        for key in expired_keys:
            del self._notification_cache[key]
        
        # Check if already notified for this exact content
        if cache_key in self._notification_cache:
            return False
        
        # Mark as notified
        self._notification_cache[cache_key] = now
        return True
    
    def analyze_context(self, screen_content: str) -> Dict[str, any]:
        """
        Analyze the context around /compact suggestion
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            Dict containing analysis results
        """
        result = {
            'has_suggestion': False,
            'commands': [],
            'context': '',
            'zed_guide': None,
            'is_multi_step': False,
            'timestamp': datetime.now()
        }
        
        if self.detect_suggestion(screen_content):
            result['has_suggestion'] = True
            result['commands'] = self.extract_commands(screen_content)
            result['is_multi_step'] = len(result['commands']) > 1
            
            # Extract ZED guide if available
            result['zed_guide'] = self.extract_zed_guide(screen_content)
            
            # Extract surrounding context (last 10 lines)
            lines = screen_content.split('\n')
            context_lines = lines[-10:]
            result['context'] = '\n'.join(context_lines)
        
        return result


class CompactExecutor:
    """Handles execution of /compact commands via tmux"""
    
    def __init__(self):
        self.execution_log: List[Dict] = []
    
    def execute_command(self, session_name: str, command: str) -> bool:
        """
        Execute a /compact command in the specified tmux session
        
        Args:
            session_name: Target tmux session
            command: The /compact command to execute
            
        Returns:
            bool: True if execution successful
        """
        import subprocess
        
        try:
            # Send command to tmux session
            result = subprocess.run(
                f'tmux send-keys -t {session_name} "{command}" Enter',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Log execution
            self.execution_log.append({
                'session': session_name,
                'command': command,
                'timestamp': datetime.now(),
                'success': result.returncode == 0,
                'error': result.stderr if result.returncode != 0 else None
            })
            
            if result.returncode == 0:
                logger.info(f"Successfully executed '{command}' in {session_name}")
                return True
            else:
                logger.error(f"Failed to execute '{command}': {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout executing '{command}' in {session_name}")
            return False
        except Exception as e:
            logger.error(f"Error executing '{command}': {e}")
            return False
    
    def execute_sequence(self, session_name: str, commands: List[str], delay: float = 1.0) -> bool:
        """
        Execute a sequence of commands with delay between them
        
        Args:
            session_name: Target tmux session
            commands: List of commands to execute
            delay: Delay in seconds between commands
            
        Returns:
            bool: True if all commands executed successfully
        """
        import time
        
        success_count = 0
        for i, command in enumerate(commands):
            logger.info(f"Executing step {i+1}/{len(commands)}: {command}")
            
            if self.execute_command(session_name, command):
                success_count += 1
                
                # Wait before next command (except for last)
                if i < len(commands) - 1:
                    time.sleep(delay)
            else:
                logger.error(f"Failed at step {i+1}: {command}")
                break
        
        return success_count == len(commands)