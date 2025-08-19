# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the Claude-Ops Telegram Bridge System.

## Core System Principles

- **Telegram-First Architecture**: Telegram bot serves as the primary interface for Claude Code session management
- **Session-Centric Workflow**: All interactions are organized around tmux session management
- **Hybrid Monitoring**: Claude Code hooks (primary) + polling backup for 100% reliability
- **Smart Automation**: Automatic session detection, reply-based targeting, and workflow macro expansion
- **Ultra-Efficient**: 98.9% code reduction through hook-based architecture

## System Overview

Claude-Ops is a Telegram bot that bridges Claude Code sessions with Telegram for remote monitoring and control. The system provides:

- **Session Management**: Monitor multiple Claude Code sessions via tmux
- **Remote Control**: Send commands and prompts to specific sessions via Telegram
- **Workflow Macros**: Pre-defined prompts for structured development workflows (@기획, @구현, @안정화, @배포)
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

### Workflow Macros

- `/remote` - 프롬프트 매크로 리모컨 활성화
- `@기획` - 구조적 탐색 및 계획 수립 프롬프트
- `@구현` - DRY 원칙 기반 체계적 구현 프롬프트  
- `@안정화` - 구조적 지속가능성 검증 프롬프트
- `@배포` - 최종 검증 및 배포 프롬프트

### Usage Patterns

1. **Project Creation**:
   ```
   /new-project my-app → claude-dev-kit installation → Git setup → tmux session
   CLI: claude-ops new-project my-app (identical functionality)
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
   /remote → @기획 → type additional context → send → auto-expands to full prompt
   ```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram      │◄──►│   Claude-Ops    │◄──►│  Claude Code    │
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

- **`claude_ops/telegram/bot.py`** - Main Telegram bot implementation
- **`claude_ops/session_manager.py`** - tmux session management
- **`claude_ops/project_creator.py`** - Unified project creation module
- **`claude_ops/hook_manager.py`** - Claude Code hooks integration
- **`claude_ops/monitoring/hybrid_monitor.py`** - Hybrid monitoring system
- **`claude_ops/utils/session_state.py`** - Session state detection
- **`claude_ops/config.py`** - Configuration management

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

3. **Setup Hook System** (NEW!):
   ```bash
   # Automated setup
   ./scripts/setup-hooks.sh
   
   # Manual setup
   python3 -m claude_ops.hook_manager setup
   ```

4. **Run Bot**:
   ```bash
   uv run python -m claude_ops.telegram.bot
   ```

## Key Features

### 1. Unified Project Creation (NEW!)
- **CLI & Telegram Identical**: `claude-ops new-project` ↔ `/new-project`
- **Remote claude-dev-kit**: Automatic installation from trusted repository
- **Complete Setup**: Git repo, comprehensive .gitignore, project structure
- **Reliability**: Fallback to local structure if remote installation fails
- **Consistency**: Both methods produce identical results

### 2. Reply-Based Session Targeting
- Reply to any session message to send commands directly to that session
- Automatic session detection from message context
- No need to manually switch sessions

### 3. Macro Expansion System
- Type `@기획` and additional text
- System automatically expands to full structured prompt
- Supports combined workflows: `@기획 today we need to...`

### 3. Hybrid Monitoring System (NEW!)
- **Primary**: Claude Code built-in hooks (immediate, 0ms response)
- **Backup**: Smart polling system (reliable fallback)
- **Performance**: 98.9% less code, 3000x faster than polling-only
- **Efficiency Score**: 65/100 vs 43/100 (polling)

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

## Best Practices

1. **Use descriptive session names** that reflect project/task context
2. **Leverage reply-based targeting** for efficient session communication
3. **Use workflow macros** for consistent development process
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