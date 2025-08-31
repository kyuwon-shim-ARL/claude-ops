"""
TADD PRD Manager - Product Requirements Document Lifecycle Management

Manages PRD creation, validation, and lifecycle for all project scales
with templates, approval workflows, and traceability.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass


class PRDStatus(Enum):
    DRAFT = "draft"
    REVIEW = "review"  
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    ARCHIVED = "archived"


class RequirementType(Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"


@dataclass
class Requirement:
    """Individual requirement with full traceability"""
    id: str
    type: RequirementType
    priority: str  # P0, P1, P2, P3
    title: str
    description: str
    acceptance_criteria: List[str]
    dependencies: List[str]
    status: str
    created_at: datetime
    updated_at: datetime


class TADDPRDManager:
    """
    Comprehensive PRD lifecycle management
    
    Features:
    - Scale-based PRD templates
    - Requirement traceability
    - Approval workflows  
    - Implementation tracking
    - Quality gates
    """
    
    def __init__(self, base_path: str = "/home/kyuwon/claude-ops"):
        self.base_path = base_path
        self.prd_path = os.path.join(base_path, "docs/specs/PRD")
        self.current_path = os.path.join(base_path, "docs/CURRENT")
        self.ensure_directories()
    
    def ensure_directories(self):
        """Ensure PRD directories exist"""
        os.makedirs(self.prd_path, exist_ok=True)
        os.makedirs(self.current_path, exist_ok=True)
    
    def create_prd(self,
                   project_name: str,
                   project_scale: str,
                   context: Dict[str, Any]) -> str:
        """Create a new PRD based on project scale"""
        
        timestamp = datetime.now()
        prd_id = f"PRD-{project_name.replace(' ', '-').lower()}-{timestamp.strftime('%Y%m%d')}"
        
        # Load appropriate template
        template = self._get_template_for_scale(project_scale)
        
        # Generate PRD content
        prd_content = self._generate_prd_content(
            prd_id, project_name, project_scale, context, template
        )
        
        # Save PRD
        prd_file = os.path.join(self.prd_path, f"{prd_id}.md")
        with open(prd_file, 'w', encoding='utf-8') as f:
            f.write(prd_content)
        
        # Create current symlink for active PRD
        current_prd = os.path.join(self.current_path, "current-PRD.md")
        if os.path.exists(current_prd):
            os.remove(current_prd)
        os.symlink(prd_file, current_prd)
        
        # Initialize requirements tracking
        self._initialize_requirements_tracking(prd_id, context)
        
        return prd_file
    
    def _get_template_for_scale(self, scale: str) -> Dict:
        """Get PRD template based on project scale"""
        templates = {
            "strategic": {
                "sections": [
                    "executive_summary", "requirements_specification", 
                    "system_architecture", "implementation_plan",
                    "success_metrics", "risk_analysis", "timeline",
                    "acceptance_criteria", "change_management"
                ],
                "detail_level": "comprehensive",
                "stakeholders": ["technical_lead", "product_owner", "qa_lead"],
                "approval_gates": 3
            },
            "tactical": {
                "sections": [
                    "executive_summary", "requirements_specification",
                    "implementation_plan", "success_metrics", 
                    "acceptance_criteria"
                ],
                "detail_level": "detailed",
                "stakeholders": ["technical_lead", "product_owner"],
                "approval_gates": 2
            },
            "operational": {
                "sections": [
                    "summary", "requirements", "acceptance_criteria"
                ],
                "detail_level": "focused", 
                "stakeholders": ["technical_lead"],
                "approval_gates": 1
            }
        }
        return templates.get(scale.lower(), templates["tactical"])
    
    def _generate_prd_content(self,
                            prd_id: str,
                            project_name: str,
                            scale: str,
                            context: Dict[str, Any],
                            template: Dict) -> str:
        """Generate comprehensive PRD content"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""# Product Requirements Document (PRD)
## {project_name}

**PRD ID**: {prd_id}  
**Version**: 1.0.0  
**Date**: {timestamp}  
**Author**: Claude Code with TADD Methodology  
**Status**: 🟡 {PRDStatus.DRAFT.value.title()}  
**Scale**: {scale.title()} ({template['detail_level']})

---

## 📋 Executive Summary

### Mission Statement
{context.get('mission', 'Mission statement to be defined...')}

### Project Scale
**🎯 {scale.title()} Level** - {self._get_scale_description(scale)}

### Success Criteria
{self._format_success_criteria(context.get('success_criteria', []))}

---

## 🎯 Requirements Specification

### Functional Requirements
{self._generate_functional_requirements(context.get('functional_requirements', []))}

### Non-Functional Requirements  
{self._generate_non_functional_requirements(context.get('non_functional_requirements', []))}

### Constraints & Assumptions
{self._generate_constraints_assumptions(context.get('constraints', []), context.get('assumptions', []))}

---

## 🏗️ System Architecture

### Component Hierarchy
{context.get('architecture', 'System architecture to be defined...')}

### Data Flow
{context.get('data_flow', 'Data flow to be defined...')}

### Integration Points
{context.get('integrations', 'Integration points to be defined...')}

---

## 📊 Implementation Plan

### Development Phases
{self._generate_implementation_phases(context.get('phases', []))}

### Resource Requirements
{context.get('resources', 'Resource requirements to be defined...')}

### Dependencies & Prerequisites
{context.get('dependencies', 'Dependencies to be identified...')}

---

## 🎯 Success Metrics

### Quantitative Metrics
{self._generate_quantitative_metrics(context.get('metrics', {}))}

### Qualitative Metrics
{context.get('qualitative_metrics', 'Qualitative metrics to be defined...')}

### Quality Gates
{self._generate_quality_gates(template['approval_gates'])}

---

## 🚨 Risk Analysis

### Technical Risks
{self._generate_risk_table(context.get('technical_risks', []))}

### Operational Risks
{self._generate_risk_table(context.get('operational_risks', []))}

### Mitigation Strategies
{context.get('mitigation', 'Mitigation strategies to be defined...')}

---

## 📅 Timeline

### Milestone Schedule
{self._generate_milestone_schedule(context.get('milestones', []))}

### Critical Path
{context.get('critical_path', 'Critical path to be defined...')}

### Buffer Analysis
{context.get('buffer_analysis', 'Buffer analysis to be performed...')}

---

## 📝 Acceptance Criteria

### Definition of Done
{self._generate_definition_of_done(context.get('done_criteria', []))}

### Sign-off Requirements
{self._generate_signoff_requirements(template['stakeholders'])}

### Testing Requirements
{context.get('testing_requirements', 'Testing requirements to be defined...')}

---

## 🔄 Change Management

### Version History
| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | {timestamp} | Initial PRD | Claude Code |

### Approval Workflow
{self._generate_approval_workflow(template['stakeholders'])}

### Change Request Process
{self._generate_change_process()}

---

## 📊 Traceability Matrix

### Requirements → Implementation
{self._generate_traceability_matrix(context.get('requirements', []))}

### Implementation → Testing
{context.get('implementation_testing_trace', 'Traceability to be established...')}

---

**Document Status**: 🟡 DRAFT - Ready for Review  
**Next Review**: {self._calculate_next_review_date()}  
**Approval Required**: {', '.join(template['stakeholders'])}

---
*Generated by TADD PRD Manager v1.0.0*
"""
        return content
    
    def validate_prd(self, prd_file: str) -> Dict[str, Any]:
        """Validate PRD completeness and quality"""
        
        validation_results = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "completeness": 0,
            "quality_score": 0
        }
        
        if not os.path.exists(prd_file):
            validation_results["valid"] = False
            validation_results["errors"].append("PRD file not found")
            return validation_results
        
        # Read PRD content
        with open(prd_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check required sections
        required_sections = [
            "Executive Summary", "Requirements Specification",
            "Success Metrics", "Acceptance Criteria"
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in content:
                missing_sections.append(section)
        
        if missing_sections:
            validation_results["errors"].extend(
                f"Missing required section: {section}" for section in missing_sections
            )
            validation_results["valid"] = False
        
        # Calculate completeness
        total_sections = len(required_sections)
        complete_sections = total_sections - len(missing_sections)
        validation_results["completeness"] = (complete_sections / total_sections) * 100
        
        # Check for placeholder content
        placeholders = [
            "to be defined", "pending", "TBD", "TODO",
            "to be implemented", "to be determined"
        ]
        
        placeholder_count = sum(content.lower().count(placeholder.lower()) 
                              for placeholder in placeholders)
        
        if placeholder_count > 5:
            validation_results["warnings"].append(
                f"High number of placeholders ({placeholder_count}) - PRD may be incomplete"
            )
        
        # Calculate quality score
        quality_factors = {
            "completeness": validation_results["completeness"] * 0.4,
            "placeholder_penalty": max(0, 40 - placeholder_count * 2),  
            "structure_bonus": 20 if "##" in content else 0,
            "metrics_bonus": 10 if "metrics" in content.lower() else 0
        }
        
        validation_results["quality_score"] = sum(quality_factors.values())
        
        return validation_results
    
    def approve_prd(self, prd_file: str, approver: str) -> bool:
        """Mark PRD as approved by stakeholder"""
        
        # Validate PRD first
        validation = self.validate_prd(prd_file)
        if not validation["valid"]:
            return False
        
        # Update PRD status in file
        self._update_prd_status(prd_file, PRDStatus.APPROVED, approver)
        
        # Log approval
        self._log_approval(prd_file, approver)
        
        return True
    
    def track_implementation_progress(self, 
                                   prd_file: str,
                                   progress: Dict[str, Any]) -> str:
        """Track implementation progress against PRD"""
        
        progress_report = f"""# PRD Implementation Progress

**PRD**: {os.path.basename(prd_file)}  
**Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Requirements Implementation Status

### Completed Requirements
{self._format_completed_requirements(progress.get('completed', []))}

### In Progress Requirements  
{self._format_in_progress_requirements(progress.get('in_progress', []))}

### Pending Requirements
{self._format_pending_requirements(progress.get('pending', []))}

## Quality Gate Status

### Current Phase
{progress.get('current_phase', 'Unknown')}

### Gates Passed
{progress.get('gates_passed', 0)} / {progress.get('total_gates', 0)}

### Next Milestone
{progress.get('next_milestone', 'Unknown')}

## Issues & Blockers

{progress.get('issues', 'No issues reported')}

---
*Progress tracked by TADD PRD Manager*
"""
        
        # Save progress report
        progress_file = os.path.join(self.current_path, "prd-progress.md")
        with open(progress_file, 'w', encoding='utf-8') as f:
            f.write(progress_report)
        
        return progress_file
    
    # Helper methods
    def _get_scale_description(self, scale: str) -> str:
        descriptions = {
            "strategic": "Major architectural changes requiring comprehensive planning and stakeholder alignment",
            "tactical": "Medium-scope features requiring detailed planning and implementation",
            "operational": "Focused tasks requiring minimal overhead and quick delivery"
        }
        return descriptions.get(scale.lower(), "Standard project scope")
    
    def _format_success_criteria(self, criteria: List[str]) -> str:
        if not criteria:
            return "Success criteria to be defined..."
        return "\\n".join(f"- ✅ {criterion}" for criterion in criteria)
    
    def _generate_functional_requirements(self, requirements: List[Dict]) -> str:
        if not requirements:
            return "Functional requirements to be defined..."
        
        output = []
        for i, req in enumerate(requirements, 1):
            output.append(f"""
#### FR-{i}: {req.get('title', 'Requirement Title')}
**Priority**: {req.get('priority', 'P2')}
{req.get('description', 'Requirement description...')}

**Acceptance Criteria**:
{self._format_acceptance_criteria(req.get('acceptance_criteria', []))}
""")
        return "\\n".join(output)
    
    def _generate_non_functional_requirements(self, requirements: List[Dict]) -> str:
        if not requirements:
            return "Non-functional requirements to be defined..."
        
        output = []
        for i, req in enumerate(requirements, 1):
            output.append(f"""
#### NFR-{i}: {req.get('title', 'NFR Title')}
**Category**: {req.get('category', 'Performance')}
**Target**: {req.get('target', 'Target value...')}
**Measurement**: {req.get('measurement', 'How to measure...')}
""")
        return "\\n".join(output)
    
    def _format_acceptance_criteria(self, criteria: List[str]) -> str:
        if not criteria:
            return "- Acceptance criteria to be defined"
        return "\\n".join(f"- {criterion}" for criterion in criteria)
    
    def _generate_constraints_assumptions(self, constraints: List[str], assumptions: List[str]) -> str:
        output = ["### Constraints"]
        if constraints:
            output.extend(f"- {constraint}" for constraint in constraints)
        else:
            output.append("- Constraints to be identified...")
        
        output.append("\\n### Assumptions")
        if assumptions:
            output.extend(f"- {assumption}" for assumption in assumptions)
        else:
            output.append("- Assumptions to be documented...")
        
        return "\\n".join(output)
    
    def _generate_implementation_phases(self, phases: List[Dict]) -> str:
        if not phases:
            return "Implementation phases to be defined..."
        
        output = []
        for phase in phases:
            output.append(f"""
**Phase {phase.get('number', 'N')}: {phase.get('name', 'Phase Name')}**
- Duration: {phase.get('duration', 'TBD')}
- Deliverables: {phase.get('deliverables', 'TBD')}
- Resources: {phase.get('resources', 'TBD')}
""")
        return "\\n".join(output)
    
    def _generate_quantitative_metrics(self, metrics: Dict) -> str:
        if not metrics:
            return "Quantitative metrics to be defined..."
        
        output = ["| Metric | Target | Measurement Method |", 
                 "|--------|--------|-------------------|"]
        
        for metric, details in metrics.items():
            target = details.get('target', 'TBD') if isinstance(details, dict) else details
            method = details.get('method', 'TBD') if isinstance(details, dict) else 'TBD'
            output.append(f"| {metric} | {target} | {method} |")
        
        return "\\n".join(output)
    
    def _generate_quality_gates(self, num_gates: int) -> str:
        gates = [
            "✅ Requirements Review Complete",
            "✅ Design Review Approved", 
            "✅ Implementation Complete",
            "✅ Testing Complete",
            "✅ Documentation Complete"
        ]
        return "\\n".join(f"- {gates[i]}" for i in range(min(num_gates, len(gates))))
    
    def _generate_risk_table(self, risks: List[Dict]) -> str:
        if not risks:
            return "Risks to be identified..."
        
        output = ["| Risk | Impact | Probability | Mitigation |",
                 "|------|--------|-------------|------------|"]
        
        for risk in risks:
            output.append(
                f"| {risk.get('name', 'Risk')} | "
                f"{risk.get('impact', 'TBD')} | "
                f"{risk.get('probability', 'TBD')} | "
                f"{risk.get('mitigation', 'TBD')} |"
            )
        
        return "\\n".join(output)
    
    def _generate_milestone_schedule(self, milestones: List[Dict]) -> str:
        if not milestones:
            return "Milestone schedule to be defined..."
        
        output = []
        for milestone in milestones:
            output.append(
                f"- **{milestone.get('name', 'Milestone')}** "
                f"({milestone.get('date', 'TBD')}): "
                f"{milestone.get('description', 'Description...')}"
            )
        
        return "\\n".join(output)
    
    def _generate_definition_of_done(self, criteria: List[str]) -> str:
        if not criteria:
            return """
- [ ] All functional requirements implemented
- [ ] All non-functional requirements met
- [ ] Test coverage > 80%
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Performance benchmarks achieved
- [ ] User acceptance confirmed
- [ ] Deployed to production
"""
        return "\\n".join(f"- [ ] {criterion}" for criterion in criteria)
    
    def _generate_signoff_requirements(self, stakeholders: List[str]) -> str:
        return "\\n".join(f"- {stakeholder.replace('_', ' ').title()} approval" 
                         for stakeholder in stakeholders)
    
    def _generate_approval_workflow(self, stakeholders: List[str]) -> str:
        return f"""
1. **Draft Review**: Internal validation
2. **Stakeholder Review**: {', '.join(stakeholders)}
3. **Final Approval**: All stakeholders sign-off
4. **Implementation Authorization**: Development begins
"""
    
    def _generate_change_process(self) -> str:
        return """
1. **Change Request**: Submit via standard template
2. **Impact Analysis**: Assess scope, timeline, resource impact
3. **Stakeholder Review**: Review with affected parties
4. **Approval Decision**: Approve, reject, or defer
5. **PRD Update**: Update document with approved changes
6. **Communication**: Notify all stakeholders of changes
"""
    
    def _generate_traceability_matrix(self, requirements: List[str]) -> str:
        if not requirements:
            return "Traceability matrix to be established during implementation..."
        return "Traceability matrix tracking to be implemented..."
    
    def _calculate_next_review_date(self) -> str:
        from datetime import timedelta
        next_review = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        next_review = next_review + timedelta(days=7)  # Next week
        return next_review.strftime("%Y-%m-%d")
    
    def _update_prd_status(self, prd_file: str, status: PRDStatus, approver: str):
        """Update PRD status in file"""
        # Read current content
        with open(prd_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update status line
        import re
        status_pattern = r'\*\*Status\*\*: 🟡 Draft'
        replacement = f'**Status**: ✅ {status.value.title()} (by {approver})'
        
        updated_content = re.sub(status_pattern, replacement, content)
        
        # Write back
        with open(prd_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)
    
    def _log_approval(self, prd_file: str, approver: str):
        """Log PRD approval event"""
        log_file = os.path.join(self.current_path, "prd-approvals.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} - {os.path.basename(prd_file)} approved by {approver}\\n")
    
    def _initialize_requirements_tracking(self, prd_id: str, context: Dict[str, Any]):
        """Initialize requirements tracking system"""
        tracking_file = os.path.join(self.current_path, f"{prd_id}-tracking.json")
        
        tracking_data = {
            "prd_id": prd_id,
            "created_at": datetime.now().isoformat(),
            "requirements": context.get('requirements', []),
            "status": "initialized"
        }
        
        with open(tracking_file, 'w', encoding='utf-8') as f:
            json.dump(tracking_data, f, indent=2)
    
    def _format_completed_requirements(self, requirements: List[str]) -> str:
        if not requirements:
            return "No requirements completed yet"
        return "\\n".join(f"- ✅ {req}" for req in requirements)
    
    def _format_in_progress_requirements(self, requirements: List[str]) -> str:
        if not requirements:
            return "No requirements in progress"
        return "\\n".join(f"- 🔄 {req}" for req in requirements)
    
    def _format_pending_requirements(self, requirements: List[str]) -> str:
        if not requirements:
            return "No pending requirements"
        return "\\n".join(f"- ⏳ {req}" for req in requirements)