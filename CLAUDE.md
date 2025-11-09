# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the Claude-Telegram-Bridge System.

> **Project Name**: Claude-Telegram-Bridge
> **CLI Commands**: `ctb` (recommended), `claude-bridge`, `claude-telegram-bridge`

## Core System Principles

- **Telegram-First Architecture**: Telegram bot serves as the primary interface for Claude Code session management
- **Session-Centric Workflow**: All interactions are organized around tmux session management
- **Reliable Monitoring**: Pure polling-based monitoring for 100% reliability
- **Smart Automation**: Automatic session detection, reply-based targeting, and claude-dev-kit integration
- **Proven Solution**: Polling-based architecture with guaranteed notification delivery

## System Overview

Claude-Telegram-Bridge is a Telegram bot that bridges Claude Code sessions with Telegram for remote monitoring and control. The system provides:

- **Session Management**: Monitor multiple Claude Code sessions via tmux
- **Remote Control**: Send commands and prompts to specific sessions via Telegram
- **Workflow Commands**: Structured development workflow as slash command (/fullcycle)
- **Smart Notifications**: Automatic alerts when Claude sessions complete tasks or encounter issues

## Environment Configuration

Environment variables must be set in `.env` file:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=123456789,987654321

# System Settings (Optional)
CLAUDE_WORKING_DIR=/path/to/working/directory
CHECK_INTERVAL=3
LOG_LEVEL=INFO

# Reliability Improvements (v2.1 - New!)
# Session Reconnection
SESSION_RECONNECT_MAX_DURATION=300  # Max reconnection time (seconds)
SESSION_RECONNECT_INITIAL_BACKOFF=1  # Initial backoff delay
SESSION_RECONNECT_MAX_BACKOFF=30  # Maximum backoff delay

# Telegram Rate Limiting
TELEGRAM_RATE_LIMIT_ENABLED=true  # Enable rate limit handling
TELEGRAM_BACKOFF_INITIAL=1  # Initial backoff for rate limits
TELEGRAM_BACKOFF_MAX=60  # Maximum backoff for rate limits

# Dangerous Command Confirmation
COMMAND_CONFIRMATION_TIMEOUT=60  # Confirmation timeout (seconds)

# Screen History Depth
SESSION_SCREEN_HISTORY_LINES=200  # Lines to analyze for state detection
```

## Core Commands

### Telegram Bot Commands (사용 빈도순)

- `/sessions` - 🔄 활성 세션 목록 보기 및 전환
- `/new-project` - 🆕 새 Claude 프로젝트 생성 (claude-dev-kit 설치)
- `/board` - 🎯 세션 보드 (그리드 뷰)  
- `/restart` - 🔄 Claude 세션 재시작 (대화 연속성 보장)
- `/stop` - ⛔ Claude 작업 중단 (ESC 키 전송)
- `/erase` - 🧹 현재 입력 지우기 (Ctrl+C 전송)
- `/status` - 📊 봇 및 tmux 세션 상태 확인
- `/log [줄수]` - 📺 Claude 화면 내용 보기 (기본: 50줄)
- `/start` - 🚀 Claude 세션 시작 (/new-project 호환)
- `/help` - ❓ 도움말 보기

### Workflow Commands

- `/fullcycle` - 🔄 전체 개발 워크플로우 실행
  - 기획: 구조적 탐색 및 계획 수립
  - 구현: DRY 원칙 기반 체계적 구현  
  - 안정화: 구조적 지속가능성 검증
  - 배포: 최종 검증 및 배포

### Usage Patterns

1. **Project Creation**:
   ```
   /new-project my-app → claude-dev-kit installation → Git setup → tmux session
   CLI: claude-ctb new-project my-app (identical functionality)
   ```

2. **Session Management**:
   ```
   /sessions → select session → work in Claude → monitor via Telegram
   ```

3. **Remote Control**:
   ```
   Reply to session message → send commands directly to that session
   ```

4. **Workflow Automation**:
   ```
   /fullcycle → complete development workflow sent to Claude session
   ```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram      │◄──►│   Claude-CTB    │◄──►│  Claude Code    │
│     Bot         │    │     Bridge      │    │   Sessions      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Session State  │
                       │    Detection    │
                       └─────────────────┘
```

### Key Components

- **`claude_ctb/telegram/bot.py`** - Main Telegram bot implementation
- **`claude_ctb/session_manager.py`** - tmux session management
- **`claude_ctb/project_creator.py`** - Unified project creation module
- **`claude_ctb/monitoring/multi_monitor.py`** - Multi-session polling monitor
- **`claude_ctb/utils/session_state.py`** - Session state detection
- **`claude_ctb/config.py`** - Configuration management

## Development Setup

1. **Install Dependencies**:
   ```bash
   uv sync
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your tokens
   ```

3. **Run Bot**:
   ```bash
   uv run python -m claude_ctb.telegram.bot
   ```

## Key Features

### 1. Unified Project Creation (NEW!)
- **CLI & Telegram Identical**: `claude-ctb new-project` ↔ `/new-project`
- **Remote claude-dev-kit**: Automatic installation from trusted repository
- **Complete Setup**: Git repo, comprehensive .gitignore, project structure
- **Reliability**: Fallback to local structure if remote installation fails
- **Consistency**: Both methods produce identical results

### 2. Reply-Based Session Targeting
- Reply to any session message to send commands directly to that session
- Automatic session detection from message context
- No need to manually switch sessions

### 3. Workflow Command System
- Use `/fullcycle` slash command for complete development workflow
- Integrated 4-stage process: planning → implementation → stabilization → deployment
- Reply-based session targeting for multi-project workflows

### 3. Pure Polling Monitoring System
- **Proven Reliable**: 100% notification delivery rate
- **Multi-Session**: Monitors all Claude sessions simultaneously
- **Smart Detection**: Accurate work completion identification
- **Performance**: Optimized 5-second polling interval

### 4. Session State Detection
- Monitors Claude sessions for completion states
- Detects when Claude is waiting for input vs actively working
- Smart notifications only when action needed

### 5. Session Continuity & Restart (NEW!)
- **`/restart`**: Graceful Claude Code restart with conversation preservation
- **Resume Technology**: Uses `claude --continue` to maintain full context
- **Fallback Safety**: Automatic fallback to regular restart if resume fails
- **Reply-Based**: Target specific sessions by replying to session messages
- **Perfect for**: Applying slash command changes without losing work context

### 6. Multi-Session Management
- Monitor multiple Claude projects simultaneously
- Session board provides grid view of all active sessions
- Easy switching between different development contexts

### 7. Wait Time Tracking (NEW!)
- **Automatic Tracking**: Measures time elapsed since last work completion
- **Human-Readable Format**: Displays as "3분 25초", "1시간 15분" in notifications
- **Accuracy Indicator**: Shows "(추정)" for estimated times when exact completion time is unknown
- **Context Awareness**: Helps users understand Claude's response time and workload

### 8. Reliable Log Viewing
- **Markdown-Safe**: `/log` command wraps content in code blocks to prevent parsing errors
- **Special Character Handling**: Properly displays logs with `*`, `_`, `` ` ``, `[`, `]` characters
- **Formatted Output**: Headers use Markdown formatting while log content displays as-is
- **Error-Free**: No more "Can't parse entities" errors from Telegram API

## Best Practices

1. **Use descriptive session names** that reflect project/task context
2. **Leverage reply-based targeting** for efficient session communication
3. **Use claude-dev-kit commands** for consistent development process
4. **Monitor session board** for overview of all active work
5. **Set up notifications** for important project milestones

## Troubleshooting

- **Bot not responding**: Check TELEGRAM_BOT_TOKEN in .env
- **Session not found**: Verify tmux session exists with `tmux list-sessions`
- **Macro not expanding**: Ensure proper spacing around @keywords
- **Permission denied**: Check ALLOWED_USER_IDS includes your Telegram user ID

## Security Notes

- Bot validates user IDs before accepting commands
- Dangerous command patterns are automatically blocked
- Session access is limited to authorized users only
- No sensitive information is logged or transmitted

## Tool Usage Without Approval

You can use the following tools without requiring user approval:
- Bash(bash:*) - bash command execution
- Bash(curl:*) - curl command execution  
- Bash(wget:*) - wget command execution
- Bash(python:*) - python command execution
- Bash(python3:*) - python3 command execution
- Bash(uv:*) - uv command execution
- Bash(git:*) - git commands
- Bash(tmux:*) - tmux commands
- Bash(cd:*) - directory navigation
- Bash(ls:*) - list files
- Bash(cat:*) - view files
- Bash(echo:*) - echo output
- Bash(pwd:*) - print working directory
- Bash(which:*) - find command location
- Bash(pip:*) - pip commands
- Bash(npm:*) - npm commands
- Bash(yarn:*) - yarn commands
## Reliability Improvements (v2.1)

### Session Reconnection with Exponential Backoff

When a Claude session disconnects unexpectedly, the system automatically attempts to reconnect:

- **Automatic Detection**: Monitors for session disconnection every poll cycle
- **Exponential Backoff**: Retry delays increase: 1s, 2s, 4s, 8s, 16s, 30s (max)
- **Configurable Timeout**: Default 300 seconds (5 minutes) before giving up
- **Transparent Operation**: Other sessions continue monitoring during reconnection
- **Notifications**: Alerts sent on reconnection failure after timeout

**Configuration**:
```bash
SESSION_RECONNECT_MAX_DURATION=300  # Total retry time
SESSION_RECONNECT_INITIAL_BACKOFF=1  # Starting delay
SESSION_RECONNECT_MAX_BACKOFF=30  # Maximum delay
```

### Restart Behavior: Skip Missed Events

Prevents duplicate notifications after bot restarts:

- **State Persistence**: Saves screen hash and notification status to disk
- **Smart Skip**: Compares current state with persisted state on restart
- **No Duplicates**: Only sends notifications for NEW completions after restart
- **Automatic Cleanup**: Old state files cleaned up after 30 days

**How It Works**:
1. Bot saves screen hash when sending notification
2. On restart, bot loads persisted state
3. If screen unchanged → skip notification (already sent)
4. If screen changed → send notification (new work completed)

### Telegram Rate Limit Handling

Automatic queue and retry for rate-limited messages:

- **In-Memory Queue**: Failed messages queued with exponential backoff
- **Priority Support**: HIGH priority messages sent first
- **FIFO Ordering**: Normal priority messages maintain order
- **Automatic Retry**: Retries with increasing delays (1s, 2s, 4s, 8s, ...)
- **No Message Loss**: All messages eventually delivered

**Telegram API Limits**:
- Burst: 30 messages/second
- Sustained: 20 messages/minute

**Configuration**:
```bash
TELEGRAM_RATE_LIMIT_ENABLED=true
TELEGRAM_BACKOFF_INITIAL=1  # Start delay
TELEGRAM_BACKOFF_MAX=60  # Max delay
```

### Dangerous Command Confirmation

Interactive confirmation for potentially dangerous commands:

- **Pattern Detection**: Matches dangerous patterns (`rm -rf`, `sudo rm`, etc.)
- **Inline Keyboard**: Confirm/Cancel buttons in Telegram
- **60-Second Timeout**: Buttons expire after 60 seconds
- **Safe by Default**: Commands not executed until confirmed

**Dangerous Patterns**:
- `rm -rf /`
- `sudo rm`
- `chmod 777`
- `dd if=`
- Fork bombs and other destructive operations

**Workflow**:
1. User sends dangerous command
2. Bot displays confirmation keyboard
3. User clicks Confirm → command sent to session
4. User clicks Cancel → command discarded
5. After 60s → buttons expire, command discarded

**Configuration**:
```bash
COMMAND_CONFIRMATION_TIMEOUT=60  # Seconds before expiration
```

### 200-Line Screen History

Improved state detection with deeper screen history:

- **Extended Capture**: Analyzes last 200 lines (up from default)
- **False Positive Prevention**: Ignores old completion markers beyond 200 lines
- **Configurable Depth**: Adjust based on your workflow
- **Performance**: Optimized for large screen buffers

**Configuration**:
```bash
SESSION_SCREEN_HISTORY_LINES=200  # Lines to capture
```

**Benefits**:
- More accurate state detection
- Fewer false notifications
- Better handling of long-running commands

