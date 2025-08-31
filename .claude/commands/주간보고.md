# /weekly-report - Git-based Sprint Review v3.0

## Command Overview
**Git commit data-driven** sprint review that **quantitatively measures** actual work performance and presents As-Is/To-Be/Gap with **MECE pyramid structure** following **Scrum 2025 best practices**

## Usage
```
/weekly-report                    # Default 2-week sprint
/weekly-report --period=1w        # 1 week period
/weekly-report --sprint=3         # Compare last 3 sprints
/weekly-report --detailed         # Include detailed commit analysis
```

## Claude Execution Process

### Step 0: Git-based Data Collection
```python
def collect_git_metrics(period="2w"):
    git_data = {
        "commits": git_log(f"--since='{period}'", "--pretty=format:'%h|%ad|%an|%s'"),
        "stats": git_log(f"--since='{period}'", "--stat", "--oneline"),
        "velocity": calculate_velocity(commits_per_week),
        "impact": analyze_commit_impact(lines_changed),
        "timeline": extract_sprint_phases(commit_dates)
    }
    return git_data
```

### Step 1: MECE-based Performance Classification & Measurement
```python
def analyze_sprint_performance(git_data, period="2w"):
    # MECE performance classification: Strategic-Tactical-Operational 3-tier matrix
    performance = {
        "strategic": analyze_commits_by_type(["feat:", "refactor:", "BREAKING"]),  # Strategic achievements
        "tactical": analyze_commits_by_type(["fix:", "perf:", "improvement"]),    # Tactical achievements  
        "operational": analyze_commits_by_type(["docs:", "test:", "chore:"]),    # Operational achievements
        "velocity": {
            "commits_per_week": len(git_data["commits"]) / weeks,
            "lines_per_week": total_lines_changed / weeks,
            "impact_score": calculate_weighted_impact(git_data["stats"])
        },
        "phase_progress": extract_development_phases(git_data["commits"])
    }
    return performance
```

### Step 2: As-Is/To-Be/Gap Quantitative Analysis (Pyramid Structure)
```python
def analyze_as_is_to_be_gap(performance, historical_data):
    # Pyramid structure: Derive key message
    analysis = {
        "executive_summary": {
            "key_insight": extract_top_insight(performance),           # Top: Core insight
            "sprint_verdict": "SUCCESS|CONCERN|BLOCKED",               # Overall verdict
            "next_priority": determine_next_sprint_focus(performance)   # Next priority
        },
        
        "as_is_state": {  # Current state quantitative measurement
            "velocity_current": performance["velocity"]["commits_per_week"],
            "capacity_utilization": performance["velocity"]["impact_score"] / max_capacity,
            "phase_distribution": performance["phase_progress"],
            "bottlenecks": identify_bottlenecks_from_commits(performance)
        },
        
        "to_be_targets": {  # Target state (compared to previous sprint)
            "velocity_target": historical_data["avg_velocity"] * 1.1,
            "phase_goals": calculate_next_phase_targets(),
            "improvement_areas": prioritize_improvement_areas(performance)
        },
        
        "gap_analysis": {  # Gap and countermeasures
            "velocity_gap": calculate_velocity_gap(performance, historical_data),
            "blocked_items": extract_blockers_from_commits(performance),
            "self_resolvable": extract_actionable_items(performance),
            "help_needed": extract_external_dependencies(performance)
        }
    }
    return analysis
```

### Step 3: Start/Stop/Continue Scrum Action Items Generation
```python
def generate_scrum_action_items(gap_analysis, performance):
    # Scrum 2025 best practice: Start/Stop/Continue approach
    action_items = {
        "start_doing": [  # New initiatives
            {
                "action": identify_high_impact_actions(gap_analysis["improvement_areas"]),
                "command": suggest_claude_commands(),
                "estimated_sprint_points": estimate_effort(),
                "success_criteria": define_measurable_outcomes()
            }
        ],
        
        "stop_doing": [   # Things to stop
            {
                "inefficiency": identify_time_wasters(performance),
                "impact_of_stopping": calculate_opportunity_cost(),
                "alternative_approach": suggest_better_methods()
            }
        ],
        
        "continue_doing": [  # Things to maintain (working well)
            {
                "strength": identify_effective_patterns(performance),
                "amplification": suggest_scaling_methods(),
                "maintain_quality": define_sustainability_measures()
            }
        ],
        
        "blockers_external": gap_analysis["help_needed"],      # External support needed
        "self_resolvable": gap_analysis["self_resolvable"]     # Self-resolvable items
    }
    return action_items
```

### Step 4: Pyramid Structure Report Generation (MECE + Quantification)
```python
def generate_pyramid_report(date, analysis, action_items):
    report_path = f"docs/CURRENT/weekly_report_git_based_{date}.md"
    
    # Pyramid structure report template
    report = f"""# 🎯 Sprint Review - Git-based Empirical Analysis
*{date} | Quantitative data-driven objective performance measurement*

## 📊 Executive Summary (Pyramid Top)

### 🔍 Key Insight
**{analysis["executive_summary"]["key_insight"]}**

### 🎯 Sprint Overall Verdict: **{analysis["executive_summary"]["sprint_verdict"]}**
- Velocity: {analysis["as_is_state"]["velocity_current"]:.1f} commits/week
- Next Priority: **{analysis["executive_summary"]["next_priority"]}**

---

## 📈 As-Is Analysis (Current State Quantitative Measurement)

### Velocity Metrics
| Metric | Current Sprint | Target | Gap | Status |
|--------|-------------|------|-----|---------|
| Commits/Week | {analysis["as_is_state"]["velocity_current"]:.1f} | {analysis["to_be_targets"]["velocity_target"]:.1f} | {analysis["gap_analysis"]["velocity_gap"]:+.1f} | {get_status_emoji(analysis["gap_analysis"]["velocity_gap"])} |
| Capacity Utilization | {analysis["as_is_state"]["capacity_utilization"]*100:.0f}% | 85% | {(analysis["as_is_state"]["capacity_utilization"]-0.85)*100:+.0f}% | {get_capacity_status(analysis["as_is_state"]["capacity_utilization"])} |

### MECE Performance Breakdown
```
🏗️ Strategic      ████████░░ {get_strategic_percentage(performance)}%
🔧 Tactical       ██████████ {get_tactical_percentage(performance)}%  
⚙️ Operational    ████░░░░░░ {get_operational_percentage(performance)}%
```

### Phase Progress
{visualize_phase_progress(analysis["as_is_state"]["phase_distribution"])}

---

## 🎯 To-Be Targets

### Next Sprint Goals
{format_improvement_areas(analysis["to_be_targets"]["improvement_areas"])}

### Phase Transition Plan  
{format_phase_goals(analysis["to_be_targets"]["phase_goals"])}

---

## ⚡ Gap Analysis & Action Plan

### 🚀 START DOING
{format_start_actions(action_items["start_doing"])}

### 🛑 STOP DOING
{format_stop_actions(action_items["stop_doing"])}

### ✅ CONTINUE DOING
{format_continue_actions(action_items["continue_doing"])}

---

## 🚧 Blockers & Support Needed

### 🆘 External Help Required
{format_external_blockers(action_items["blockers_external"])}

### 🛠️ Self-Resolvable (Next Sprint)
{format_self_resolvable(action_items["self_resolvable"])}

---

## 📊 Sprint Retrospective Dashboard

### Performance Trends
| Metric | 2 Sprints Ago | Last Sprint | Current | Trend | Target |
|--------|---------------|-------------|---------|-------|--------|
| Velocity | {get_historical_velocity(-2):.1f} | {get_historical_velocity(-1):.1f} | {analysis["as_is_state"]["velocity_current"]:.1f} | {get_trend_arrow()} | {analysis["to_be_targets"]["velocity_target"]:.1f} |
| Impact Score | {get_historical_impact(-2):.1f} | {get_historical_impact(-1):.1f} | {get_current_impact():.1f} | {get_impact_trend()} | {get_target_impact():.1f} |

### Commit Pattern Analysis
- **Most Productive Days**: {identify_productive_days(git_data)}
- **Peak Hours**: {identify_peak_hours(git_data)}
- **Collaboration Score**: {calculate_collaboration_score(git_data)}

### Success Patterns (Continue Amplifying)
{extract_success_patterns(performance)}

### Anti-Patterns (Stop Immediately)  
{extract_anti_patterns(performance)}

---

## 🎯 Next Sprint Commitment

### Sprint Goals (SMART)
{format_smart_goals(analysis["executive_summary"]["next_priority"])}

### Definition of Done
{define_completion_criteria(action_items)}

### Risk Mitigation
{identify_risks_and_mitigation(analysis)}

---

*📅 Next Review: {calculate_next_review_date()}*
*🔄 Sprint Cycle: {get_sprint_cycle_info()}*
*⏱️ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    
    # Save file
    write_file(report_path, report)
    return report_path
```

## Key Improvements (v2.0 → v3.0)

### ✅ Scrum 2025 Best Practices Applied
1. **Git-based Objective Measurement**: Removed PRD/doc dependency, using actual work data
2. **Start/Stop/Continue**: Clear action items, specific improvement directions
3. **MECE Pyramid Structure**: Core insights first, hierarchical details
4. **Quantified Metrics**: All decisions backed by numbers and trends

### ✅ Systematic As-Is/To-Be/Gap Analysis
- **As-Is**: Accurately measure current state with Git data
- **To-Be**: Set improvement targets vs. previous sprint  
- **Gap**: Present specific gaps and solutions

### ✅ Collaboration-Centric Structure
- **Self-resolvable** vs **External support** clearly separated
- **Blocker Identification**: Issues requiring team-level priority
- **Success Patterns**: Share what's working well across team

## Execution Example

### Input:
```
/weekly-report
```

### Claude Execution:
1. **Git Data Collection**: Analyze last 1 week commit history
2. **MECE Performance Classification**: Measure performance by strategic-tactical-operational levels  
3. **Pyramid Structure Analysis**: Core insight → Detailed analysis → Action items
4. **Start/Stop/Continue**: Specific improvement directions in Scrum style
5. **Quantitative Report Generation**: Comprehensive report based on objective metrics

### Output Example:
```markdown
# 🎯 Sprint Review - Git-based Empirical Analysis
*2025-08-29 | Quantitative data-driven objective performance measurement*

## 📊 Executive Summary

### 🔍 Key Insight
**Achieved 93% codebase optimization through massive legacy code cleanup, maintaining 100% test pass rate**

### 🎯 Sprint Overall Verdict: **SUCCESS**
- Velocity: 3.5 commits/week (+17% vs. target 3.0)  
- Next Priority: **Transition to new feature development phase**

## 📈 As-Is Analysis

### Velocity Metrics
| Metric | Current Sprint | Target | Gap | Status |
|--------|-------------|------|-----|---------|
| Commits/Week | 3.5 | 3.0 | +0.5 | ✅ |
| Capacity Utilization | 95% | 85% | +10% | ⚠️ |

### MECE Performance Breakdown
```
🏗️ Strategic      ████████░░ 80%
🔧 Tactical       ██████░░░░ 60%  
⚙️ Operational    ██████████ 100%
```

## ⚡ Gap Analysis & Action Plan

### 🚀 START DOING
- **Build new feature development pipeline**: Implement `/plan` → `/implement` → `/verify` system
- **Estimated Sprint Points**: 8 points
- **Success Criteria**: Complete first new feature MVP

### 🛑 STOP DOING  
- **Excessive refactoring**: Currently at 95% capacity, need to focus on new development
- **Alternative**: Switch to incremental improvements

### ✅ CONTINUE DOING
- **Maintain 100% E2E test coverage**: Quality assurance pattern established
- **Scaling**: Apply same test standards to new features

## 🚧 Blockers & Support Needed

### 🆘 External Help Required
- None (all current work within self-resolvable scope)

### 🛠️ Self-Resolvable
- Define new feature requirements and priorities
- Extend development environment for new feature support

---
*📅 Next Review: 2025-09-12*  
*🔄 Sprint Cycle: 2-week sprints*
```

## Benefits

### 📈 Objectivity
- Measure **actual performance** based on Git commit data, not speculation
- **Unbiased judgment** through quantitative metrics

### 🎯 Actionability
- **Specific action guidelines** through Start/Stop/Continue
- **Immediate executability** by clearly separating self-resolvable vs. external support

### 🔄 Continuous Improvement
- Track improvement trends through **quantitative comparison** with previous sprints
- **Accumulate learning** by identifying success patterns and anti-patterns

### 🤝 Team Collaboration
- **Hierarchical understanding** from core to details with pyramid structure
- **Team-level sharing** of blockers and solutions

---
*Measure actual performance, not speculation, with Git-based quantitative data.*