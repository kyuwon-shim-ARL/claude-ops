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

### Sub-Agent 활용 가이드

Claude Code의 Task 도구를 활용하여 복잡한 작업을 효율적으로 처리하세요:

#### 언제 사용하나요?
- **대규모 검색**: 전체 코드베이스에서 특정 패턴 찾기
- **병렬 작업**: 여러 파일/모듈 동시 분석
- **복잡한 리팩토링**: 다수 파일의 일관된 변경

#### 사용 예시
```python
# 코드베이스 전체에서 Notion API 호출 찾기
Task(
    description="Find all Notion API usage",
    prompt="Search for all files using notion-client and analyze the API patterns",
    subagent_type="general-purpose"
)

# 여러 모듈 동시 문서화
Task(
    description="Document all modules",
    prompt="Create comprehensive documentation for each module in src/",
    subagent_type="general-purpose"
)
```

#### 팁
- Sub-Agent는 독립적인 컨텍스트를 가지므로 명확한 지시사항 제공
- 검색 작업은 Sub-Agent가 더 효율적으로 처리
- 결과는 메인 대화로 돌아와서 요약됨

For detailed workflow information, see `/slash_commands/` directory.