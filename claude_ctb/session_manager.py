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
    
    def get_all_claude_sessions(self, sort_by_mtime: bool = True) -> List[str]:
        """Get list of all Claude sessions (excluding monitoring sessions)

        Args:
            sort_by_mtime: If True, sort sessions by most recently modified (newest first)
        """
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

                if sort_by_mtime and sessions:
                    # Sort by tmux session activity time (most recent first)
                    sessions = self._sort_sessions_by_activity(sessions)

                return sessions
            else:
                return []
        except Exception:
            return []

    def _sort_sessions_by_activity(self, sessions: List[str]) -> List[str]:
        """Sort sessions by last activity time (most recent first)"""
        import subprocess
        import re

        session_times = []
        for session in sessions:
            try:
                # Get session activity time from tmux
                result = subprocess.run(
                    f"tmux display-message -t {session} -p '#{{session_activity}}'",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=1
                )

                if result.returncode == 0 and result.stdout.strip():
                    activity_time = int(result.stdout.strip())
                    session_times.append((session, activity_time))
                else:
                    # If can't get time, put at end
                    session_times.append((session, 0))
            except Exception:
                # If error, put at end
                session_times.append((session, 0))

        # Sort by activity time descending (most recent first)
        session_times.sort(key=lambda x: x[1], reverse=True)

        return [session for session, _ in session_times]
    
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

    def send_command(self, session_name: str, command: str) -> dict:
        """Send command to session (stub for v2.1)."""
        import subprocess
        result = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True
        )
        if result.returncode != 0:
            return {"success": False, "error": "Session not found"}

        # Send command
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, command, "Enter"],
            check=True
        )
        return {"success": True}

    def validate_session_name(self, name: str) -> bool:
        """Validate session name (no special characters)."""
        import re
        # Allow alphanumeric, underscore, dash
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))

    def get_session_path(self, session_name: str) -> str:
        """Get working directory of a tmux session."""
        import subprocess
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", session_name, "-p", "#{pane_current_path}"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def find_sessions_for_project(self, project_path: str) -> List[str]:
        """Find all sessions working in the given project directory.

        Handles sessions with suffixes like claude_my-app-1, claude_my-app-2.
        """
        import subprocess
        project_path = os.path.abspath(os.path.expanduser(project_path))
        matching_sessions = []

        for session in self.get_all_claude_sessions():
            session_path = self.get_session_path(session)
            if session_path == project_path:
                matching_sessions.append(session)

        return matching_sessions

    def get_available_projects(self, scan_dirs: List[str] = None) -> List[Dict]:
        """Get list of available projects from running sessions and scan directories.

        Returns list of dicts with 'path', 'name', and 'has_session' keys.
        """
        if scan_dirs is None:
            scan_dirs = [os.path.expanduser("~/projects")]

        projects = {}

        # Add projects from running sessions
        for session in self.get_all_claude_sessions():
            path = self.get_session_path(session)
            if path and os.path.isdir(path):
                projects[path] = {
                    "path": path,
                    "name": os.path.basename(path),
                    "has_session": True
                }

        # Scan configured directories
        for scan_dir in scan_dirs:
            scan_dir = os.path.expanduser(scan_dir)
            if not os.path.isdir(scan_dir):
                continue

            try:
                for entry in os.listdir(scan_dir):
                    full_path = os.path.join(scan_dir, entry)
                    if os.path.isdir(full_path) and not entry.startswith('.'):
                        if full_path not in projects:
                            projects[full_path] = {
                                "path": full_path,
                                "name": entry,
                                "has_session": False
                            }
            except Exception:
                continue

        # Sort by name
        return sorted(projects.values(), key=lambda x: x['name'])

    def connect_to_project(self, project_path: str) -> Dict:
        """Connect to an existing project directory.

        If sessions already exist for this project, switch to the most recent one.
        Otherwise, create a new session.
        """
        import subprocess

        # Normalize path
        project_path = os.path.abspath(os.path.expanduser(project_path))

        # Check if directory exists
        if not os.path.isdir(project_path):
            return {
                "status": "error",
                "error": f"Directory not found: {project_path}"
            }

        # Check if sessions already exist for this project
        existing_sessions = self.find_sessions_for_project(project_path)

        if existing_sessions:
            # Switch to the most recent session (last in list)
            target_session = existing_sessions[-1]
            self.switch_session(target_session)
            return {
                "status": "switched",
                "session_name": target_session,
                "project_path": project_path,
                "message": f"Switched to existing session: {target_session}"
            }

        # No existing session - create new one
        project_name = os.path.basename(project_path)

        # Generate session name with suffix check
        base_session_name = f"claude_{project_name}"
        session_name = base_session_name
        suffix = 1

        # Find available session name
        while self.session_exists(session_name):
            session_name = f"{base_session_name}-{suffix}"
            suffix += 1

        try:
            # Create tmux session in project directory
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, "-c", project_path],
                check=True
            )

            # Start claude
            subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "claude", "Enter"],
                check=True
            )

            # Switch to new session
            self.switch_session(session_name)

            return {
                "status": "created",
                "session_name": session_name,
                "project_path": project_path,
                "message": f"Created new session: {session_name}"
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create session: {str(e)}"
            }


# Global session manager instance
session_manager = SessionManager()
