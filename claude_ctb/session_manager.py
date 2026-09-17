"""
Session Manager for Multi-Session Support

Manages active session state and switching between different Claude Code sessions.
"""

import glob
import json
import os
import time
from datetime import datetime
from typing import Dict, List


# ---------------------------------------------------------------------------
# Hook event helpers (module-level)
# ---------------------------------------------------------------------------

_CTB_HOOK_MARKER = "ctb-stall-hook"  # settings.json에서 CTB hook을 식별하는 마커


def write_hook_event(session_id: str, event_type: str) -> None:
    """hook 이벤트를 원자적으로 /tmp/ctb-events-{session_id}-{ts_ns}.json에 기록."""
    try:
        ts_ns = int(time.time_ns())
        event = {
            "session_id": session_id,
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
        }
        tmp_path = f"/tmp/ctb-events-{session_id}-{ts_ns}.tmp"
        final_path = f"/tmp/ctb-events-{session_id}-{ts_ns}.json"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(event, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.rename(tmp_path, final_path)
    except Exception:
        pass  # 이벤트 기록 실패는 무시 (모니터링 보조 기능)


def _build_hook_command(session_id: str) -> str:
    """PreToolUse hook에 사용할 셸 명령어를 생성합니다."""
    return (
        f"python3 -c \""
        f"import os,json,time;"
        f"sid='{session_id}';"
        f"ts=int(time.time_ns());"
        f"event={{'session_id':sid,'timestamp_iso':__import__('datetime').datetime.utcnow().isoformat()+'Z','event_type':'tool_start'}};"
        f"tmp=f'/tmp/ctb-events-{{sid}}-{{ts}}.tmp';"
        f"final=f'/tmp/ctb-events-{{sid}}-{{ts}}.json';"
        f"fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);"
        f"os.write(fd,json.dumps(event).encode());"
        f"os.close(fd);"
        f"os.rename(tmp,final)"
        f"\""
    )


def register_session_hooks(project_dir: str, session_id: str) -> bool:
    """프로젝트의 .claude/settings.json에 CTB stall 감지 hooks를 등록합니다.

    Args:
        project_dir: Claude Code 프로젝트 루트 디렉토리
        session_id: 세션 식별자 (tmux 세션명 권장)

    Returns:
        True if successfully registered, False otherwise
    """
    try:
        settings_path = os.path.join(project_dir, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)

        # 기존 settings 로드
        settings: Dict = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

        # hooks 섹션 초기화
        if "hooks" not in settings:
            settings["hooks"] = {}

        # 이미 CTB hook이 등록되어 있으면 스킵
        pre_hooks = settings["hooks"].get("PreToolUse", [])
        for h in pre_hooks:
            if isinstance(h, dict) and any(
                _CTB_HOOK_MARKER in hk.get("command", "")
                for hk in h.get("hooks", [])
            ):
                return True  # 이미 등록됨

        # PreToolUse hook 추가
        cmd = _build_hook_command(session_id)
        ctb_hook = {
            "matcher": "",
            "hooks": [{"type": "command", "command": f"# {_CTB_HOOK_MARKER}\n{cmd}"}],
        }
        if "PreToolUse" not in settings["hooks"]:
            settings["hooks"]["PreToolUse"] = []
        settings["hooks"]["PreToolUse"].append(ctb_hook)

        # .omc/state/sessions/{session_id}/ 디렉토리에 hook_supported 플래그 생성
        flag_dir = os.path.join(".omc", "state", "sessions", session_id)
        os.makedirs(flag_dir, exist_ok=True)
        with open(os.path.join(flag_dir, "hook_supported"), "w") as f:
            f.write(session_id)

        # settings.json 저장
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        return True
    except Exception:
        return False


def unregister_session_hooks(project_dir: str, session_id: str) -> None:
    """CTB hooks를 settings.json에서 제거하고 이벤트 파일을 정리합니다."""
    try:
        settings_path = os.path.join(project_dir, ".claude", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

            if "hooks" in settings and "PreToolUse" in settings["hooks"]:
                settings["hooks"]["PreToolUse"] = [
                    h for h in settings["hooks"]["PreToolUse"]
                    if not (
                        isinstance(h, dict)
                        and any(
                            _CTB_HOOK_MARKER in hk.get("command", "")
                            for hk in h.get("hooks", [])
                        )
                    )
                ]
                if not settings["hooks"]["PreToolUse"]:
                    del settings["hooks"]["PreToolUse"]
                if not settings["hooks"]:
                    del settings["hooks"]

            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # 이벤트 파일 정리
    try:
        for path in glob.glob(f"/tmp/ctb-events-{session_id}-*.json"):
            try:
                os.unlink(path)
            except Exception:
                pass
    except Exception:
        pass

    # hook_supported 플래그 제거
    try:
        flag_path = os.path.join(".omc", "state", "sessions", session_id, "hook_supported")
        if os.path.exists(flag_path):
            os.unlink(flag_path)
    except Exception:
        pass


class SessionManager:
    """Manages multiple Claude Code sessions"""
    
    def __init__(self):
        self.state_file = "/tmp/claude_ctb_active_session.json"
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
        """Sort sessions by last activity time (most recent first)

        Uses single tmux call to fetch all session activity times at once.
        """
        import subprocess

        try:
            # Single tmux call to get all session names + activity times
            result = subprocess.run(
                "tmux list-sessions -F '#{session_name} #{session_activity}'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return sessions

            # Parse into lookup dict
            activity_map = {}
            for line in result.stdout.strip().split('\n'):
                parts = line.strip().split(' ', 1)
                if len(parts) == 2:
                    try:
                        activity_map[parts[0]] = int(parts[1])
                    except ValueError:
                        activity_map[parts[0]] = 0

            # Sort requested sessions by activity time
            session_times = [(s, activity_map.get(s, 0)) for s in sessions]
            session_times.sort(key=lambda x: x[1], reverse=True)
            return [s for s, _ in session_times]

        except Exception:
            return sessions
    
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
        project_path = os.path.abspath(os.path.expanduser(project_path))
        matching_sessions = []

        for session in self.get_all_claude_sessions():
            session_path = self.get_session_path(session)
            if session_path == project_path or session_path.startswith(project_path + '/'):
                matching_sessions.append(session)

        return matching_sessions

    @staticmethod
    def _resolve_worktree_parent(path: str) -> str:
        """Resolve a worktree path to its parent project path.

        If path contains '/.claude/worktrees/', returns the project root.
        Otherwise returns the path unchanged.
        """
        marker = '/.claude/worktrees/'
        idx = path.find(marker)
        if idx != -1:
            return path[:idx]
        return path

    def get_available_projects(self, scan_dirs: List[str] = None) -> List[Dict]:
        """Get list of available projects from running sessions and scan directories.

        Returns list of dicts with 'path', 'name', 'has_session', and 'mtime' keys.
        Sorted by modification time (oldest first, so newest appear at bottom in Telegram).
        """
        if scan_dirs is None:
            scan_dirs = [os.path.expanduser("~/projects")]

        projects = {}

        # Add projects from running sessions
        for session in self.get_all_claude_sessions():
            path = self.get_session_path(session)
            if path and os.path.isdir(path):
                # Resolve worktree paths to parent project
                project_path = self._resolve_worktree_parent(path)
                if not os.path.isdir(project_path):
                    project_path = path  # fallback to original if parent missing
                try:
                    mtime = os.path.getmtime(path)
                except Exception:
                    mtime = 0

                # Use parent project path as key to avoid duplicate entries
                if project_path in projects:
                    # Update mtime if this session is more recent
                    if mtime > projects[project_path]["mtime"]:
                        projects[project_path]["mtime"] = mtime
                else:
                    projects[project_path] = {
                        "path": project_path,
                        "name": os.path.basename(project_path),
                        "has_session": True,
                        "mtime": mtime
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
                            try:
                                mtime = os.path.getmtime(full_path)
                            except Exception:
                                mtime = 0

                            projects[full_path] = {
                                "path": full_path,
                                "name": entry,
                                "has_session": False,
                                "mtime": mtime
                            }
            except Exception:
                continue

        # Sort by modification time (oldest first, so newest appear at bottom in Telegram)
        return sorted(projects.values(), key=lambda x: x['mtime'])

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
            # Switch to the most recent session (first in activity-sorted list)
            target_session = existing_sessions[0]
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
                ["tmux", "send-keys", "-t", session_name, "claude --dangerously-skip-permissions", "Enter"],
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

    def register_hooks(self, project_dir: str, session_id: str) -> bool:
        """프로젝트에 CTB stall 감지 hooks를 등록합니다."""
        return register_session_hooks(project_dir, session_id)

    def unregister_hooks(self, project_dir: str, session_id: str) -> None:
        """프로젝트에서 CTB hooks를 제거하고 이벤트 파일을 정리합니다."""
        unregister_session_hooks(project_dir, session_id)


# Global session manager instance
session_manager = SessionManager()
