"""
Compact UI Mode Detector for Claude Code

Detects when Claude Code is in compact UI mode (condensed interface)
and provides monitoring capabilities.
"""

import re
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class CompactUIDetector:
    """Detects when Claude Code is in compact UI mode"""
    
    def __init__(self):
        # Patterns that indicate compact UI mode
        self.compact_mode_patterns = [
            r"Context left until auto-compact:\s*\d+%",  # Primary indicator
            r"⏵⏵\s+accept edits on",  # Compact mode UI element
            r"shift\+tab to cycle",  # Compact mode hint
            r"ctrl\+r to expand",  # Compact mode expand option
        ]
        
        # Patterns that indicate normal UI mode
        self.normal_mode_patterns = [
            r"Tool Results",
            r"Human:",
            r"Assistant:",
            r"<function_calls>",
        ]
        
        # UI state tracking
        self._state_cache: Dict[str, Dict] = {}
    
    def detect_compact_mode(self, screen_content: str) -> bool:
        """
        Check if Claude Code is in compact UI mode
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            bool: True if in compact mode
        """
        if not screen_content:
            return False
        
        # Check for compact mode indicators
        for pattern in self.compact_mode_patterns:
            if re.search(pattern, screen_content, re.IGNORECASE):
                logger.debug(f"Detected compact UI mode with pattern: {pattern}")
                return True
        
        return False
    
    def get_context_percentage(self, screen_content: str) -> Optional[int]:
        """
        Extract the context percentage from compact mode display
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            int: Context percentage remaining, or None if not found
        """
        pattern = r"Context left until auto-compact:\s*(\d+)%"
        match = re.search(pattern, screen_content)
        
        if match:
            return int(match.group(1))
        
        return None
    
    def detect_ui_state(self, screen_content: str) -> str:
        """
        Detect the current UI state of Claude Code
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            str: 'compact', 'normal', or 'unknown'
        """
        # Check for compact mode first (more specific)
        if self.detect_compact_mode(screen_content):
            return 'compact'
        
        # Check for normal mode indicators
        for pattern in self.normal_mode_patterns:
            if re.search(pattern, screen_content):
                return 'normal'
        
        # If we see typical Claude output but no specific mode indicators
        if screen_content.strip():
            # Look for common Claude elements
            if any(indicator in screen_content for indicator in ['●', '⎿', '✓', '✢']):
                return 'normal'
        
        return 'unknown'
    
    def analyze_compact_state(self, screen_content: str) -> Dict[str, any]:
        """
        Analyze the compact UI state in detail
        
        Args:
            screen_content: Current tmux screen content
            
        Returns:
            Dict containing detailed analysis
        """
        result = {
            'is_compact': False,
            'ui_state': 'unknown',
            'context_percentage': None,
            'has_pending_edits': False,
            'is_running': False,
            'timestamp': datetime.now()
        }
        
        # Detect UI state
        ui_state = self.detect_ui_state(screen_content)
        result['ui_state'] = ui_state
        result['is_compact'] = (ui_state == 'compact')
        
        # Get context percentage if in compact mode
        if result['is_compact']:
            result['context_percentage'] = self.get_context_percentage(screen_content)
        
        # Check for pending edits
        if "accept edits on" in screen_content:
            result['has_pending_edits'] = True
        
        # Check if running
        if any(indicator in screen_content for indicator in ['Running…', 'Whirring…', 'Metamorphosing…']):
            result['is_running'] = True
        
        return result
    
    def should_notify_compact_mode(self, session_name: str, context_percentage: Optional[int] = None) -> bool:
        """
        Determine if we should notify about compact mode
        
        Args:
            session_name: Name of the tmux session
            context_percentage: Current context percentage
            
        Returns:
            bool: True if notification should be sent
        """
        # Get or create session cache
        if session_name not in self._state_cache:
            self._state_cache[session_name] = {
                'last_notification': None,
                'last_percentage': None
            }
        
        cache = self._state_cache[session_name]
        now = datetime.now()
        
        # Don't notify too frequently (5 minute cooldown)
        if cache['last_notification']:
            time_since_last = (now - cache['last_notification']).total_seconds()
            if time_since_last < 300:  # 5 minutes
                return False
        
        # Notify if context is critically low
        if context_percentage is not None and context_percentage <= 10:
            cache['last_notification'] = now
            cache['last_percentage'] = context_percentage
            return True
        
        return False
    
    def get_ui_status_message(self, analysis: Dict) -> str:
        """
        Generate a human-readable status message
        
        Args:
            analysis: Analysis result from analyze_compact_state
            
        Returns:
            str: Status message
        """
        if analysis['is_compact']:
            msg = "🔄 **Compact UI Mode**\n"
            
            if analysis['context_percentage'] is not None:
                msg += f"Context remaining: {analysis['context_percentage']}%\n"
                
                if analysis['context_percentage'] <= 10:
                    msg += "⚠️ Context is very low!\n"
            
            if analysis['has_pending_edits']:
                msg += "📝 Has pending edits (shift+tab to cycle)\n"
            
            if analysis['is_running']:
                msg += "⚙️ Currently processing...\n"
            
            msg += "\n💡 Press Ctrl+R to expand the view"
            
        else:
            msg = f"📊 **UI Mode: {analysis['ui_state'].title()}**"
            
            if analysis['is_running']:
                msg += "\n⚙️ Currently processing..."
        
        return msg


class CompactUIMonitor:
    """Monitor for compact UI mode changes"""
    
    def __init__(self):
        self.detector = CompactUIDetector()
        self.previous_states: Dict[str, Dict] = {}
    
    def check_for_changes(self, session_name: str, screen_content: str) -> Optional[Dict]:
        """
        Check for significant UI state changes
        
        Args:
            session_name: Name of the tmux session
            screen_content: Current screen content
            
        Returns:
            Dict with change information if significant change detected
        """
        current_analysis = self.detector.analyze_compact_state(screen_content)
        
        # Get previous state
        previous = self.previous_states.get(session_name, {})
        
        # Detect significant changes
        changes = None
        
        # Entered compact mode
        if current_analysis['is_compact'] and not previous.get('is_compact', False):
            changes = {
                'type': 'entered_compact',
                'analysis': current_analysis,
                'message': '📥 Entered compact UI mode'
            }
        
        # Exited compact mode
        elif not current_analysis['is_compact'] and previous.get('is_compact', False):
            changes = {
                'type': 'exited_compact',
                'analysis': current_analysis,
                'message': '📤 Exited compact UI mode'
            }
        
        # Context critically low
        elif current_analysis['is_compact']:
            prev_percentage = previous.get('context_percentage')
            curr_percentage = current_analysis['context_percentage']
            
            if curr_percentage is not None and prev_percentage is not None:
                # Notify when crossing 10% threshold
                if prev_percentage > 10 and curr_percentage <= 10:
                    changes = {
                        'type': 'low_context',
                        'analysis': current_analysis,
                        'message': f'⚠️ Context critically low: {curr_percentage}%'
                    }
        
        # Update state cache
        self.previous_states[session_name] = current_analysis
        
        return changes