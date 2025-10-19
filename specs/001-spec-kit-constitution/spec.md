# Feature Specification: Claude-CTB System Reliability Improvements

**Feature Branch**: `001-spec-kit-constitution`
**Created**: 2025-10-01
**Status**: Draft
**Input**: User description: "이미 진행중인 프로젝트인데, spec-kit를 적용해보고싶어. constitution 역으로 산출 가능해? claude 세션의 진행사항을 telegram으로 연동하여 진행사항 확인하고 telegram 메시지를 보내면 실제 claude 세션에 명령을 보낼 수있도록 구성했어. 세부내역은 방금 reverse-engineering 으로 모두 포착했어. 다만 아직 기능들이 완벽하지 않아서 보완이 필요해."

## Clarifications

### Session 2025-10-01
- Q: When a monitored tmux session disconnects unexpectedly, what should happen? → A: Retry reconnection attempts for a configurable duration then notify user of failure
- Q: When the monitoring system restarts, how should it handle sessions that may have completed work during the downtime? → A: Skip missed events and only track new state changes after restart
- Q: When Telegram API rate limits are exceeded, what should the system do with queued messages? → A: Queue messages in memory and retry with exponential backoff until successful
- Q: When a user sends a command containing a dangerous pattern (rm -rf, sudo, etc.), what should the system do? → A: Send a confirmation request requiring explicit user approval before executing
- Q: When detecting session state changes, how much screen history should be analyzed to distinguish active indicators from historical artifacts? → A: Last 200 lines sufficient

## User Scenarios & Testing

### Primary User Story
A developer is working on multiple projects using Claude Code. They want to monitor all Claude sessions remotely via Telegram and send commands to specific sessions without being physically present at their terminal. When a Claude session completes work or encounters an issue, they should receive immediate Telegram notifications with accurate context about which session needs attention.

### Acceptance Scenarios

1. **Given** three active Claude Code sessions are running in tmux, **When** any session completes a task and waits for user input, **Then** the user receives a Telegram notification within 10 seconds identifying the specific session and showing relevant context.

2. **Given** a user receives a notification about session "claude_project-a", **When** the user replies to that notification with a command, **Then** the command is sent exclusively to the "claude_project-a" session, not any other active sessions.

3. **Given** a Claude session is actively working (showing "esc to interrupt"), **When** the monitoring system checks the session state, **Then** no notification is sent because work is still in progress.

4. **Given** a Claude session completes work and the screen shows a prompt without "esc to interrupt", **When** 5 seconds pass, **Then** a notification is sent exactly once (no duplicates).

5. **Given** a user sends the `/sessions` command, **When** Telegram responds, **Then** all active Claude Code sessions are listed (excluding monitoring/management sessions), with their current state (working/waiting/idle).

6. **Given** a Claude session outputs 8000 characters of log content, **When** the user requests `/log`, **Then** the content is split intelligently at line boundaries into multiple messages preserving markdown formatting.

7. **Given** a user sends a command containing "sudo rm -rf /", **When** the system detects the dangerous pattern, **Then** a confirmation request is sent to the user requiring explicit approval before the command executes.

### Edge Cases

- When tmux session disconnects during monitoring, system retries reconnection for configurable duration then notifies user of failure
- When monitoring system restarts, missed events during downtime are skipped and only new state changes after restart are tracked
- When Telegram API rate limits are hit, messages are queued in memory and retried with exponential backoff until successful
- When dangerous command patterns are detected, system sends confirmation request requiring explicit user approval before executing
- State detection analyzes last 200 lines of screen history to distinguish active indicators from historical artifacts
- When monitoring session (claude-monitor) is not running, system MUST NOT send any notifications regardless of session state changes
- When /summary command generates output exceeding Telegram's 4096 character limit, messages MUST be split intelligently across multiple sends
- When multiple sessions complete work simultaneously (within same poll cycle), system sends individual notifications in session discovery order without dropping any
- When user sends command to non-existent session, system replies with "Session not found" error message

## Requirements

### Functional Requirements

#### Monitoring & Notification
- **FR-001**: System MUST continuously monitor all Claude Code tmux sessions at 3-5 second intervals using screen capture polling
- **FR-002**: System MUST detect when a Claude session transitions from "working" state to "waiting for input" state
- **FR-003**: System MUST send Telegram notifications within 10 seconds of work completion
- **FR-004**: System MUST prevent duplicate notifications for the same completion event
- **FR-005**: System MUST distinguish between active work indicators and historical screen artifacts
- **FR-006**: System MUST NOT send notifications when "esc to interrupt" is visible on screen
- **FR-007**: System MUST track notification delivery state across system restarts, skipping missed events during downtime and only notifying for new state changes after restart
- **FR-033**: Monitoring session (claude-monitor) MUST be initialized and running before any notifications can be sent
- **FR-034**: System MUST provide status check to verify monitoring session is active and operational

#### Session Targeting & Control
- **FR-008**: System MUST support reply-based session targeting (user replies to notification to target that specific session)
- **FR-009**: System MUST route commands to the correct tmux session based on user intent
- **FR-010**: System MUST validate that target sessions exist before sending commands
- **FR-011**: System MUST provide a session list command showing all active Claude Code sessions
- **FR-012**: System MUST exclude monitoring and management sessions from user-visible session lists
- **FR-013**: System MUST support switching between sessions without ambiguity

#### Message Handling
- **FR-014**: System MUST split messages exceeding 4000 characters into multiple chunks
- **FR-015**: Message splitting MUST preserve line boundaries (no mid-line breaks)
- **FR-016**: Message splitting MUST preserve markdown formatting across chunks
- **FR-017**: System MUST queue messages in memory and retry with exponential backoff when Telegram API rate limits are exceeded

#### State Detection
- **FR-018**: System MUST use a single unified state detection module as the source of truth
- **FR-019**: State detection MUST categorize sessions as: ERROR, WAITING_INPUT, WORKING, IDLE, or UNKNOWN
- **FR-020**: State detection MUST prioritize states correctly (ERROR > WAITING_INPUT > WORKING > IDLE > UNKNOWN)
- **FR-021**: State detection MUST analyze the last 200 lines of screen history using context-aware pattern matching to distinguish active indicators from historical artifacts
- **FR-022**: System MUST provide debugging information for notification decisions

#### Security & Access Control
- **FR-023**: System MUST validate user IDs against allowed user list before processing commands
- **FR-024**: System MUST detect dangerous command patterns (rm -rf, sudo, etc.) and send confirmation request requiring explicit user approval before executing
- **FR-025**: System MUST limit command input length to 10,000 characters
- **FR-026**: System MUST NOT expose sensitive information in logs or messages

#### Reliability & Error Handling
- **FR-027**: System MUST retry reconnection to disconnected tmux sessions for a configurable duration before notifying user of failure
- **FR-028**: System MUST recover from Telegram API failures (rate limits, network errors, timeouts) without losing notification state by queueing messages and retrying with exponential backoff
- **FR-029**: System MUST log all critical decisions (notification sent/suppressed, state changes)
- **FR-030**: System MUST maintain operation even if individual session monitoring fails
- **FR-031**: System MUST provide health check mechanism for monitoring status
- **FR-032**: System MUST allow configuration of reconnection retry duration and interval for disconnected sessions

### Performance Requirements
- **PR-001**: Notification latency MUST be less than 10 seconds from work completion
- **PR-002**: System MUST support monitoring 10+ concurrent sessions without degradation
- **PR-003**: Telegram command responses MUST complete within 1 second
- **PR-004**: Polling overhead MUST NOT exceed 5% CPU usage per monitored session

### Key Entities

- **Claude Code Session**: A tmux session running Claude Code CLI, identified by session name prefix "claude_", has states (working/waiting/idle/error), tracked for notification delivery
- **Notification State**: Persistent tracking of whether a notification has been sent for a session's current completion event, prevents duplicate notifications
- **Session State**: Current operational state of a Claude session detected from screen content, determines notification eligibility
- **User Command**: Message from Telegram user intended for a specific Claude session, includes target session reference and command text
- **MonitoringThread**: Per-session background thread that polls tmux screen capture and triggers notifications, maintains session-specific state

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked (none remaining)
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed
