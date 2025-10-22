<!--
Sync Impact Report:
Version Change: (none) → 1.0.0
Modified Principles: Initial creation
Added Sections: All core sections created
Removed Sections: None
Templates Requiring Updates:
  ✅ plan-template.md - Constitution Check section references this document
  ✅ spec-template.md - Already aligned with principles
  ✅ tasks-template.md - Already aligned with TDD and monitoring principles
Follow-up TODOs: None
-->

# Claude-CTB Constitution

## Core Principles

### I. Bridge-First Architecture
**The system is a pure bridge, not a workflow manager.**

Claude-CTB exists solely to connect Telegram with Claude Code sessions. It MUST NOT implement workflows, prompt templates, or development methodologies. These belong in external tools like claude-dev-kit.

Rationale: Separation of concerns ensures the bridge remains reliable, maintainable, and focused. Workflow complexity belongs in dedicated tools.

### II. Polling-Based Reliability
**100% notification delivery is non-negotiable.**

The system MUST use pure polling-based monitoring with no asynchronous event handlers, WebSockets, or push mechanisms. Every state change MUST be detected through tmux screen capture polling at 3-5 second intervals.

Rationale: Polling guarantees deterministic notification delivery. Event-based systems introduce race conditions and missed notifications.

### III. Session State Detection
**State detection MUST be unified and context-aware.**

All session state logic (working/idle/waiting) MUST be centralized in a single source of truth (`session_state.py`). Detection MUST distinguish between active work indicators and historical artifacts on screen.

Rationale: Distributed state logic led to notification inconsistencies and false positives. Unified detection ensures reliability.

### IV. Reply-Based Session Targeting
**User intent determines target session.**

When users reply to a notification message, the command MUST target the session referenced in that message. This prevents session confusion in multi-project workflows.

Rationale: Explicit targeting through replies is more reliable than implicit session switching or "active session" heuristics.

### V. Test-Driven Development (TDD)
**All features MUST follow Red-Green-Refactor.**

Tests MUST be written first, reviewed by users, fail initially, then implementation makes them pass. No exceptions.

Test coverage requirements:
- Contract tests for all external integrations (Telegram API, tmux)
- Integration tests for notification workflows
- Unit tests for state detection logic
- Edge case tests for session tracking

Rationale: TDD ensures reliability in a system where notification failures are unacceptable. Pre-written tests document expected behavior.

### VI. Conservative Detection
**False positives are worse than missed notifications.**

When uncertain about work completion, the system MUST err on the side of NOT sending notifications. Only send when "esc to interrupt" disappears AND prompt appears.

Rationale: False positives train users to ignore notifications. Missed notifications are recoverable via `/log` command.

### VII. Message Splitting
**Never truncate user-visible content.**

Long messages MUST be intelligently split at line boundaries while preserving markdown formatting. Maximum chunk size: 4000 characters.

Rationale: Telegram has 4096-char limits. Smart splitting maintains readability and prevents data loss.

## System Integration Requirements

### External Dependencies
Claude-CTB MUST integrate with:
- **Telegram Bot API**: Primary user interface
- **tmux**: Session management and screen capture
- **claude-dev-kit**: External workflow provider (via prompt forwarding)
- **Git**: Project creation and version control

### Prohibited Dependencies
The system MUST NOT depend on:
- WebSockets or event streams
- Database systems (state persists in tmux and filesystem)
- Container orchestration
- Complex async frameworks beyond python-telegram-bot

Rationale: Minimal dependencies ensure reliability and reduce failure modes.

## Development Workflow

### Feature Development Process
1. **Specification**: Define requirements in `spec.md` (WHAT and WHY, not HOW)
2. **Planning**: Create `plan.md` with technical approach and constitution check
3. **Task Generation**: Create `tasks.md` with TDD-ordered implementation steps
4. **Implementation**: Execute tasks in order (tests first, then implementation)
5. **Validation**: Verify all tests pass and constitution compliance

### Code Review Gates
- [ ] Constitution principles verified
- [ ] TDD process followed (tests before implementation)
- [ ] No workflow logic added (delegates to claude-dev-kit)
- [ ] Polling-based monitoring maintained
- [ ] State detection uses `session_state.py`
- [ ] Integration tests pass
- [ ] No false positive notifications introduced

## Observability & Monitoring

### Logging Requirements
- **Notification decisions**: Log why notifications were sent or suppressed
- **State transitions**: Log session state changes with timestamps
- **Detection confidence**: Log pattern matches and detection certainty
- **User actions**: Log commands received and target sessions

### Debug Tools
- Notification debugger tracks detection events
- Conservative detector provides confidence scores
- Wait time tracker monitors session activity patterns

Rationale: Notification systems are inherently hard to debug. Comprehensive logging enables post-mortem analysis.

## Performance & Scale

### Performance Targets
- Notification latency: <10 seconds from work completion
- Polling interval: 3-5 seconds per session
- Concurrent sessions: 10+ sessions without degradation
- Message handling: <1 second response to Telegram commands

### Scalability Constraints
- System designed for 1-10 concurrent sessions per user
- Not designed for team-wide deployment (requires multi-user fork)
- Polling overhead scales linearly with session count

Rationale: Focus on single-user reliability over multi-tenancy complexity.

## Security & Access Control

### Authentication
- User ID validation against `ALLOWED_USER_IDS` environment variable
- Token-based Telegram bot authentication
- No password storage or session cookies

### Command Safety
- Dangerous command patterns blocked (`rm -rf`, `sudo`, etc.)
- Input length limits (10,000 characters)
- No arbitrary code execution in bot process

Rationale: Telegram bot has full tmux access. Defense-in-depth prevents accidental damage.

## Versioning & Breaking Changes

### Version Format
MAJOR.MINOR.PATCH following semantic versioning:
- **MAJOR**: Breaking changes to Telegram commands or configuration
- **MINOR**: New features, backward-compatible improvements
- **PATCH**: Bug fixes, documentation updates

### Breaking Change Policy
- Constitution changes require MAJOR version bump
- Deprecation warnings before command removal
- Migration guides for configuration changes

## Governance

### Constitution Authority
This constitution supersedes all other documentation. When conflicts arise, constitution principles take precedence.

### Amendment Process
1. Identify principle violation or missing guidance
2. Propose amendment with rationale
3. Validate against existing codebase
4. Update dependent templates and documentation
5. Increment version (MAJOR for breaking changes, MINOR for additions, PATCH for clarifications)

### Compliance Review
- Every PR MUST verify constitution compliance
- Implementation complexity MUST be justified against principles
- Runtime development guidance in `CLAUDE.md` for AI assistants

**Version**: 1.0.0 | **Ratified**: 2025-10-01 | **Last Amended**: 2025-10-01
