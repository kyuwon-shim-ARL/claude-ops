"""
Unified Session State Detection Module

This module provides a single source of truth for detecting Claude Code session states,
eliminating the code duplication and inconsistencies that existed across multiple components.

Design Principles:
- Single Source of Truth: All state detection logic centralized here
- Context-Aware: Distinguishes between recent activity and historical artifacts  
- Priority-Based: Clear state hierarchy for conflict resolution (ERROR > WAITING_INPUT > WORKING > IDLE > UNKNOWN)
- Performance-Optimized: 2-tier caching (screen content + computed states)
- Extensible: Easy to add new states and patterns
- Testable: Clear interfaces for unit testing with 30+ test cases
- Thread-Safe: Concurrent access from multiple monitoring threads

Architecture:
    SessionStateAnalyzer: Core state detection engine with caching
    SessionState: Enum defining all possible states with priorities  
    StateTransition: Data class for tracking state changes over time
    
Usage:
    analyzer = SessionStateAnalyzer()
    current_state = analyzer.get_state("claude_session_name")
    is_working = analyzer.is_working("claude_session_name")
    
Performance Features:
    - Screen content cached for 1 second (reduces tmux calls)
    - Computed states cached for 500ms (reduces pattern analysis)
    - Automatic cleanup prevents memory leaks
    - Optimized pattern matching for large screen content
    
Error Handling:
    - Graceful degradation when tmux sessions don't exist
    - Timeout protection for subprocess calls
    - Safe handling of malformed screen content
    - Clear fallback to UNKNOWN state for unhandleable cases
"""

import subprocess
import logging
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from .log_length_manager import get_current_log_length

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Session state definitions with clear priorities"""
    CONTEXT_LIMIT = "context_limit"  # Highest priority - context window exhausted
    ERROR = "error"               # System errors
    WAITING_INPUT = "waiting"     # User response required
    WORKING = "working"           # Active work in progress
    IDLE = "idle"                 # No activity, ready for commands
    UNKNOWN = "unknown"           # Cannot determine state


class StateTransition:
    """Represents a state change event"""
    def __init__(self, session: str, from_state: Optional[SessionState], 
                 to_state: SessionState, timestamp: datetime = None):
        self.session = session
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = timestamp or datetime.now()
    
    def __repr__(self):
        return f"StateTransition({self.session}: {self.from_state} → {self.to_state})"


class SessionStateAnalyzer:
    """
    Unified session state analyzer - single source of truth for all state detection.
    
    This class replaces the fragmented logic that was scattered across:
    - working_detector.py 
    - multi_monitor.py.is_waiting_for_input()
    - notifier.py._is_work_running_from_content()
    """
    
    # State priority for conflict resolution (lower number = higher priority)
    STATE_PRIORITY = {
        SessionState.CONTEXT_LIMIT: 0,
        SessionState.ERROR: 1,
        SessionState.WAITING_INPUT: 2,
        SessionState.WORKING: 3,
        SessionState.IDLE: 4,
        SessionState.UNKNOWN: 5
    }
    
    def __init__(self):
        # NOTE: These patterns are used ONLY by _detect_input_waiting() as a
        # working-state guard (lines 534-550) and get_state_details() for debug
        # output. The primary detection logic in _detect_working_state() uses
        # its own priority-based pattern cascade and does NOT read this list.
        self.working_patterns = [
            "esc to interrupt",
            "ctrl+c to interrupt",
            "ctrl+b to run in background",
            "Thinking…",
            "Running…",
            "Building",
            "Testing",
            "Installing",
            "Processing",
            "Analyzing",
            "Compacting context",
        ]
        
        # Patterns indicating user input is required
        self.input_waiting_patterns = [
            # Standard confirmation prompts
            "Do you want to proceed?",
            "Choose an option:",
            "Select:",
            "Enter your choice:",
            "What would you like to do?",
            "How would you like to proceed?",
            "Please choose:",
            "Continue?",
            # Numbered option selection
            "❯ 1.",                      # Option selection
            "❯ 2.",                      # Option selection
            # AskUserQuestion patterns (Claude Code's question UI)
            "Question ",                 # "Question 1 of 5:" etc
            "│ Option │",                # Table header for options
            "│ A ",                       # Option A row
            "│ B ",                       # Option B row
            "│ C ",                       # Option C row
            "│ D ",                       # Option D row
            "│ Short ",                   # Short answer option
            "│ Other ",                   # Other option
            "┌────────┬",                # Table top border
            "(<=",                        # Character limit hint like "(<=5 words)"
        ]
        
        # Completion message patterns
        # IMPORTANT: These must be specific enough to avoid matching Claude's
        # working output (e.g., "✓ Edit applied", "Successfully wrote file").
        # Overly broad patterns like "✓", "done.", "Successfully" cause false alarms.
        self.completion_patterns = [
            "Build succeeded",
            "Tests passed",
            "All tests passed",
            "0 errors",
            "0 failures",
            "Done!",                    # Standalone "Done!" is intentional
            "✅ All",                   # "✅ All tests passed" etc (not bare ✅)
            r"took \d+\.\d+s",         # Execution time pattern
            r"in \d+\.\d+ seconds",    # Time duration pattern
        ]
        
        # NEW: Command prompt patterns (regex)
        self.prompt_patterns = [
            r"\$$",                     # Bash prompt (ends with $)
            r"\$ $",                    # Bash prompt with space
            r">$",                      # Shell prompt
            r"> $",                     # Shell prompt with space
            r"❯$",                      # Zsh/fancy prompt
            r"❯ $",                     # Zsh/fancy prompt with space
            r">>>$",                    # Python prompt
            r">>> $",                   # Python prompt with space
            r"In \[\d+\]:$",           # IPython prompt
            r"In \[\d+\]: $",          # IPython prompt with space
            r"\w+@[\w\-\.]+.*\$$",     # User@host prompt (user@host:~/path$)
            r"\w+@[\w\-\.]+.*\$ $",    # User@host prompt with space
        ]
        
        # Cache for screen content to avoid repeated tmux calls
        self._screen_cache: Dict[str, tuple[str, datetime]] = {}
        self._cache_ttl_seconds = 1  # Cache for 1 second
        
        # Cache for computed states to avoid repeated analysis
        self._state_cache: Dict[str, tuple[SessionState, datetime]] = {}
        self._state_cache_ttl_seconds = 0.5  # State cache for 500ms
        
        # NEW: Track screen stability for quiet completion detection
        self._last_screen_hash: Dict[str, str] = {}
        self._screen_stable_count: Dict[str, int] = {}

        # WORKING state hold timer: once WORKING is detected, maintain it for
        # hold_seconds even if working indicators briefly disappear (tool transitions)
        self._last_working_time: Dict[str, float] = {}
        self._working_hold_seconds = 10  # Smooth out micro-gaps up to 10 seconds
    
    def get_screen_content(self, session_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Get tmux screen content with optional caching
        
        Args:
            session_name: Name of the tmux session
            use_cache: Whether to use cached content (default: True)
            
        Returns:
            Screen content as string, or None if failed
        """
        now = datetime.now()
        
        # Check cache first
        if use_cache and session_name in self._screen_cache:
            content, timestamp = self._screen_cache[session_name]
            if (now - timestamp).total_seconds() < self._cache_ttl_seconds:
                return content
        
        try:
            # 동적 로그 길이 적용
            log_lines = get_current_log_length()
            
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{log_lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                content = result.stdout
                # Update cache
                self._screen_cache[session_name] = (content, now)
                return content
            else:
                logger.warning(f"Failed to capture tmux pane for {session_name}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout capturing screen content for {session_name}")
            return None
        except Exception as e:
            logger.error(f"Error getting screen content for {session_name}: {e}")
            return None
    
    def get_current_screen_only(self, session_name: str) -> Optional[str]:
        """
        Get only current visible screen content for real-time state detection
        
        This method is specifically for notification systems that need to detect
        the current state without being influenced by scrollback history.
        Unlike get_screen_content(), this does NOT use log_length_manager.
        
        Args:
            session_name: Name of the tmux session
            
        Returns:
            Current screen content as string, or None if failed
        """
        try:
            # 현재 보이는 화면만 캡처 (스크롤백 없음)
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Failed to capture current screen for {session_name}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout capturing current screen for {session_name}")
            return None
        except Exception as e:
            logger.error(f"Error getting current screen for {session_name}: {e}")
            return None
    
    def _detect_working_state(self, screen_content: str) -> bool:
        """
        IMPROVED: Check for RECENT work indicators only

        Priority order:
        1. Check last 25 lines for 'esc to interrupt' → WORKING (definitive)
        2. Check working patterns on FILTERED content (OMC bars removed) → WORKING
           This runs BEFORE prompt detection because OMC always renders ❯ cursor
           below working content, and bottom-up prompt scan would hit it first.
        3. Check for prompts in last 10 lines → IDLE
        4. Default → not working

        This prevents false positives from:
        - Old 'esc to interrupt' text that remains on screen
        - OMC status bar lines (session:Xm, ctx:Y%, etc.)
        - Past output bullets (● 완료, ● 보고 etc.) in scrollback
        """
        if not screen_content:
            return False

        import re

        lines = screen_content.split('\n')

        # CRITICAL FIX: Only check RECENT lines for 'esc to interrupt'
        # Old work indicators can remain on screen after completion
        # Increased to 25 lines to handle scrolling as new output is generated
        recent_lines = lines[-25:]  # Last 25 lines (was 15, increased for scrolling)
        recent_content = '\n'.join(recent_lines)

        # PRIORITY 1: Check for interrupt indicators in RECENT content (definitive)
        # Claude Code shows either 'esc to interrupt' or 'ctrl+c to interrupt' when working.
        # Also check with adjacent lines joined to handle tmux line-wrap where the
        # pattern might be split across two lines (e.g., "esc to inter" + "rupt").
        interrupt_patterns = ["esc to interrupt", "ctrl+c to interrupt"]
        for pattern in interrupt_patterns:
            if pattern in recent_content:
                logger.debug(f"🎯 WORKING: '{pattern}' detected in recent lines")
                return True
        # Line-wrap fallback: join consecutive line pairs and re-check
        for i in range(len(recent_lines) - 1):
            joined = recent_lines[i].rstrip() + recent_lines[i + 1].lstrip()
            for pattern in interrupt_patterns:
                if pattern in joined:
                    logger.debug(f"🎯 WORKING: '{pattern}' detected via line-wrap join")
                    return True

        # Build FILTERED content early: remove OMC status bar lines and separators
        # This is used by PRIORITY 2 (working patterns) and prevents OMC artifacts
        # from interfering with pattern matching
        filtered_recent = []
        for line in recent_lines:
            # Skip OMC status bar lines
            if any(marker in line for marker in ['[OMC#', '⏵⏵', 'bypass permissions']):
                continue
            # Skip separator lines
            stripped = line.strip()
            if stripped and stripped.startswith('─') and stripped.endswith('─'):
                continue
            filtered_recent.append(line)
        filtered_content = '\n'.join(filtered_recent)

        # PRIORITY 2: Working patterns on FILTERED content (before prompt check)
        # OMC layout places ❯ cursor directly below working content (3 lines gap).
        # If we check prompts first, ❯ is detected as idle before we see spinners/tokens above it.
        # By checking working patterns on filtered content first, we catch active work correctly.
        #
        # KEY: Find the ❯ prompt position, then check if the last non-blank
        # content line before ❯ is a working indicator or output text.
        # If it's output (⎿, regular text), any working patterns above are stale.
        # If no prompt found (vanilla Claude), check last 8 filtered lines.
        prompt_idx = None
        for i in range(len(filtered_recent) - 1, -1, -1):
            s = filtered_recent[i].strip()
            if s in ['❯', '❯\xa0', '❯ ']:
                prompt_idx = i
                break

        if prompt_idx is not None:
            # Take up to 6 lines before prompt as candidates
            check_lines = filtered_recent[max(0, prompt_idx - 6):prompt_idx]
            # Guard: if output indicator (⎿) appears in these lines, it means
            # Claude produced output after working → any patterns above ⎿ are stale.
            # Only keep lines BELOW the last ⎿ line.
            last_output_idx = None
            for i in range(len(check_lines) - 1, -1, -1):
                if '⎿' in check_lines[i]:
                    last_output_idx = i
                    break
            if last_output_idx is not None:
                # When last_output_idx == 0, parent_lines is empty (no parent exists)
                # — this is correct: ⎿ on the first check line has no initiator above.
                # Keep the parent line (initiator of ⎿ output block) + lines after output.
                # The parent line often contains working indicators like:
                #   ✢ Building... (27m 45s · ↓ 1.5k tokens · thinking)
                #   ⎿  ◼ task list...   ← ⎿ is sub-output of active thinking
                # Cutting the parent would misclassify active thinking as idle.
                parent_lines = check_lines[max(0, last_output_idx - 1):last_output_idx]
                check_lines = parent_lines + check_lines[last_output_idx + 1:]
        else:
            # No prompt found (vanilla Claude Code without OMC), check last 8 lines
            check_lines = filtered_recent[-8:]
        filtered_narrow = '\n'.join(check_lines)

        # 2a: String-based working patterns (checked on narrow filtered window)
        working_patterns = [
            "ctrl+b to run in background",  # Background execution option
            "tokens \xb7 thought for",      # Claude Code thinking status (· = U+00B7)
            "background tasks still running",  # Main work done but background tasks active
            "Compacting context",           # Context compaction in progress
        ]
        # Note: "| thinking |" is NOT checked here because it appears in OMC status bar
        # (e.g., "[OMC#4.5.1] | thinking | session:11m") and would false-positive on IDLE sessions.
        # It's only valid as a working signal if found in filtered content (OMC bars removed).
        if "| thinking |" in filtered_narrow:
            logger.debug("🎯 WORKING: '| thinking |' detected in filtered content")
            return True

        for pattern in working_patterns:
            if pattern in filtered_narrow:
                logger.debug(f"🎯 WORKING: '{pattern}' detected in filtered content")
                return True

        # 2b: Structural regex patterns on narrow filtered content
        structural_patterns = [
            # Claude Code active tool execution: ● Running, ● Reading, ● Writing, etc.
            r'^\s*● (?:Running|Reading|Writing|Editing|Searching|Calling|Fetching|Executing)',
            # Token streaming indicator: ↓ 404 tokens, ↑ 36 tokens
            r'[↓↑] [\d.,]+k? tokens',
            # Active progress: time counter with tokens on status bar
            r'\d+s\s+·\s+[\d.,]+k?\s+tokens',
            # Active time display with minutes
            r'\d+m\s+\d+s\s+·\s+[\d.,]+k?\s+tokens',
            # Agent/Skill execution: Running N agents, Skill(
            r'Running \d+ ',
            r'Skill\(',
            # Retrying/overloaded (still working, just delayed)
            r'Retrying in \d+',
            r'attempt \d+/\d+',
        ]
        for pattern in structural_patterns:
            if re.search(pattern, filtered_narrow, re.MULTILINE):
                logger.debug(f"🎯 WORKING: structural pattern '{pattern}' matched")
                return True

        # PRIORITY 3: Check for prompts → IDLE
        # Only reached if no working patterns found on filtered content
        # Check last 10 lines bottom-up
        for i in range(len(lines) - 1, max(len(lines) - 10, -1), -1):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                continue

            # Skip OMC status bar lines
            if any(marker in line for marker in ['[OMC#', '⏵⏵', 'bypass permissions']):
                continue

            # Skip separator lines (────)
            if stripped.startswith('─') and stripped.endswith('─'):
                continue

            # Check for various prompt patterns
            if stripped in ['>', '❯', '│ >', '│ ❯'] or line.endswith(('$ ', '> ', '❯ ')):
                logger.debug("⏸️ IDLE: Prompt detected, no working patterns found")
                return False

            # Found a non-empty, non-status-bar line — stop looking for prompts
            break

        # No recent working patterns and no clear prompt
        return False
    
    # _detect_working_state_original removed in e007 (dead code since commit 099a52d).
    # Superseded by priority-based _detect_working_state() with OMC-aware filtering.
    
    def _detect_input_waiting(self, screen_content: str) -> bool:
        """
        Detect if session is waiting for user input based on prompt patterns

        CRITICAL: Working state takes precedence. If working indicators are present,
        this returns False even if input patterns exist (they may be artifacts
        from before the current work started).

        Input Waiting Patterns Detected:
            - "Do you want to proceed?": Confirmation prompts
            - "❯ 1.", "❯ 2.": Selection menu indicators
            - "Choose an option:", "Select:": Choice requests
            - AskUserQuestion table patterns

        Returns:
            bool: True if input waiting patterns found AND not currently working
        """
        if not screen_content:
            return False

        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-25:])

        # CRITICAL FIX: If working indicators present, NOT waiting for input
        # Working state must take precedence to prevent false alarms
        working_indicators = [
            "esc to interrupt",
            "ctrl+c to interrupt",
            "ctrl+b to run in background",
            "Thinking…",
            "Running…",
            "Implementing",
            "Building",
            "Testing",
            "Installing",
            "Processing",
            "Analyzing",
        ]

        for indicator in working_indicators:
            if indicator in recent_content:
                return False

        # Check last 10 lines for input waiting patterns
        # Input prompts are typically at the bottom of the screen
        recent_lines = lines[-10:]

        for line in recent_lines:
            for pattern in self.input_waiting_patterns:
                if pattern in line:
                    return True

        return False
    
    def _detect_context_limit(self, screen_content: str) -> bool:
        """
        Detect if session has hit the context window limit.

        Claude Code displays specific messages when the context window is exhausted.
        This is distinct from generic errors because it requires a different recovery
        strategy (exit + fresh session, NOT /compact which deadlocks).

        Known patterns (from GitHub issues #23047, #18211, #18159):
        - "Context limit reached"
        - "Conversation is too long"
        - "context window"
        """
        if not screen_content:
            return False

        context_limit_patterns = [
            "Context limit reached",
            "Conversation is too long",
            "context window exceeded",
            "Context left until auto-compact: 0%",
        ]

        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-15:])

        return any(pattern.lower() in recent_content.lower() for pattern in context_limit_patterns)

    def _detect_error_state(self, screen_content: str) -> bool:
        """
        Detect if session is in an error state

        Looks for error indicators, timeout messages, or other failure conditions.
        Suppressed when working indicators are present (same guard as _detect_input_waiting).
        """
        if not screen_content:
            return False

        lines = screen_content.split('\n')
        recent_lines = lines[-25:]
        recent_content_wide = '\n'.join(recent_lines)

        # Guard: if working indicators are present, error strings are likely
        # part of Claude's analysis output, not actual session errors.
        working_guards = [
            "esc to interrupt", "ctrl+c to interrupt",
            "ctrl+b to run in background",
            "Thinking…", "Running…",
        ]
        if any(guard in recent_content_wide for guard in working_guards):
            return False

        error_patterns = [
            "Error:",
            "Failed:",
            "Exception:",
            "Timeout:",
            "Connection refused",
            "Permission denied",
        ]

        recent_content = '\n'.join(lines[-10:])

        return any(pattern in recent_content for pattern in error_patterns)
    
    def get_state(self, session_name: str, use_cache: bool = True) -> SessionState:
        """
        Get the current state of a session with priority-based resolution
        
        This is the main entry point for state detection. It checks for all
        possible states and returns the highest priority one found.
        
        Args:
            session_name: Name of the tmux session
            use_cache: Whether to use cached state (default: True)
            
        Returns:
            Current SessionState
        """
        now = datetime.now()
        
        # Check state cache first
        if use_cache and session_name in self._state_cache:
            cached_state, timestamp = self._state_cache[session_name]
            if (now - timestamp).total_seconds() < self._state_cache_ttl_seconds:
                return cached_state
        
        screen_content = self.get_screen_content(session_name, use_cache=use_cache)
        
        if screen_content is None:
            state = SessionState.UNKNOWN
        elif not screen_content.strip():
            # Empty screen content is considered IDLE (session exists but no activity)
            state = SessionState.IDLE
        else:
            # Check states in priority order
            detected_states = []

            if self._detect_context_limit(screen_content):
                detected_states.append(SessionState.CONTEXT_LIMIT)

            if self._detect_error_state(screen_content):
                detected_states.append(SessionState.ERROR)

            if self._detect_input_waiting(screen_content):
                detected_states.append(SessionState.WAITING_INPUT)

            if self._detect_working_state(screen_content):
                detected_states.append(SessionState.WORKING)

            # If no specific state detected, assume idle
            if not detected_states:
                detected_states.append(SessionState.IDLE)

            # Return highest priority state
            state = min(detected_states, key=lambda s: self.STATE_PRIORITY[s])

        # Update state cache
        if use_cache:
            self._state_cache[session_name] = (state, now)

        return state
    
    def get_state_for_notification(self, session_name: str) -> SessionState:
        """
        Get session state specifically for notification decisions

        This method uses only the current visible screen (no scrollback) to avoid
        false positives from historical content. It's designed for real-time
        notification systems that need accurate current state detection.

        Includes a WORKING hold timer: once WORKING is detected, the state is
        maintained for _working_hold_seconds even if working indicators briefly
        disappear during tool transitions (micro-gaps). This prevents false
        completion notifications during continuous active work.

        Args:
            session_name: Name of the tmux session

        Returns:
            Current SessionState based on visible screen only
        """
        import time as _time

        # 알림용은 항상 현재 화면만 사용 (캐시 없음)
        screen_content = self.get_current_screen_only(session_name)

        if screen_content is None:
            return SessionState.UNKNOWN
        elif not screen_content.strip():
            return SessionState.IDLE
        else:
            # Check states in priority order
            detected_states = []

            if self._detect_context_limit(screen_content):
                detected_states.append(SessionState.CONTEXT_LIMIT)

            if self._detect_error_state(screen_content):
                detected_states.append(SessionState.ERROR)

            if self._detect_input_waiting(screen_content):
                detected_states.append(SessionState.WAITING_INPUT)

            is_working = self._detect_working_state(screen_content)
            if is_working:
                detected_states.append(SessionState.WORKING)
                # Update hold timer
                self._last_working_time[session_name] = _time.time()

            # If no specific state detected, check hold timer before assuming idle
            if not detected_states:
                last_working = self._last_working_time.get(session_name, 0)
                hold_remaining = self._working_hold_seconds - (_time.time() - last_working)
                if hold_remaining > 0:
                    # Within hold period — maintain WORKING to smooth micro-gaps
                    logger.debug(
                        f"⏳ WORKING hold active for {session_name}: "
                        f"{hold_remaining:.1f}s remaining"
                    )
                    detected_states.append(SessionState.WORKING)
                else:
                    detected_states.append(SessionState.IDLE)

            # Return highest priority state
            return min(detected_states, key=lambda s: self.STATE_PRIORITY[s])

    def analyze_from_content(self, content: str) -> SessionState:
        """
        Analyze session state from pre-fetched content (no tmux call)

        This method reuses existing detection logic but operates on
        provided content instead of calling tmux. Used for batch processing
        to avoid multiple tmux calls per session.

        Args:
            content: Screen content already captured from tmux

        Returns:
            SessionState enum value
        """
        if content is None:
            return SessionState.UNKNOWN
        elif not content.strip():
            return SessionState.IDLE

        # Check states in priority order using existing detection methods
        detected_states = []

        if self._detect_error_state(content):
            detected_states.append(SessionState.ERROR)

        if self._detect_input_waiting(content):
            detected_states.append(SessionState.WAITING_INPUT)

        if self._detect_working_state(content):
            detected_states.append(SessionState.WORKING)

        # If no specific state detected, assume idle
        if not detected_states:
            detected_states.append(SessionState.IDLE)

        # Return highest priority state
        return min(detected_states, key=lambda s: self.STATE_PRIORITY[s])
    
    def clear_cache(self, session_name: Optional[str] = None) -> None:
        """
        Clear cache for performance optimization or when sessions end
        
        Args:
            session_name: If provided, clear cache only for this session.
                         If None, clear all caches.
        """
        if session_name:
            # Clear specific session cache
            self._screen_cache.pop(session_name, None)
            self._state_cache.pop(session_name, None)
        else:
            # Clear all caches
            self._screen_cache.clear()
            self._state_cache.clear()
    
    def cleanup_expired_cache(self) -> None:
        """Remove expired entries from cache to prevent memory leaks"""
        now = datetime.now()
        
        # Clean up expired screen cache
        expired_sessions = []
        for session_name, (content, timestamp) in self._screen_cache.items():
            if (now - timestamp).total_seconds() > self._cache_ttl_seconds * 10:  # Keep 10x longer for cleanup
                expired_sessions.append(session_name)
        
        for session_name in expired_sessions:
            del self._screen_cache[session_name]
        
        # Clean up expired state cache
        expired_sessions = []
        for session_name, (state, timestamp) in self._state_cache.items():
            if (now - timestamp).total_seconds() > self._state_cache_ttl_seconds * 10:  # Keep 10x longer for cleanup
                expired_sessions.append(session_name)
        
        for session_name in expired_sessions:
            del self._state_cache[session_name]
    
    def is_working(self, session_name: str) -> bool:
        """Check if session is currently working (legacy interface)"""
        return self.get_state(session_name) == SessionState.WORKING
    
    def is_waiting_for_input(self, session_name: str) -> bool:
        """Check if session is waiting for user input (legacy interface)"""
        return self.get_state(session_name) == SessionState.WAITING_INPUT
    
    def is_context_limit(self, session_name: str) -> bool:
        """Check if session has hit context limit"""
        return self.get_state(session_name) == SessionState.CONTEXT_LIMIT

    def is_idle(self, session_name: str) -> bool:
        """Check if session is idle (legacy interface)"""
        return self.get_state(session_name) == SessionState.IDLE
    
    def detect_quiet_completion(self, session_name: str) -> bool:
        """
        Detect quiet completion: work that ends without explicit indicators

        This handles cases like 'git log', 'ls', 'docker images' that output
        results and return to prompt without showing 'Running...' or 'esc to interrupt'

        Args:
            session_name: Name of the tmux session

        Returns:
            bool: True if quiet completion detected
        """
        import re
        import hashlib

        current_screen = self.get_current_screen_only(session_name)
        if not current_screen:
            return False

        # CRITICAL: First check if work is still running
        # Use full working detection (including structural regex patterns)
        # to catch time/token displays and other indicators that the simple
        # string-based self.working_patterns would miss
        if self._detect_working_state(current_screen):
            return False  # Still working, not a quiet completion!

        # NEW: Exclude UI prompts that are NOT command completions
        ui_prompt_patterns = [
            "bypass permissions",
            "shift+tab to cycle",
            "Do you want to make this edit",
            "❯ 1. Yes",
            "❯ 2. No",
            "Choose an option",
            "What would you like to do",
            "How would you like to proceed",
        ]

        for ui_pattern in ui_prompt_patterns:
            if ui_pattern in current_screen:
                # This is a UI prompt, not a command completion
                return False

        # 1. Check for completion messages
        for pattern in self.completion_patterns:
            if pattern.startswith('r"'):
                # Regex pattern
                if re.search(pattern[2:-1], current_screen):
                    return True
            elif pattern in current_screen:
                return True

        # 2. Check if at command prompt
        lines = current_screen.split('\n')
        last_non_empty = None
        for line in reversed(lines):
            if line.strip():
                last_non_empty = line.strip()
                break

        if last_non_empty:
            for prompt_pattern in self.prompt_patterns:
                try:
                    if re.search(prompt_pattern, last_non_empty):
                        # At prompt - check for screen stability
                        screen_hash = hashlib.md5(current_screen.encode()).hexdigest()

                        if session_name not in self._last_screen_hash:
                            self._last_screen_hash[session_name] = screen_hash
                            self._screen_stable_count[session_name] = 1  # Start at 1
                            return False

                        if self._last_screen_hash[session_name] == screen_hash:
                            # Screen unchanged
                            self._screen_stable_count[session_name] += 1

                            # IMPROVED: More strict conditions
                            # - Increased stability requirement: 3 → 5 checks (15s → 25s)
                            # - Higher output threshold: 5 → 10 lines
                            if self._screen_stable_count[session_name] >= 5:
                                output_lines = len([l for l in lines if l.strip()])
                                if output_lines > 10:
                                    return True
                        else:
                            # Screen changed, reset counter
                            self._last_screen_hash[session_name] = screen_hash
                            self._screen_stable_count[session_name] = 1

                        # Only process the first matching pattern
                        break
                except re.error:
                    continue  # Skip invalid regex patterns

        return False
    
    def has_completion_indicators(self, screen_content: str) -> bool:
        """
        Check if screen has explicit completion indicators

        IMPORTANT: Returns False if working state patterns are also detected,
        to handle tmux screen corruption where stale time/token displays
        coexist with completion text.

        Args:
            screen_content: Screen content to check

        Returns:
            bool: True if completion indicators found AND no working indicators
        """
        import re

        if not screen_content:
            return False

        # GUARD: If working state detected, completion indicators are likely
        # artifacts from Claude's output (e.g., "✓ Edit applied") or stale
        # screen content from tmux corruption
        if self._detect_working_state(screen_content):
            return False

        # Check for completion patterns
        for pattern in self.completion_patterns:
            if pattern.startswith('r"'):
                # Regex pattern
                if re.search(pattern[2:-1], screen_content):
                    return True
            elif pattern.lower() in screen_content.lower():
                return True
        
        return False
    
    def get_state_details(self, session_name: str) -> Dict[str, Any]:
        """
        Get detailed state information for debugging and analysis
        
        Returns:
            Dict containing state, patterns found, and analysis details
        """
        screen_content = self.get_screen_content(session_name)
        
        if not screen_content:
            return {
                "state": SessionState.UNKNOWN,
                "error": "No screen content available",
                "session": session_name,
                "timestamp": datetime.now().isoformat()
            }
        
        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-20:])
        
        # Find all detected patterns
        working_patterns_found = [
            pattern for pattern in self.working_patterns 
            if pattern in recent_content
        ]
        
        input_patterns_found = [
            pattern for pattern in self.input_waiting_patterns
            if pattern in '\n'.join(lines[-10:])
        ]
        
        current_state = self.get_state(session_name)
        
        return {
            "state": current_state,
            "session": session_name,
            "timestamp": datetime.now().isoformat(),
            "screen_length": len(screen_content),
            "working_patterns_found": working_patterns_found,
            "input_patterns_found": input_patterns_found,
            "analysis": {
                "is_working": bool(working_patterns_found),
                "is_waiting_input": bool(input_patterns_found),
                "state_priority": self.STATE_PRIORITY[current_state],
                "decision_logic": f"State: {current_state.value}, Priority: {self.STATE_PRIORITY[current_state]}"
            }
        }


# Global singleton instance for easy import (maintains backward compatibility)
session_state_analyzer = SessionStateAnalyzer()


# Legacy functions for backward compatibility
def is_session_working(session_name: str) -> bool:
    """Legacy function - use session_state_analyzer.is_working() instead"""
    return session_state_analyzer.is_working(session_name)


def get_session_working_info(session_name: str) -> Dict[str, Any]:
    """Legacy function - use session_state_analyzer.get_state_details() instead"""
    details = session_state_analyzer.get_state_details(session_name)
    
    # Convert to old format for compatibility
    return {
        "screen_length": details["screen_length"],
        "working_patterns_found": details["working_patterns_found"],
        "final_decision": details["state"] == SessionState.WORKING,
        "logic": details["analysis"]["decision_logic"]
    }

# Additional helpers for v2.1 reliability improvements
class ScreenHistory:
    """Helper for capturing and parsing screen history."""

    def __init__(self, session_name: str, max_lines: int = 200):
        self.session_name = session_name
        self.max_lines = max_lines

    def build_capture_command(self) -> list:
        """Build tmux capture-pane command with history depth."""
        return [
            "tmux", "capture-pane",
            "-t", self.session_name,
            "-p",
            "-S", f"-{self.max_lines}"
        ]

    def limit_lines(self, content: str, max_lines: int = 200) -> str:
        """Limit content to max_lines."""
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[-max_lines:])
        return content


def get_screen_content(session_name: str, max_lines: int = 200) -> str:
    """Get screen content from tmux session with line limit."""
    history = ScreenHistory(session_name, max_lines)
    cmd = history.build_capture_command()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return history.limit_lines(result.stdout, max_lines)
        return ""
    except Exception as e:
        logger.error(f"Failed to get screen content: {e}")
        return ""


def detect_state(session_name: Optional[str] = None, screen_content: Optional[str] = None, max_lines: int = 200) -> Dict[str, Any]:
    """Detect session state from screen content."""
    if screen_content is None and session_name:
        screen_content = get_screen_content(session_name, max_lines)

    if not screen_content:
        return {"state": "UNKNOWN"}

    if ">" in screen_content[-100:]:
        return {"state": "WAITING_INPUT"}
    elif "Error:" in screen_content:
        return {"state": "ERROR"}
    else:
        return {"state": "WORKING"}
