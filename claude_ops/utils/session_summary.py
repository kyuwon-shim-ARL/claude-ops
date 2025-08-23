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
from ..utils.prompt_recall import PromptRecallSystem
from ..session_manager import session_manager

class SessionSummaryHelper:
    """Helper class for generating session summaries"""
    
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
        self.tracker = wait_tracker  # Use the global tracker instance
        self.prompt_recall = PromptRecallSystem()  # Reuse existing prompt extraction
        
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
                # Use PromptRecallSystem for better prompt extraction
                last_prompt = self.prompt_recall.extract_last_user_prompt(session_name)
                # Clean up the prompt if it contains error messages
                if "프롬프트" in last_prompt or "실패" in last_prompt:
                    last_prompt = ""
                waiting_sessions.append((session_name, wait_time, last_prompt))
            else:
                # Reset wait time for working sessions
                self.tracker.reset_session(session_name)
        
        # Sort by wait time (longest first - reverse order)
        waiting_sessions.sort(key=lambda x: x[1], reverse=True)
        return waiting_sessions
    
    # Removed extract_last_prompt - now using PromptRecallSystem.extract_last_user_prompt
    
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
            # Get more lines to find meaningful content
            scan_lines = 50  # Scan last 50 lines to find meaningful content
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{scan_lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return "화면 캡처 실패"
            
            content = result.stdout.strip()
            if not content:
                return "뺈 화면"
            
            # Split into lines and process from bottom up
            all_lines = content.split('\n')
            cleaned_lines = []
            
            # Common UI patterns to skip
            skip_patterns = [
                r'^\s*[⏵⏴▶◀]+\s*accept edits',  # Accept edits UI
                r'^\s*Auto-updating',  # Auto-updating message
                r'^\s*>\s*$',  # Empty prompt
                r'^\s*[─│╭╮╯╰┌┐└┘]+\s*$',  # Box drawing only
                r'^\s*$',  # Empty line
                r'^\s*\?\s+for\s+shortcuts\s*$',  # Shortcuts hint
                r'^\s*shift\+tab\s+to\s+cycle',  # Navigation hint
            ]
            
            # Process lines from bottom up to find most recent meaningful content
            for line in reversed(all_lines):
                # Skip UI patterns
                skip = False
                for pattern in skip_patterns:
                    if re.match(pattern, line):
                        skip = True
                        break
                
                if skip:
                    continue
                
                # Clean the line
                cleaned = re.sub(r'[╭─╮╯╰│┌┐└┘├┤┬┴┼]', ' ', line).strip()
                
                # Check if line has meaningful content
                if cleaned and len(cleaned) > 3:
                    # Skip lines that are just UI elements
                    if 'accept edits' in cleaned.lower() or 'auto-updating' in cleaned.lower():
                        continue
                    if 'shift+tab' in cleaned.lower() or 'esc to interrupt' in cleaned.lower():
                        continue
                    
                    # Truncate long lines
                    if len(cleaned) > 70:
                        cleaned = cleaned[:67] + "..."
                    
                    cleaned_lines.insert(0, f"  {cleaned}")
                    
                    # Stop when we have enough meaningful lines
                    if len(cleaned_lines) >= lines:
                        break
            
            # If still no content, try to get anything that's not pure UI
            if not cleaned_lines:
                for line in reversed(all_lines[-20:]):  # Check last 20 lines
                    simple = line.strip()
                    if simple and not all(c in '─│╭╮╯╰┌┐└┘├┤┬┴┼ >?' for c in simple):
                        if len(simple) > 70:
                            simple = simple[:67] + "..."
                        cleaned_lines.insert(0, f"  {simple}")
                        if len(cleaned_lines) >= 3:
                            break
            
            return '\n'.join(cleaned_lines) if cleaned_lines else "화면 대기 중"
            
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
            if last_prompt and len(last_prompt) > 2:
                # Truncate if too long
                if len(last_prompt) > 60:
                    last_prompt = last_prompt[:57] + "..."
                message += f"💬 {last_prompt}\n"
            
            # Screen summary (get more lines for better context)
            screen_summary = self.get_screen_summary(session_name, 5)
            if screen_summary and screen_summary != "화면 대기 중":
                message += f"\n```\n{screen_summary}\n```\n\n"
            else:
                # Try to get at least the current status
                message += f"\n_화면 대기 중_\n\n"
        
        # Footer with longest waiting session (which is now the first one due to reverse sort)
        if waiting_sessions:
            longest_session, longest_time, _ = waiting_sessions[0]  # First one is the longest now
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