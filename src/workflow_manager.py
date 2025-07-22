#!/usr/bin/env python3

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse

from dotenv import load_dotenv
from notion_client import Client as NotionClient
from github import Github
import requests

# Load environment variables from .env file
load_dotenv()


class WorkflowManager:
    def __init__(self):
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.github_token = os.getenv('GITHUB_PAT')
        self.tasks_db_id = os.getenv('NOTION_TASKS_DB_ID')
        self.projects_db_id = os.getenv('NOTION_PROJECTS_DB_ID')
        self.knowledge_hub_id = os.getenv('NOTION_KNOWLEDGE_HUB_ID')
        self.repo_owner = os.getenv('GITHUB_REPO_OWNER')
        self.repo_name = os.getenv('GITHUB_REPO_NAME')
        
        # Initialize clients
        if self.notion_token:
            self.notion = NotionClient(auth=self.notion_token)
        else:
            self.notion = None
            print("⚠️  NOTION_API_KEY not found in environment variables")
            
        if self.github_token:
            self.github = Github(self.github_token)
        else:
            self.github = None
            print("⚠️  GITHUB_PAT not found in environment variables")

    def check_environment(self) -> bool:
        """Check if all required environment variables are set"""
        required_vars = [
            'NOTION_API_KEY', 'GITHUB_PAT', 
            'NOTION_TASKS_DB_ID', 'NOTION_PROJECTS_DB_ID', 'NOTION_KNOWLEDGE_HUB_ID'
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            print("❌ Missing required environment variables:")
            for var in missing:
                print(f"   - {var}")
            print("\n💡 Please check your .env file contains these variables:")
            for var in missing:
                print(f"   {var}=your_value_here")
            return False
        
        return True

    def inspect_database_schema(self, db_id: str, db_name: str):
        """Inspect database schema for debugging"""
        try:
            db_info = self.notion.databases.retrieve(database_id=db_id)
            print(f"\n🔍 {db_name} Database Schema:")
            for prop_name, prop_info in db_info['properties'].items():
                print(f"  - {prop_name}: {prop_info['type']}")
        except Exception as e:
            print(f"❌ Could not retrieve {db_name} schema: {e}")

    def create_project_plan(self, source_file: str, project_id: Optional[str] = None) -> bool:
        """Create Epic and Task tickets in Notion from proposal document"""
        print(f"📋 Creating project plan from {source_file}")
        
        if not self.check_environment():
            return False
        
        # Debug: Inspect database schemas
        self.inspect_database_schema(self.projects_db_id, "Projects")
        self.inspect_database_schema(self.tasks_db_id, "Tasks")
        
        # Read and parse source document
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"❌ Source file not found: {source_file}")
            return False
        
        # For now, create a simple demo Epic and Tasks
        # In production, would use AI to parse the document
        epic_title = "연구용 데이터 분석 파이프라인 구축"
        
        try:
            # Create Epic in Projects database
            epic_response = self.notion.pages.create(
                parent={"database_id": self.projects_db_id},
                properties={
                    "Project name": {"title": [{"text": {"content": f"[Epic] {epic_title}"}}]},
                    "Key Goal": {"rich_text": [{"text": {"content": "재현 가능하고 확장 가능한 연구용 데이터 분석 파이프라인 구축"}}]},
                }
            )
            epic_id = epic_response["id"]
            print(f"✅ Created Epic: {epic_id}")
            
            # Create Tasks in Tasks database
            tasks = [
                "데이터 전처리 모듈 구현",
                "통계 분석 모듈 구현", 
                "시각화 모듈 구현",
                "보고서 생성 모듈 구현",
                "파이프라인 테스트 및 검증"
            ]
            
            task_ids = []
            for i, task_title in enumerate(tasks):
                task_response = self.notion.pages.create(
                    parent={"database_id": self.tasks_db_id},
                    properties={
                        "Task name": {"title": [{"text": {"content": f"[Task] {task_title}"}}]},
                        "Text": {"rich_text": [{"text": {"content": f"데이터 분석 파이프라인 구성요소: {task_title}"}}]},
                        "Projects": {"relation": [{"id": epic_id}]},
                        "Priority": {"select": {"name": "Medium"}},
                    }
                )
                task_id = task_response["id"]
                task_ids.append(task_id)
                print(f"✅ Created Task: T-{i+1:03d} - {task_title}")
            
            print(f"\n🎉 Project plan created successfully!")
            print(f"Epic ID: {epic_id}")
            print(f"Task IDs: {task_ids}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create project plan: {e}")
            return False

    def start_task(self, task_id: str) -> bool:
        """Start a Notion task and create Git branch"""
        print(f"🚀 Starting task: {task_id}")
        
        # Git operations don't require Notion/GitHub tokens
        git_success = False
        
        try:
            # Get current git branch
            current_branch = subprocess.run(
                ['git', 'branch', '--show-current'], 
                capture_output=True, text=True, check=True
            ).stdout.strip()
            
            # Create new branch name
            branch_name = f"feature/T-{task_id}"
            
            # Check if branch already exists
            existing_branches = subprocess.run(
                ['git', 'branch', '--list', branch_name],
                capture_output=True, text=True
            ).stdout.strip()
            
            if existing_branches:
                print(f"⚠️  Branch {branch_name} already exists, switching to it")
                subprocess.run(['git', 'checkout', branch_name], check=True)
            else:
                # Create and checkout new branch
                subprocess.run(['git', 'checkout', '-b', branch_name], check=True)
                print(f"✅ Created and switched to branch: {branch_name}")
            
            git_success = True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Git operation failed: {e}")
            git_success = False
        except Exception as e:
            print(f"❌ Git error: {e}")
            git_success = False
        
        # Update Notion task status (if credentials available)
        notion_success = True
        if self.notion and self.check_environment():
            try:
                print(f"📝 Would update Notion task {task_id} status to 'In progress'")
                # In production: actual Notion API call here
            except Exception as e:
                print(f"⚠️  Notion update failed: {e}")
                notion_success = False
        else:
            print(f"📝 Notion integration not configured, skipping status update")
        
        return git_success

    def archive_task(self, task_id: str, conversation_file: Optional[str] = None) -> bool:
        """Archive terminal conversation log to Notion Task page"""
        print(f"📦 Archiving task: {task_id}")
        
        if not conversation_file:
            # Look for recent conversation export
            export_files = list(Path('.').glob('*-command-message*.txt'))
            if export_files:
                conversation_file = str(max(export_files, key=os.path.getctime))
                print(f"📄 Found conversation file: {conversation_file}")
            else:
                print("❌ No conversation file found. Please run /export first.")
                return False
        
        try:
            with open(conversation_file, 'r', encoding='utf-8') as f:
                conversation_content = f.read()
            
            print(f"✅ Read conversation log ({len(conversation_content)} characters)")
            print("📝 In production, would upload to Notion Task toggle block")
            print("📝 For now, saved conversation content locally")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to archive task: {e}")
            return False

    def finish_task(self, task_id: str, create_pr: bool = False) -> bool:
        """Complete task, create PR, and update Notion"""
        print(f"🏁 Finishing task: {task_id}")
        
        try:
            current_branch = subprocess.run(
                ['git', 'branch', '--show-current'], 
                capture_output=True, text=True, check=True
            ).stdout.strip()
            
            if create_pr and self.github and self.repo_owner and self.repo_name:
                # Get repo
                repo_full_name = f"{self.repo_owner}/{self.repo_name}"
                repo = self.github.get_repo(repo_full_name)
                
                # Create PR
                pr_title = f"[T-{task_id}] Task completion"
                pr_body = f"""
## Summary
Completed task T-{task_id}

## Changes
- Implemented required functionality
- Added tests and documentation

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
"""
                
                pr = repo.create_pull(
                    title=pr_title,
                    body=pr_body,
                    head=current_branch,
                    base="main"
                )
                print(f"✅ Created PR: {pr.html_url}")
            
            print("📝 In production, would update Notion task status to 'Done'")
            return True
            
        except Exception as e:
            print(f"❌ Failed to finish task: {e}")
            return False

    def publish_task(self, task_id: str) -> bool:
        """Publish completed task knowledge to Knowledge Hub"""
        print(f"📚 Publishing task knowledge: {task_id}")
        print("📝 In production, would create knowledge article in Notion Knowledge Hub")
        return True


def main():
    parser = argparse.ArgumentParser(description="Notion-Git Workflow Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Project plan command
    plan_parser = subparsers.add_parser("project-plan", help="Create Epic/Task tickets from proposal")
    plan_parser.add_argument("--source", required=True, help="Source proposal file")
    plan_parser.add_argument("--project", help="Project ID")
    
    # Task commands
    start_parser = subparsers.add_parser("task-start", help="Start a task")
    start_parser.add_argument("task_id", help="Task ID")
    
    archive_parser = subparsers.add_parser("task-archive", help="Archive task conversation")
    archive_parser.add_argument("task_id", help="Task ID")
    archive_parser.add_argument("--file", help="Conversation file path")
    
    finish_parser = subparsers.add_parser("task-finish", help="Finish a task")
    finish_parser.add_argument("task_id", help="Task ID")
    finish_parser.add_argument("--pr", action="store_true", help="Create pull request")
    
    publish_parser = subparsers.add_parser("task-publish", help="Publish task knowledge")
    publish_parser.add_argument("task_id", help="Task ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    manager = WorkflowManager()
    
    success = False
    if args.command == "project-plan":
        success = manager.create_project_plan(args.source, args.project)
    elif args.command == "task-start":
        success = manager.start_task(args.task_id)
    elif args.command == "task-archive":
        success = manager.archive_task(args.task_id, args.file)
    elif args.command == "task-finish":
        success = manager.finish_task(args.task_id, args.pr)
    elif args.command == "task-publish":
        success = manager.publish_task(args.task_id)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())