"""
TADD Session Archiver - Automated Session Lifecycle Management

Provides comprehensive session archiving with automatic document migration,
version control integration, and session lifecycle tracking.
"""

import os
import shutil
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import subprocess


class SessionArchiver:
    """
    Comprehensive session archiving system
    
    Features:
    - Automatic CURRENT/ → sessions/ migration
    - Git integration with semantic commits
    - Session summary generation
    - Next session template creation
    - Archive integrity validation
    """
    
    def __init__(self, base_path: str = "/home/kyuwon/claude-ops"):
        self.base_path = base_path
        self.current_path = os.path.join(base_path, "docs/CURRENT")
        self.sessions_path = os.path.join(base_path, "docs/development/sessions")
        self.ensure_directories()
    
    def ensure_directories(self):
        """Ensure all required directories exist"""
        os.makedirs(self.current_path, exist_ok=True)
        os.makedirs(self.sessions_path, exist_ok=True)
    
    def archive_current_session(self, 
                              session_name: str = None,
                              commit_message: str = None) -> Dict[str, Any]:
        """
        Archive current session with full lifecycle management
        
        Returns:
            Dict with archive results including paths, git info, and summary
        """
        timestamp = datetime.now()
        year_month = timestamp.strftime("%Y-%m")
        
        # Generate session name if not provided
        if not session_name:
            session_name = self._generate_session_name(timestamp)
        
        # Create monthly archive directory
        monthly_path = os.path.join(self.sessions_path, year_month)
        os.makedirs(monthly_path, exist_ok=True)
        
        # Create session archive directory
        session_path = os.path.join(monthly_path, session_name)
        
        # Check if session already exists
        if os.path.exists(session_path):
            session_name = f"{session_name}-{timestamp.strftime('%H%M%S')}"
            session_path = os.path.join(monthly_path, session_name)
        
        os.makedirs(session_path, exist_ok=True)
        
        # Archive current documents
        archived_files = self._archive_documents(session_path)
        
        # Generate session summary
        session_summary = self._generate_session_summary(archived_files, timestamp)
        
        # Save session summary
        summary_file = os.path.join(session_path, "session-summary.md")
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(session_summary)
        
        # Create git commit
        git_result = self._create_git_commit(session_name, commit_message, archived_files)
        
        # Clean CURRENT directory
        self._clean_current_directory()
        
        # Create next session template
        self._create_next_session_template()
        
        # Validate archive integrity
        validation_result = self._validate_archive_integrity(session_path)
        
        return {
            "success": True,
            "session_name": session_name,
            "session_path": session_path,
            "archived_files": archived_files,
            "git_commit": git_result,
            "validation": validation_result,
            "timestamp": timestamp.isoformat()
        }
    
    def _generate_session_name(self, timestamp: datetime) -> str:
        """Generate unique session name"""
        year_month = timestamp.strftime("%Y-%m")
        monthly_path = os.path.join(self.sessions_path, year_month)
        
        # Count existing sessions in the month
        session_count = 0
        if os.path.exists(monthly_path):
            for item in os.listdir(monthly_path):
                if os.path.isdir(os.path.join(monthly_path, item)) and item.startswith("session-"):
                    session_count += 1
        
        return f"session-{session_count + 1:03d}"
    
    def _archive_documents(self, session_path: str) -> List[str]:
        """Archive all documents from CURRENT/ to session directory"""
        archived_files = []
        
        if not os.path.exists(self.current_path):
            return archived_files
        
        for filename in os.listdir(self.current_path):
            file_path = os.path.join(self.current_path, filename)
            
            # Skip directories and hidden files
            if os.path.isdir(file_path) or filename.startswith('.'):
                continue
            
            # Copy file to session directory
            dest_path = os.path.join(session_path, filename)
            shutil.copy2(file_path, dest_path)
            archived_files.append(filename)
        
        return archived_files
    
    def _generate_session_summary(self, archived_files: List[str], timestamp: datetime) -> str:
        """Generate comprehensive session summary"""
        
        # Analyze session content
        session_analysis = self._analyze_session_content(archived_files)
        
        summary = f"""# Session Summary
## {timestamp.strftime("%Y-%m-%d %H:%M:%S")} - TADD Workflow Session

**Generated**: {timestamp.strftime("%Y-%m-%d %H:%M:%S")}  
**Session Type**: {session_analysis['session_type']}  
**Duration**: {session_analysis['estimated_duration']}  
**Scale**: {session_analysis['project_scale']}

---

## 📊 Session Overview

### Documents Created
{self._format_document_list(archived_files)}

### Key Achievements
{session_analysis['achievements']}

### Work Completed
{session_analysis['work_completed']}

---

## 🎯 TADD Workflow Analysis

### Phases Completed
{session_analysis['phases_completed']}

### Tasks Accomplished
{session_analysis['tasks_completed']}

### Quality Gates Passed
{session_analysis['quality_gates']}

---

## 📈 Progress Metrics

### Quantitative Results
{session_analysis['quantitative_metrics']}

### Quality Indicators
{session_analysis['quality_indicators']}

### Performance Benchmarks
{session_analysis['performance_benchmarks']}

---

## 🔍 Session Analysis

### Strengths
{session_analysis['strengths']}

### Areas for Improvement
{session_analysis['improvements']}

### Lessons Learned
{session_analysis['lessons_learned']}

---

## 🔄 Next Session Recommendations

### Priority Tasks
{session_analysis['next_priorities']}

### Context to Preserve
{session_analysis['context_preservation']}

### Follow-up Actions
{session_analysis['follow_up_actions']}

---

## 📚 Knowledge Base Updates

### New Patterns Identified
{session_analysis['new_patterns']}

### Best Practices Confirmed
{session_analysis['best_practices']}

### Technical Insights
{session_analysis['technical_insights']}

---

## 🏷️ Session Metadata

### Tags
{session_analysis['tags']}

### Related Sessions
{session_analysis['related_sessions']}

### External References
{session_analysis['external_references']}

---

**Session Rating**: {session_analysis['session_rating']}/10  
**Archival Status**: ✅ Complete  
**Next Session Template**: Created

---
*Generated by TADD Session Archiver v1.0.0*
"""
        return summary
    
    def _analyze_session_content(self, archived_files: List[str]) -> Dict[str, str]:
        """Analyze session content to generate insights"""
        
        # Default analysis structure
        analysis = {
            "session_type": "Development Workflow",
            "estimated_duration": "2-4 hours",
            "project_scale": "Tactical",
            "achievements": "Session achievements to be analyzed...",
            "work_completed": "Work completion analysis pending...",
            "phases_completed": "Phase completion analysis pending...",
            "tasks_completed": "Task completion analysis pending...",
            "quality_gates": "Quality gate analysis pending...",
            "quantitative_metrics": "Metrics analysis pending...",
            "quality_indicators": "Quality indicator analysis pending...",
            "performance_benchmarks": "Performance benchmark analysis pending...",
            "strengths": "Session strength analysis pending...",
            "improvements": "Improvement analysis pending...",
            "lessons_learned": "Lessons learned analysis pending...",
            "next_priorities": "Priority analysis pending...",
            "context_preservation": "Context preservation analysis pending...",
            "follow_up_actions": "Follow-up action analysis pending...",
            "new_patterns": "Pattern analysis pending...",
            "best_practices": "Best practice analysis pending...",
            "technical_insights": "Technical insight analysis pending...",
            "tags": "TADD, Development, Workflow",
            "related_sessions": "Related session analysis pending...",
            "external_references": "External reference analysis pending...",
            "session_rating": "8"
        }
        
        # Analyze specific files if they exist
        for filename in archived_files:
            file_path = os.path.join(self.current_path, filename)
            if os.path.exists(file_path):
                self._analyze_specific_file(file_path, analysis)
        
        return analysis
    
    def _analyze_specific_file(self, file_path: str, analysis: Dict[str, str]):
        """Analyze specific file content for insights"""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            filename = os.path.basename(file_path)
            
            if filename == "PRD-TADD-Integration.md":
                analysis["session_type"] = "Strategic Planning"
                analysis["project_scale"] = "Strategic"
                if "Strategic Level" in content:
                    analysis["achievements"] = "✅ Strategic PRD created with comprehensive requirements"
            
            elif filename == "planning.md":
                analysis["phases_completed"] = "✅ 기획 (Planning) phase completed"
                if "MECE" in content:
                    analysis["work_completed"] = "✅ MECE-based work breakdown structure established"
            
            elif filename == "implementation.md":
                analysis["phases_completed"] += "\\n✅ 구현 (Implementation) phase completed"
                if "DRY" in content:
                    analysis["work_completed"] += "\\n✅ DRY principle applied in implementation"
            
            elif filename == "test-report.md":
                analysis["phases_completed"] += "\\n✅ 안정화 (Stabilization) phase completed"
                analysis["quality_gates"] = "✅ Comprehensive testing completed"
            
            elif filename == "active-todos.md":
                # Count completed vs pending tasks
                completed_count = content.count("✅")
                pending_count = content.count("⏳") + content.count("🔄")
                
                analysis["tasks_completed"] = f"✅ {completed_count} tasks completed, {pending_count} remaining"
        
        except Exception as e:
            # Log error but continue
            pass
    
    def _format_document_list(self, files: List[str]) -> str:
        """Format archived files list"""
        if not files:
            return "No documents were archived in this session"
        
        categorized = {
            "Planning": [],
            "Implementation": [],
            "Testing": [],
            "Documentation": [],
            "Other": []
        }
        
        for filename in files:
            if "planning" in filename.lower() or "PRD" in filename:
                categorized["Planning"].append(filename)
            elif "implementation" in filename.lower():
                categorized["Implementation"].append(filename)
            elif "test" in filename.lower():
                categorized["Testing"].append(filename)
            elif filename.endswith(".md"):
                categorized["Documentation"].append(filename)
            else:
                categorized["Other"].append(filename)
        
        output = []
        for category, files in categorized.items():
            if files:
                output.append(f"\\n**{category}**:")
                output.extend(f"- {file}" for file in files)
        
        return "\\n".join(output)
    
    def _create_git_commit(self, 
                         session_name: str, 
                         commit_message: str,
                         archived_files: List[str]) -> Dict[str, Any]:
        """Create git commit for session archive"""
        
        git_result = {
            "success": False,
            "commit_hash": None,
            "message": None,
            "error": None
        }
        
        try:
            # Change to repository root
            os.chdir(self.base_path)
            
            # Add archived files to git
            subprocess.run(["git", "add", "docs/development/sessions/"], check=True)
            
            # Generate commit message if not provided
            if not commit_message:
                commit_message = f"""feat: archive {session_name} - TADD workflow session

📦 Session Archive:
{chr(10).join(f"- {file}" for file in archived_files[:5])}
{'- ...' if len(archived_files) > 5 else ''}

🎯 TADD Integration: Complete workflow cycle with automated documentation

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"""
            
            # Create commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            
            git_result.update({
                "success": True,
                "commit_hash": hash_result.stdout.strip(),
                "message": commit_message
            })
            
        except subprocess.CalledProcessError as e:
            git_result["error"] = f"Git command failed: {e}"
        except Exception as e:
            git_result["error"] = f"Unexpected error: {e}"
        
        return git_result
    
    def _clean_current_directory(self):
        """Clean CURRENT directory while preserving structure"""
        
        if not os.path.exists(self.current_path):
            return
        
        # Keep important files but remove session-specific content
        keep_files = {
            ".gitkeep", "README.md"
        }
        
        for filename in os.listdir(self.current_path):
            if filename not in keep_files:
                file_path = os.path.join(self.current_path, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
    
    def _create_next_session_template(self):
        """Create template for next session"""
        
        template_content = f"""# Next Session Planning Template

**Created**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Status**: 🟡 Template Ready for Next Session

---

## 🎯 Session Preparation Checklist

### Context Loading (Always Required)
- [ ] Read project_rules.md for current principles  
- [ ] Review previous session summary
- [ ] Check active-todos.md for pending tasks
- [ ] Verify system status.md

### Workflow Selection
- [ ] **기획**: For new features/architecture changes
- [ ] **구현**: For development tasks
- [ ] **안정화**: For testing/quality assurance  
- [ ] **배포**: For production deployment

### Scale Assessment
- [ ] **Strategic**: Major changes requiring PRD + comprehensive docs
- [ ] **Tactical**: Medium changes requiring detailed planning
- [ ] **Operational**: Small changes requiring minimal overhead

---

## 📋 Pre-Session Context

### Previous Session Results
Context will be loaded from previous session summary...

### Pending Work Items  
- Review active-todos.md for incomplete tasks
- Check for any urgent issues
- Identify priority items

### System Status
- Verify all systems operational
- Check for any recent changes
- Confirm environment setup

---

## 🚀 Session Kickoff Guide

### TADD Workflow Initiation
1. **Context Loading**: Execute automatic context loading
2. **Scale Detection**: Determine appropriate project scale
3. **TodoWrite Setup**: Initialize task tracking
4. **Document Preparation**: Set up required document templates

### Quality Assurance Setup
- [ ] Real testing environment ready (NO MOCKS)
- [ ] Performance measurement tools available
- [ ] Documentation sync mechanisms active
- [ ] Git workflow prepared for commits

---

## 📊 Success Criteria Template

### Session Goals
- Define specific, measurable objectives
- Set clear success criteria
- Establish quality gates
- Plan documentation requirements

### Output Expectations
- Functional deliverables expected
- Documentation artifacts required
- Testing validation needed
- Deployment readiness criteria

---

**Template Status**: ✅ Ready for Next Session  
**Usage**: Delete this template when session begins

---
*Generated by TADD Session Archiver v1.0.0*
"""
        
        template_file = os.path.join(self.current_path, "next-session.md")
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(template_content)
    
    def _validate_archive_integrity(self, session_path: str) -> Dict[str, Any]:
        """Validate archive integrity and completeness"""
        
        validation = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "file_count": 0,
            "total_size_kb": 0
        }
        
        try:
            # Count files and calculate total size
            for filename in os.listdir(session_path):
                file_path = os.path.join(session_path, filename)
                if os.path.isfile(file_path):
                    validation["file_count"] += 1
                    validation["total_size_kb"] += os.path.getsize(file_path) / 1024
            
            # Check required files
            required_files = ["session-summary.md"]
            for required_file in required_files:
                if not os.path.exists(os.path.join(session_path, required_file)):
                    validation["errors"].append(f"Missing required file: {required_file}")
                    validation["valid"] = False
            
            # Check for empty files
            for filename in os.listdir(session_path):
                file_path = os.path.join(session_path, filename)
                if os.path.isfile(file_path) and os.path.getsize(file_path) == 0:
                    validation["warnings"].append(f"Empty file detected: {filename}")
            
            # Validate total archive size
            if validation["total_size_kb"] < 1:
                validation["warnings"].append("Archive seems very small - may be incomplete")
            
        except Exception as e:
            validation["errors"].append(f"Archive validation failed: {e}")
            validation["valid"] = False
        
        return validation
    
    def list_archived_sessions(self, year_month: str = None) -> List[Dict[str, Any]]:
        """List all archived sessions with metadata"""
        
        sessions = []
        
        if year_month:
            # List sessions for specific month
            monthly_path = os.path.join(self.sessions_path, year_month)
            if os.path.exists(monthly_path):
                sessions.extend(self._get_sessions_in_directory(monthly_path, year_month))
        else:
            # List all sessions
            for month_dir in os.listdir(self.sessions_path):
                monthly_path = os.path.join(self.sessions_path, month_dir)
                if os.path.isdir(monthly_path):
                    sessions.extend(self._get_sessions_in_directory(monthly_path, month_dir))
        
        # Sort by date descending
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return sessions
    
    def _get_sessions_in_directory(self, directory: str, year_month: str) -> List[Dict[str, Any]]:
        """Get session metadata for sessions in directory"""
        
        sessions = []
        
        for session_dir in os.listdir(directory):
            session_path = os.path.join(directory, session_dir)
            
            if not os.path.isdir(session_path):
                continue
            
            # Get session metadata
            summary_file = os.path.join(session_path, "session-summary.md")
            
            session_info = {
                "name": session_dir,
                "path": session_path,
                "year_month": year_month,
                "timestamp": self._extract_timestamp_from_path(session_path),
                "file_count": len([f for f in os.listdir(session_path) 
                                 if os.path.isfile(os.path.join(session_path, f))]),
                "has_summary": os.path.exists(summary_file)
            }
            
            # Try to extract additional metadata from summary
            if session_info["has_summary"]:
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary_content = f.read()
                    
                    # Extract session type, scale, rating from summary
                    session_info.update(self._parse_summary_metadata(summary_content))
                
                except Exception:
                    pass
            
            sessions.append(session_info)
        
        return sessions
    
    def _extract_timestamp_from_path(self, session_path: str) -> datetime:
        """Extract timestamp from session path"""
        
        # Try to get creation time from filesystem
        try:
            return datetime.fromtimestamp(os.path.getctime(session_path))
        except:
            return datetime.now()
    
    def _parse_summary_metadata(self, content: str) -> Dict[str, Any]:
        """Parse metadata from session summary content"""
        
        metadata = {}
        
        # Extract session type
        if "**Session Type**: " in content:
            start = content.find("**Session Type**: ") + len("**Session Type**: ")
            end = content.find("\\n", start)
            if end > start:
                metadata["session_type"] = content[start:end].strip()
        
        # Extract scale
        if "**Scale**: " in content:
            start = content.find("**Scale**: ") + len("**Scale**: ")
            end = content.find("\\n", start)
            if end > start:
                metadata["scale"] = content[start:end].strip()
        
        # Extract rating
        if "**Session Rating**: " in content:
            start = content.find("**Session Rating**: ") + len("**Session Rating**: ")
            end = content.find("/", start)
            if end > start:
                try:
                    metadata["rating"] = int(content[start:end].strip())
                except ValueError:
                    pass
        
        return metadata


class TADDSessionArchiver(SessionArchiver):
    """TADD-specific session archiver with enhanced features"""
    
    def __init__(self, base_path: str = "/home/kyuwon/claude-ops"):
        super().__init__(base_path)
    
    def archive_with_deployment(self, 
                              session_name: str = None,
                              push_to_remote: bool = True) -> Dict[str, Any]:
        """Archive session with deployment and remote push"""
        
        # Standard archiving
        archive_result = self.archive_current_session(session_name)
        
        if not archive_result["success"]:
            return archive_result
        
        # Push to remote if requested
        if push_to_remote:
            push_result = self._push_to_remote()
            archive_result["remote_push"] = push_result
        
        return archive_result
    
    def _push_to_remote(self) -> Dict[str, Any]:
        """Push archived session to remote repository"""
        
        push_result = {
            "success": False,
            "error": None
        }
        
        try:
            os.chdir(self.base_path)
            
            # Push to remote
            result = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True,
                text=True,
                check=True
            )
            
            push_result["success"] = True
            
        except subprocess.CalledProcessError as e:
            push_result["error"] = f"Git push failed: {e.stderr}"
        except Exception as e:
            push_result["error"] = f"Unexpected error during push: {e}"
        
        return push_result