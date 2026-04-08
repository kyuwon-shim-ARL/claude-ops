"""
Session State Detection for CTB Dashboard.

Detects Claude Code session states (WORKING, IDLE, WAITING_INPUT, etc.)
by analyzing tmux screen content with pattern matching.

Extracted from claude_ctb.utils.session_state (core detection subset).
"""

import json
import os
import subprocess
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Session state definitions with clear priorities"""
    CONTEXT_LIMIT = "context_limit"      # Highest priority - context window exhausted
    ERROR = "error"                      # System errors
    WAITING_INPUT = "waiting"            # User response required
    WORKING = "working"                  # Active work in progress
    STUCK_AFTER_AGENT = "stuck_after_agent"  # Agent returned result, no follow-up
    IDLE = "idle"                        # No activity, ready for commands
    UNKNOWN = "unknown"                  # Cannot determine state


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
        SessionState.STUCK_AFTER_AGENT: 35,  # Between WORKING(3) and IDLE(4), stored as int*10
        SessionState.IDLE: 40,
        SessionState.UNKNOWN: 50,
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

        # PRIORITY 1c: Claude Code background tasks / local agents still running
        # Matches both old "background tasks still running" and new "local agents still running"
        if ('background task' in recent_content or 'local agents' in recent_content) and 'still running' in recent_content:
            logger.debug("WORKING: Claude background task(s)/local agents still running detected")
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
            "local agents still running",      # Newer Claude Code phrasing (post-update)
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
            if 'background task' not in check_content and 'local agents' not in check_content:
                logger.debug("NOT WORKING: past-tense completion line detected")
                return False
            else:
                logger.debug("WORKING: past-tense line has background task(s)/local agents still running")
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

    # How long (seconds) after last tool_result before flagging stuck
    _STUCK_DETECTION_DELAY = 10
    # Don't flag sessions whose JSONL hasn't changed in this many seconds
    _STUCK_MAX_AGE = 600

    def _detect_stuck_after_agent(self, session_path: str) -> bool:
        """Detect if session is stuck: agent returned tool_result but no assistant follow-up.

        Reads the session's most recent JSONL file from ~/.claude/projects/.
        Returns True if the last meaningful exchange ends with an unanswered tool_result
        that has been sitting for at least _STUCK_DETECTION_DELAY seconds.
        """
        if not session_path:
            return False

        import glob as _glob
        import time as _time

        # Encode session path to Claude storage format: /home/foo/bar -> -home-foo-bar
        encoded = session_path.replace('/', '-')
        if encoded.startswith('-'):
            pass  # already has leading dash from leading /
        claude_base = os.path.expanduser("~/.claude/projects")
        project_dir = os.path.join(claude_base, encoded)

        if not os.path.isdir(project_dir):
            return False

        try:
            jsonl_files = [
                f for f in _glob.glob(os.path.join(project_dir, "*.jsonl"))
                if os.path.isfile(f)
            ]
            if not jsonl_files:
                return False

            # Most recently modified JSONL (active session)
            jsonl_files.sort(key=os.path.getmtime, reverse=True)
            latest = jsonl_files[0]

            mtime = os.path.getmtime(latest)
            age = _time.time() - mtime

            # Don't flag: too fresh (agent might still be processing) or too old
            if age < self._STUCK_DETECTION_DELAY or age > self._STUCK_MAX_AGE:
                return False

            # Read last 150 lines
            with open(latest, 'r', encoding='utf-8', errors='ignore') as fh:
                tail = fh.readlines()[-150:]

            messages = []
            for line in tail:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

            # Find positions of last assistant and last user-with-tool_result
            last_assistant_idx = -1
            last_tool_result_idx = -1

            for i, entry in enumerate(messages):
                msg = entry.get('message', {})
                role = msg.get('role', '')
                content = msg.get('content', [])

                if role == 'assistant':
                    last_assistant_idx = i
                elif role == 'user' and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'tool_result':
                            last_tool_result_idx = i
                            break

            # Stuck: tool_result arrived AFTER last assistant turn
            if last_tool_result_idx <= last_assistant_idx:
                return False
            if last_assistant_idx < 0:
                return False

            # Verify the assistant turn before the tool_result used Agent tool
            for i in range(last_assistant_idx, -1, -1):
                msg = messages[i].get('message', {})
                if msg.get('role') != 'assistant':
                    continue
                content = msg.get('content', [])
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'tool_use':
                            # Agent tool is the primary culprit, but also flag other tools
                            return True
                break

            return False

        except Exception as e:
            logger.debug(f"_detect_stuck_after_agent error for {session_path}: {e}")
            return False

    def get_state(self, session_name: str, session_path: str = None, use_cache: bool = True) -> SessionState:
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
                # Session is IDLE — check if it's actually stuck after an agent result
                if session_path and self._detect_stuck_after_agent(session_path):
                    detected_states.append(SessionState.STUCK_AFTER_AGENT)
                else:
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

    # Prompt detection patterns — mirrored from claude_ctb/utils/prompt_recall.py.
    # Keep in sync: any pattern change should be applied to both locations.
    _PROMPT_PATTERNS = [
        re.compile(r'^>\s*(.+)$'),               # > prompt
        re.compile(r'^❯\s*(.+)$'),              # ❯ prompt
        re.compile(r'^Human:\s*(.+)$'),          # Human: prefix
        re.compile(r'^사용자:\s*(.+)$'),          # Korean 사용자:
        re.compile(r'^@[\w가-힣]+\s+(.+)$'),     # @command form
    ]

    # Slash commands to filter out (system/navigation commands, not user work)
    _SLASH_BLOCKLIST = frozenset({
        '/help', '/clear', '/exit', '/quit', '/reset', '/model', '/compact',
    })

    @staticmethod
    def _is_allowed_prompt(text: str) -> bool:
        """Check if prompt text should be displayed (slash command blocklist filter)."""
        if text.startswith('/'):
            cmd = text.split()[0].lower()
            return cmd not in SessionStateAnalyzer._SLASH_BLOCKLIST
        return True

    _MEANINGLESS_PROMPT_RE = [
        re.compile(r'^[0-9]+$'),
        re.compile(r'^[yYnN]$'),
        re.compile(r'^(yes|no)$', re.IGNORECASE),
        re.compile(r'^(quit|exit|q)$', re.IGNORECASE),
        re.compile(r'^\s*$'),
        re.compile(r'^[0-9]+\.\s*Yes', re.IGNORECASE),
        re.compile(r'^[0-9]+\.\s*No', re.IGNORECASE),
        re.compile(r'^❯\s*[0-9]+\.'),
        re.compile(r'^(Continue|Stop|Cancel)\s*\?*$', re.IGNORECASE),
    ]

    @staticmethod
    def _is_meaningful_prompt(text: str) -> bool:
        """Filter out UI choices, single-char answers, and other noise."""
        if len(text) < 5 or len(text) > 500:
            return False
        for pat in SessionStateAnalyzer._MEANINGLESS_PROMPT_RE:
            if pat.match(text):
                return False
        return True

    def extract_last_prompt(self, screen_content: Optional[str]) -> Optional[str]:
        """Extract the last user prompt/message from screen content.

        Uses the same 5-pattern matching and quality filter as the Telegram
        prompt_recall system for consistency.

        Returns:
            Last user prompt text (truncated to 200 chars), or None if not found
        """
        if not screen_content:
            return None

        lines = screen_content.split('\n')
        prompts = []

        for line in lines:
            stripped = line.strip()
            for pat in self._PROMPT_PATTERNS:
                m = pat.match(stripped)
                if m:
                    text = m.group(1).strip()
                    if text and self._is_allowed_prompt(text) and self._is_meaningful_prompt(text):
                        prompts.append(text)
                    break

        if prompts:
            # Deduplicate, return last match
            seen = dict.fromkeys(prompts)
            return list(seen)[-1][:200]

        # Fallback: continuation line after bare ❯ prompt
        for i in range(len(lines) - 1, max(len(lines) - 50, -1), -1):
            line = lines[i].strip()
            if line in ['\u276f', '\u276f ']:
                continue
            if i > 0:
                prev = lines[i - 1].strip()
                if prev in ['\u276f', '\u276f '] and line and not line.startswith(('\u2500', '[OMC#', '\u23f5')):
                    if self._is_meaningful_prompt(line):
                        return line[:200]

        return None

    def extract_work_context(self, session_path: Optional[str]) -> Optional[str]:
        """Extract current work context from OMC state files in the session's working directory.

        Checks in priority order:
        1a. .omc/state/*-state.json — active mode goal/task
        1b. .omc/state/critique-lock.json — converged/executing ticket
        1c. .omc/state/skill-sessions.json — active skill
        2.  .omc/notepad.md — priority section first line
        3.  MANIFEST.yaml — current experiment ID + title
        4.  CLAUDE.md — project name from heading
        5.  git branch + directory name
        6.  directory name only

        Returns:
            Short work context string (truncated to 120 chars), or None
        """
        if not session_path:
            return None

        root = Path(session_path)

        # 1. OMC active mode state
        state_dir = root / ".omc" / "state"
        if state_dir.is_dir():
            try:
                for state_file in sorted(state_dir.glob("*-state.json")):
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        status = data.get("status", "")
                        if status in ("active", "running", "in_progress"):
                            goal = data.get("goal") or data.get("task") or data.get("description", "")
                            mode = state_file.stem.replace("-state", "")
                            if goal:
                                ctx = f"[{mode}] {goal}"
                                return ctx[:120]
                            elif mode:
                                return f"[{mode}] active"
                    except (json.JSONDecodeError, OSError):
                        continue
            except OSError:
                pass

        # 1b. OMC critique-lock.json — converged/executing ticket summary
        lock_file = root / ".omc" / "state" / "critique-lock.json"
        if lock_file.is_file():
            try:
                lock = json.loads(lock_file.read_text(encoding="utf-8"))
                verdict = lock.get("final_verdict", "")
                summary = lock.get("ticket_summary", "")
                if verdict in ("CONVERGED", "EXECUTING") and summary:
                    tag = "exec" if verdict == "EXECUTING" else "plan"
                    return f"[{tag}] {summary}"[:120]
            except (json.JSONDecodeError, OSError):
                pass

        # 1c. OMC skill-sessions.json — active skill
        skill_file = root / ".omc" / "state" / "skill-sessions.json"
        if skill_file.is_file():
            try:
                skills = json.loads(skill_file.read_text(encoding="utf-8"))
                if isinstance(skills, dict):
                    for sid, info in skills.items():
                        if isinstance(info, dict) and info.get("status") in ("active", "running"):
                            skill_name = info.get("skill", sid)
                            return f"[{skill_name}] active"[:120]
            except (json.JSONDecodeError, OSError):
                pass

        # 2. OMC notepad priority section
        notepad = root / ".omc" / "notepad.md"
        if notepad.is_file():
            try:
                content = notepad.read_text(encoding="utf-8")
                in_priority = False
                for line in content.split("\n"):
                    if re.match(r"^##\s+.*[Pp]riority", line):
                        in_priority = True
                        continue
                    if in_priority:
                        stripped = line.strip()
                        if stripped.startswith("##"):
                            break
                        if stripped and stripped != "---" and not stripped.startswith("<!--"):
                            text = re.sub(r"^[-*]\s+", "", stripped)
                            if text:
                                return text[:120]
            except OSError:
                pass

        # 3. MANIFEST.yaml — current experiment (check root and outputs/)
        manifest = root / "MANIFEST.yaml"
        if not manifest.is_file():
            manifest = root / "outputs" / "MANIFEST.yaml"
        if manifest.is_file():
            try:
                content = manifest.read_text(encoding="utf-8")
                current_exp = None
                current_desc = None
                last_active_exp = None
                last_active_desc = None
                in_experimental = False
                for line in content.split("\n"):
                    m = re.match(r"^\s*-?\s*(e\d{3,4})\s*:", line)
                    if m:
                        current_exp = m.group(1)
                        current_desc = None
                        in_experimental = False
                    if current_exp:
                        tm = re.match(r"""^\s+(?:title|name|description):\s*["']?(.+?)["']?\s*$""", line)
                        if tm:
                            current_desc = tm.group(1).strip()
                        sm = re.match(r"^\s+status:\s*(\w+)", line)
                        if sm and sm.group(1) == "experimental":
                            in_experimental = True
                            last_active_exp = current_exp
                            last_active_desc = current_desc
                # Prefer last experimental experiment; fall back to last experiment
                exp = last_active_exp or current_exp
                desc = last_active_desc or current_desc
                if exp and desc:
                    return f"[{exp}] {desc}"[:120]
                elif exp:
                    return f"[{exp}] active"
            except OSError:
                pass

        # 4. CLAUDE.md — project description from heading or first line
        claude_md = root / "CLAUDE.md"
        if claude_md.is_file():
            try:
                content = claude_md.read_text(encoding="utf-8")
                for line in content.split("\n")[:30]:
                    stripped = line.strip()
                    # Match "# ProjectName" or "> **Project Name**: ..."
                    hm = re.match(r"^#\s+(.+)", stripped)
                    if hm:
                        title = hm.group(1).strip()
                        # Skip generic headings like "CLAUDE.md", "README", "# Configuration"
                        if title and len(title) > 3 and not re.match(r"(?i)^(claude\.?md|readme|config)", title):
                            return f"[project] {title}"[:120]
                    pm = re.match(r"^>\s+\*\*Project\s+Name\*\*:\s*(.+)", stripped, re.IGNORECASE)
                    if pm:
                        return f"[project] {pm.group(1).strip()}"[:120]
            except OSError:
                pass

        # 5. Generic fallback: git branch + directory name (works for any session)
        dir_name = root.name
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                if branch:
                    return f"[{branch}] {dir_name}"[:120]
        except (subprocess.TimeoutExpired, OSError):
            logger.debug(f"Git branch lookup failed for {session_path}")
        except Exception:
            pass

        # 6. Non-git directory: show directory name only
        if dir_name:
            return f"[dir] {dir_name}"[:120]

        return None
