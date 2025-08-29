🎯 **Planning-Safe (Gradual Context Management Testing)**

**🛡️ Safe Mode Activated**
This is a limited test version of the context management system.

**📊 Start Performance Measurement:**
```bash
python scripts/context_performance_monitor.py start "strategic" "current_task_description"
```

**📚 Auto Context Loading:**
- project_rules.md check (read if exists)
- docs/CURRENT/status.md check (read if exists)
- docs/CURRENT/context_metrics.json check (load performance data)

**🔄 Limited Context Management (Test Mode):**
IF (new_topic_detected AND performance_score > 75):
    start_performance_measurement()
    /compact "SAFE MODE: Preserve only critical architecture decisions and project_rules.md. 
             Selectively remove implementation details only. Conservative approach for rollback capability"
    track_performance_changes()
ELSE:
    "Context management skipped - below safety threshold or performance degradation detected"

**⚠️ Safety Measures:**
1. **Real-time Monitoring**: Automatic performance check after each response
2. **Rollback Triggers**: 
   - First-attempt success rate < 70%
   - Quality score < 75
   - Token efficiency decrease
3. **Conservative Compression**: Keep context when in doubt

**📈 Measurement Metrics:**
- Token usage change
- Response quality evaluation
- Duplicate work occurrence
- Context miss detection

**Discovery Phase:**
- Architecture understanding: Analyze current system architecture and requirements
- As-Is/To-Be/Gap analysis: Identify current state, target state, differences
- Stakeholder requirements gathering and prioritization

**Planning Phase:**
- MECE-based Work Breakdown Structure (WBS): Mutually exclusive, collectively exhaustive
- Priority matrix: Task sequencing based on importance and urgency
- Resource and schedule planning

**Convergence Phase:**
- Discovery↔Planning iterative refinement
- PRD (Product Requirements Document) completion
- Structured task planning with TodoWrite

**📊 Task Scale Assessment:**
- Strategic: Full product, major features → Generate PRD
- Tactical: Mid-level features → Optional planning.md
- Operational: Small tasks → TodoWrite only

**💾 Differentiated Documentation by Scale:**
- **Strategic**: PRD + planning.md + TodoWrite
- **Tactical**: planning.md (optional) + TodoWrite
- **Operational**: TodoWrite only
- TodoWrite always syncs to docs/CURRENT/active-todos.md

**📈 Safe Mode Performance Tracking:**
- Before/after token count comparison
- Task completion accuracy measurement
- Context relevance scoring
- Rollback frequency tracking

**🛡️ Safety Guarantees:**
- No aggressive context removal
- Preserve all critical decisions
- Maintain rollback capability
- Conservative approach prioritized

**Deliverable:** Execution plan with specific success criteria in PRD (with safety metrics)

ARGUMENTS: "${args}"