"""
Git Branch Manager

Handles Git branch creation, management, and integration with Notion tasks.
"""

import os
import logging
import subprocess
from typing import Optional
from ..config import ClaudeOpsConfig

logger = logging.getLogger(__name__)


class BranchManager:
    """Manages Git branches with Notion task integration"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        """
        Initialize branch manager
        
        Args:
            config: Claude-Ops configuration
        """
        self.config = config or ClaudeOpsConfig()
    
    def create_task_branch(self, task_id: str, description: str = "") -> str:
        """
        Create a new branch for a Notion task
        
        Args:
            task_id: Notion task ID
            description: Branch description
            
        Returns:
            Branch name
        """
        # Generate branch name following convention: feature/TID-XXXXXXXX-description
        branch_name = f"feature/TID-{task_id}"
        if description:
            # Sanitize description for branch name
            desc_clean = description.lower().replace(" ", "-").replace("_", "-")[:20]
            branch_name += f"-{desc_clean}"
        
        try:
            # Create and checkout new branch
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            logger.info(f"Created branch: {branch_name}")
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create branch {branch_name}: {e}")
            raise
    
    def get_current_branch(self) -> str:
        """Get current Git branch name"""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get current branch: {e}")
            return "unknown"
    
    def extract_task_id_from_branch(self, branch_name: Optional[str] = None) -> Optional[str]:
        """
        Extract Notion task ID from branch name
        
        Args:
            branch_name: Branch name (uses current branch if None)
            
        Returns:
            Task ID or None
        """
        if not branch_name:
            branch_name = self.get_current_branch()
        
        # Extract TID from branch name like feature/TID-XXXXXXXX-description
        if "TID-" in branch_name:
            parts = branch_name.split("TID-")
            if len(parts) > 1:
                # Get the part after TID- and before next dash (if any)
                task_part = parts[1].split("-")[0]
                return task_part
        
        return None
    
    def commit_and_push(self, message: str, push: bool = True) -> bool:
        """
        Commit changes and optionally push
        
        Args:
            message: Commit message
            push: Whether to push to remote
            
        Returns:
            Success status
        """
        try:
            # Add all changes
            subprocess.run(["git", "add", "."], check=True)
            
            # Commit with message
            subprocess.run(["git", "commit", "-m", message], check=True)
            logger.info(f"Committed: {message}")
            
            if push:
                branch_name = self.get_current_branch()
                subprocess.run(["git", "push", "-u", "origin", branch_name], check=True)
                logger.info(f"Pushed branch: {branch_name}")
            
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to commit/push: {e}")
            return False
    
    def create_pull_request(self, title: str, body: str = "") -> bool:
        """
        Create pull request using GitHub CLI
        
        Args:
            title: PR title
            body: PR body
            
        Returns:
            Success status
        """
        try:
            cmd = ["gh", "pr", "create", "--title", title]
            if body:
                cmd.extend(["--body", body])
            
            subprocess.run(cmd, check=True)
            logger.info(f"Created PR: {title}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create PR: {e}")
            return False