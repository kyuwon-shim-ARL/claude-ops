"""
TADD Task Manager - TodoWrite Integration Layer

Provides comprehensive task management with TodoWrite synchronization,
dependency tracking, and automatic documentation updates.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(Enum):
    P0_CRITICAL = "P0"
    P1_HIGH = "P1"
    P2_MEDIUM = "P2"
    P3_LOW = "P3"


@dataclass
class TADDTask:
    """TADD Task with full metadata"""
    content: str
    activeForm: str
    status: TaskStatus
    priority: TaskPriority = TaskPriority.P2_MEDIUM
    created_at: datetime = None
    updated_at: datetime = None
    dependencies: List[str] = None
    estimated_hours: float = 0
    actual_hours: float = 0
    tags: List[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = []


class TADDTaskManager:
    """
    Comprehensive task management with TodoWrite integration
    
    Features:
    - TodoWrite API synchronization
    - active-todos.md file sync
    - Dependency tracking
    - Progress analytics
    - Task templates
    """
    
    def __init__(self, base_path: str = "/home/kyuwon/claude-ops"):
        self.base_path = base_path
        self.todos_file = os.path.join(base_path, "docs/CURRENT/active-todos.md")
        self.tasks: Dict[str, TADDTask] = {}
        self.load_existing_tasks()
    
    def add_task(self, 
                 content: str, 
                 active_form: str, 
                 priority: TaskPriority = TaskPriority.P2_MEDIUM,
                 dependencies: List[str] = None,
                 estimated_hours: float = 0,
                 tags: List[str] = None) -> str:
        """Add a new task with full TADD metadata"""
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        task = TADDTask(
            content=content,
            activeForm=active_form,
            status=TaskStatus.PENDING,
            priority=priority,
            dependencies=dependencies or [],
            estimated_hours=estimated_hours,
            tags=tags or []
        )
        
        self.tasks[task_id] = task
        self._sync_to_todowrite()
        self._sync_to_markdown()
        return task_id
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """Update task status with validation"""
        if task_id not in self.tasks:
            return False
            
        task = self.tasks[task_id]
        old_status = task.status
        
        # Validate dependencies for in_progress
        if status == TaskStatus.IN_PROGRESS:
            if self._has_incomplete_dependencies(task_id):
                raise ValueError(f"Cannot start task {task_id}: dependencies not completed")
                
            # Ensure only one task is in progress
            self._set_single_in_progress(task_id)
        
        task.status = status
        task.updated_at = datetime.now()
        
        self._sync_to_todowrite()
        self._sync_to_markdown()
        return True
    
    def get_todowrite_format(self) -> List[Dict]:
        """Generate TodoWrite API format"""
        todos = []
        for task_id, task in self.tasks.items():
            todos.append({
                "content": task.content,
                "activeForm": task.activeForm,
                "status": task.status.value
            })
        return todos
    
    def _sync_to_todowrite(self):
        """Synchronize with TodoWrite tool (would call actual tool here)"""
        # In real implementation, this would call the TodoWrite tool
        # For now, we prepare the format
        todos = self.get_todowrite_format()
        
        # TODO: Implement actual TodoWrite tool integration
        # This would be: await todowrite_tool.update(todos)
        pass
    
    def _sync_to_markdown(self):
        """Synchronize to active-todos.md file"""
        os.makedirs(os.path.dirname(self.todos_file), exist_ok=True)
        
        with open(self.todos_file, 'w', encoding='utf-8') as f:
            f.write("# Active TODOs - TADD Task Management\\n\\n")
            f.write(f"**Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")
            
            # Group by status
            for status in TaskStatus:
                tasks_in_status = [(tid, task) for tid, task in self.tasks.items() 
                                 if task.status == status]
                
                if tasks_in_status:
                    f.write(f"## {status.value.title()} Tasks\\n\\n")
                    
                    for task_id, task in tasks_in_status:
                        # Status icon
                        icon = {
                            TaskStatus.PENDING: "⏳",
                            TaskStatus.IN_PROGRESS: "🔄", 
                            TaskStatus.COMPLETED: "✅"
                        }[task.status]
                        
                        # Priority badge
                        priority_badge = f"**{task.priority.value}**" if task.priority != TaskPriority.P2_MEDIUM else ""
                        
                        f.write(f"- {icon} {priority_badge} {task.content}\\n")
                        
                        if task.dependencies:
                            f.write(f"  - *Dependencies*: {', '.join(task.dependencies)}\\n")
                        
                        if task.estimated_hours > 0:
                            f.write(f"  - *Estimated*: {task.estimated_hours}h\\n")
                            
                        if task.tags:
                            f.write(f"  - *Tags*: {', '.join(task.tags)}\\n")
                            
                        f.write("\\n")
            
            # Analytics section
            f.write("## 📊 Task Analytics\\n\\n")
            total_tasks = len(self.tasks)
            completed_tasks = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])
            in_progress_tasks = len([t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS])
            
            f.write(f"- **Total Tasks**: {total_tasks}\\n")
            f.write(f"- **Completed**: {completed_tasks} ({completed_tasks/total_tasks*100:.1f}%)\\n")
            f.write(f"- **In Progress**: {in_progress_tasks}\\n")
            f.write(f"- **Remaining**: {total_tasks - completed_tasks}\\n\\n")
    
    def _has_incomplete_dependencies(self, task_id: str) -> bool:
        """Check if task has incomplete dependencies"""
        task = self.tasks[task_id]
        for dep_id in task.dependencies:
            if dep_id in self.tasks and self.tasks[dep_id].status != TaskStatus.COMPLETED:
                return True
        return False
    
    def _set_single_in_progress(self, task_id: str):
        """Ensure only one task is in progress at a time"""
        for tid, task in self.tasks.items():
            if tid != task_id and task.status == TaskStatus.IN_PROGRESS:
                task.status = TaskStatus.PENDING
                task.updated_at = datetime.now()
    
    def load_existing_tasks(self):
        """Load existing tasks from active-todos.md if available"""
        if os.path.exists(self.todos_file):
            # Parse existing markdown file
            # This is a simplified version - real implementation would parse markdown
            pass
    
    def get_progress_report(self) -> Dict:
        """Generate comprehensive progress report"""
        total = len(self.tasks)
        if total == 0:
            return {"total": 0, "progress": 0, "status": "No tasks"}
            
        completed = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])
        in_progress = len([t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS])
        pending = total - completed - in_progress
        
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "progress": (completed / total) * 100,
            "estimated_remaining": sum(t.estimated_hours for t in self.tasks.values() 
                                    if t.status != TaskStatus.COMPLETED)
        }
    
    def create_task_template(self, template_name: str, tasks: List[Tuple[str, str]]) -> List[str]:
        """Create a set of tasks from template"""
        task_ids = []
        for content, active_form in tasks:
            task_id = self.add_task(content, active_form, tags=[template_name])
            task_ids.append(task_id)
        return task_ids


# Predefined task templates for common TADD workflows
TADD_TEMPLATES = {
    "기획": [
        ("컨텍스트 로딩 (project_rules.md, status.md)", "컨텍스트를 로딩하는 중"),
        ("탐색 단계: 전체 구조 파악", "전체 구조를 파악하는 중"),
        ("As-Is/To-Be/Gap 분석", "As-Is/To-Be/Gap을 분석하는 중"),
        ("MECE 기반 작업분해(WBS)", "MECE 기반 작업분해를 진행하는 중"),
        ("PRD 작성 및 검토", "PRD를 작성하고 검토하는 중")
    ],
    "구현": [
        ("기존 코드 검색 및 분석", "기존 코드를 검색하고 분석하는 중"),
        ("DRY 원칙 적용 코딩", "DRY 원칙을 적용하여 코딩하는 중"),
        ("단위 테스트 작성", "단위 테스트를 작성하는 중"),
        ("통합 테스트 실행", "통합 테스트를 실행하는 중"),
        ("코드 리뷰 및 리팩토링", "코드 리뷰 및 리팩토링을 진행하는 중")
    ],
    "안정화": [
        ("Repository Structure Scan", "저장소 구조를 스캔하는 중"),
        ("Structural Optimization", "구조적 최적화를 진행하는 중"),
        ("Dependency Resolution", "의존성 해결을 진행하는 중"),
        ("실제 시나리오 E2E 테스트", "실제 시나리오 E2E 테스트를 진행하는 중"),
        ("성능 벤치마크 측정", "성능 벤치마크를 측정하는 중"),
        ("Documentation Sync", "문서 동기화를 진행하는 중")
    ],
    "배포": [
        ("최종 테스트 실행", "최종 테스트를 실행하는 중"),
        ("Git 커밋 및 태깅", "Git 커밋 및 태깅을 진행하는 중"),
        ("원격 저장소 푸시", "원격 저장소에 푸시하는 중"),
        ("배포 후 검증", "배포 후 검증을 진행하는 중"),
        ("세션 아카이빙", "세션 아카이빙을 진행하는 중")
    ]
}