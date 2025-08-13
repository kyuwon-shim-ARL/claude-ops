"""
Smart Notification Module

Advanced Telegram notification system with context awareness and duplicate detection.
"""

import os
import asyncio
import logging
import subprocess
from typing import Optional
from ..config import ClaudeOpsConfig
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..utils.prompt_recall import get_context_for_notification
from ..utils.log_length_manager import get_current_log_length

logger = logging.getLogger(__name__)


class SmartNotifier:
    """Smart notification system with context awareness"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        """
        Initialize the smart notifier
        
        Args:
            config: Bridge configuration
        """
        self.config = config or ClaudeOpsConfig()
        self.state_analyzer = SessionStateAnalyzer()  # Unified state detection
        self._last_notification_hash = None
    
    def _get_current_time(self) -> str:
        """Get current time formatted for display"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def _get_current_screen_content(self) -> str:
        """Get current screen content from tmux session"""
        try:
            # 동적 로그 길이 적용
            log_lines = get_current_log_length()
            
            result = subprocess.run(
                f"tmux capture-pane -t {self.config.session_name} -p -S -{log_lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout
            return ""
            
        except Exception as e:
            logger.warning(f"Failed to get screen content: {str(e)}")
            return ""

    def _is_work_currently_running(self) -> bool:
        """Check if work is currently running (uses unified state analyzer)"""
        return self.state_analyzer.is_working(self.config.session_name)
        
    def _get_session_state(self) -> SessionState:
        """Get current session state"""
        return self.state_analyzer.get_state(self.config.session_name)
        
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
            # Check if message contains rich context (starts with emoji)
            if message.startswith("✅") and "```" in message:
                # For rich notifications, use no parse mode to avoid markdown issues
                data = {
                    "chat_id": chat_id,
                    "text": message
                }
            else:
                # For simple notifications, use markdown
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
                logger.error(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
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
    
    def send_waiting_input_notification(self) -> bool:
        """Send notification when Claude is waiting for user input"""
        # Get session information
        session_name = self.config.session_name
        session_display = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
        working_dir = self.config.working_directory
        
        # Get current screen to show what Claude is waiting for
        try:
            import subprocess
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -3", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                screen_lines = result.stdout.strip().split('\n')[-3:]  # Get last 3 lines
                context_text = '\n'.join(screen_lines).strip()
            else:
                context_text = "Claude가 입력을 기다리고 있습니다"
                
        except Exception as e:
            logger.debug(f"Failed to get screen context: {e}")
            context_text = "Claude가 입력을 기다리고 있습니다"
        
        # 동적 로그 길이 정보 추가
        log_length = get_current_log_length()
        
        # Enhanced message with session information for reply targeting
        message = f"""⏸️ **입력 대기** [`{session_name}`]

📁 **프로젝트**: `{working_dir}`
🎯 **세션**: `{session_name}` (로그: {log_length}줄)
⏰ **대기 시작**: {self._get_current_time()}

**현재 상태:**
{context_text}

💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
        
        success = self._send_telegram_notification(message)
        
        if success:
            logger.info(f"✅ Sent waiting input notification for session: {session_name}")
        else:
            logger.warning(f"❌ Failed to send waiting input notification for session: {session_name}")
        
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
        """Send work completion notification with enhanced context and session info"""
        # Check current state using unified analyzer
        current_state = self._get_session_state()
        
        # Don't send notification if still working
        if current_state == SessionState.WORKING:
            logger.info("Work still in progress, skipping notification")
            return False
            
        # Get session information
        session_name = self.config.session_name
        session_display = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
        working_dir = self.config.working_directory
        
        # Get last user prompt for context recall
        prompt_context = get_context_for_notification(session_name)
        
        # Get rich context for notification
        context = self.extract_work_context()
        
        # 동적 로그 길이 정보 추가
        log_length = get_current_log_length()
        
        if context:
            # Enhanced message with session information and prompt recall
            message = f"""✅ **작업 완료** [`{session_name}`]

{prompt_context}📁 **프로젝트**: `{working_dir}`
🎯 **세션**: `{session_name}` (로그: {log_length}줄)
⏰ **완료 시간**: {self._get_current_time()}

{context}

💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
            
            # Check for duplicate notifications
            import hashlib
            message_hash = hashlib.md5(message.encode()).hexdigest()
            if message_hash == self._last_notification_hash:
                logger.info("Duplicate notification detected, skipping")
                return True  # Return True to avoid error logging
                
            self._last_notification_hash = message_hash
            return self._send_telegram_notification(message)
        else:
            # Simple fallback message with session info
            message = f"""✅ **작업 완료** [`{session_name}`]

📁 **프로젝트**: `{working_dir}`
🎯 **세션**: `{session_name}` (로그: {log_length}줄)
⏰ **완료 시간**: {self._get_current_time()}

Claude가 작업을 완료했습니다. 결과를 확인해보세요.

💡 **답장하려면** 이 메시지에 Reply로 응답하세요!"""
            return self.send_notification_sync(message)
    
    def send_response_completion_notification(self) -> bool:
        """Send response completion notification"""
        return self.send_notification_sync("💬 **응답 완료**\n\nClaude가 응답을 완료했습니다.")
    
    def send_error_notification(self, error_message: str) -> bool:
        """Send error notification"""
        return self.send_notification_sync(f"❌ **오류 발생**\n\n{error_message}", force=True)
    
    def extract_work_context(self) -> str:
        """Extract rich context from tmux session for work completion notification"""
        try:
            # Use the same screen content source as state analyzer for consistency
            screen_content = self.state_analyzer.get_screen_content(self.config.session_name)
            if not screen_content:
                return ""
            
            tmux_output = screen_content.strip()
            if not tmux_output:
                return ""
            
            # Find last bullet point (● or •) and get everything after it
            lines = tmux_output.split('\n')
            last_bullet_index = -1
            
            # Find the last meaningful bullet point, but skip TUI screens and edit dialogs
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i].strip()  # Remove leading/trailing whitespace
                # Check for bullet points at any indentation level
                if line.startswith('●') or line.startswith('•'):
                    # Check if this bullet point is currently running
                    is_running = False
                    # Check if this is a TUI/edit dialog (look for UI elements)
                    is_tui_dialog = False
                    
                    for j in range(i + 1, min(i + 20, len(lines))):
                        if j < len(lines):
                            check_line = lines[j]
                            # Running indicators
                            if ("esc to interrupt" in check_line or 
                                "Running…" in check_line):
                                is_running = True
                                break
                            # TUI dialog indicators  
                            if ("Do you want to make this edit" in check_line or
                                "❯ 1. Yes" in check_line or
                                "Edit file" in check_line or
                                "╭─" in check_line and "╮" in check_line):
                                is_tui_dialog = True
                                break
                    
                    if not is_running and not is_tui_dialog:
                        last_bullet_index = i
                        break
            
            # If no bullet point found, get last 50 lines (reduced from 100)
            if last_bullet_index == -1:
                start_index = max(0, len(lines) - 50)
            else:
                start_index = last_bullet_index
            
            # Get lines from last bullet point to end
            content_lines = lines[start_index:]
            
            # Remove bounding box characters only
            cleaned_lines = []
            for line in content_lines:
                # Remove all bounding box characters including horizontal lines
                cleaned_line = line
                
                # Remove box drawing characters
                for char in ['╭', '╮', '╯', '╰', '│', '├', '└', '┌', '┐', '┘', '┴', '┬', '┤', '┼', '─', '━', '═', '▀', '▄', '█']:
                    cleaned_line = cleaned_line.replace(char, '')
                
                # Skip lines that are only horizontal lines (like ───────)
                if cleaned_line.strip() and not all(c in '─━═▀▄█ ' for c in cleaned_line):
                    cleaned_lines.append(cleaned_line)
                elif not cleaned_line.strip():
                    # Keep empty lines for formatting
                    cleaned_lines.append(cleaned_line)
            
            # Apply smart truncation strategy
            content = self._smart_truncate_content(cleaned_lines)
            
            # Format with project and session info
            try:
                from ..session_manager import session_manager
                active_session = session_manager.get_active_session()
                session_info = session_manager.get_session_info(active_session)
                
                header = f"📁 Project: {session_info['directory']}\n🎯 Session: {active_session}\n\n"
                return header + f"```\n{content}\n```"
            except:
                return f"```\n{content}\n```"
            
        except Exception as e:
            logger.warning(f"Failed to extract work context: {str(e)}")
            return ""
    
    def _smart_truncate_content(self, cleaned_lines: list) -> str:
        """
        Smart truncation that preserves important information
        
        Strategy:
        1. Always preserve the last part (most recent activity)
        2. If too long, use middle truncation with "...(중간 생략)..."
        3. Preserve important lines (prompts, choices, errors)
        
        Args:
            cleaned_lines: List of cleaned content lines
            
        Returns:
            str: Appropriately truncated content
        """
        # Telegram limit (4096 chars total) - reserve space for headers (about 500 chars)
        max_content_length = 3500
        
        # Join lines first to check length
        full_content = '\n'.join(cleaned_lines)
        
        if len(full_content) <= max_content_length:
            return full_content
            
        # Content is too long - apply smart truncation
        important_patterns = [
            "Do you want to",
            "❯ 1.", "❯ 2.", "❯ 3.",
            "Choose", "Select", "Enter your choice",
            "Error:", "Failed:", "Exception:",
            "Continue?"
        ]
        
        # Find important lines to always preserve
        important_lines = []
        for i, line in enumerate(cleaned_lines):
            if any(pattern in line for pattern in important_patterns):
                important_lines.append((i, line))
        
        # Strategy: Preserve last N lines + important lines + truncation indicator
        preserve_last = 15  # Last 15 lines are usually most important
        
        if len(cleaned_lines) <= preserve_last:
            # If total lines are few, just truncate text length
            truncated = full_content[:max_content_length - 50]  # Reserve space for indicator
            return truncated + "\n\n...(내용이 길어서 일부만 표시)"
        
        # Get last lines
        last_lines = cleaned_lines[-preserve_last:]
        
        # Check if last lines + important lines fit
        last_content = '\n'.join(last_lines)
        important_content = '\n'.join([line for _, line in important_lines[-5:]])  # Last 5 important lines
        
        middle_truncation_indicator = "\n...(중간 생략)...\n"
        
        # Try: first few lines + important + truncation + last lines
        if len(cleaned_lines) > preserve_last + 10:
            first_lines = cleaned_lines[:5]  # Show first 5 lines for context
            first_content = '\n'.join(first_lines)
            
            combined = first_content + middle_truncation_indicator + important_content + middle_truncation_indicator + last_content
            
            if len(combined) <= max_content_length:
                return combined
        
        # Fallback: Just show last lines with truncation indicator
        if len(last_content) > max_content_length - 100:
            # Even last lines are too long, truncate them
            truncated_last = last_content[-(max_content_length - 100):]
            return "...(앞부분 생략)...\n" + truncated_last
        else:
            return "...(앞부분 생략)...\n" + last_content
    
    def process_tmux_output_for_notification(self, tmux_output: str) -> str:
        """Process tmux output to create a meaningful notification"""
        lines = tmux_output.split('\n')
        
        # Find the last bullet point (•) and get everything after it
        last_bullet_index = -1
        
        # Find the last meaningful bullet point (both • and ●) at the start of a line (no indentation)
        # Skip any bullet points that look like currently running commands
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            stripped_line = line.lstrip()
            # Check if line starts with bullet point (no or minimal indentation)
            if (stripped_line.startswith('•') or stripped_line.startswith('●')) and len(line) - len(stripped_line) < 4:
                # Skip if this looks like a currently running command
                # Check next few lines for running indicators
                is_running = False
                for j in range(i + 1, min(i + 8, len(lines))):
                    if j < len(lines):
                        line_content = lines[j]
                        # More accurate indicators of currently running commands
                        if ("esc to interrupt" in line_content or 
                            "tokens" in line_content or
                            "Running…" in line_content or
                            "Forging…" in line_content or 
                            "Envisioning…" in line_content or
                            "⚒" in line_content):
                            is_running = True
                            break
                
                if is_running:
                    continue
                    
                last_bullet_index = i
                break
        
        # If no bullet point found, get last 10 lines
        if last_bullet_index == -1:
            start_index = max(0, len(lines) - 10)
        else:
            start_index = last_bullet_index
        
        # Collect lines from the last bullet point to the end, but limit to just one bullet point
        meaningful_lines = []
        bullet_count = 0
        
        for i in range(start_index, len(lines)):
            line = lines[i]
            
            # Remove box drawing characters but keep content
            cleaned_line = self.clean_box_characters(line)
            if cleaned_line:
                # Count bullet points and stop after finding the next one (if any)
                if cleaned_line.lstrip().startswith('●') or cleaned_line.lstrip().startswith('•'):
                    bullet_count += 1
                    if bullet_count > 1:  # Stop after the first bullet point
                        break
                        
                meaningful_lines.append(cleaned_line)
        
        if not meaningful_lines:
            return ""
        
        
        # Format the context nicely
        context_text = '\n'.join(meaningful_lines)
        
        # Limit total length for Telegram
        if len(context_text) > 2000:
            context_text = context_text[:1800] + "\n\n...(내용이 길어서 일부만 표시)"
        
        # Add project and session info
        try:
            from ..session_manager import session_manager
            active_session = session_manager.get_active_session()
            session_info = session_manager.get_session_info(active_session)
            
            header = f"📁 Project: {session_info['directory']}\n🎯 Session: {active_session}\n\n"
            
            # Use plain text format to avoid markdown issues
            return header + f"```\n{context_text}\n```"
        except:
            return f"```\n{context_text}\n```"
    
    def escape_markdown(self, text: str) -> str:
        """Escape markdown characters that might break Telegram parsing"""
        # Common problematic characters in Telegram markdown
        chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        escaped_text = text
        for char in chars_to_escape:
            if char in escaped_text:
                escaped_text = escaped_text.replace(char, f'\\{char}')
        
        return escaped_text
    
    def clean_box_characters(self, line: str) -> str:
        """Remove box drawing characters but preserve content"""
        # Remove common box drawing characters
        box_chars = ['│', '├', '└', '╭', '╮', '╯', '╰', '─', '┌', '┐', '┘', '└', '┤', '┴', '┬', '┼']
        
        cleaned = line
        for char in box_chars:
            cleaned = cleaned.replace(char, '')
        
        # Remove excessive whitespace
        cleaned = ' '.join(cleaned.split())
        
        # Remove "Do you want to proceed?" type prompts
        if 'Do you want to proceed?' in cleaned or 'esc to interrupt' in cleaned:
            return ""
            
        return cleaned.strip()


def main():
    """Main entry point for standalone notification sending"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m claude_bridge.notifier <message> [--force]")
        sys.exit(1)
    
    message = sys.argv[1]
    force = "--force" in sys.argv
    
    try:
        config = ClaudeOpsConfig()
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