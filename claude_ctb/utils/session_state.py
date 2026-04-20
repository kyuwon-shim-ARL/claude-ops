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

import re
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
    OVERLOADED = "overloaded"     # API 529 overloaded — retry with backoff
    WAITING_INPUT = "waiting"     # User response required
    WORKING = "working"           # Active work in progress
    IDLE = "idle"                 # No activity, ready for commands
    SCHEDULED = "scheduled"       # Idle but cron job is scheduled
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
        SessionState.OVERLOADED: 2,
        SessionState.WAITING_INPUT: 3,
        SessionState.WORKING: 4,
        SessionState.IDLE: 5,
        SessionState.SCHEDULED: 6,
        SessionState.UNKNOWN: 7,
    }
    
    # Claude Code spinner/bullet glyphs used for tool execution and thinking.
    # Source: xQ6() spinner cycle + h5 tool bullet + st completed marker.
    # Cycle glyphs (platform-dependent): · ✢ ✳ ✶ ✻ ✽ *
    # Tool bullet: ● (Linux) / ⏺ (macOS)
    # Completed marker (fixed): ✻
    _TOOL_GLYPHS = '·✢✳✶✻✽●⏺'

    # Working-state guard patterns: shared by _detect_input_waiting() and
    # get_state_details(). If any of these appear in recent screen content,
    # Claude is working and NOT waiting for user input.
    _WORKING_GUARD_PATTERNS = [
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
        "Compacting",
        "Running PreCompact hooks",
    ]

    def __init__(self):
        # Legacy alias — kept for get_state_details() compatibility
        self.working_patterns = self._WORKING_GUARD_PATTERNS
        
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
            # y/n confirmation prompts (English and Korean ralplan/plan skills)
            "(y/n)",                      # e.g. "이 계획대로 구현을 시작할까요? (y/n)"
            "(Y/n)",                      # e.g. "Continue? (Y/n)"
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
            # Claude Code past-tense completion: "✻ Cogitated for 5m 8s", "✻ Worked for 57s"
            r"[·✢✳✶✻✽●⏺] \w+ for \d+[ms]",
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
    
    @staticmethod
    def _collapse_sub_output(lines: list) -> list:
        """Remove ⎿ sub-output lines and their indented continuations.

        Claude Code renders tool output as:
            ● Tool(args)
              ⎿  output line 1
                 continuation line 2  (5+ leading spaces)
                 ...N more lines...

        Sub-output blocks can be arbitrarily long (20+ task list items).
        Collapsing them keeps only initiator/status lines, so a small
        fixed-size window always reaches the working indicator regardless
        of how many sub-items exist.
        """
        result = []
        in_sub_output = False
        for line in lines:
            stripped = line.strip()
            leading = len(line) - len(line.lstrip()) if stripped else 0

            if '⎿' in line:
                in_sub_output = True
                continue

            if in_sub_output:
                if not stripped:
                    # Blank line ends sub-output block
                    in_sub_output = False
                    result.append(line)
                    continue
                if leading >= 5:
                    # Deep indent = continuation of ⎿ output
                    continue
                # Non-blank, low indent = new block
                in_sub_output = False

            result.append(line)
        return result

    def _detect_working_state(self, screen_content: str) -> bool:
        """Detect whether Claude is actively working based on screen content.

        Priority cascade:
        1.  'esc to interrupt' / 'ctrl+c to interrupt' in last 25 lines → WORKING
        1b. OMC '⏵⏵ (running)' background task in last 25 lines → WORKING
        2.  Filtered content (OMC bars removed), prompt-anchored, collapse-compressed:
            2a. String patterns (ctrl+b, tokens·thought, Compacting, etc.) → WORKING
            2b. Structural regex (tool glyphs, token arrows, time counters) → WORKING
        3.  Bottom-up prompt scan in last 10 lines → IDLE (returns False)
        4.  Default → not working (returns False)

        Key design decisions:
        - P1 uses last 25 raw lines (interrupt strings are always near bottom).
        - P2 uses ALL lines because _collapse_sub_output() compresses arbitrarily
          long ⎿ blocks, and the 2-non-blank-line window prevents stale scrollback.
        - _TOOL_GLYPHS covers ·✢✳✶✻✽●⏺ (Claude Code spinner/bullet variants).
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

        # PRIORITY 1b: Check for OMC background task actively running
        # ⏵⏵ lines with "(running)" indicate an active background agent.
        # Must check BEFORE OMC bar filtering strips these lines.
        for line in recent_lines:
            if '⏵⏵' in line and '(running)' in line:
                logger.debug("🎯 WORKING: OMC background task '(running)' detected")
                return True

        # PRIORITY 1b-2: OMC status bar shows active skill execution
        # e.g. "skill:external-context(다음 키워드...)" in the OMC bar means
        # a background skill sub-agent is still running, even if the main Claude
        # prompt shows "✻ Cooked for Xm" (past-tense) and ❯ is visible.
        #
        # Two guard cases:
        # GUARD A — stale ⚡N counter (MC_reanalysis pattern):
        #   skill: + ⚡N(>0) visible + ❯ visible → counter stuck at N after work
        #   done; presence of ❯ means Claude is at idle, override → skip.
        # GUARD B — ⚡0 explicit → all tasks finished → skip.
        #
        # NO guard when ⚡N is absent/truncated (narrow terminal, e.g. 151 chars):
        #   status bar `... | skill:external-context(...) | ctx:56% | agent…`
        #   gets cut off before ⚡N. skill: alone is treated as WORKING because
        #   we cannot confirm ⚡0.
        _prompt_visible = any(l.strip() in ('❯', '❯\xa0', '❯ ') for l in recent_lines)
        _skill_bar_re = re.compile(r'\bskill:[A-Za-z0-9_:\-]+\([^)]+\)')
        _active_tasks_re = re.compile(r'⚡([1-9]\d*)')  # ⚡1..∞
        _zero_tasks_re = re.compile(r'⚡0\b')            # ⚡0 = explicitly done
        for line in recent_lines:
            if not _skill_bar_re.search(line):
                continue
            has_active = bool(_active_tasks_re.search(line))
            has_zero = bool(_zero_tasks_re.search(line))
            if has_active and _prompt_visible:
                # GUARD A: ⚡N visible but counter is stuck; ❯ = idle → skip
                logger.debug("⏭ SKIP 1b-2: ❯ visible + ⚡N visible — stale counter (GUARD A)")
                continue
            if has_zero:
                # GUARD B: ⚡0 = all tasks done → skip
                logger.debug("⏭ SKIP 1b-2: ⚡0 explicit — tasks finished (GUARD B)")
                continue
            # skill: found, ⚡N not visible (truncated or absent) and not ⚡0
            logger.debug(f"🎯 WORKING: OMC status bar shows active skill (⚡N absent/truncated): {line.strip()[:80]}")
            return True

        # PRIORITY 1c: Check for Claude Code background tasks still running
        # "N background task(s) still running" appears on the completion summary
        # line (e.g., "✻ Crunched for 59s · 3 background tasks still running").
        # Also matches newer "local agents" phrasing (Claude Code update).
        # This is a definitive working indicator but can appear many lines above
        # the ❯ prompt when Claude writes output text below it. Checking it here
        # (against recent_content) prevents the narrow [-1:] window from missing it.
        if ('background task' in recent_content or 'local agents' in recent_content) and 'still running' in recent_content:
            logger.debug("🎯 WORKING: Claude background task(s)/local agents still running detected in recent lines")
            return True

        # PRIORITY 1c-2: OMC status bar shows active sub-agents
        # When OMC sub-agents are running, the main Claude sits at ❯ prompt
        # (no interrupt strings). The OMC bar reports live agent count:
        # "[OMC#4.12.0] | ... | agents:1 | ..."
        # agents:0 = all done, agents:N (N>0) = actively running.
        # Guard: skip if agents:0 explicitly shown.
        #
        # GUARD C — stale agents:N:
        # When the executor finishes but the OMC bar hasn't updated yet,
        # the screen shows both "✻ Baked for Xs" (past-tense) and ❯ (idle)
        # while agents:N is still non-zero. In this case the bar is stale.
        # Detect: ❯ visible AND last non-blank non-status-bar line above ❯
        # matches the past-tense completion pattern → skip agents:N.
        _omc_agents_re = re.compile(r'\bagents:([1-9]\d*)\b')
        _past_completion_re = re.compile(
            rf'[{SessionStateAnalyzer._TOOL_GLYPHS}] \w+ for \d+'
        )
        # Pre-compute last content line before ❯ (for GUARD C)
        _last_before_prompt = None
        if _prompt_visible:
            for _ln in reversed(recent_lines):
                _s = _ln.strip()
                if not _s or _s in ('❯', '❯\xa0', '❯ '):
                    continue
                if any(_m in _ln for _m in ['[OMC#', '⏵⏵', 'bypass permissions', '└─']):
                    continue
                # Skip separator lines (────)
                if _s.startswith('─') and _s.endswith('─'):
                    continue
                _last_before_prompt = _s
                break

        for line in recent_lines:
            if '[OMC#' not in line:
                continue
            m = _omc_agents_re.search(line)
            if m:
                # GUARD C: ❯ visible + last content is past-tense completion → stale bar
                # Exception: if the completion line itself contains "background task
                # still running" or "local agents still running", the session IS
                # still working (mirrors the 2b-guard exception in Priority 2).
                if (_prompt_visible and _last_before_prompt
                        and _past_completion_re.search(_last_before_prompt)
                        and 'background task' not in _last_before_prompt
                        and 'local agents' not in _last_before_prompt):
                    logger.debug(
                        "⏭ SKIP 1c-2: ❯ visible + last content is past-tense completion "
                        f"(GUARD C) — agents:{m.group(1)} treated as stale: "
                        f"{_last_before_prompt[:60]}"
                    )
                    continue
                logger.debug(f"🎯 WORKING: OMC status bar shows agents:{m.group(1)} running")
                return True

        # PRIORITY 1d: Active spinner glyph with ellipsis in recent raw lines
        # Claude Code shows "✻ Cogitating…" (glyph + verb + U+2026) while actively
        # working. The ellipsis (…) distinguishes active spinners from past-tense
        # completion lines ("✻ Cogitated for 5m 8s" — no ellipsis).
        # Checked on raw lines so inline UI elements below the spinner (e.g.,
        # "How is Claude doing this session?" dialog) don't cause the P2 [-1:]
        # window to miss it.
        _spinner_active_re = re.compile(
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \S+\u2026'
        )
        for line in recent_lines:
            if _spinner_active_re.search(line):
                logger.debug(f"🎯 WORKING: active spinner glyph+ellipsis in raw recent lines: {line.strip()[:60]}")
                return True

        # Build FILTERED content: remove OMC status bar lines and separators.
        # Uses ALL lines (not just recent_lines) because _collapse_sub_output()
        # will compress arbitrarily long tool output blocks. The 25-line limit
        # is only appropriate for P1 (esc to interrupt); P2 needs full context
        # so that initiator lines aren't truncated before collapse can reach them.
        filtered_lines = []
        for line in lines:
            # Skip OMC status bar lines
            if any(marker in line for marker in ['[OMC#', '⏵⏵', 'bypass permissions']):
                continue
            # Skip separator lines
            stripped = line.strip()
            if stripped and stripped.startswith('─') and stripped.endswith('─'):
                continue
            filtered_lines.append(line)
        filtered_content = '\n'.join(filtered_lines)

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
        for i in range(len(filtered_lines) - 1, -1, -1):
            s = filtered_lines[i].strip()
            if s in ['❯', '❯\xa0', '❯ ']:
                prompt_idx = i
                break

        if prompt_idx is not None:
            # Collapse sub-output blocks (⎿ + indented continuations) before
            # windowing. This structurally solves the "window too narrow" problem:
            # no matter how many sub-items a task list has (20+), the initiator
            # line (with token/time indicators) is always within reach.
            pre_prompt = filtered_lines[:prompt_idx]
            collapsed = self._collapse_sub_output(pre_prompt)
            # Take only the last 1 non-blank line from collapsed view.
            # When Claude is actively working, the spinner/status line is
            # ALWAYS the last non-blank line before ❯. If response text
            # appears after a spinner, work is complete — the spinner is stale.
            # Checking only [-1:] eliminates false positives from stale
            # spinners that sit at [-2] when Claude writes a short response.
            non_blank = [l for l in collapsed if l.strip()]
            check_lines = non_blank[-1:] if non_blank else []
        else:
            # No prompt found (vanilla Claude Code without OMC), check last 8 lines
            collapsed = self._collapse_sub_output(filtered_lines)
            non_blank = [l for l in collapsed if l.strip()]
            check_lines = non_blank[-8:]
        check_content = '\n'.join(check_lines)

        # 2a: String-based working patterns (checked on narrow filtered window)
        working_patterns = [
            "ctrl+b to run in background",  # Background execution option
            "tokens \xb7 thought for",      # Claude Code thinking status (· = U+00B7)
            "background task still running",   # Main work done but background task(s) active
            "local agents still running",      # Newer Claude Code phrasing (post-update)
            "to manage)",                   # "(↓ to manage)" shown below background task indicator
            "Compacting",                   # Context compaction in progress (covers "Compacting context" and "Compacting conversation")
            "Running PreCompact hooks",     # PreCompact hooks executing before compaction
        ]
        # Note: "| thinking |" is NOT checked here because it appears in OMC status bar
        # (e.g., "[OMC#4.5.1] | thinking | session:11m") and would false-positive on IDLE sessions.
        # It's only valid as a working signal if found in filtered content (OMC bars removed).
        if "| thinking |" in check_content:
            logger.debug("🎯 WORKING: '| thinking |' detected in filtered content")
            return True

        for pattern in working_patterns:
            if pattern in check_content:
                logger.debug(f"🎯 WORKING: '{pattern}' detected in filtered content")
                return True

        # 2b-guard: Past-tense completion line → NOT working
        # e.g. "✻ Cogitated for 5m 8s", "✻ Worked for 57s"
        # These indicate Claude finished; must not be confused with working.
        # Exception: "Worked for Xs · N background task(s) still running" IS still working.
        if re.search(
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \w+ for \d+',
            check_content, re.MULTILINE,
        ):
            if 'background task' not in check_content and 'local agents' not in check_content:
                logger.debug("⏸️ NOT WORKING: past-tense completion line detected (glyph + verb + 'for' + duration)")
                return False
            else:
                logger.debug("🎯 WORKING: past-tense line has background task(s)/local agents still running")
                return True

        # 2b: Structural regex patterns on narrow filtered content
        structural_patterns = [
            # Generic glyph + verb + ellipsis (…) = actively working
            # Catches ALL random verbs: Swooping…, Stewing…, Cogitating…, etc.
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] \S+\u2026',
            # Claude Code active tool execution with any known glyph
            rf'^\s*[{SessionStateAnalyzer._TOOL_GLYPHS}] (?:Running|Reading|Writing|Editing|Searching|Calling|Fetching|Executing)',
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
            if re.search(pattern, check_content, re.MULTILINE):
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
        for indicator in self._WORKING_GUARD_PATTERNS:
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

    def detect_stuck_after_agent(self, session_path: str,
                                 delay_seconds: int = 45,
                                 max_age_seconds: int = 600) -> bool:
        """Return True if the most recent session JSONL ends with unanswered tool_result.

        Only fires when the JSONL has been idle >= delay_seconds (gives Claude time
        to respond naturally before we consider it stuck).
        """
        import glob as _glob
        import time as _time
        import os as _os
        import json as _json

        if not session_path:
            return False

        encoded = session_path.replace('/', '-')
        project_dir = _os.path.join(_os.path.expanduser('~/.claude/projects'), encoded)
        if not _os.path.isdir(project_dir):
            return False

        try:
            files = sorted(
                [f for f in _glob.glob(_os.path.join(project_dir, '*.jsonl'))
                 if _os.path.isfile(f)],
                key=_os.path.getmtime, reverse=True,
            )
            if not files:
                return False

            latest = files[0]
            age = _time.time() - _os.path.getmtime(latest)
            if age < delay_seconds or age > max_age_seconds:
                return False

            with open(latest, 'r', encoding='utf-8', errors='ignore') as fh:
                tail = fh.readlines()[-150:]

            last_assistant = -1
            last_assistant_had_tool_use = False
            last_tool_result = -1
            for i, line in enumerate(tail):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                msg = entry.get('message', {})
                role = msg.get('role', '')
                content = msg.get('content', [])
                if role == 'assistant':
                    last_assistant = i
                    last_assistant_had_tool_use = isinstance(content, list) and any(
                        isinstance(c, dict) and c.get('type') == 'tool_use'
                        for c in content
                    )
                elif role == 'user' and isinstance(content, list):
                    if any(isinstance(c, dict) and c.get('type') == 'tool_result'
                           for c in content):
                        last_tool_result = i

            return last_tool_result > last_assistant >= 0 and last_assistant_had_tool_use

        except Exception as e:
            logger.debug(f'detect_stuck_after_agent error ({session_path}): {e}')
            return False

    def detect_stuck_ca(self, working_dir: str, delay_seconds: int = 60) -> bool:
        """Return True if a /ca execution is stalled mid-run.

        Reads {working_dir}/.omc/state/critique-lock.json and returns True
        when final_verdict is EXECUTING and the file has not been modified
        for at least delay_seconds (session died or stalled during execution).
        """
        import os as _os
        import json as _json
        import time as _time

        if not working_dir:
            return False

        lock_path = _os.path.join(working_dir, '.omc', 'state', 'critique-lock.json')
        if not _os.path.isfile(lock_path):
            return False

        try:
            age = _time.time() - _os.path.getmtime(lock_path)
            if age < delay_seconds:
                return False

            with open(lock_path, 'r', encoding='utf-8') as fh:
                data = _json.load(fh)

            return data.get('final_verdict') == 'EXECUTING'

        except Exception as e:
            logger.debug(f'detect_stuck_ca error ({working_dir}): {e}')
            return False

    def extract_last_prompt(self, screen_content: str) -> Optional[str]:
        """Extract the last user prompt from screen content (text after '❯ ')."""
        if not screen_content:
            return None
        lines = screen_content.split('\n')
        # Search in reverse for a line containing '❯ ' with actual text after it
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith('❯ '):
                prompt = stripped[2:].strip()
                if prompt:
                    return prompt
        return None

    def _detect_overloaded(self, screen_content: str) -> bool:
        """Detect API 529 overloaded error or rate limit in recent screen content."""
        if not screen_content:
            return False
        recent = '\n'.join(screen_content.split('\n')[-20:])
        # Rate limit check BEFORE working guard: "hit your limit" overrides any
        # working indicators still lingering in the scroll buffer.
        if "hit your limit" in recent and "resets" in recent:
            logger.debug("🚦 OVERLOADED: rate limit detected (hit your limit · resets ...)")
            return True
        if any(guard in screen_content[-2000:] for guard in self._WORKING_GUARD_PATTERNS):
            return False
        if 'overloaded_error' in recent or 'API Error: 529' in recent:
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
        if any(guard in recent_content_wide for guard in self._WORKING_GUARD_PATTERNS):
            return False

        error_patterns = [
            "Error:",
            "Failed:",
            "Exception:",
            "Timeout:",
            "Connection refused",
            "Permission denied",
            # Python-specific
            "Traceback (most recent call last):",
            "returned non-zero exit status",
            # Shell errors
            "command not found",
            "No such file or directory",
        ]

        import re as _re
        recent_content = '\n'.join(lines[-10:])

        if any(pattern in recent_content for pattern in error_patterns):
            return True

        # Non-zero exit code (e.g. "exit 1", "exited with code 2")
        if _re.search(r'\bexit(?:ed)?(?: with| code)? [1-9]\d*\b', recent_content):
            return True

        return False
    
    def _detect_background_process(self, session_name: str) -> bool:
        """Detect background processes running inside a tmux pane via PID check.

        Gets the shell PID of the pane and checks for child processes that aren't
        trivial (the shell itself, ps). Handles the case where the screen looks idle
        but a background job is still running.

        Returns:
            True if a non-trivial child process exists under the pane's shell PID.
        """
        try:
            pid_result = subprocess.run(
                f"tmux display-message -t {session_name} -p '#{{pane_pid}}'",
                shell=True, capture_output=True, text=True, timeout=3,
            )
            if pid_result.returncode != 0:
                return False
            pane_pid = pid_result.stdout.strip()
            if not pane_pid.isdigit():
                return False

            ps_result = subprocess.run(
                f"ps --ppid {pane_pid} -o pid=,comm=,stat=",
                shell=True, capture_output=True, text=True, timeout=3,
            )
            if ps_result.returncode != 0:
                return False

            # Shells and transient helpers that don't count as "real" background work.
            # 'claude' and 'node' are excluded because Claude Code's working/idle state
            # is detected via screen content analysis (P1/P2), not process presence.
            trivial = {'sh', 'bash', 'zsh', 'fish', 'dash', 'ps', 'tmux', 'claude', 'node'}
            for line in ps_result.stdout.strip().splitlines():
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    comm = parts[1].strip()
                    # Zombie processes (Z stat) are already dead, skip them
                    stat = parts[2].strip() if len(parts) > 2 else ''
                    if comm not in trivial and 'Z' not in stat:
                        logger.debug(f"🎯 BACKGROUND PROCESS: {comm} (pid={parts[0].strip()}) in {session_name}")
                        return True
            return False
        except Exception as e:
            logger.debug(f"_detect_background_process error ({session_name}): {e}")
            return False

    def _detect_scheduled(self, session_name: str) -> bool:
        """Detect if a cron job is scheduled that references this session.

        Scans the current user's crontab for non-comment lines that contain
        the session name. Returns True when the session is idle but has a
        scheduled job that will start it again.

        Returns:
            True if a crontab entry referencing session_name is found.
        """
        try:
            result = subprocess.run(
                "crontab -l", shell=True, capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                return False
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and session_name in line:
                    logger.debug(f"📅 SCHEDULED: crontab entry found for {session_name}")
                    return True
            return False
        except Exception as e:
            logger.debug(f"_detect_scheduled error ({session_name}): {e}")
            return False

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

            if self._detect_overloaded(screen_content):
                detected_states.append(SessionState.OVERLOADED)

            if self._detect_input_waiting(screen_content):
                detected_states.append(SessionState.WAITING_INPUT)

            if self._detect_working_state(screen_content):
                detected_states.append(SessionState.WORKING)

            # If no specific state detected, check process/cron before defaulting to IDLE
            if not detected_states:
                if self._detect_background_process(session_name):
                    detected_states.append(SessionState.WORKING)
                elif self._detect_scheduled(session_name):
                    detected_states.append(SessionState.SCHEDULED)
                else:
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

            # If no specific state detected, check hold timer, then process/cron
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
                elif self._detect_background_process(session_name):
                    detected_states.append(SessionState.WORKING)
                elif self._detect_scheduled(session_name):
                    detected_states.append(SessionState.SCHEDULED)
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


    def extract_workflow_phase(self, screen_content: Optional[str], state: "SessionState") -> Optional[str]:
        """Detect the current agent workflow phase from screen content and session state.

        Priority: error > awaiting_approval > reporting_completion > executing > planning > exploring > None

        Args:
            screen_content: Raw tmux screen content (pre-fetched; avoids duplicate tmux capture)
            state: Current session state

        Returns:
            Workflow phase string or None
        """
        if not screen_content:
            return None

        if state == SessionState.ERROR:
            return "error"

        lines = screen_content.split("\n")
        recent_content = "\n".join(lines[-25:])

        if state == SessionState.WAITING_INPUT:
            approval_patterns = ["A)", "B)", "[Y/n]", "y/n", "진행할까", "승인", "proceed?", "계속할까"]
            for pattern in approval_patterns:
                if pattern in recent_content:
                    return "awaiting_approval"

            completion_patterns = ["완료", "done", "성공적으로", "finished", "결과", "summary"]
            lower_recent = recent_content.lower()
            for pattern in completion_patterns:
                if pattern.lower() in lower_recent:
                    return "reporting_completion"

            return "idle_wait"

        if state == SessionState.WORKING:
            # executing: file mutation tools (avoid matching "Write" inside "TodoWrite")
            if (any(p in recent_content for p in ["Edit", "Bash"]) or
                    ("Write" in recent_content and "TodoWrite" not in recent_content)):
                return "executing"

            if any(p in recent_content for p in ["TodoWrite", "계획", "plan"]):
                return "planning"

            if any(p in recent_content for p in ["Read", "Grep", "Glob", "search"]):
                return "exploring"

            return None

        return None


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
