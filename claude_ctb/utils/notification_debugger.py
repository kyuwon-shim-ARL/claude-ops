"""
Notification System Debugger

Advanced debugging utilities for Claude-Ops notification detection system.
Helps identify missed notifications, false positives, and state transition issues.
"""

import os
import json
import time
import hashlib
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from pathlib import Path

from ..utils.session_state import SessionState, SessionStateAnalyzer

logger = logging.getLogger(__name__)


class NotificationEvent(Enum):
    """Types of notification events"""
    SENT = "sent"
    MISSED = "missed"
    SUPPRESSED = "suppressed"
    FALSE_POSITIVE = "false_positive"


class NotificationDebugger:
    """
    Advanced debugging tool for notification system
    
    Features:
    - State transition logging with context
    - Missed notification detection
    - False positive analysis
    - Performance metrics
    - Debug report generation
    """
    
    def __init__(self, debug_dir: str = "/tmp/claude-ops-debug"):
        """
        Initialize the debugger
        
        Args:
            debug_dir: Directory for debug logs and reports
        """
        self.debug_dir = Path(debug_dir)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_analyzer = SessionStateAnalyzer()
        
        # Debug data storage
        self.state_history: Dict[str, List[Dict]] = {}
        self.notification_log: List[Dict] = []
        self.performance_metrics: Dict[str, List[float]] = {}
        
        # Configuration
        self.enable_verbose = True
        self.capture_screenshots = False
        self.max_history_size = 100
        
        # Debug session file
        self.session_file = self.debug_dir / f"debug_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        logger.info(f"📝 Notification debugger initialized: {self.debug_dir}")
    
    def log_state_change(self, session_name: str, 
                        previous_state: Optional[SessionState],
                        current_state: SessionState,
                        reason: str = "",
                        context: Optional[Dict] = None) -> None:
        """
        Log a state change with full context
        
        Args:
            session_name: Name of the tmux session
            previous_state: Previous state (None if first detection)
            current_state: Current detected state
            reason: Reason for state change
            context: Additional context information
        """
        timestamp = datetime.now()
        
        # Initialize history for new session
        if session_name not in self.state_history:
            self.state_history[session_name] = []
        
        # Capture screen context
        screen_context = self._capture_screen_context(session_name)
        
        # Create state entry
        entry = {
            'timestamp': timestamp.isoformat(),
            'session': session_name,
            'previous_state': previous_state.value if previous_state else None,
            'current_state': current_state.value,
            'transition': f"{previous_state.value.upper() if previous_state else 'INIT'} → {current_state.value.upper()}",
            'reason': reason,
            'screen_context': screen_context,
            'additional_context': context or {},
            'duration_in_state': self._calculate_state_duration(session_name, previous_state)
        }
        
        # Add to history
        self.state_history[session_name].append(entry)
        
        # Trim history if too large
        if len(self.state_history[session_name]) > self.max_history_size:
            self.state_history[session_name].pop(0)
        
        # Verbose logging
        if self.enable_verbose:
            logger.debug(
                f"🔍 [{session_name}] State: {entry['transition']} | "
                f"Reason: {reason} | Duration: {entry['duration_in_state']:.1f}s"
            )
        
        # Auto-save to file
        self._save_debug_session()
    
    def log_notification(self, session_name: str,
                        event_type: NotificationEvent,
                        message: str,
                        state: SessionState,
                        context: Optional[Dict] = None) -> None:
        """
        Log a notification event
        
        Args:
            session_name: Session that triggered the notification
            event_type: Type of notification event
            message: Notification message or reason
            state: Current session state
            context: Additional context
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'session': session_name,
            'event_type': event_type.value,
            'message': message,
            'state': state.value,
            'context': context or {}
        }
        
        self.notification_log.append(entry)
        
        # Log based on event type
        if event_type == NotificationEvent.SENT:
            logger.info(f"✅ Notification sent: {session_name} - {message}")
        elif event_type == NotificationEvent.MISSED:
            logger.warning(f"⚠️ Missed notification: {session_name} - {message}")
        elif event_type == NotificationEvent.FALSE_POSITIVE:
            logger.warning(f"❌ False positive: {session_name} - {message}")
    
    def _capture_screen_context(self, session_name: str) -> Dict[str, Any]:
        """
        Capture detailed screen context for debugging
        
        Args:
            session_name: Name of the tmux session
            
        Returns:
            Dictionary with screen context information
        """
        try:
            # Get current screen content
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return {'error': 'Failed to capture screen'}
            
            screen_content = result.stdout
            lines = screen_content.split('\n')
            
            context = {
                'last_10_lines': lines[-10:],
                'total_lines': len(lines),
                'screen_hash': hashlib.md5(screen_content.encode()).hexdigest(),
                'screen_size': len(screen_content),
                
                # Pattern detection
                'has_working_indicator': 'esc to interrupt' in screen_content,
                'has_running_text': 'Running' in screen_content or 'running' in screen_content,
                'has_prompt': any(p in screen_content for p in ['$ ', '> ', '❯ ']),
                'has_error': any(e in screen_content for e in ['Error:', 'Failed:', 'Exception:']),
                'has_completion': any(c in screen_content for c in ['Done', 'Completed', 'Successfully']),
                
                # Last non-empty line
                'last_non_empty_line': next((line for line in reversed(lines) if line.strip()), ''),
                
                # Activity indicators
                'has_spinner': any(c in screen_content for c in ['⠋', '⠙', '⠹', '⠸']),
                'has_progress_bar': '[' in screen_content and ']' in screen_content and '%' in screen_content
            }
            
            # Capture screenshot if enabled
            if self.capture_screenshots:
                screenshot_path = self._capture_screenshot(session_name)
                if screenshot_path:
                    context['screenshot'] = str(screenshot_path)
            
            return context
            
        except Exception as e:
            logger.error(f"Error capturing screen context for {session_name}: {e}")
            return {'error': str(e)}
    
    def _calculate_state_duration(self, session_name: str, 
                                 state: Optional[SessionState]) -> float:
        """
        Calculate how long the session was in the previous state
        
        Args:
            session_name: Session name
            state: The state to calculate duration for
            
        Returns:
            Duration in seconds
        """
        if not state or session_name not in self.state_history:
            return 0.0
        
        history = self.state_history[session_name]
        if len(history) < 1:
            return 0.0
        
        # Find when this state started
        state_start = None
        for entry in reversed(history):
            if entry['current_state'] == state.value:
                state_start = datetime.fromisoformat(entry['timestamp'])
            else:
                break
        
        if state_start:
            return (datetime.now() - state_start).total_seconds()
        
        return 0.0
    
    def analyze_missed_notifications(self, session_name: str) -> List[Dict]:
        """
        Analyze potentially missed notifications for a session
        
        Args:
            session_name: Session to analyze
            
        Returns:
            List of missed notification events
        """
        if session_name not in self.state_history:
            return []
        
        missed = []
        history = self.state_history[session_name]
        
        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]
            
            # Check for completion patterns without notification
            if self._is_completion_pattern(prev, curr):
                if not self._has_notification_between(prev['timestamp'], curr['timestamp'], session_name):
                    missed.append({
                        'timestamp': curr['timestamp'],
                        'transition': curr['transition'],
                        'reason': 'Completion pattern detected but no notification sent',
                        'context': curr['screen_context']
                    })
            
            # Check for quiet completions
            if curr['screen_context'].get('has_completion') and \
               curr['current_state'] == 'idle' and \
               not self._has_recent_notification(session_name, curr['timestamp']):
                missed.append({
                    'timestamp': curr['timestamp'],
                    'transition': curr['transition'],
                    'reason': 'Quiet completion (completion message without WORKING state)',
                    'context': curr['screen_context']
                })
        
        return missed
    
    def _is_completion_pattern(self, prev: Dict, curr: Dict) -> bool:
        """Check if state transition represents a completion"""
        # Handle both string values and SessionState enums
        prev_state = prev.get('current_state', '')
        curr_state = curr.get('current_state', '')
        
        # Normalize to lowercase for comparison
        if isinstance(prev_state, str):
            prev_state = prev_state.lower()
        else:
            prev_state = prev_state.value if hasattr(prev_state, 'value') else str(prev_state).lower()
            
        if isinstance(curr_state, str):
            curr_state = curr_state.lower()
        else:
            curr_state = curr_state.value if hasattr(curr_state, 'value') else str(curr_state).lower()
        
        return (
            prev_state == 'working' and
            curr_state in ['idle', 'waiting']
        )
    
    def _has_notification_between(self, start_time: str, end_time: str, 
                                 session_name: str) -> bool:
        """Check if notification was sent between two timestamps"""
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        
        for notif in self.notification_log:
            if notif['session'] != session_name:
                continue
            
            notif_time = datetime.fromisoformat(notif['timestamp'])
            if start <= notif_time <= end and notif['event_type'] == NotificationEvent.SENT.value:
                return True
        
        return False
    
    def _has_recent_notification(self, session_name: str, timestamp: str,
                                window_seconds: int = 30) -> bool:
        """Check if notification was sent recently"""
        check_time = datetime.fromisoformat(timestamp)
        
        for notif in reversed(self.notification_log):
            if notif['session'] != session_name:
                continue
            
            notif_time = datetime.fromisoformat(notif['timestamp'])
            if (check_time - notif_time).total_seconds() <= window_seconds:
                if notif['event_type'] == NotificationEvent.SENT.value:
                    return True
        
        return False
    
    def _capture_screenshot(self, session_name: str) -> Optional[Path]:
        """Capture tmux pane screenshot (if possible)"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_path = self.debug_dir / f"screenshot_{session_name}_{timestamp}.txt"
            
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p > {screenshot_path}",
                shell=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return screenshot_path
                
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
        
        return None
    
    def generate_debug_report(self, session_name: Optional[str] = None) -> str:
        """
        Generate a comprehensive debug report
        
        Args:
            session_name: Specific session to report on (None for all)
            
        Returns:
            Formatted debug report as string
        """
        report = []
        report.append("=" * 80)
        report.append("CLAUDE-OPS NOTIFICATION DEBUG REPORT")
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("=" * 80)
        report.append("")
        
        # Session selection
        sessions = [session_name] if session_name else list(self.state_history.keys())
        
        for session in sessions:
            report.append(f"\n## Session: {session}")
            report.append("-" * 40)
            
            # State history summary
            if session in self.state_history:
                history = self.state_history[session]
                report.append(f"State changes: {len(history)}")
                
                if history:
                    report.append("\nRecent state transitions:")
                    for entry in history[-5:]:
                        report.append(f"  {entry['timestamp']}: {entry['transition']}")
                        if entry['reason']:
                            report.append(f"    Reason: {entry['reason']}")
            
            # Missed notifications
            missed = self.analyze_missed_notifications(session)
            if missed:
                report.append(f"\n⚠️ Potentially missed notifications: {len(missed)}")
                for miss in missed[-3:]:
                    report.append(f"  - {miss['timestamp']}: {miss['reason']}")
            
            # Notification summary
            session_notifs = [n for n in self.notification_log if n['session'] == session]
            if session_notifs:
                report.append(f"\nNotifications sent: {len([n for n in session_notifs if n['event_type'] == 'sent'])}")
                report.append(f"False positives: {len([n for n in session_notifs if n['event_type'] == 'false_positive'])}")
        
        report.append("\n" + "=" * 80)
        report.append("END OF REPORT")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def _save_debug_session(self) -> None:
        """Save debug session to file"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'state_history': self.state_history,
                'notification_log': self.notification_log,
                'performance_metrics': self.performance_metrics
            }
            
            with open(self.session_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save debug session: {e}")
    
    def load_debug_session(self, session_file: str) -> bool:
        """
        Load a previous debug session
        
        Args:
            session_file: Path to session file
            
        Returns:
            True if loaded successfully
        """
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
            
            self.state_history = data.get('state_history', {})
            self.notification_log = data.get('notification_log', [])
            self.performance_metrics = data.get('performance_metrics', {})
            
            logger.info(f"📂 Loaded debug session from {session_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load debug session: {e}")
            return False
    
    def clear_session_data(self, session_name: str) -> None:
        """Clear debug data for a specific session"""
        if session_name in self.state_history:
            del self.state_history[session_name]
        
        self.notification_log = [
            n for n in self.notification_log 
            if n['session'] != session_name
        ]
        
        logger.info(f"🧹 Cleared debug data for session: {session_name}")


# Global debugger instance (singleton)
_debugger_instance: Optional[NotificationDebugger] = None


def get_debugger() -> NotificationDebugger:
    """Get or create the global debugger instance"""
    global _debugger_instance
    if _debugger_instance is None:
        _debugger_instance = NotificationDebugger()
    return _debugger_instance


def enable_debug_mode(verbose: bool = True, screenshots: bool = False) -> None:
    """
    Enable debug mode for notification system
    
    Args:
        verbose: Enable verbose logging
        screenshots: Capture screen screenshots
    """
    debugger = get_debugger()
    debugger.enable_verbose = verbose
    debugger.capture_screenshots = screenshots
    logger.info(f"🐛 Debug mode enabled (verbose={verbose}, screenshots={screenshots})")


def disable_debug_mode() -> None:
    """Disable debug mode"""
    debugger = get_debugger()
    debugger.enable_verbose = False
    debugger.capture_screenshots = False
    logger.info("🔕 Debug mode disabled")


def generate_report(session_name: Optional[str] = None) -> str:
    """
    Generate a debug report
    
    Args:
        session_name: Specific session or None for all
        
    Returns:
        Debug report as string
    """
    debugger = get_debugger()
    return debugger.generate_debug_report(session_name)