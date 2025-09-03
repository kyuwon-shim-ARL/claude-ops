"""
Session Manager for Multi-Session Support

Manages active session state and switching between different Claude Code sessions.
"""

import os
import json
from typing import Dict, List


class SessionManager:
    """Manages multiple Claude Code sessions"""
    
    def __init__(self):
        self.state_file = "/tmp/claude_ops_active_session.json"
        self.ensure_state_file()
    
    def ensure_state_file(self) -> None:
        """Ensure session state file exists"""
        if not os.path.exists(self.state_file):
            # Initialize with default session
            default_state = {
                "active_session": "claude_session",  # Default to original session
                "session_history": ["claude_session"],
                "last_updated": None
            }
            self.save_state(default_state)
    
    def load_state(self) -> Dict:
        """Load current session state"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception:
            # Fallback to default
            return {
                "active_session": "claude_session",
                "session_history": ["claude_session"],
                "last_updated": None
            }
    
    def save_state(self, state: Dict) -> None:
        """Save session state"""
        try:
            import time
            state["last_updated"] = time.time()
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Failed to save session state: {e}")
    
    def get_active_session(self) -> str:
        """Get currently active session name"""
        state = self.load_state()
        return state.get("active_session", "claude_session")
    
    def switch_session(self, session_name: str) -> bool:
        """Switch to a different session"""
        # Verify session exists
        if not self.session_exists(session_name):
            return False
        
        # Update state
        state = self.load_state()
        old_session = state.get("active_session")
        state["active_session"] = session_name
        
        # Add to history if not already there
        if session_name not in state.get("session_history", []):
            state["session_history"].append(session_name)
        
        self.save_state(state)
        print(f"Switched from {old_session} to {session_name}")
        return True
    
    def session_exists(self, session_name: str) -> bool:
        """Check if tmux session exists"""
        result = os.system(f"tmux has-session -t {session_name} 2>/dev/null")
        return result == 0
    
    def get_all_claude_sessions(self) -> List[str]:
        """Get list of all Claude sessions (excluding monitoring sessions)"""
        try:
            import subprocess
            result = subprocess.run(
                "tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
                # Exclude monitoring sessions and telegram bridge
                sessions = [s for s in sessions if s not in ['claude-multi-monitor', 'claude-monitor', 'claude-telegram-bridge']]
                return sessions
            else:
                return []
        except Exception:
            return []
    
    def get_session_info(self, session_name: str) -> Dict:
        """Get detailed information about a session"""
        info = {
            "name": session_name,
            "exists": self.session_exists(session_name),
            "is_active": session_name == self.get_active_session(),
            "status_file": self.get_status_file_for_session(session_name)
        }
        
        # Extract directory name (remove claude prefix)
        if session_name.startswith("claude_"):
            info["directory"] = session_name[7:]  # Remove "claude_"
        elif session_name.startswith("claude-"):
            info["directory"] = session_name[7:]  # Remove "claude-"
        else:
            info["directory"] = session_name
            
        return info
    
    def get_status_file_for_session(self, session_name: str) -> str:
        """Get status file path for a specific session"""
        if session_name == "claude_session":
            # Original session uses the main status file
            return "/tmp/claude_work_status"
        elif session_name.startswith("claude_"):
            # Directory-based sessions use their own status files
            dir_name = session_name[7:]  # Remove "claude_" prefix
            return f"/tmp/claude_work_status_{dir_name}"
        else:
            # Fallback
            return f"/tmp/claude_work_status_{session_name}"
    
    def get_session_history(self) -> List[str]:
        """Get list of recently used sessions"""
        state = self.load_state()
        return state.get("session_history", [])


# Global session manager instance
session_manager = SessionManager()