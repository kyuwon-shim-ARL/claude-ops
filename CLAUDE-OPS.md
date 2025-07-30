# CLAUDE-OPS.md

This file contains Claude-Ops utility-specific instructions. Include this in your main CLAUDE.md file.

## Claude-Ops Integration

Claude-Ops provides automated workflow utilities for Claude Code. To use these features:

### Available Commands

#### Notion Integration
- `/project-plan <file>`: Create Project → Epic → Task hierarchy in Notion
- `/task-start <TID>`: Start Notion task and create Git branch
- `/task-archive [TID]`: Export conversation and create structured summary
- `/task-finish <TID> --pr [--auto-merge]`: Complete task with PR creation
- `/task-publish <TID>`: Publish completed task knowledge to Knowledge Hub

#### Status Management
- Status files are automatically managed in `/tmp/claude_work_status*`
- Telegram notifications are sent on task completion

### Configuration

Ensure your `.env` file contains all required environment variables:
```
# Notion Integration
NOTION_API_KEY=
NOTION_PROJECTS_DB_ID=
NOTION_TASKS_DB_ID=
NOTION_KNOWLEDGE_HUB_ID=

# GitHub Integration
GITHUB_PAT=
GITHUB_REPO_OWNER=
GITHUB_REPO_NAME=

# Telegram Integration (Optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALLOWED_USER_IDS=
```

For detailed workflow information, see `/slash_commands/` directory.