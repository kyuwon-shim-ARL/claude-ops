"""
Session State Detection for CTB Dashboard.

Detects Claude Code session states (WORKING, IDLE, WAITING_INPUT, etc.)
by analyzing tmux screen content with pattern matching.

Extracted from claude_ctb.utils.session_state (core detection subset).
"""

import subprocess
import logging
import re
from enum import Enum
from typing import Optional, Dict
from datetime import datetime

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
        return f"StateTransition({self.session}: {self.from_state} -> {self.to_state})"


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

    # Claude Code spinner/bullet glyphs used for tool execution and thinking.
    _TOOL_GLYPHS = '\u00b7\u2722\u2733\u2736\u273b\u273d\u25cf\u23fa'

    # Working-state guard patterns: if any of these appear in recent screen content,
    # Claude is working and NOT waiting for user input.
    _WORKING_GUARD_PATTERNS = [
        "esc to interrupt",
        "ctrl+c to interrupt",
        "ctrl+b to run in background",
        "Thinking\u2026",
        "Running\u2026",
        "Implementing",
        "Building",
        "Testing",
        "Installing",
        "Processing",
        "Analyzing",
        "Compacting",
        "Running PreCompact hooks",
    ]

    def __init__(self):
        # Legacy alias
        self.working_patterns = self._WORKING_GUARD_PATTERNS

        # Patterns indicating user input is required
        self.input_waiting_patterns = [
            "Do you want to proceed?",
            "Choose an option:",
            "Select:",
            "Enter your choice:",
            "What would you like to do?",
            "How would you like to proceed?",
            "Please choose:",
            "Continue?",
            "\u276f 1.",
            "\u276f 2.",
            "Question ",
            "\u2502 Option \u2502",
            "\u2502 A ",
            "\u2502 B ",
            "\u2502 C ",
            "\u2502 D ",
            "\u2502 Short ",
            "\u2502 Other ",
            "\u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u252c",
            "(<=",
        ]

        # Completion message patterns
        self.completion_patterns = [
            "Build succeeded",
            "Tests passed",
            "All tests passed",
            "0 errors",
            "0 failures",
            "Done!",
            "\u2705 All",
            r"took \d+\.\d+s",
            r"in \d+\.\d+ seconds",
            r"[\u00b7\u2722\u2733\u2736\u273b\u273d\u25cf\u23fa] \w+ for \d+[ms]",
        ]

        # Command prompt patterns (regex)
        self.prompt_patterns = [
            r"\$$",
            r"\$ $",
            r">$",
            r"> $",
            r"\u276f$",
            r"\u276f $",
            r">>>$",
            r">>> $",
            r"In \[\d+\]:$",
            r"In \[\d+\]: $",
            r"\w+@[\w\-\.]+.*\$$",
            r"\w+@[\w\-\.]+.*\$ $",
        ]

        # Cache for screen content to avoid repeated tmux calls
        self._screen_cache: Dict[str, tuple[str, datetime]] = {}
        self._cache_ttl_seconds = 1

        # Cache for computed states
        self._state_cache: Dict[str, tuple[SessionState, datetime]] = {}
        self._state_cache_ttl_seconds = 0.5

        # Track screen stability for quiet completion detection
        self._last_screen_hash: Dict[str, str] = {}
        self._screen_stable_count: Dict[str, int] = {}

        # WORKING state hold timer
        self._last_working_time: Dict[str, float] = {}
        self._working_hold_seconds = 10

        # Regex for OMC context percentage: ctx:67% or ctx:[████░░░░░░]67%
        self._context_pct_re = re.compile(
            r'ctx:\[?[█░]*\]?(\d+)%'
        )
        # Fallback: Claude Code native context display
        self._context_native_re = re.compile(
            r'Context left until auto-compact:\s*(\d+)%'
        )

    def get_screen_content(self, session_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Get tmux screen content with optional caching.

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
            log_lines = 200

            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{log_lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                content = result.stdout
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

    @staticmethod
    def _collapse_sub_output(lines: list) -> list:
        """Remove sub-output lines and their indented continuations.

        Claude Code renders tool output as:
            * Tool(args)
              output line 1
                 continuation line 2  (5+ leading spaces)
                 ...N more lines...

        Collapsing them keeps only initiator/status lines, so a small
        fixed-size window always reaches the working indicator.
        """
        result = []
        in_sub_output = False
        for line in lines:
            stripped = line.strip()
            leading = len(line) - len(line.lstrip()) if stripped else 0

            if '\u23bf' in line:
                in_sub_output = True
                continue

            if in_sub_output:
                if not stripped:
                    in_sub_output = False
                    result.append(line)
                    continue
                if leading >= 5:
                    continue
                in_sub_output = False

            result.append(line)
        return result

    def _detect_working_state(self, screen_content: str) -> bool:
        """Detect whether Claude is actively working based on screen content.

        Priority cascade:
        1.  'esc to interrupt' / 'ctrl+c to interrupt' in last 25 lines
        1b. OMC background task '(running)' in last 25 lines
        1c. Claude Code background tasks still running
        1d. Active spinner glyph with ellipsis in recent raw lines
        2.  Filtered content, prompt-anchored, collapse-compressed:
            2a. String patterns
            2b. Structural regex
        3.  Bottom-up prompt scan in last 10 lines -> IDLE
        4.  Default -> not working
        """
        if not screen_content:
            return False

        lines = screen_content.split('\n')

        # Last 25 lines for interrupt indicators
        recent_lines = lines[-25:]
        recent_content = '\n'.join(recent_lines)

        # PRIORITY 1: Check for interrupt indicators in RECENT content
        interrupt_patterns = ["esc to interrupt", "ctrl+c to interrupt"]
        for pattern in interrupt_patterns:
            if pattern in recent_content:
                logger.debug(f"WORKING: '{pattern}' detected in recent lines")
                return True
        # Line-wrap fallback
        for i in range(len(recent_lines) - 1):
            joined = recent_lines[i].rstrip() + recent_lines[i + 1].lstrip()
            for pattern in interrupt_patterns:
                if pattern in joined:
                    logger.debug(f"WORKING: '{pattern}' detected via line-wrap join")
                    return True

        # PRIORITY 1b: OMC background task actively running
        for line in recent_lines:
            if '\u23f5\u23f5' in line and '(running)' in line:
                logger.debug("WORKING: OMC background task '(running)' detected")
                return True

        # PRIORITY 1c: Claude Code background tasks still running
        if 'background task' in recent_content and 'still running' in recent_content:
            logger.debug("WORKING: Claude background task(s) still running detected")
            return True

        # PRIORITY 1d: Active spinner glyph with ellipsis
        _spinner_active_re = re.compile(
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \S+\u2026'
        )
        for line in recent_lines:
            if _spinner_active_re.search(line):
                logger.debug(f"WORKING: active spinner glyph+ellipsis: {line.strip()[:60]}")
                return True

        # Build FILTERED content: remove OMC status bar lines and separators
        filtered_lines = []
        for line in lines:
            if any(marker in line for marker in ['[OMC#', '\u23f5\u23f5', 'bypass permissions']):
                continue
            stripped = line.strip()
            if stripped and stripped.startswith('\u2500') and stripped.endswith('\u2500'):
                continue
            filtered_lines.append(line)

        # PRIORITY 2: Find prompt position, check content before it
        prompt_idx = None
        for i in range(len(filtered_lines) - 1, -1, -1):
            s = filtered_lines[i].strip()
            if s in ['\u276f', '\u276f\xa0', '\u276f ']:
                prompt_idx = i
                break

        if prompt_idx is not None:
            pre_prompt = filtered_lines[:prompt_idx]
            collapsed = self._collapse_sub_output(pre_prompt)
            non_blank = [l for l in collapsed if l.strip()]
            check_lines = non_blank[-1:] if non_blank else []
        else:
            collapsed = self._collapse_sub_output(filtered_lines)
            non_blank = [l for l in collapsed if l.strip()]
            check_lines = non_blank[-8:]
        check_content = '\n'.join(check_lines)

        # 2a: String-based working patterns
        working_patterns = [
            "ctrl+b to run in background",
            "tokens \xb7 thought for",
            "background task still running",
            "to manage)",
            "Compacting",
            "Running PreCompact hooks",
        ]
        if "| thinking |" in check_content:
            logger.debug("WORKING: '| thinking |' detected in filtered content")
            return True

        for pattern in working_patterns:
            if pattern in check_content:
                logger.debug(f"WORKING: '{pattern}' detected in filtered content")
                return True

        # 2b-guard: Past-tense completion line -> NOT working
        if re.search(
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \w+ for \d+',
            check_content, re.MULTILINE,
        ):
            if 'background task' not in check_content:
                logger.debug("NOT WORKING: past-tense completion line detected")
                return False
            else:
                logger.debug("WORKING: past-tense line has background task(s) still running")
                return True

        # 2b: Structural regex patterns
        structural_patterns = [
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \S+\u2026',
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] (?:Running|Reading|Writing|Editing|Searching|Calling|Fetching|Executing)',
            r'[\u2193\u2191] [\d.,]+k? tokens',
            r'\d+s\s+\xb7\s+[\d.,]+k?\s+tokens',
            r'\d+m\s+\d+s\s+\xb7\s+[\d.,]+k?\s+tokens',
            r'Running \d+ ',
            r'Skill\(',
            r'Retrying in \d+',
            r'attempt \d+/\d+',
        ]
        for pattern in structural_patterns:
            if re.search(pattern, check_content, re.MULTILINE):
                logger.debug(f"WORKING: structural pattern '{pattern}' matched")
                return True

        # PRIORITY 3: Check for prompts -> IDLE
        for i in range(len(lines) - 1, max(len(lines) - 10, -1), -1):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                continue

            if any(marker in line for marker in ['[OMC#', '\u23f5\u23f5', 'bypass permissions']):
                continue

            if stripped.startswith('\u2500') and stripped.endswith('\u2500'):
                continue

            if stripped in ['>', '\u276f', '\u2502 >', '\u2502 \u276f'] or line.endswith(('$ ', '> ', '\u276f ')):
                logger.debug("IDLE: Prompt detected, no working patterns found")
                return False

            break

        return False

    def _detect_input_waiting(self, screen_content: str) -> bool:
        """Detect if session is waiting for user input."""
        if not screen_content:
            return False

        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-25:])

        # If working indicators present, NOT waiting for input
        for indicator in self._WORKING_GUARD_PATTERNS:
            if indicator in recent_content:
                return False

        recent_lines = lines[-10:]
        for line in recent_lines:
            for pattern in self.input_waiting_patterns:
                if pattern in line:
                    return True

        return False

    def _detect_context_limit(self, screen_content: str) -> bool:
        """Detect if session has hit the context window limit."""
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
        """Detect if session is in an error state."""
        if not screen_content:
            return False

        lines = screen_content.split('\n')
        recent_lines = lines[-25:]
        recent_content_wide = '\n'.join(recent_lines)

        # Guard: if working indicators are present, error strings are likely
        # part of Claude's analysis output
        if any(guard in recent_content_wide for guard in self._WORKING_GUARD_PATTERNS):
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
        Get the current state of a session with priority-based resolution.

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
            state = SessionState.IDLE
        else:
            detected_states = []

            if self._detect_context_limit(screen_content):
                detected_states.append(SessionState.CONTEXT_LIMIT)

            if self._detect_error_state(screen_content):
                detected_states.append(SessionState.ERROR)

            if self._detect_input_waiting(screen_content):
                detected_states.append(SessionState.WAITING_INPUT)

            if self._detect_working_state(screen_content):
                detected_states.append(SessionState.WORKING)

            if not detected_states:
                detected_states.append(SessionState.IDLE)

            state = min(detected_states, key=lambda s: self.STATE_PRIORITY[s])

        # Update state cache
        if use_cache:
            self._state_cache[session_name] = (state, now)

        return state

    def extract_context_percent(self, screen_content: Optional[str]) -> Optional[int]:
        """Extract context window usage percentage from OMC statusline in screen content.

        Parses OMC HUD format: ctx:67% or ctx:[████░░░░░░]67%
        Fallback: Claude Code native 'Context left until auto-compact: XX%'

        Returns:
            Context usage percentage (0-100), or None if not found
        """
        if not screen_content:
            return None

        # Search bottom-up (statusline is near the bottom)
        lines = screen_content.split('\n')
        for line in reversed(lines[-30:]):
            m = self._context_pct_re.search(line)
            if m:
                return min(100, max(0, int(m.group(1))))

        # Fallback: Claude Code native context display (shows remaining, not used)
        for line in reversed(lines[-15:]):
            m = self._context_native_re.search(line)
            if m:
                remaining = int(m.group(1))
                return min(100, max(0, 100 - remaining))

        return None

    def extract_last_prompt(self, screen_content: Optional[str]) -> Optional[str]:
        """Extract the last user prompt/message from screen content.

        Looks for the ❯ prompt character and extracts the user's input text.

        Returns:
            Last user prompt text (truncated to 200 chars), or None if not found
        """
        if not screen_content:
            return None

        lines = screen_content.split('\n')

        # Find last non-empty ❯ prompt with text after it
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            # Match: ❯ user typed text  or  > user typed text
            if line.startswith('\u276f ') and len(line) > 2:
                text = line[2:].strip()
                if text and not text.startswith('/') and len(text) > 1:
                    return text[:200]
            if line.startswith('\u276f') and len(line) > 1 and line[1] != ' ':
                # ❯text (no space)
                text = line[1:].strip()
                if text and len(text) > 1:
                    return text[:200]

        # Fallback: look for lines that appear to be user input
        # (between consecutive ❯ prompts, or after the last one)
        for i in range(len(lines) - 1, max(len(lines) - 50, -1), -1):
            line = lines[i].strip()
            if line in ['\u276f', '\u276f ']:
                # Empty prompt - look at the line above for the last assistant output
                # or the previous prompt with text
                continue
            # Check if previous line was a ❯ prompt (this line is continuation)
            if i > 0:
                prev = lines[i - 1].strip()
                if prev in ['\u276f', '\u276f '] and line and not line.startswith(('\u2500', '[OMC#', '\u23f5')):
                    return line[:200]

        return None
