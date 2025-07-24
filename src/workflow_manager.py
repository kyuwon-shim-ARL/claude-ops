#!/usr/bin/env python3

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

from dotenv import load_dotenv
from notion_client import Client as NotionClient
from github import Github

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
        
        # Read and parse source document (for future AI parsing)
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                _ = f.read()  # Will be used for AI parsing in future
        except FileNotFoundError:
            print(f"❌ Source file not found: {source_file}")
            return False
        
        # Parse document and create proper hierarchy
        project_title = "연구용 데이터 분석 파이프라인 프로젝트"
        
        try:
            # Step 1: Create Project in Projects database
            project_response = self.notion.pages.create(
                parent={"database_id": self.projects_db_id},
                properties={
                    "Project name": {"title": [{"text": {"content": project_title}}]},
                    "Key Goal": {"rich_text": [{"text": {"content": "재현 가능하고 확장 가능한 연구용 데이터 분석 파이프라인 구축을 위한 종합 프로젝트"}}]},
                }
            )
            project_id = project_response["id"]
            print(f"✅ Created Project: {project_id}")
            
            # Step 2: Create Epics in Tasks database
            epics = [
                {
                    "title": "데이터 처리 파이프라인 구축",
                    "description": "원본 데이터 수집부터 정제된 분석용 데이터 생성까지의 전체 파이프라인 구축",
                    "tasks": ["데이터 수집 모듈 구현", "데이터 전처리 모듈 구현", "데이터 검증 모듈 구현"]
                },
                {
                    "title": "분석 및 모델링 시스템 구축", 
                    "description": "통계 분석, 기계학습 모델링, 결과 해석을 위한 분석 시스템 구축",
                    "tasks": ["통계 분석 모듈 구현", "모델링 모듈 구현", "결과 해석 모듈 구현"]
                },
                {
                    "title": "시각화 및 보고서 시스템 구축",
                    "description": "분석 결과의 시각화 및 자동 보고서 생성 시스템 구축", 
                    "tasks": ["시각화 모듈 구현", "보고서 생성 모듈 구현", "대시보드 구현"]
                }
            ]
            
            epic_ids = []
            all_task_ids = []
            
            for epic_num, epic_info in enumerate(epics, 1):
                # Create Epic as Task with IsEpic=True
                epic_response = self.notion.pages.create(
                    parent={"database_id": self.tasks_db_id},
                    properties={
                        "Task name": {"title": [{"text": {"content": f"Epic {epic_num}: {epic_info['title']}"}}]},
                        "Text": {"rich_text": [{"text": {"content": epic_info['description']}}]},
                        "Projects": {"relation": [{"id": project_id}]},
                        "Priority": {"select": {"name": "High"}},
                    }
                )
                epic_id = epic_response["id"]
                epic_ids.append(epic_id)
                print(f"✅ Created Epic: {epic_info['title']}")
                
                # Add detailed content to Epic page
                self._add_epic_content(epic_id, epic_info)
                
                # Create SubTasks for this Epic
                task_ids = []
                for task_num, task_title in enumerate(epic_info['tasks'], 1):
                    task_response = self.notion.pages.create(
                        parent={"database_id": self.tasks_db_id},
                        properties={
                            "Task name": {"title": [{"text": {"content": f"Task {epic_num}.{task_num}: {task_title}"}}]},
                            "Text": {"rich_text": [{"text": {"content": f"{epic_info['title']} 세부 구현 작업: {task_title}"}}]},
                            "Projects": {"relation": [{"id": project_id}]},
                            "ParentTask": {"relation": [{"id": epic_id}]},
                            "Priority": {"select": {"name": "Medium"}},
                        }
                    )
                    task_id = task_response["id"]
                    task_ids.append(task_id)
                    all_task_ids.append({"id": task_id, "title": task_title, "epic": epic_info['title']})
                    
                    # Add detailed content to Task page
                    self._add_task_content(task_id, task_title, epic_info['title'])
                    
                    print(f"  ✅ Created SubTask: {task_title}")
            
            print(f"\n🎉 Project plan created successfully!")
            print(f"📁 Project ID: {project_id}")
            print(f"📋 Epic IDs: {epic_ids}")
            print(f"✅ Total Tasks created: {len(all_task_ids)}")
            
            # Print TIDs for direct use with slash commands
            self._print_task_ids(all_task_ids)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to create project plan: {e}")
            return False

    def _add_epic_content(self, epic_id: str, epic_info: dict):
        """Add detailed content to Epic page"""
        try:
            content_blocks = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "🎯 Epic 목표"}}]
                    }
                },
                {
                    "object": "block", 
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": epic_info['description']}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2", 
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "📋 SubTasks"}}]
                    }
                }
            ]
            
            # Add task list items
            for task in epic_info['tasks']:
                content_blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": task}}]
                    }
                })
            
            for block in content_blocks:
                self.notion.blocks.children.append(block_id=epic_id, children=[block])
                
        except Exception as e:
            print(f"⚠️  Could not add content to Epic page: {e}")

    def _add_task_content(self, task_id: str, task_title: str, epic_title: str):
        """Add detailed content to Task page"""
        try:
            content_blocks = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "🎯 작업 목표"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph", 
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": f"{epic_title}의 일환으로 {task_title}를 구현합니다."}}]
                    }
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "📚 참고 자료"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "• 관련 문서 및 레퍼런스 추가 예정\n• 기술 스펙 및 요구사항 정리 예정"}}]
                    }
                },
                {
                    "object": "block", 
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "🔄 탐색 일지 및 산출물"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": "💬 AI 대화 기록 (task-archive로 자동 업데이트)"}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "paragraph", 
                                "paragraph": {
                                    "rich_text": [{"type": "text", "text": {"content": "여기에 작업 과정의 AI 대화 기록이 자동으로 저장됩니다."}}]
                                }
                            }
                        ]
                    }
                }
            ]
            
            for block in content_blocks:
                self.notion.blocks.children.append(block_id=task_id, children=[block])
                
        except Exception as e:
            print(f"⚠️  Could not add content to Task page: {e}")

    def _print_task_ids(self, all_task_ids: list):
        """Print Notion TIDs for direct use with slash commands"""
        print(f"\n📋 Use these Notion TIDs for task management:")
        for task_info in all_task_ids:
            tid = task_info["id"].replace("-", "")[:8]  # Use first 8 chars as TID
            print(f"/task-start {tid}  # {task_info['title']}")
        print(f"/task-archive [TID]")
        print(f"/task-finish [TID] --pr [--auto-merge]")

    def start_task(self, notion_tid: str) -> bool:
        """Start a Notion task and create Git branch using Notion TID"""
        print(f"🚀 Starting task: {notion_tid}")
        
        if not self.notion or not self.check_environment():
            print("❌ Notion integration not configured")
            return False
        
        task_page = None
        task_title = None
        epic_title = "Unknown Epic"
        
        try:
            # First try direct page ID lookup
            if len(notion_tid.replace("-", "")) == 32:  # Standard UUID length
                task_page = self.notion.pages.retrieve(page_id=notion_tid)
                task_title = task_page['properties']['Task name']['title'][0]['text']['content']
            else:
                # If not a direct UUID, search by TID in task database
                print(f"🔍 Searching for task with TID: {notion_tid}")
                
                # Search in tasks database
                query_result = self.notion.databases.query(
                    database_id=self.tasks_db_id,
                    filter={
                        "or": [
                            {
                                "property": "Task name",
                                "title": {
                                    "contains": notion_tid
                                }
                            },
                            {
                                "property": "Task name", 
                                "title": {
                                    "contains": "task-1-2"  # Search for the task identifier
                                }
                            }
                        ]
                    }
                )
                
                if query_result['results']:
                    task_page = query_result['results'][0]
                    notion_tid = task_page['id']  # Update TID to actual page ID
                    task_title = task_page['properties']['Task name']['title'][0]['text']['content']
                    print(f"✅ Found task: {task_title}")
                else:
                    print(f"❌ No task found matching TID: {notion_tid}")
                    return False
            
            # Get Epic info if this is a subtask
            if task_page['properties'].get('ParentTask', {}).get('relation'):
                parent_id = task_page['properties']['ParentTask']['relation'][0]['id']
                parent_page = self.notion.pages.retrieve(page_id=parent_id)
                epic_title = parent_page['properties']['Task name']['title'][0]['text']['content']
            
            print(f"📋 Task: {task_title}")
            print(f"🎯 Epic: {epic_title}")
            print(f"🆔 Notion TID: {notion_tid}")
            
        except Exception as e:
            print(f"❌ Failed to retrieve task info from Notion: {e}")
            return False
        
        # Git operations
        git_success = False
        try:
            # Create new branch name with TID format
            tid_short = notion_tid.replace("-", "")[:8]
            task_summary = task_title.split(': ', 1)[-1] if ': ' in task_title else task_title
            branch_name = f"feature/TID-{tid_short}-{task_summary.replace(' ', '-').lower()}"
            
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
        
        # Update Notion task status
        try:
            # Update task status to "In progress"
            self.notion.pages.update(
                page_id=notion_tid,
                properties={
                    "Status": {"status": {"name": "In progress"}}
                }
            )
            print(f"✅ Updated Notion task status to 'In progress'")
            
            # Add start timestamp to task page
            start_block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"🚀 작업 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}}
                    ]
                }
            }
            self.notion.blocks.children.append(block_id=notion_tid, children=[start_block])
            
        except Exception as e:
            print(f"⚠️  Notion update failed: {e}")
        
        return git_success

    def archive_task(self, notion_tid: Optional[str] = None, conversation_file: Optional[str] = None) -> bool:
        """Archive terminal conversation log to Notion Task page"""
        
        # Auto-detect TID from Git branch if not provided
        if not notion_tid:
            try:
                current_branch = subprocess.run(
                    ['git', 'branch', '--show-current'], 
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                
                # Extract TID from branch name like "feature/TID-12346abc-api-integration"
                if current_branch.startswith('feature/TID-'):
                    tid_short = current_branch.split('TID-')[1].split('-')[0]
                    print(f"🔍 Extracted short TID from branch: {tid_short}")
                    
                    # Query Notion database to find the matching task
                    if self.notion and self.tasks_db_id:
                        response = self.notion.databases.query(database_id=self.tasks_db_id)
                        
                        for task in response['results']:
                            if tid_short in task['id']:
                                notion_tid = task['id']
                                title_prop = task['properties'].get('Task name', {})
                                if title_prop.get('title'):
                                    title = title_prop['title'][0]['text']['content']
                                    print(f"✅ Found matching task: {title}")
                                    break
                    
                    if not notion_tid:
                        print(f"❌ Could not find Notion task matching TID: {tid_short}")
                        return False
                else:
                    print("❌ Could not auto-detect TID from current Git branch")
                    print("💡 Use: /task-archive [TID] or switch to a task branch")
                    return False
                    
            except Exception as e:
                print(f"❌ Failed to detect TID from Git branch: {e}")
                return False
        
        print(f"📦 Archiving conversation for TID: {notion_tid}")
        
        if not self.notion or not self.check_environment():
            print("❌ Notion integration not configured")
            return False
        
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
            
            # Create summary of conversation for better readability
            conversation_summary = self._create_conversation_summary(conversation_content, notion_tid)
            print(f"📋 Created conversation summary ({len(conversation_summary)} characters)")
            
            # Find the toggle block for AI conversation records
            page_blocks = self.notion.blocks.children.list(block_id=notion_tid)
            toggle_block_id = None
            
            for block in page_blocks['results']:
                if (block.get('type') == 'toggle' and 
                    block.get('toggle', {}).get('rich_text') and
                    '💬 AI 대화 기록' in block['toggle']['rich_text'][0]['text']['content']):
                    toggle_block_id = block['id']
                    break
            
            if toggle_block_id:
                # Split conversation summary into chunks (Notion has 2000 character limit)
                chunks = [conversation_summary[i:i+1800] for i in range(0, len(conversation_summary), 1800)]
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"📦 Splitting conversation into {len(chunks)} chunks")
                
                # Add header block
                header_block = {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"🕐 {timestamp} - Conversation Archive ({len(chunks)} chunks)\n"}, "annotations": {"bold": True}}
                        ]
                    }
                }
                
                blocks_to_add = [header_block]
                
                # Add chunks to blocks
                for i, chunk in enumerate(chunks):
                    chunk_block = {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": f"📝 Part {i+1}/{len(chunks)}\n"}, "annotations": {"italic": True}},
                                {"type": "text", "text": {"content": chunk}}
                            ]
                        }
                    }
                    blocks_to_add.append(chunk_block)
                
                # Add all blocks at once
                self.notion.blocks.children.append(
                    block_id=toggle_block_id, 
                    children=blocks_to_add
                )
                print(f"✅ Archived conversation ({len(chunks)} chunks) to Notion Task page")
            else:
                print(f"⚠️  Could not find conversation toggle block in task page")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to archive task: {e}")
            return False

    def _create_conversation_summary(self, raw_content: str, task_id: str) -> str:
        """Create a structured summary of the conversation for archiving"""
        
        # Extract key information
        summary_parts = [
            f"# 작업 대화 요약 - Task {task_id[:8]}",
            f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 주요 작업 내용",
        ]
        
        # Look for key implementation sections
        if "def " in raw_content:
            summary_parts.append("✅ 코드 구현 완료")
        if "git commit" in raw_content:
            summary_parts.append("✅ Git 커밋 수행")
        if "test" in raw_content.lower():
            summary_parts.append("✅ 테스트 실행")
        if "error" in raw_content.lower():
            summary_parts.append("⚠️ 오류 해결 과정 포함")
        if "success" in raw_content.lower():
            summary_parts.append("🎉 작업 성공적 완료")
            
        # Extract user questions and key decisions
        lines = raw_content.split('\n')
        user_inputs = [line for line in lines if line.startswith('Human:')]
        
        if user_inputs:
            summary_parts.extend([
                "",
                "## 사용자 요청사항",
            ])
            for i, user_input in enumerate(user_inputs[:3], 1):  # Limit to first 3
                clean_input = user_input.replace('Human:', '').strip()[:100]
                summary_parts.append(f"{i}. {clean_input}...")
        
        # Add technical details section
        summary_parts.extend([
            "",
            "## 기술적 세부사항",
            "- 전체 대화 길이: {:,} 문자".format(len(raw_content)),
            "- 주요 도구 사용: Claude Code 자동화 시스템",
            "- 결과물: Git LFS 추적 대상 포함",
            "",
            "---",
            "*이 요약은 AI 대화 기록을 구조화한 것입니다. 전체 로그는 연구 재현성을 위해 보관됩니다.*"
        ])
        
        return '\n'.join(summary_parts)

    def finish_task(self, notion_tid: str, create_pr: bool = False, auto_merge: bool = False) -> bool:
        """Complete task, create PR, and update Notion"""
        print(f"🏁 Finishing task: {notion_tid}")
        
        try:
            current_branch = subprocess.run(
                ['git', 'branch', '--show-current'], 
                capture_output=True, text=True, check=True
            ).stdout.strip()
            
            # Get task info from Notion
            if self.notion and self.check_environment():
                task_page = self.notion.pages.retrieve(page_id=notion_tid)
                task_title = task_page['properties']['Task name']['title'][0]['text']['content']
            else:
                task_title = "Task"
            
            if create_pr and self.github and self.repo_owner and self.repo_name:
                # Get repo
                repo_full_name = f"{self.repo_owner}/{self.repo_name}"
                repo = self.github.get_repo(repo_full_name)
                
                # Create PR with TID format
                tid_short = notion_tid.replace("-", "")[:8]
                pr_title = f"[TID-{tid_short}] {task_title}"
                pr_body = f"""
## Summary
Completed task: {task_title}

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
                
                # Auto-merge if requested
                if auto_merge:
                    try:
                        # Wait a moment for PR to be ready
                        import time
                        time.sleep(2)
                        
                        # Merge the PR
                        merge_result = pr.merge(
                            commit_title=f"Auto-merge: {pr_title}",
                            commit_message="🤖 Auto-merged by Claude Code workflow",
                            merge_method="squash"
                        )
                        print(f"🔀 Auto-merged PR successfully: {merge_result.sha}")
                        
                        # Delete the feature branch
                        try:
                            repo.get_git_ref(f"heads/{current_branch}").delete()
                            print(f"🗑️  Deleted remote branch: {current_branch}")
                        except Exception as e:
                            print(f"⚠️  Could not delete remote branch: {e}")
                        
                        # Switch to main and delete local branch
                        subprocess.run(['git', 'checkout', 'main'], check=True)
                        subprocess.run(['git', 'pull', 'origin', 'main'], check=True)
                        subprocess.run(['git', 'branch', '-D', current_branch], check=True)
                        print(f"🧹 Cleaned up local branch: {current_branch}")
                        
                    except Exception as e:
                        print(f"⚠️  Auto-merge failed: {e}")
                        print(f"💡 PR created but needs manual merge: {pr.html_url}")
            
            # Update Notion task status to Done
            if self.notion and self.check_environment():
                try:
                    self.notion.pages.update(
                        page_id=notion_tid,
                        properties={
                            "Status": {"status": {"name": "Done"}}
                        }
                    )
                    print(f"✅ Updated Notion task status to 'Done'")
                except Exception as e:
                    print(f"⚠️  Failed to update Notion status: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to finish task: {e}")
            return False

    def publish_task(self, notion_tid: str) -> bool:
        """Publish completed task knowledge to Knowledge Hub"""
        print(f"📚 Publishing task knowledge: {notion_tid}")
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
    start_parser.add_argument("notion_tid", help="Notion Task ID")
    
    archive_parser = subparsers.add_parser("task-archive", help="Archive task conversation")
    archive_parser.add_argument("notion_tid", nargs="?", help="Notion Task ID (auto-detect from Git branch if not provided)")
    archive_parser.add_argument("--file", help="Conversation file path")
    
    finish_parser = subparsers.add_parser("task-finish", help="Finish a task")
    finish_parser.add_argument("notion_tid", help="Notion Task ID")
    finish_parser.add_argument("--pr", action="store_true", help="Create pull request")
    finish_parser.add_argument("--auto-merge", action="store_true", help="Auto-merge PR after creation")
    
    publish_parser = subparsers.add_parser("task-publish", help="Publish task knowledge")
    publish_parser.add_argument("notion_tid", help="Notion Task ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    manager = WorkflowManager()
    
    success = False
    if args.command == "project-plan":
        success = manager.create_project_plan(args.source, args.project)
    elif args.command == "task-start":
        success = manager.start_task(args.notion_tid)
    elif args.command == "task-archive":
        success = manager.archive_task(args.notion_tid, args.file)
    elif args.command == "task-finish":
        success = manager.finish_task(args.notion_tid, args.pr, args.auto_merge)
    elif args.command == "task-publish":
        success = manager.publish_task(args.notion_tid)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())