"""
Session Summary Helper for Claude-Ops

Provides summary and analysis of Claude sessions with wait time tracking
"""

import re
import subprocess
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional
from datetime import datetime
from ..utils.session_state import SessionStateAnalyzer, SessionState

logger = logging.getLogger(__name__)
# Import improved tracker with auto-recovery
try:
    from ..utils.wait_time_tracker_v2 import ImprovedWaitTimeTracker, migrate_to_v2
    wait_tracker = migrate_to_v2()  # Auto-migrate on import
except ImportError:
    # Fallback to original tracker if v2 not available
    from ..utils.wait_time_tracker import wait_tracker
from ..utils.prompt_recall import PromptRecallSystem
from ..session_manager import session_manager

class SessionSummaryHelper:
    """Helper class for generating session summaries"""
    
    def __init__(self):
        self.state_analyzer = SessionStateAnalyzer()
        self.tracker = wait_tracker  # Use the global tracker instance
        self.prompt_recall = PromptRecallSystem()  # Reuse existing prompt extraction

    def _get_session_data_batch(self, session_name: str) -> dict:
        """
        Single tmux call, multiple data extraction

        IMPORTANT: Uses 500 lines to match Task 2 fallback depth.
        This ensures prompt extraction can succeed without additional tmux calls.

        Returns:
            dict with keys: content, state, prompt, context_warning, screen_summary
        """
        try:
            # One call with 500 lines (matches Task 2 fallback depth)
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -500",
                shell=True, capture_output=True, text=True, timeout=5
            )

            content = result.stdout if result.returncode == 0 else ""

            return {
                'content': content,
                'state': self.state_analyzer.analyze_from_content(content),  # DRY: reuse existing logic
                'prompt': self._extract_prompt_from_content(content),
                'context_warning': self._detect_context_from_content(content),
                'screen_summary': self._extract_summary_from_content(content, lines=3)
            }
        except Exception as e:
            logger.error(f"Error in batch session data fetch for {session_name}: {e}")
            return {
                'content': '',
                'state': SessionState.UNKNOWN,
                'prompt': '',
                'context_warning': None,
                'screen_summary': '데이터 조회 실패'
            }

    def _extract_prompt_from_content(self, content: str) -> str:
        """
        Extract last user prompt from pre-fetched content
        """
        if not content:
            return ""

        lines = content.split('\n')

        # Simple patterns for user prompts
        simple_patterns = [
            r'^>\s*(.+)$',                    # > 프롬프트
            r'^❯\s*(.+)$',                   # ❯ 프롬프트
            r'^Human:\s*(.+)$',              # Human: 프롬프트
            r'^사용자:\s*(.+)$',              # 한글 사용자:
            r'^@[\w가-힣]+\s+(.+)$',         # @명령어 형태
        ]

        for line in reversed(lines):
            stripped = line.strip()
            for pattern in simple_patterns:
                match = re.match(pattern, stripped)
                if match:
                    prompt_text = match.group(1).strip()
                    if prompt_text and len(prompt_text) >= 5 and len(prompt_text) <= 500:
                        return prompt_text[:100]  # Truncate to 100 chars

        return ""

    def _detect_context_from_content(self, content: str) -> Optional[dict]:
        """
        Detect context warning from pre-fetched content
        """
        if not content:
            return None

        patterns = [
            r'Context\s+left\s+until\s+auto-compact:\s*(\d+)%',
            r'(\d+)%\s*used.*?([~\d,]+[kK]?)\s*(?:tokens?\s*)?remaining',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if "auto-compact" in pattern:
                    remaining_pct = int(match.group(1))
                    usage_pct = 100 - remaining_pct
                    return {
                        'usage_percent': usage_pct,
                        'remaining_tokens': int(200000 * remaining_pct / 100 / 1000)
                    }
                else:
                    return {
                        'usage_percent': int(match.group(1)),
                        'remaining_tokens': int(match.group(2).replace(',', '').replace('k', '000').replace('K', '000').replace('~', ''))
                    }

        return None

    def _extract_summary_from_content(self, content: str, lines: int = 3) -> str:
        """
        Extract screen summary from pre-fetched content
        """
        if not content:
            return "빈 화면"

        all_lines = content.split('\n')
        cleaned = []

        skip_patterns = [
            'accept edits', 'shift+tab', 'esc to interrupt',
            'auto-updating', '? for shortcuts'
        ]

        for line in reversed(all_lines):
            stripped = line.strip()

            if not stripped or len(stripped) < 4:
                continue
            if all(c in '─│╭╮╯╰┌┐└┘├┤┬┴┼ >?' for c in stripped):
                continue
            if any(p in stripped.lower() for p in skip_patterns):
                continue

            safe = stripped.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if len(safe) > 70:
                safe = safe[:67] + "..."

            cleaned.insert(0, f"  {safe}")
            if len(cleaned) >= lines:
                break

        return '\n'.join(cleaned) if cleaned else "화면 대기 중"

    def _get_session_status_sync(self, session_name: str) -> Tuple[str, float, str, str, bool, Optional[dict], str]:
        """
        Synchronous helper for parallel execution (single tmux call via batch).
        Returns 7-tuple: (session_name, wait_time, last_prompt, status, has_record, context_warning, screen_summary)
        """
        try:
            # Single tmux call via batch (replaces 3-5 individual calls)
            batch = self._get_session_data_batch(session_name)
            state = batch['state']
            context_warning = batch['context_warning']
            screen_summary = batch['screen_summary']

            # Quality-checked prompt extraction (reuses PromptRecallSystem logic
            # including _is_meaningful_prompt() filtering and deduplication)
            detected_prompts = self.prompt_recall._detect_user_prompts(batch['content'])
            last_prompt = detected_prompts[-1] if detected_prompts else ""

            # Clean prompt
            if "프롬프트" in last_prompt or "실패" in last_prompt:
                last_prompt = ""

            # Get wait time (unchanged logic)
            if hasattr(self.tracker, 'get_wait_time_since_completion'):
                result = self.tracker.get_wait_time_since_completion(session_name)
                if isinstance(result, tuple) and len(result) == 2:
                    wait_time, has_record = result
                else:
                    wait_time = result
                    has_record = self.tracker.has_completion_record(session_name)
            else:
                wait_time = self.tracker.get_wait_time_since_completion(session_name)
                has_record = self.tracker.has_completion_record(session_name)

            status = 'working' if state == SessionState.WORKING else 'waiting'
            return (session_name, wait_time, last_prompt, status, has_record, context_warning, screen_summary)

        except Exception as e:
            logger.error(f"Error getting status for {session_name}: {e}")
            return (session_name, 0.0, "", 'waiting', False, None, '데이터 조회 실패')

    async def get_all_sessions_with_status_async(self) -> List[Tuple[str, float, str, str, bool, Optional[dict], str]]:
        """
        Get ALL sessions with parallel processing using ThreadPoolExecutor.

        Returns:
            List of 7-tuples: (session_name, wait_time, last_prompt, status, has_record, context_warning, screen_summary)
        """
        sessions = session_manager.get_all_claude_sessions()

        if not sessions:
            return []

        # Use ThreadPoolExecutor for parallel tmux calls
        # Each worker runs 1 subprocess (tmux capture-pane) - safe to parallelize all sessions
        with ThreadPoolExecutor(max_workers=len(sessions)) as executor:
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(executor, self._get_session_status_sync, session)
                for session in sessions
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and sort
        all_sessions = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Parallel session fetch error: {result}")
                continue
            all_sessions.append(result)

        # Sort: working sessions first, then waiting sessions by wait time ASC (shortest wait = most recent at bottom for easy Telegram access)
        all_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,
            x[1] if x[3] == 'waiting' else 0,
            x[0]
        ))

        return all_sessions

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
                # Use user's definition: time since last completion notification
                wait_time, is_accurate = self.tracker.get_wait_time_since_completion(session_name)
                # Use PromptRecallSystem for better prompt extraction
                last_prompt = self.prompt_recall.extract_last_user_prompt(session_name)
                # Clean up the prompt if it contains error messages
                if "프롬프트" in last_prompt or "실패" in last_prompt:
                    last_prompt = ""
                waiting_sessions.append((session_name, wait_time, last_prompt))
            else:
                # Working sessions don't affect completion time tracking
                pass
        
        # Sort by wait time ASC (shortest wait = most recent at top)
        waiting_sessions.sort(key=lambda x: x[1])
        return waiting_sessions
    
    def get_all_sessions_with_status(self) -> List[Tuple[str, float, str, str]]:
        """
        Get ALL sessions (both waiting and working) with their status
        
        Returns:
            List of tuples: (session_name, wait_time_seconds, last_prompt, status)
            status is either 'waiting' or 'working'
        """
        all_sessions = []
        sessions = session_manager.get_all_claude_sessions()
        
        for session_name in sessions:
            # Check current state
            state = self.state_analyzer.get_state_for_notification(session_name)
            
            if state != SessionState.WORKING:
                # Waiting session - use time since last completion
                # Check if we're using v2 tracker with accuracy indicator
                if hasattr(self.tracker, 'get_wait_time_since_completion'):
                    result = self.tracker.get_wait_time_since_completion(session_name)
                    if isinstance(result, tuple) and len(result) == 2:
                        wait_time, is_accurate = result
                        has_record = is_accurate  # v2 tracker provides accuracy
                    else:
                        # Fallback for non-v2 tracker
                        wait_time = result
                        has_record = self.tracker.has_completion_record(session_name)
                else:
                    # Original tracker
                    wait_time = self.tracker.get_wait_time_since_completion(session_name)
                    has_record = self.tracker.has_completion_record(session_name)
                last_prompt = self.prompt_recall.extract_last_user_prompt(session_name)
                if "프롬프트" in last_prompt or "실패" in last_prompt:
                    last_prompt = ""
                # Include transparency info: (session, wait_time, prompt, status, has_completion_record)
                all_sessions.append((session_name, wait_time, last_prompt, 'waiting', has_record))
            else:
                # Working session - still show time since last completion
                # Check if we're using v2 tracker with accuracy indicator
                if hasattr(self.tracker, 'get_wait_time_since_completion'):
                    result = self.tracker.get_wait_time_since_completion(session_name)
                    if isinstance(result, tuple) and len(result) == 2:
                        wait_time, is_accurate = result
                        has_record = is_accurate  # v2 tracker provides accuracy
                    else:
                        # Fallback for non-v2 tracker
                        wait_time = result
                        has_record = self.tracker.has_completion_record(session_name)
                else:
                    # Original tracker
                    wait_time = self.tracker.get_wait_time_since_completion(session_name)
                    has_record = self.tracker.has_completion_record(session_name)
                last_prompt = self.prompt_recall.extract_last_user_prompt(session_name)
                if "프롬프트" in last_prompt or "실패" in last_prompt:
                    last_prompt = ""
                # Include transparency info: (session, wait_time, prompt, status, has_completion_record)  
                all_sessions.append((session_name, wait_time, last_prompt, 'working', has_record))
        
        # Sort: working sessions first, then waiting sessions by wait time ASC (shortest wait = most recent at bottom for easy Telegram access)
        all_sessions.sort(key=lambda x: (
            0 if x[3] == 'working' else 1,
            x[1] if x[3] == 'waiting' else 0,
            x[0]
        ))
        return all_sessions
    
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
                return "빈 화면"
            
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
                    
                    # Escape HTML special characters first
                    cleaned = cleaned.replace('&', '&amp;')
                    cleaned = cleaned.replace('<', '&lt;')
                    cleaned = cleaned.replace('>', '&gt;')
                    # Clean other problematic characters
                    cleaned = cleaned.replace('"', "'")
                    cleaned = cleaned.replace('`', "'")
                    
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
                        # Escape HTML special characters first
                        simple = simple.replace('&', '&amp;')
                        simple = simple.replace('<', '&lt;')
                        simple = simple.replace('>', '&gt;')
                        # Clean other problematic characters
                        simple = simple.replace('"', "'")
                        simple = simple.replace('`', "'")
                        if len(simple) > 70:
                            simple = simple[:67] + "..."
                        cleaned_lines.insert(0, f"  {simple}")
                        if len(cleaned_lines) >= 3:
                            break
            
            return '\n'.join(cleaned_lines) if cleaned_lines else "화면 대기 중"
            
        except Exception as e:
            error_msg = str(e).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f"오류: {error_msg}"
    
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
    
    def escape_markdown(self, text: str) -> str:
        """
        Escape special characters for Telegram Markdown (legacy mode)

        Args:
            text: Text to escape

        Returns:
            Escaped text safe for Markdown
        """
        # For Telegram legacy Markdown, only these need escaping:
        # _ * ` [ ]
        # Note: Do NOT escape backslash or dots - that causes more problems
        text = text.replace('_', '\\_')
        text = text.replace('*', '\\*')
        text = text.replace('`', "'")  # Replace backticks with quotes (safer)
        text = text.replace('[', '(')  # Replace brackets with parentheses (safer)
        text = text.replace(']', ')')
        return text
    
    def _generate_single_session_summary(self, session_name: str) -> str:
        """
        Generate summary for a single session with context info
        
        Args:
            session_name: Name of the session
            
        Returns:
            Formatted summary with context status
        """
        try:
            # Get session status
            state = self.state_analyzer.get_state_for_notification(session_name)
            status_text = "작업 중" if state == SessionState.WORKING else "대기 중"
            
            # Get context warning info
            context_info = None
            try:
                # Try to get screen content for context detection
                result = subprocess.run(
                    f"tmux capture-pane -t {session_name} -p -S -100",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                tmux_output = result.stdout if result.returncode == 0 else None
            except Exception:
                tmux_output = None
            
            # Build summary message
            message = f"📊 **세션 요약**\n\n"
            message += f"**세션:** {session_name}\n"
            message += f"**상태:** {status_text}\n"
            
            # Add context status with proper error handling
            try:
                # Try to detect context warning - may raise exception
                context_info = self._detect_context_warning(tmux_output)
                
                if context_info:
                    usage = context_info['usage_percent']
                    remaining = context_info['remaining_tokens']
                    
                    # Format remaining tokens
                    if remaining >= 1000:
                        remaining_str = f"{remaining // 1000}K 토큰 남음"
                    else:
                        remaining_str = f"{remaining} 토큰 남음"
                    
                    # Choose appropriate message based on usage
                    if usage >= 90:
                        message += f"⚠️ 컨텍스트: {usage}% 사용됨 ({remaining_str}) - 곧 정리 필요\n"
                    else:
                        message += f"📊 컨텍스트: {usage}% 사용됨 ({remaining_str})\n"
                else:
                    message += "📊 컨텍스트: 여유\n"
            except Exception:
                message += "📊 컨텍스트: 상태 확인 불가\n"
            
            return message
            
        except Exception as e:
            return f"오류 발생: {str(e)}"
    
    def _detect_context_warning(self, tmux_output: str = None, session_name: str = None) -> Optional[dict]:
        """
        Detect context warning from tmux output or screen content
        
        Args:
            tmux_output: Optional tmux output to parse. If None, fetches from session
            session_name: Session name to get tmux output from (if tmux_output is None)
            
        Returns:
            Dict with usage_percent, remaining_tokens, total_tokens or None if no warning
        """
        try:
            if tmux_output is None and session_name:
                # Get raw screen content from specific session for context detection
                # Don't use get_screen_summary as it filters out UI elements
                try:
                    import subprocess
                    result = subprocess.run(
                        ["tmux", "capture-pane", "-t", session_name, "-p"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    
                    if result.returncode == 0:
                        tmux_output = result.stdout.strip()
                        if not tmux_output:
                            return None
                    else:
                        return None
                except Exception:
                    return None
            elif tmux_output is None:
                # Neither tmux_output nor session_name provided
                return None
            
            # Pattern matching for various context warning formats
            # Claude typically shows warnings like:
            # "Context window approaching limit (85% used, ~15K tokens remaining)"
            # "⚠️ Context window: 85% used (~15,000 tokens remaining)"
            # "Context: 85% (15K remaining)"
            
            patterns = [
                r'(\d+)%\s*used.*?([~\d,]+[kK]?)\s*(?:tokens?\s*)?remaining',
                r'Context.*?(\d+)%.*?([~\d,]+[kK]?)\s*remaining',
                r'⚠️.*?Context.*?(\d+)%.*?([~\d,]+[kK]?)',
                # Pattern for "Context left until auto-compact: 6%" format
                r'Context\s+left\s+until\s+auto-compact:\s*(\d+)%',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, tmux_output, re.IGNORECASE)
                if match:
                    # Check if this is the "Context left until auto-compact: X%" pattern
                    if "auto-compact" in pattern:
                        remaining_percent = int(match.group(1))
                        usage_percent = 100 - remaining_percent  # Convert to usage percent
                        
                        # Estimate tokens based on typical Claude context windows
                        # Assuming ~200K context window (conservative estimate)
                        estimated_total = 200000
                        remaining_tokens = int(estimated_total * (remaining_percent / 100))
                        
                        return {
                            'usage_percent': usage_percent,
                            'remaining_tokens': int(remaining_tokens / 1000),  # Convert to K tokens
                            'total_tokens': estimated_total
                        }
                    else:
                        # Original token-based patterns
                        usage_percent = int(match.group(1))
                        
                        # Parse remaining tokens
                        remaining_str = match.group(2).replace(',', '').replace('~', '')
                        if 'k' in remaining_str.lower():
                            remaining_tokens = int(float(remaining_str.replace('k', '').replace('K', '')) * 1000)
                        else:
                            remaining_tokens = int(remaining_str)
                        
                        # Estimate total tokens from percentage and remaining
                        if usage_percent > 0:
                            total_tokens = int(remaining_tokens / ((100 - usage_percent) / 100))
                        else:
                            total_tokens = remaining_tokens
                        
                        return {
                            'usage_percent': usage_percent,
                            'remaining_tokens': remaining_tokens,
                            'total_tokens': total_tokens
                        }
            
            return None
            
        except Exception:
            # Silent fail - context detection is optional feature
            return None
    
    def generate_summary(self, session_name: str = None) -> str:
        """
        Generate complete session summary or single session summary with context info
        
        Args:
            session_name: Optional session name for single session summary
        
        Returns:
            Formatted summary message for Telegram
        """
        # For single session summary (used in tests)
        if session_name:
            return self._generate_single_session_summary(session_name)
        
        # Original multi-session summary
        all_sessions = self.get_all_sessions_with_status()
        
        if not all_sessions:
            return "📊 **세션 요약**\n\n✅ 현재 활성 세션이 없습니다."
        
        # Count waiting and working sessions  
        waiting_count = sum(1 for s in all_sessions if s[3] == 'waiting')
        working_count = sum(1 for s in all_sessions if s[3] == 'working')
        
        # Count sessions using fallback estimates
        fallback_count = sum(1 for s in all_sessions if not s[4])  # s[4] is has_record
        
        # Header with HTML formatting
        current_time = datetime.now().strftime("%H:%M")
        message = f"📊 <b>세션 요약</b> ({current_time} 기준)\n\n"
        message += f"<b>전체 세션: {len(all_sessions)}개</b> (대기: {waiting_count}, 작업중: {working_count})\n\n"

        # Session details
        for i, (session_name, wait_time, last_prompt, status, has_record) in enumerate(all_sessions, 1):
            # Format session name
            display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name

            # Add separator
            message += "━" * 25 + "\n"

            # Session header with bold
            if status == 'working':
                message += f"🔨 <b>{display_name}</b> (작업 중)\n"
            else:
                wait_str = self.format_wait_time(wait_time)
                message += f"🎯 <b>{display_name}</b> ({wait_str} 대기)\n"

            # Add copyable command wrapped in HTML code tag
            message += f"    ↳ <code>/sessions {session_name}</code>\n"

            # Last prompt if available
            if last_prompt and len(last_prompt) > 2:
                # Escape HTML special characters
                last_prompt = last_prompt.replace('&', '&amp;')
                last_prompt = last_prompt.replace('<', '&lt;')
                last_prompt = last_prompt.replace('>', '&gt;')
                # Truncate if too long
                if len(last_prompt) > 60:
                    last_prompt = last_prompt[:57] + "..."
                message += f"💬 <i>{last_prompt}</i>\n"

            # Context status for each session
            try:
                context_info = self._detect_context_warning(session_name=session_name)
                if context_info:
                    usage_percent = context_info['usage_percent']
                    remaining_tokens = context_info['remaining_tokens']

                    if usage_percent >= 90:
                        message += f"⚠️ 컨텍스트: {usage_percent}% ({remaining_tokens}K 남음)\n"
                    else:
                        message += f"📊 컨텍스트: {usage_percent}% ({remaining_tokens}K 남음)\n"
                else:
                    message += f"📊 컨텍스트: 여유\n"
            except Exception:
                message += f"📊 컨텍스트: 확인 불가\n"

            # Screen summary in code block (HTML <pre> tag)
            screen_summary = self.get_screen_summary(session_name, 3)
            if screen_summary and screen_summary not in ["화면 대기 중", "빈 화면", "화면 캡처 실패"]:
                # Ensure no unclosed tags - double check HTML escaping
                safe_summary = screen_summary.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                # Avoid double escaping
                safe_summary = safe_summary.replace('&amp;amp;', '&amp;').replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
                message += f"\n<pre>{safe_summary}</pre>\n\n"
            else:
                message += "\n"

        # Footer with longest waiting session
        waiting_sessions = [(s[0], s[1]) for s in all_sessions if s[3] == 'waiting']
        if waiting_sessions:
            longest_session, longest_time = max(waiting_sessions, key=lambda x: x[1])
            longest_name = longest_session.replace('claude_', '') if longest_session.startswith('claude_') else longest_session
            message += f"💡 <b>가장 오래 대기</b>: {longest_name} ({self.format_wait_time(longest_time)})"
        
        return message

    async def generate_summary_async(self, session_name: str = None) -> str:
        """
        Async version of generate_summary() - uses parallel batch fetching.
        Eliminates N+1 tmux queries by using enriched 7-tuple data.

        Args:
            session_name: Optional session name for single session summary

        Returns:
            Formatted summary message for Telegram (identical HTML to sync version)
        """
        # For single session summary (used in tests) - delegate to sync
        if session_name:
            return self._generate_single_session_summary(session_name)

        # Async parallel fetch - 1 tmux call per session, all in parallel
        all_sessions = await self.get_all_sessions_with_status_async()

        if not all_sessions:
            return "📊 **세션 요약**\n\n✅ 현재 활성 세션이 없습니다."

        # Count waiting and working sessions
        waiting_count = sum(1 for s in all_sessions if s[3] == 'waiting')
        working_count = sum(1 for s in all_sessions if s[3] == 'working')

        # Header with HTML formatting
        current_time = datetime.now().strftime("%H:%M")
        message = f"📊 <b>세션 요약</b> ({current_time} 기준)\n\n"
        message += f"<b>전체 세션: {len(all_sessions)}개</b> (대기: {waiting_count}, 작업중: {working_count})\n\n"

        # Session details - uses enriched 7-tuple (no additional tmux calls)
        for i, (sess_name, wait_time, last_prompt, status, has_record, context_warning, screen_summary) in enumerate(all_sessions, 1):
            # Format session name
            display_name = sess_name.replace('claude_', '') if sess_name.startswith('claude_') else sess_name

            # Add separator
            message += "━" * 25 + "\n"

            # Session header with bold
            if status == 'working':
                message += f"🔨 <b>{display_name}</b> (작업 중)\n"
            else:
                wait_str = self.format_wait_time(wait_time)
                message += f"🎯 <b>{display_name}</b> ({wait_str} 대기)\n"

            # Add copyable command wrapped in HTML code tag
            message += f"    ↳ <code>/sessions {sess_name}</code>\n"

            # Last prompt if available
            if last_prompt and len(last_prompt) > 2:
                # Escape HTML special characters
                escaped_prompt = last_prompt.replace('&', '&amp;')
                escaped_prompt = escaped_prompt.replace('<', '&lt;')
                escaped_prompt = escaped_prompt.replace('>', '&gt;')
                # Truncate if too long
                if len(escaped_prompt) > 60:
                    escaped_prompt = escaped_prompt[:57] + "..."
                message += f"💬 <i>{escaped_prompt}</i>\n"

            # Context status from batch data (no additional tmux call)
            try:
                if context_warning:
                    usage_percent = context_warning['usage_percent']
                    remaining_tokens = context_warning['remaining_tokens']

                    if usage_percent >= 90:
                        message += f"⚠️ 컨텍스트: {usage_percent}% ({remaining_tokens}K 남음)\n"
                    else:
                        message += f"📊 컨텍스트: {usage_percent}% ({remaining_tokens}K 남음)\n"
                else:
                    message += f"📊 컨텍스트: 여유\n"
            except Exception:
                message += f"📊 컨텍스트: 확인 불가\n"

            # Screen summary from batch data (no additional tmux call)
            if screen_summary and screen_summary not in ["화면 대기 중", "빈 화면", "화면 캡처 실패", "데이터 조회 실패"]:
                # Ensure no unclosed tags - double check HTML escaping
                safe_summary = screen_summary.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                # Avoid double escaping
                safe_summary = safe_summary.replace('&amp;amp;', '&amp;').replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
                message += f"\n<pre>{safe_summary}</pre>\n\n"
            else:
                message += "\n"

        # Footer with longest waiting session
        waiting_sessions = [(s[0], s[1]) for s in all_sessions if s[3] == 'waiting']
        if waiting_sessions:
            longest_session, longest_time = max(waiting_sessions, key=lambda x: x[1])
            longest_name = longest_session.replace('claude_', '') if longest_session.startswith('claude_') else longest_session
            message += f"💡 <b>가장 오래 대기</b>: {longest_name} ({self.format_wait_time(longest_time)})"

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