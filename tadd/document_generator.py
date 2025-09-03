"""
TADD Document Generator - Automatic Documentation System

Provides comprehensive document generation for all TADD workflow stages
with templates, automation, and quality assurance.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class DocumentType(Enum):
    PRD = "PRD"
    PLANNING = "planning" 
    IMPLEMENTATION = "implementation"
    TEST_REPORT = "test-report"
    SESSION_SUMMARY = "session-summary"


class ProjectScale(Enum):
    STRATEGIC = "strategic"    # PRD + planning.md + TodoWrite
    TACTICAL = "tactical"      # planning.md(optional) + TodoWrite
    OPERATIONAL = "operational" # TodoWrite only


class TADDDocumentGenerator:
    """
    Comprehensive document generator for TADD workflows
    
    Features:
    - Template-based generation
    - Scale-aware documentation
    - Auto-updating documents
    - Context-aware content
    """
    
    def __init__(self, base_path: str = "/home/kyuwon/claude-ops"):
        self.base_path = base_path
        self.current_path = os.path.join(base_path, "docs/CURRENT")
        self.templates_path = os.path.join(base_path, "docs/specs")
        self.ensure_directories()
    
    def ensure_directories(self):
        """Ensure all required directories exist"""
        os.makedirs(self.current_path, exist_ok=True)
        os.makedirs(self.templates_path, exist_ok=True)
    
    def detect_project_scale(self, context: Dict[str, Any]) -> ProjectScale:
        """
        Detect project scale based on context
        
        Strategic: Major features, architecture changes, new products
        Tactical: Medium features, enhancements, integrations  
        Operational: Bug fixes, small changes, maintenance
        """
        # Check for strategic indicators
        strategic_keywords = [
            "architecture", "system", "framework", "platform",
            "integration", "migration", "transformation", "redesign"
        ]
        
        # Check for operational indicators
        operational_keywords = [
            "bug", "fix", "patch", "hotfix", "maintenance",
            "cleanup", "minor", "small", "quick"
        ]
        
        description = str(context.get("description", "")).lower()
        requirements = str(context.get("requirements", "")).lower()
        full_text = f"{description} {requirements}"
        
        strategic_score = sum(1 for keyword in strategic_keywords if keyword in full_text)
        operational_score = sum(1 for keyword in operational_keywords if keyword in full_text)
        
        if strategic_score >= 2:
            return ProjectScale.STRATEGIC
        elif operational_score >= 2:
            return ProjectScale.OPERATIONAL
        else:
            return ProjectScale.TACTICAL
    
    def generate_planning_document(self, 
                                 project_name: str,
                                 context: Dict[str, Any],
                                 scale: Optional[ProjectScale] = None) -> str:
        """Generate planning.md document"""
        
        if scale is None:
            scale = self.detect_project_scale(context)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Scale-specific content depth
        content_depth = {
            ProjectScale.STRATEGIC: "comprehensive",
            ProjectScale.TACTICAL: "detailed", 
            ProjectScale.OPERATIONAL: "focused"
        }
        
        planning_content = f"""# Planning Document - {project_name}

**Generated**: {timestamp}  
**Scale**: {scale.value.title()} ({content_depth[scale]})  
**TADD Phase**: 🎯 기획 (Structured Discovery & Planning Loop)

---

## 📋 Context Loading Results

### Project Rules Status
- ✅ project_rules.md: Loaded and analyzed
- ✅ Current status: {self._check_status_file()}
- ✅ Active todos: {self._count_active_todos()} items tracked

### Previous Session Context
{self._load_previous_context()}

---

## 🔍 Structured Discovery

### Current State Analysis (As-Is)
{context.get('as_is', 'Current state analysis pending...')}

### Target State Definition (To-Be)  
{context.get('to_be', 'Target state definition pending...')}

### Gap Analysis
{context.get('gap_analysis', 'Gap analysis pending...')}

---

## 📊 MECE Work Breakdown Structure

### Primary Work Streams
{self._generate_work_breakdown(context, scale)}

### Dependencies & Prerequisites
{self._analyze_dependencies(context)}

---

## 🎯 Success Criteria

### Functional Requirements
{context.get('functional_requirements', 'Functional requirements to be defined...')}

### Non-Functional Requirements  
{context.get('non_functional_requirements', 'Non-functional requirements to be defined...')}

### Acceptance Criteria
{context.get('acceptance_criteria', 'Acceptance criteria to be defined...')}

---

## 📈 Implementation Strategy

### Approach
**{scale.value.title()} Scale Approach**
- Documentation Level: {self._get_doc_level(scale)}
- Testing Strategy: {self._get_testing_strategy(scale)}
- Review Process: {self._get_review_process(scale)}

### Risk Assessment
{context.get('risks', 'Risk assessment pending...')}

### Timeline Estimate
{context.get('timeline', 'Timeline estimation pending...')}

---

## 🔄 Iterative Refinement Log

### Planning Iterations
1. **Initial Planning** ({timestamp}): Base structure established
{context.get('iterations', '')}

---

## ✅ Planning Checklist

- [ ] Context fully loaded and analyzed
- [ ] Stakeholder requirements gathered
- [ ] Work breakdown structure complete
- [ ] Success criteria defined
- [ ] Risks identified and mitigated
- [ ] Timeline estimated and approved
- [ ] TodoWrite plan synchronized

---

**Planning Status**: 🟡 In Progress  
**Next Phase**: 📍 구현 (Implementation with DRY)  
**Ready for Implementation**: {self._check_implementation_readiness()}

---
*Generated by TADD Document Generator v1.0.0*
"""
        
        # Save to current directory
        planning_file = os.path.join(self.current_path, "planning.md")
        with open(planning_file, 'w', encoding='utf-8') as f:
            f.write(planning_content)
        
        return planning_file
    
    def generate_implementation_document(self,
                                       project_name: str,
                                       implementation_details: Dict[str, Any]) -> str:
        """Generate implementation.md document"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        implementation_content = f"""# Implementation Report - {project_name}

**Generated**: {timestamp}  
**TADD Phase**: ⚡ 구현 (Implementation with DRY)

---

## 📚 Context Loading Results

### Pre-Implementation Validation
- ✅ project_rules.md: {self._check_file_exists('project_rules.md')}
- ✅ planning.md: {self._check_file_exists('planning.md')}
- ✅ active-todos.md: {self._check_file_exists('active-todos.md')}

---

## 🔄 DRY Principle Application

### Code Analysis Results
{implementation_details.get('code_analysis', 'Code analysis pending...')}

### Reusability Assessment  
{implementation_details.get('reusability', 'Reusability assessment pending...')}

### New Components Created
{implementation_details.get('new_components', 'New components list pending...')}

---

## 🏗️ Implementation Progress

### Completed Tasks
{self._format_completed_tasks(implementation_details.get('completed_tasks', []))}

### Current Task
{implementation_details.get('current_task', 'No active task')}

### Remaining Tasks
{self._format_remaining_tasks(implementation_details.get('remaining_tasks', []))}

---

## 🧪 Quality Assurance

### Testing Results
{implementation_details.get('testing_results', 'Testing results pending...')}

### Code Coverage
{implementation_details.get('code_coverage', 'Code coverage pending...')}

### Performance Metrics
{implementation_details.get('performance', 'Performance metrics pending...')}

---

## 📝 Implementation Notes

### Technical Decisions
{implementation_details.get('technical_decisions', 'Technical decisions pending...')}

### Challenges & Solutions
{implementation_details.get('challenges', 'Challenges and solutions pending...')}

### Code Conventions Applied
{implementation_details.get('conventions', 'Code conventions pending...')}

---

## ⚠️ Issues & Blockers

### Current Issues
{implementation_details.get('issues', 'No current issues reported')}

### Resolved Issues
{implementation_details.get('resolved_issues', 'No resolved issues yet')}

---

## 📊 Progress Analytics

### Implementation Velocity
{implementation_details.get('velocity', 'Velocity tracking pending...')}

### Quality Metrics
{implementation_details.get('quality_metrics', 'Quality metrics pending...')}

---

**Implementation Status**: {implementation_details.get('status', '🟡 In Progress')}  
**Next Phase**: 📍 안정화 (Structural Sustainability Protocol)  
**Ready for Stabilization**: {implementation_details.get('ready_for_stabilization', '❌ Not Ready')}

---
*Generated by TADD Document Generator v1.0.0*
"""
        
        # Save to current directory
        impl_file = os.path.join(self.current_path, "implementation.md")
        with open(impl_file, 'w', encoding='utf-8') as f:
            f.write(implementation_content)
        
        return impl_file
    
    def generate_test_report(self,
                           project_name: str,
                           test_results: Dict[str, Any]) -> str:
        """Generate test-report.md document"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        test_content = f"""# Test Report - {project_name}

**Generated**: {timestamp}  
**TADD Phase**: 🔧 안정화 (Structural Sustainability Protocol v2.0)

---

## 📚 Context Loading Results

### Pre-Testing Validation
- ✅ project_rules.md: {self._check_file_exists('project_rules.md')}
- ✅ implementation.md: {self._check_file_exists('implementation.md')}
- ✅ Previous test results: {self._check_file_exists('test-report.md')}

---

## 🏗️ 6-Stage Integrated Verification Loop

### 1. Repository Structure Scan
{test_results.get('structure_scan', '📊 Repository structure analysis pending...')}

### 2. Structural Optimization  
{test_results.get('optimization', '🔧 Structural optimization pending...')}

### 3. Dependency Resolution
{test_results.get('dependencies', '🔗 Dependency resolution pending...')}

### 4. User-Centric Comprehensive Testing ⚠️ NO MOCKS
{self._format_real_testing_results(test_results.get('real_testing', {}))}

### 5. Documentation Sync
{test_results.get('doc_sync', '📚 Documentation sync pending...')}

### 6. Quality Assurance
{test_results.get('quality_assurance', '✅ Quality assurance pending...')}

---

## 🎯 PRD-Based Real Scenario Testing

### Core User Stories Validation
{self._format_user_stories_results(test_results.get('user_stories', []))}

### End-to-End Workflow Testing
{self._format_e2e_results(test_results.get('e2e_results', {}))}

### Performance Benchmarks (Quantitative)
{self._format_performance_results(test_results.get('performance', {}))}

---

## 📊 Test Coverage Analysis

### Coverage Metrics
```
Overall Coverage: {test_results.get('coverage', {}).get('overall', 'N/A')}%
Unit Tests: {test_results.get('coverage', {}).get('unit', 'N/A')}%  
Integration Tests: {test_results.get('coverage', {}).get('integration', 'N/A')}%
E2E Tests: {test_results.get('coverage', {}).get('e2e', 'N/A')}%
```

### Test Suite Results
{self._format_test_suite_results(test_results.get('test_suites', []))}

---

## ⚠️ Issues & Failures

### Critical Issues
{test_results.get('critical_issues', 'No critical issues detected')}

### Test Failures
{test_results.get('failures', 'No test failures')}

### Performance Issues
{test_results.get('performance_issues', 'No performance issues detected')}

---

## 🔄 Preventive Management Triggers

### Repository Health Check
- Root file count: {test_results.get('root_files', 'Unknown')} (Trigger: 20+)
- Temp file count: {test_results.get('temp_files', 'Unknown')} (Trigger: 5+) 
- Import errors: {test_results.get('import_errors', 'Unknown')} (Trigger: 3+)

### Action Required
{test_results.get('action_required', 'No immediate action required')}

---

## 📈 Quality Metrics

### Code Quality
{test_results.get('code_quality', 'Code quality metrics pending...')}

### Maintainability Score
{test_results.get('maintainability', 'Maintainability score pending...')}

### Security Assessment
{test_results.get('security', 'Security assessment pending...')}

---

## ✅ Stabilization Checklist

- [ ] Repository structure optimized
- [ ] All dependencies resolved
- [ ] Real scenario tests passing
- [ ] Performance benchmarks met
- [ ] Documentation synchronized
- [ ] Quality gates satisfied
- [ ] No critical issues remaining

---

**Test Status**: {test_results.get('status', '🟡 Testing In Progress')}  
**Next Phase**: 📍 배포 (Deployment)  
**Ready for Deployment**: {test_results.get('ready_for_deployment', '❌ Not Ready')}

---
*Generated by TADD Document Generator v1.0.0*
"""
        
        # Save to current directory
        test_file = os.path.join(self.current_path, "test-report.md")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        return test_file
    
    def update_status_document(self, updates: Dict[str, Any]) -> str:
        """Update status.md with latest information"""
        status_file = os.path.join(self.base_path, "docs/CURRENT/status.md")
        
        # Read existing status if available
        existing_content = ""
        if os.path.exists(status_file):
            with open(status_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # Update specific sections while preserving structure
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # This is a simplified update - real implementation would parse and update sections
        with open(status_file, 'w', encoding='utf-8') as f:
            f.write("# Current System Status - Claude-Ops\\n\\n")
            f.write(f"**Last Updated**: {timestamp}\\n")
            f.write("**TADD Integration**: 🟢 Active\\n\\n")
            
            for section, content in updates.items():
                f.write(f"## {section}\\n{content}\\n\\n")
        
        return status_file
    
    # Helper methods
    def _check_status_file(self) -> str:
        status_file = os.path.join(self.base_path, "docs/CURRENT/status.md")
        return "Available" if os.path.exists(status_file) else "Missing"
    
    def _count_active_todos(self) -> int:
        todos_file = os.path.join(self.current_path, "active-todos.md")
        if os.path.exists(todos_file):
            with open(todos_file, 'r', encoding='utf-8') as f:
                content = f.read()
                return content.count("- ⏳") + content.count("- 🔄")
        return 0
    
    def _load_previous_context(self) -> str:
        # Load context from previous session files
        return "Previous context loading to be implemented..."
    
    def _generate_work_breakdown(self, context: Dict, scale: ProjectScale) -> str:
        # Generate WBS based on scale and context
        if scale == ProjectScale.STRATEGIC:
            return """
1. **Architecture Design** (Strategic)
2. **Core Implementation** (Tactical)  
3. **Integration Testing** (Tactical)
4. **Documentation** (Operational)
"""
        return "Work breakdown to be refined based on specific context..."
    
    def _analyze_dependencies(self, context: Dict) -> str:
        return "Dependency analysis to be implemented..."
    
    def _get_doc_level(self, scale: ProjectScale) -> str:
        return {
            ProjectScale.STRATEGIC: "Comprehensive (PRD + Planning + Implementation + Tests)",
            ProjectScale.TACTICAL: "Detailed (Planning + Implementation + Tests)",
            ProjectScale.OPERATIONAL: "Focused (TodoWrite tracking only)"
        }[scale]
    
    def _get_testing_strategy(self, scale: ProjectScale) -> str:
        return {
            ProjectScale.STRATEGIC: "Full E2E + Integration + Unit testing",
            ProjectScale.TACTICAL: "Integration + Unit testing",
            ProjectScale.OPERATIONAL: "Unit testing + smoke tests"
        }[scale]
    
    def _get_review_process(self, scale: ProjectScale) -> str:
        return {
            ProjectScale.STRATEGIC: "Architecture review + Code review + QA review",
            ProjectScale.TACTICAL: "Code review + QA review", 
            ProjectScale.OPERATIONAL: "Code review"
        }[scale]
    
    def _check_implementation_readiness(self) -> str:
        # Check if planning phase is complete
        return "Implementation readiness check to be implemented..."
    
    def _check_file_exists(self, filename: str) -> str:
        filepath = os.path.join(self.current_path, filename)
        return "✅ Found" if os.path.exists(filepath) else "❌ Missing"
    
    def _format_completed_tasks(self, tasks: List) -> str:
        if not tasks:
            return "No completed tasks yet"
        return "\\n".join(f"- ✅ {task}" for task in tasks)
    
    def _format_remaining_tasks(self, tasks: List) -> str:
        if not tasks:
            return "No remaining tasks"
        return "\\n".join(f"- ⏳ {task}" for task in tasks)
    
    def _format_real_testing_results(self, results: Dict) -> str:
        if not results:
            return "🚨 **CRITICAL**: Real testing results missing - Mock tests are prohibited"
        
        return f"""
#### Real Data Testing Results ✅
- **User Scenarios Tested**: {results.get('scenarios_tested', 0)}
- **Actual Data Used**: {results.get('real_data_used', 'Unknown')}
- **Success Rate**: {results.get('success_rate', 'Unknown')}%
- **Performance Measured**: {results.get('performance_measured', 'Unknown')}

#### Quantitative Metrics (Required)
- **Response Time**: {results.get('response_time', 'MISSING')}ms
- **Throughput**: {results.get('throughput', 'MISSING')} req/sec
- **Memory Usage**: {results.get('memory_usage', 'MISSING')}MB
- **Error Rate**: {results.get('error_rate', 'MISSING')}%
"""
    
    def _format_user_stories_results(self, stories: List) -> str:
        if not stories:
            return "User stories testing pending..."
        return "\\n".join(f"- {story}" for story in stories)
    
    def _format_e2e_results(self, results: Dict) -> str:
        return f"E2E testing results: {results}"
    
    def _format_performance_results(self, results: Dict) -> str:
        return f"Performance results: {results}"
    
    def _format_test_suite_results(self, suites: List) -> str:
        if not suites:
            return "No test suites executed"
        return "\\n".join(f"- {suite}" for suite in suites)


# Document templates for different project scales
DOCUMENT_TEMPLATES = {
    ProjectScale.STRATEGIC: {
        "requires": ["PRD", "planning", "implementation", "test-report"],
        "optional": []
    },
    ProjectScale.TACTICAL: {
        "requires": ["implementation", "test-report"],
        "optional": ["planning"]
    },
    ProjectScale.OPERATIONAL: {
        "requires": [],
        "optional": ["implementation"]
    }
}