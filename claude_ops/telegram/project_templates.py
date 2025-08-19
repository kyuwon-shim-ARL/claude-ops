"""
Project Templates for Claude-Ops
Interactive project creation system with templates
"""

import os
import subprocess
from typing import Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class ProjectTemplateManager:
    """Manage project templates and interactive creation"""
    
    def __init__(self):
        self.templates = {
            "🐍 Python": {
                "name": "python",
                "description": "Python project with uv",
                "init_commands": [
                    "uv init",
                    "uv add pytest ruff",
                    "echo '# Python Project\n\nCreated with Claude-Ops' > README.md"
                ]
            },
            "🌐 Web": {
                "name": "web",
                "description": "Web project (Node.js)",
                "init_commands": [
                    "npm init -y",
                    "npm install --save-dev vite",
                    "echo '# Web Project\n\nCreated with Claude-Ops' > README.md"
                ]
            },
            "📊 Data": {
                "name": "data",
                "description": "Data analysis (Jupyter)",
                "init_commands": [
                    "uv init",
                    "uv add jupyter pandas numpy matplotlib",
                    "echo '# Data Analysis Project\n\nCreated with Claude-Ops' > README.md"
                ]
            },
            "🤖 AI/ML": {
                "name": "ml",
                "description": "AI/ML project",
                "init_commands": [
                    "uv init",
                    "uv add torch transformers scikit-learn",
                    "echo '# AI/ML Project\n\nCreated with Claude-Ops' > README.md"
                ]
            },
            "📝 General": {
                "name": "general",
                "description": "General project",
                "init_commands": [
                    "echo '# Project\n\nCreated with Claude-Ops' > README.md"
                ]
            }
        }
    
    def get_recent_projects(self, limit: int = 5) -> List[Dict[str, str]]:
        """Get recent projects from ~/projects directory"""
        projects = []
        projects_dir = os.path.expanduser("~/projects")
        
        if not os.path.exists(projects_dir):
            return projects
        
        # Get directories sorted by modification time
        try:
            dirs = []
            for name in os.listdir(projects_dir):
                path = os.path.join(projects_dir, name)
                if os.path.isdir(path) and not name.startswith('.'):
                    mtime = os.path.getmtime(path)
                    dirs.append((mtime, name, path))
            
            # Sort by modification time (newest first)
            dirs.sort(reverse=True)
            
            # Return top N projects
            for _, name, path in dirs[:limit]:
                projects.append({
                    "name": name,
                    "path": path,
                    "session": f"claude_{name}"
                })
        except Exception as e:
            print(f"Error getting recent projects: {e}")
        
        return projects
    
    def get_project_selection_keyboard(self) -> InlineKeyboardMarkup:
        """Get keyboard for project selection"""
        keyboard = []
        
        # Recent projects section
        recent_projects = self.get_recent_projects(3)
        if recent_projects:
            keyboard.append([
                InlineKeyboardButton(
                    "📂 최근 프로젝트",
                    callback_data="project_recent_header"
                )
            ])
            for project in recent_projects:
                keyboard.append([
                    InlineKeyboardButton(
                        f"▶️ {project['name']}",
                        callback_data=f"project_open_{project['name']}"
                    )
                ])
        
        # New project templates
        keyboard.append([
            InlineKeyboardButton(
                "🆕 새 프로젝트 만들기",
                callback_data="project_new_header"
            )
        ])
        
        template_row = []
        for icon_name, template in self.templates.items():
            if len(template_row) == 2:
                keyboard.append(template_row)
                template_row = []
            template_row.append(
                InlineKeyboardButton(
                    icon_name,
                    callback_data=f"project_template_{template['name']}"
                )
            )
        if template_row:
            keyboard.append(template_row)
        
        # Manual input option
        keyboard.append([
            InlineKeyboardButton(
                "✏️ 직접 입력",
                callback_data="project_manual_input"
            )
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_project_name_prompt(self, template_name: str) -> str:
        """Get prompt message for project name input"""
        template = None
        for t in self.templates.values():
            if t['name'] == template_name:
                template = t
                break
        
        if not template:
            return "프로젝트 이름을 입력하세요:"
        
        return f"""🎯 {template['description']} 프로젝트 생성

프로젝트 이름을 입력하세요:
(예: my_awesome_project)

💡 팁: 영문, 숫자, 언더스코어(_)만 사용하세요"""
    
    def create_project_with_template(
        self, 
        project_name: str, 
        template_name: str,
        custom_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """Create project with specified template"""
        template = None
        for t in self.templates.values():
            if t['name'] == template_name:
                template = t
                break
        
        if not template:
            return {"error": "Template not found"}
        
        # Determine project directory
        if custom_dir:
            project_dir = os.path.join(custom_dir, project_name)
        else:
            project_dir = os.path.join(os.path.expanduser("~/projects"), project_name)
        
        # Create directory
        os.makedirs(project_dir, exist_ok=True)
        
        # Initialize git repository
        subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
        
        # Create .gitignore
        gitignore_content = self._get_gitignore_for_template(template_name)
        with open(os.path.join(project_dir, ".gitignore"), "w") as f:
            f.write(gitignore_content)
        
        # Run template initialization commands
        for cmd in template.get("init_commands", []):
            try:
                subprocess.run(cmd, shell=True, cwd=project_dir, capture_output=True)
            except Exception as e:
                print(f"Error running command '{cmd}': {e}")
        
        # Initial git commit
        subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"🎉 Initial commit - {template['description']}"],
            cwd=project_dir,
            capture_output=True
        )
        
        return {
            "name": project_name,
            "path": project_dir,
            "template": template_name,
            "session": f"claude_{project_name}"
        }
    
    def _get_gitignore_for_template(self, template_name: str) -> str:
        """Get appropriate .gitignore content for template"""
        base_ignore = """# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
*.log
logs/

# Claude
.claude/
CLAUDE.md

# Environment
.env
.env.local
"""
        
        template_specific = {
            "python": """
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
""",
            "web": """
# Node
node_modules/
dist/
build/
.cache/
.parcel-cache/
coverage/
*.local
""",
            "data": """
# Jupyter
.ipynb_checkpoints/
*.ipynb_checkpoints
__pycache__/
.venv/
data/raw/
data/processed/
""",
            "ml": """
# ML/AI
__pycache__/
.venv/
models/
checkpoints/
*.h5
*.pkl
*.pth
wandb/
mlruns/
""",
            "general": ""
        }
        
        return base_ignore + template_specific.get(template_name, "")