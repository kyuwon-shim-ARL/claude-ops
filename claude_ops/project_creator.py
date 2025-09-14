"""
Unified Project Creator
Provides consistent project creation functionality for both CLI and Telegram interfaces
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ProjectCreator:
    """Unified project creation with Git initialization and complete setup"""
    
    def __init__(self, project_name: str, project_path: Optional[str] = None):
        self.project_name = project_name
        self.session_name = f"claude_{project_name}"
        
        # Determine target directory
        if project_path:
            self.project_dir = Path(project_path).resolve()
        else:
            self.project_dir = Path.home() / "projects" / project_name
        
        self.results = {
            "project_name": project_name,
            "project_path": str(self.project_dir),
            "session_name": self.session_name,
            "git_initialized": False,
            "session_created": False,
            "status": "pending"
        }
    
    def create_project(self, initialize_git: bool = True, install_dev_kit: bool = True) -> Dict[str, Any]:
        """Create complete project with all features"""
        try:
            logger.info(f"🚀 Creating project: {self.project_name}")
            
            # Step 1: Create directory
            if not self._create_directory():
                return self._error_result("Directory creation failed")
            
            # Step 2: Initialize Git repository (if requested)
            if initialize_git:
                if not self._initialize_git():
                    return self._error_result("Git initialization failed")
            
            # Step 3: Install development kit (if requested)
            if install_dev_kit:
                if not self._install_dev_kit():
                    logger.warning("Dev kit installation failed, continuing...")
            
            # Step 4: Create tmux session
            if not self._create_tmux_session():
                return self._error_result("Tmux session creation failed")
            
            # Success
            success_message = f"✅ Project '{self.project_name}' created successfully!"
            
            # Add warning if git remote not configured
            if self.results.get("git_remote_warning"):
                success_message += "\n\n⚠️  IMPORTANT: Git remote not configured!"
                success_message += "\n   Run: git remote add origin <your-repo-url>"
                success_message += "\n   See GIT_REMOTE_NOT_SET.txt for details"
            
            self.results.update({
                "status": "success",
                "message": success_message,
                "created_at": datetime.now().isoformat()
            })
            
            logger.info(f"✅ Project creation completed: {self.project_name}")
            
            # Show prominent warning if remote not set
            if self.results.get("git_remote_warning"):
                logger.warning("=" * 60)
                logger.warning("⚠️  GIT REMOTE NOT CONFIGURED - ACTION REQUIRED!")
                logger.warning("=" * 60)
                logger.warning("Your project was created but cannot be pushed to GitHub/GitLab.")
                logger.warning("To fix this:")
                logger.warning("  1. Create a repository on GitHub/GitLab")
                logger.warning("  2. Run: git remote add origin <your-repo-url>")
                logger.warning("  3. Push: git push -u origin main")
                logger.warning("=" * 60)
            
            return self.results
            
        except Exception as e:
            logger.error(f"❌ Project creation failed: {e}")
            return self._error_result(f"Unexpected error: {str(e)}")
    
    def _create_directory(self) -> bool:
        """Create project directory"""
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created directory: {self.project_dir}")
            return True
        except Exception as e:
            logger.error(f"Directory creation error: {e}")
            return False
    
    def _initialize_git(self) -> bool:
        """Initialize Git repository with .gitignore and initial commit"""
        try:
            # Check if already a git repository
            if (self.project_dir / ".git").exists():
                logger.info("📦 Git repository already exists")
                self.results["git_initialized"] = True
                return True
            
            # Change to project directory
            original_cwd = os.getcwd()
            os.chdir(self.project_dir)
            
            try:
                # Initialize git
                result = subprocess.run(
                    ["git", "init"], 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
                if result.returncode != 0:
                    logger.error(f"Git init failed: {result.stderr}")
                    return False
                
                # Create comprehensive .gitignore
                gitignore_content = self._get_gitignore_template()
                gitignore_path = self.project_dir / ".gitignore"
                gitignore_path.write_text(gitignore_content, encoding='utf-8')
                
                # Add and commit
                subprocess.run(["git", "add", ".gitignore"], check=True, timeout=10)
                
                commit_message = f"""🎉 Initial commit - Project: {self.project_name}

Generated by Claude-Ops ProjectCreator
Directory: {self.project_dir}
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                
                subprocess.run(
                    ["git", "commit", "-m", commit_message], 
                    check=True, 
                    timeout=10
                )
                
                logger.info("📦 Git repository initialized with .gitignore and initial commit")
                
                # Check for remote configuration
                remote_check = subprocess.run(
                    ["git", "remote", "-v"], 
                    capture_output=True, 
                    text=True,
                    timeout=5
                )
                
                if not remote_check.stdout.strip():
                    # No remote configured - show warning
                    logger.warning("⚠️  Git remote not configured!")
                    logger.warning("   Set remote with: git remote add origin <your-repo-url>")
                    logger.warning("   Example: git remote add origin git@github.com:USERNAME/REPO.git")
                    
                    # Create warning file in project directory
                    self._create_git_remote_warning_file()
                    
                    # Install pre-push hook to verify remote
                    self._install_pre_push_hook()
                    
                    self.results["git_remote_warning"] = True
                else:
                    logger.info(f"✅ Git remote configured: {remote_check.stdout.strip().split()[1]}")
                    self.results["git_remote_configured"] = True
                
                self.results["git_initialized"] = True
                return True
                
            finally:
                os.chdir(original_cwd)
                
        except subprocess.TimeoutExpired:
            logger.error("Git operations timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Git initialization error: {e}")
            return False
    
    def _get_gitignore_template(self) -> str:
        """Get comprehensive .gitignore template"""
        return """# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
.env
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/

# Node
node_modules/
dist/
build/
.cache/
.parcel-cache/
coverage/
*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Claude
.claude/
CLAUDE.md

# Environment
.env
.env.local

# Jupyter
.ipynb_checkpoints/
*.ipynb_checkpoints

# ML/AI
models/
checkpoints/
*.h5
*.pkl
*.pth
wandb/
mlruns/

# Database
*.db
*.sqlite
*.sqlite3

# Temporary files
*.tmp
*.temp
.tmp/
.temp/
"""
    
    def _install_dev_kit(self) -> bool:
        """Install development kit with claude-dev-kit remote installation"""
        try:
            logger.info("🛠️ Starting claude-dev-kit installation...")
            
            # Try remote claude-dev-kit installation first
            if self._install_remote_claude_dev_kit():
                logger.info("✅ Remote claude-dev-kit installation successful")
                return True
            else:
                logger.warning("⚠️ Remote installation failed, falling back to local setup")
                return self._install_local_fallback()
                
        except Exception as e:
            logger.error(f"Dev kit installation error: {e}")
            logger.info("🔄 Falling back to local setup")
            return self._install_local_fallback()
    
    def _install_remote_claude_dev_kit(self) -> bool:
        """Install claude-dev-kit from remote repository with enhanced error handling"""
        try:
            # Ensure project directory exists
            self.project_dir.mkdir(parents=True, exist_ok=True)
            
            original_cwd = os.getcwd()
            os.chdir(self.project_dir)
            
            try:
                # Pre-create essential directories to prevent installation failures
                essential_dirs = [
                    "docs/development/guides",
                    "docs/development/sessions",
                    "docs/CURRENT",
                    "docs/specs",
                    f"src/{self.project_name}/core",
                    f"src/{self.project_name}/models",
                    f"src/{self.project_name}/services",
                    "tests",
                    "scripts",
                    "examples"
                ]
                
                for dir_path in essential_dirs:
                    Path(self.project_dir / dir_path).mkdir(parents=True, exist_ok=True)
                
                logger.info("📁 Pre-created essential directories")
                
                # Run remote installation
                install_command = (
                    f"curl -sSL https://raw.githubusercontent.com/kyuwon-shim-ARL/claude-dev-kit/main/install.sh | "
                    f"bash -s {self.project_name} 'Claude-managed project with dev-ops automation'"
                )
                
                logger.info(f"Executing remote installation: {install_command[:80]}...")
                result = subprocess.run(
                    install_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.project_dir
                )
                
                # Validate installation regardless of return code
                if self._validate_installation():
                    logger.info("🚀 Claude-dev-kit remote installation completed successfully")
                    return True
                else:
                    logger.warning(f"Remote installation incomplete: {result.stderr[:200] if result.stderr else 'Missing critical files'}")
                    return False
                    
            finally:
                os.chdir(original_cwd)
                
        except subprocess.TimeoutExpired:
            logger.warning("Remote installation timed out after 30 seconds")
            # Still create basic structure on timeout
            self._ensure_basic_structure()
            return False
        except Exception as e:
            logger.error(f"Remote installation error: {e}")
            self._ensure_basic_structure()
            return False
    
    def _install_local_fallback(self) -> bool:
        """Comprehensive local fallback with complete claude-dev-kit structure"""
        try:
            logger.info("🔧 Installing comprehensive local fallback structure...")
            
            # Create complete directory structure
            directory_structure = {
                f"src/{self.project_name}/core": ["__init__.py"],
                f"src/{self.project_name}/models": ["__init__.py"],
                f"src/{self.project_name}/services": ["__init__.py"],
                f"src/{self.project_name}": ["__init__.py"],
                "docs/CURRENT": ["active-todos.md", "planning.md", "status.md"],
                "docs/development/sessions": [],
                "docs/development/guides": ["claude-code-workflow.md"],
                "docs/specs": [],
                "tests": ["__init__.py", "test_main.py"],
                "scripts": ["test_setup.py"],
                "examples": ["basic_usage.py"]
            }
            
            # Create directories and files
            for dir_path, files in directory_structure.items():
                full_dir = self.project_dir / dir_path
                full_dir.mkdir(parents=True, exist_ok=True)
                
                for file_name in files:
                    file_path = full_dir / file_name
                    if not file_path.exists():
                        if file_name == "__init__.py":
                            file_path.write_text('"""Package initialization"""\n')
                        elif file_name == "active-todos.md":
                            file_path.write_text(f"# Active TODOs\n\n- [ ] Initialize {self.project_name} project\n")
                        elif file_name == "planning.md":
                            file_path.write_text(f"# {self.project_name} Planning\n\n## Overview\n\n## Objectives\n\n")
                        elif file_name == "status.md":
                            file_path.write_text(f"# Project Status\n\n**Project**: {self.project_name}\n**Created**: {datetime.now().isoformat()}\n")
                        elif file_name == "claude-code-workflow.md":
                            file_path.write_text(self._get_workflow_guide_content())
                        elif file_name == "test_main.py":
                            file_path.write_text(self._get_test_template())
                        elif file_name == "test_setup.py":
                            file_path.write_text(self._get_test_setup_script())
                        elif file_name == "basic_usage.py":
                            file_path.write_text(self._get_example_code())
            
            # Create root files
            self._create_claude_md()
            self._create_comprehensive_gitignore()
            self._create_main_app()
            self._create_readme()
            
            logger.info("✅ Comprehensive local fallback structure created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Local fallback installation error: {e}")
            return False
    
    def _create_tmux_session(self) -> bool:
        """Create tmux session for the project"""
        try:
            # Check if session already exists
            check_result = subprocess.run(
                ["tmux", "has-session", "-t", self.session_name],
                capture_output=True,
                timeout=10
            )
            
            if check_result.returncode == 0:
                logger.info(f"🎯 Session '{self.session_name}' already exists")
                self.results["session_created"] = True
                return True
            
            # Create new session
            subprocess.run([
                "tmux", "new-session", "-d", "-s", self.session_name,
                "-c", str(self.project_dir)
            ], check=True, timeout=10)
            
            # Start claude in the session
            subprocess.run([
                "tmux", "send-keys", "-t", self.session_name, "claude", "Enter"
            ], check=True, timeout=5)
            
            logger.info(f"🎯 Created tmux session: {self.session_name}")
            self.results["session_created"] = True
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Tmux operations timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Tmux command failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Tmux session creation error: {e}")
            return False
    
    def _validate_installation(self) -> bool:
        """Validate that installation was successful"""
        critical_paths = [
            self.project_dir / "CLAUDE.md",
            self.project_dir / "src" / self.project_name,
            self.project_dir / "docs" / "development" / "guides"
        ]
        
        for path in critical_paths:
            if not path.exists():
                logger.debug(f"Validation failed: {path} does not exist")
                return False
        
        return True
    
    def _create_git_remote_warning_file(self) -> None:
        """Create warning file about git remote configuration"""
        try:
            warning_file = self.project_dir / "GIT_REMOTE_NOT_SET.txt"
            warning_content = """⚠️  GIT REMOTE NOT CONFIGURED ⚠️
=====================================

Your Git repository has been initialized but NO REMOTE is configured.
This means you cannot push your code to GitHub/GitLab/etc.

TO FIX THIS:
------------
1. Create a repository on GitHub/GitLab/Bitbucket
2. Add the remote URL to your local repository:
   
   git remote add origin <your-repo-url>
   
   Examples:
   - GitHub SSH:   git remote add origin git@github.com:USERNAME/REPO.git
   - GitHub HTTPS: git remote add origin https://github.com/USERNAME/REPO.git
   - GitLab SSH:   git remote add origin git@gitlab.com:USERNAME/REPO.git

3. Verify the remote is set:
   git remote -v

4. Push your code:
   git push -u origin main

⚠️  DELETE THIS FILE after setting up your remote ⚠️

Note: A pre-push hook has been installed that will remind you
      to set up the remote before your first push attempt.
"""
            warning_file.write_text(warning_content, encoding='utf-8')
            logger.info(f"📝 Created git remote warning file: {warning_file.name}")
        except Exception as e:
            logger.error(f"Failed to create git remote warning file: {e}")
    
    def _install_pre_push_hook(self) -> None:
        """Install pre-push hook to verify remote configuration"""
        try:
            hooks_dir = self.project_dir / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            
            pre_push_hook = hooks_dir / "pre-push"
            hook_content = """#!/bin/bash
# Pre-push hook to verify git remote configuration

# Check if remote is configured
if [ -z "$(git remote -v)" ]; then
    echo "❌ ERROR: No git remote configured!"
    echo ""
    echo "You must set up a remote repository before pushing:"
    echo "  git remote add origin <your-repo-url>"
    echo ""
    echo "Example:"
    echo "  git remote add origin git@github.com:USERNAME/REPO.git"
    echo ""
    echo "After setting the remote, you can push with:"
    echo "  git push -u origin main"
    echo ""
    exit 1
fi

# Check if warning file exists and remind to delete it
if [ -f "GIT_REMOTE_NOT_SET.txt" ]; then
    echo "⚠️  Reminder: Delete GIT_REMOTE_NOT_SET.txt after verifying remote setup"
    echo ""
fi

exit 0
"""
            pre_push_hook.write_text(hook_content, encoding='utf-8')
            
            # Make hook executable
            pre_push_hook.chmod(0o755)
            
            logger.info("🪝 Installed pre-push hook for remote verification")
        except Exception as e:
            logger.error(f"Failed to install pre-push hook: {e}")
    
    def _ensure_basic_structure(self) -> None:
        """Ensure basic directory structure exists"""
        try:
            basic_dirs = ["src", "docs", "tests"]
            for dir_name in basic_dirs:
                (self.project_dir / dir_name).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create basic structure: {e}")
    
    def _create_claude_md(self) -> None:
        """Create CLAUDE.md file with project configuration"""
        content = f"""# {self.project_name}: Claude Code Project

## Project Overview
Claude-managed project with full dev-ops automation

## Development Workflow

This project uses 4-stage keyword-based development:
- **"기획"** → Structured Discovery & Planning
- **"구현"** → Implementation with DRY principles
- **"안정화"** → Structural Sustainability Protocol
- **"배포"** → Deployment with quality gates

## Project Structure

```
{self.project_name}/
├── src/{self.project_name}/
│   ├── core/       # Core business logic
│   ├── models/     # Data models
│   └── services/   # Service layer
├── docs/
│   ├── CURRENT/    # Active documentation
│   └── development/# Development guides
├── tests/          # Test suite
└── examples/       # Usage examples
```

## Created
{datetime.now().isoformat()}
"""
        (self.project_dir / "CLAUDE.md").write_text(content)
    
    def _create_comprehensive_gitignore(self) -> None:
        """Create comprehensive .gitignore file"""
        content = self._get_gitignore_content()
        (self.project_dir / ".gitignore").write_text(content)
    
    def _get_gitignore_content(self) -> str:
        """Get comprehensive .gitignore content (reuse existing template)"""
        return self._get_gitignore_template()
    
    def _create_main_app(self) -> None:
        """Create main application entry point"""
        content = f'''#!/usr/bin/env python3
"""
{self.project_name} - Main Application Entry Point
"""

def run():
    """Main application runner"""
    print(f"Running {self.project_name}...")
    # Application logic here

if __name__ == "__main__":
    run()
'''
        (self.project_dir / "main_app.py").write_text(content)
    
    def _create_readme(self) -> None:
        """Create README.md file"""
        content = f"""# {self.project_name}

Created with Claude-Ops ProjectCreator

## Getting Started

This project was created on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} using Claude-Ops.

## Project Structure

- `src/{self.project_name}/` - Source code with modular architecture
- `tests/` - Test files  
- `docs/` - Comprehensive documentation
- `examples/` - Usage examples
- `scripts/` - Utility scripts

## Development

Start working in your Claude session:
```bash
tmux attach -t {self.session_name}
```

## Claude Integration

This project is set up for Claude Code development with:
- Complete claude-dev-kit structure
- Git repository initialized
- Comprehensive .gitignore
- Modular project architecture
- tmux session configured
"""
        (self.project_dir / "README.md").write_text(content)
    
    def _get_workflow_guide_content(self) -> str:
        """Get claude-code-workflow.md content"""
        return """# Claude Code Development Workflow

## Keyword-Based Development

### 1. 기획 (Planning)
- Structured discovery and analysis
- MECE-based task breakdown
- Priority setting

### 2. 구현 (Implementation)
- Search existing code first
- Reuse before creating new
- TodoWrite-based systematic progress
- Unit tests & basic validation

### 3. 안정화 (Stabilization)
- Structure scan and optimization
- Dependency resolution
- Integration testing
- Documentation sync

### 4. 배포 (Deployment)
- Final validation
- Structured commits
- Push with tags
"""
    
    def _get_test_template(self) -> str:
        """Get test template content"""
        return f'''"""
Test suite for {self.project_name}
"""

import unittest


class Test{self.project_name.title().replace("_", "")}(unittest.TestCase):
    """Main test class"""
    
    def test_example(self):
        """Example test case"""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
'''
    
    def _get_test_setup_script(self) -> str:
        """Get test setup script content"""
        return '''#!/usr/bin/env python3
"""Test setup and utilities"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_test_environment():
    """Set up test environment"""
    print("Test environment configured")

if __name__ == "__main__":
    setup_test_environment()
'''
    
    def _get_example_code(self) -> str:
        """Get example code content"""
        return f'''#!/usr/bin/env python3
"""
Basic usage example for {self.project_name}
"""

def main():
    """Main entry point for example"""
    print(f"Running {self.project_name} example...")
    # Add your example code here

if __name__ == "__main__":
    main()
'''
    
    def _error_result(self, error_message: str) -> Dict[str, Any]:
        """Create error result"""
        self.results.update({
            "status": "error",
            "error": error_message,
            "failed_at": datetime.now().isoformat()
        })
        return self.results
    
    @classmethod
    def create_project_simple(
        cls, 
        project_name: str, 
        project_path: Optional[str] = None,
        initialize_git: bool = True,
        install_dev_kit: bool = True
    ) -> Dict[str, Any]:
        """Simple class method for creating projects"""
        creator = cls(project_name, project_path)
        return creator.create_project(initialize_git, install_dev_kit)


def main():
    """CLI interface for testing ProjectCreator"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m claude_ops.project_creator <project_name> [project_path]")
        return
    
    project_name = sys.argv[1]
    project_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = ProjectCreator.create_project_simple(project_name, project_path)
    
    if result["status"] == "success":
        print(f"✅ {result['message']}")
        print(f"📁 Path: {result['project_path']}")
        print(f"🎯 Session: {result['session_name']}")
        if result.get('git_initialized'):
            print("📦 Git repository initialized")
    else:
        print(f"❌ Error: {result['error']}")


if __name__ == "__main__":
    main()