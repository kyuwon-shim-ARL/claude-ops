"""
Session Summary Helper for Claude-Ops

Provides summary and analysis of Claude sessions with wait time tracking
"""

import time
import re
import subprocess
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..utils.wait_time_tracker import wait_tracker
from ..session_manager import session_manager

class SessionSummaryHelper:
    """Helper class for generating session summaries"""
    
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
        self.tracker = wait_tracker  # Use the global tracker instance
        
    def get_waiting_sessions_with_times(self) -> List[Tuple[str, float, str]]:
        """
        Get all waiting/idle sessions with their wait times
        
        Returns:
            List of tuples: (session_name, wait_time_seconds, last_prompt)
        """
        waiting_sessions = []
        sessions = session_manager.get_all_claude_sessions()
        
        for session_name in sessions:
            # Check current state
            state = self.state_analyzer.get_state_for_notification(session_name)
            
            # Consider all non-working states as waiting
            if state != SessionState.WORKING:
                # Get wait time from persistent tracker
                wait_time = self.tracker.get_wait_time(session_name)
                last_prompt = self.extract_last_prompt(session_name)
                waiting_sessions.append((session_name, wait_time, last_prompt))
            else:
                # Reset wait time for working sessions
                self.tracker.reset_session(session_name)
        
        # Sort by wait time (shortest first)
        waiting_sessions.sort(key=lambda x: x[1])
        return waiting_sessions
    
    def extract_last_prompt(self, session_name: str) -> str:
        """
        Extract the last user prompt from session
        
        Args:
            session_name: Name of the tmux session
            
        Returns:
            Last prompt text or empty string
        """
        try:
            # Get last 30 lines of screen
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p | tail -30",
                shell=True,
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return ""
            
            lines = result.stdout.split('\n')
            
            # Look for common prompt patterns
            prompt_patterns = [
                r'^>\s*(.+)',  # > prompt
                r'^User:\s*(.+)',  # User: prompt
                r'^Human:\s*(.+)',  # Human: prompt
                r'^\?\s*(.+)',  # ? prompt
                r'^▶\s*(.+)',  # ▶ prompt
            ]
            
            # Search from bottom up for last prompt
            for line in reversed(lines):
                line = line.strip()
                for pattern in prompt_patterns:
                    match = re.match(pattern, line)
                    if match:
                        prompt = match.group(1).strip()
                        # Truncate if too long
                        if len(prompt) > 50:
                            prompt = prompt[:47] + "..."
                        return prompt
            
            # If no prompt pattern found, look for question marks
            for line in reversed(lines):
                if '?' in line and len(line) > 5:
                    prompt = line.strip()
                    if len(prompt) > 50:
                        prompt = prompt[:47] + "..."
                    return prompt
                    
            return ""
            
        except Exception:
            return ""
    
    def get_screen_summary(self, session_name: str, lines: int = 5) -> str:
        """
        Get last N lines of screen content
        
        Args:
            session_name: Name of the tmux session
            lines: Number of lines to retrieve
            
        Returns:
            Formatted screen summary
        """
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p | tail -{lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return "화면 캡처 실패"
            
            content = result.stdout.strip()
            if not content:
                return "빈 화면"
            
            # Clean up and format
            lines_list = content.split('\n')
            cleaned_lines = []
            for line in lines_list:
                # First check if line has any meaningful content before cleaning
                # Remove box drawing characters but preserve the text
                cleaned = re.sub(r'[╭─╮╯╰│┌┐└┘├┤┬┴┼]', ' ', line).strip()
                
                # Also try to detect common UI patterns and clean them
                cleaned = re.sub(r'^\s*[▶⏵◀⏴]+\s*', '', cleaned)  # Remove arrow indicators
                cleaned = re.sub(r'^\s*>\s*$', '', cleaned)  # Remove lone prompts
                
                # Keep lines that have actual text content (not just spaces/symbols)
                if cleaned and len(cleaned) > 2 and not cleaned.isspace():
                    # Truncate long lines
                    if len(cleaned) > 60:
                        cleaned = cleaned[:57] + "..."
                    cleaned_lines.append(f"  {cleaned}")
            
            # If no meaningful content found, try to get raw content without heavy filtering
            if not cleaned_lines:
                # Just get non-empty lines without box characters
                for line in lines_list:
                    simple_clean = line.strip()
                    # Check if line has actual text (not just box drawing chars)
                    if simple_clean:
                        # Remove only pure box drawing lines
                        has_text = False
                        for char in simple_clean:
                            if char.isalnum() or char in '!@#$%^&*()_+-={}[]|:";<>?,./':
                                has_text = True
                                break
                        
                        if has_text:
                            if len(simple_clean) > 60:
                                simple_clean = simple_clean[:57] + "..."
                            cleaned_lines.append(f"  {simple_clean}")
            
            return '\n'.join(cleaned_lines) if cleaned_lines else "빈 화면"
            
        except Exception as e:
            return f"오류: {str(e)}"
    
    def format_wait_time(self, seconds: float) -> str:
        """
        Format wait time in human-readable format
        
        Args:
            seconds: Wait time in seconds
            
        Returns:
            Formatted string like "5분", "1시간 23분"
        """
        if seconds < 60:
            return f"{int(seconds)}초"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}분"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            if minutes > 0:
                return f"{hours}시간 {minutes}분"
            return f"{hours}시간"
    
    def generate_summary(self) -> str:
        """
        Generate complete session summary
        
        Returns:
            Formatted summary message for Telegram
        """
        waiting_sessions = self.get_waiting_sessions_with_times()
        
        if not waiting_sessions:
            return "📊 **세션 요약**\n\n✅ 현재 대기 중인 세션이 없습니다."
        
        # Header
        current_time = datetime.now().strftime("%H:%M")
        message = f"📊 **세션 요약**\n_{current_time} 기준_\n\n"
        message += f"**대기 중 세션: {len(waiting_sessions)}개**\n\n"
        
        # Session details
        for i, (session_name, wait_time, last_prompt) in enumerate(waiting_sessions, 1):
            # Format session name
            display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
            
            # Format wait time
            wait_str = self.format_wait_time(wait_time)
            
            # Add separator
            message += "━" * 25 + "\n"
            
            # Session header
            message += f"🎯 **{display_name}** ({wait_str})\n"
            
            # Last prompt if available
            if last_prompt:
                message += f"└ \"{last_prompt}\"\n"
            
            # Screen summary (get more lines for better context)
            screen_summary = self.get_screen_summary(session_name, 5)
            if screen_summary and screen_summary != "빈 화면":
                message += f"\n```\n{screen_summary}\n```\n\n"
            else:
                message += f"\n_화면 대기 중_\n\n"
        
        # Footer with longest waiting session
        if waiting_sessions:
            longest_session, longest_time, _ = max(waiting_sessions, key=lambda x: x[1])
            longest_name = longest_session.replace('claude_', '') if longest_session.startswith('claude_') else longest_session
            message += f"💡 **가장 오래 대기**: {longest_name} ({self.format_wait_time(longest_time)})"
        
        return message
    
    def get_session_wait_time(self, session_name: str) -> Optional[float]:
        """
        Get wait time for a specific session
        
        Args:
            session_name: Name of the session
            
        Returns:
            Wait time in seconds or None if not waiting
        """
        state = self.state_analyzer.get_state_for_notification(session_name)
        
        # Return wait time for non-working sessions
        if state != SessionState.WORKING:
            return self.tracker.get_wait_time(session_name)
        else:
            # Reset wait time for working sessions
            self.tracker.reset_session(session_name)
            return None


# Global instance for shared state
summary_helper = SessionSummaryHelper()