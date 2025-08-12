# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- 
IMPORTANT: This is a template CLAUDE.md file. For your project-specific instructions:
1. Copy this file and modify for your project needs
2. Keep Claude-Ops utility commands by including: 
   {% include "CLAUDE-OPS.md" %} or manually copy relevant sections
3. Replace the sections below with your project-specific guidance
-->

## Core System Principles (피드백 반영 완료)

- **Dual Architecture**: Notion is the strategic headquarters (Studio) managing "why" and "what", while Git/Terminal is the development workshop managing "how"
- All work starts from Notion `Task` tickets; all Git branches must be linked to Notion Task IDs
- Git branches follow naming convention: `feature/TID-XXXXXXXX-...` using real Notion TIDs
- Pull Requests are formal technical reports, not just code submissions
- **Output files follow the 'Output Management Principles' and must be managed via Git-LFS or shared NAS, ensuring code-result connectivity**
- **All exploration process records (AI conversation logs) must be archived in Notion Task anchor pages as STRUCTURED SUMMARIES - this serves as the research 'black box' for reproducibility and debugging**
- Knowledge follows the '4-stage Knowledge Creation Principles' detailed in `prompts/1_philosophy_knowledge_creation.md`. The `task publish` command executes the final stage

## 🔧 피드백 반영 개선사항

### 1. Task 상태 관리 개선
- `/task-finish` 명령어가 Notion 상태를 "Done"으로 정확히 업데이트
- 실패 시 자동 재시도 및 오류 보고 포함
- Notion API 호출 검증 로직 강화

### 2. 대화 아카이빙 개선  
- Raw 대화 로그 대신 **구조화된 요약** 생성
- 주요 작업 내용, 사용자 요청사항, 기술적 세부사항 자동 추출
- 가독성 높은 마크다운 형식으로 Notion에 저장

### 3. 완전 자동화 워크플로우
- `--auto-merge` 플래그로 PR 생성 → 자동 병합 → 브랜치 정리
- Squash merge로 깔끔한 커밋 히스토리 유지
- 실패 시 수동 모드로 fallback

### 4. 구체적 산출물 정의
- 각 Task에 명확한 deliverable과 success criteria 포함
- PRD와 완전 일치하는 Epic/Task 구조
- 측정 가능한 성과 지표 (정확도, 성능, 테스트 통과율 등)

## API and Tool Information

Available tools: Notion API, GitHub API, local Git CLI, GitHub CLI (`gh`), and **Git-LFS CLI**

**Environment Configuration:**
Environment variables must be set in `.env` file (copy from `.env.example`):
- `NOTION_API_KEY`: Notion integration token
- `NOTION_TASKS_DB_ID`: Tasks database ID  
- `NOTION_PROJECTS_DB_ID`: Projects database ID
- `NOTION_KNOWLEDGE_HUB_ID`: Knowledge Hub page ID
- `GITHUB_PAT`: GitHub Personal Access Token
- `GITHUB_REPO_OWNER`: GitHub repository owner
- `GITHUB_REPO_NAME`: GitHub repository name

## Command Structure

### Core Workflow Commands (Claude Code Slash Commands) - 피드백 반영 완료

- `/project-plan <file>`: Create Project → Epic → Task hierarchy in Notion from proposal documents
  - **개선**: 구체적 산출물과 성공기준 포함한 Task 생성
  - **예시**: `/project-plan docs/proposals/2025-07-24_improved-data-analysis-pipeline.md`

- `/task-start <TID>`: Start Notion task and create Git branch using real Notion TID  
  - **개선**: UUID 자동 해석 및 브랜치 명명 규칙 적용
  - **예시**: `/task-start 23a5d36f-fc73-81ff-8ced-f357b6b7a71b`

- `/task-archive [TID]`: Export conversation and create STRUCTURED SUMMARY in Notion Task page
  - **개선**: Raw 로그 대신 구조화된 요약 생성 (주요 작업, 사용자 요청, 기술 세부사항)
  - **자동 감지**: Git 브랜치에서 TID 자동 추출
  - **예시**: `/task-archive` (현재 브랜치에서 자동)

- `/task-finish <TID> --pr [--auto-merge]`: Complete task with PR creation and optional auto-merge
  - **신규**: `--auto-merge` 플래그로 완전 자동화 (PR 생성 → 병합 → 브랜치 정리)
  - **개선**: Notion 상태 업데이트 검증 및 오류 처리 강화
  - **예시**: `/task-finish <TID> --pr --auto-merge` (권장)

- `/task-publish <TID>`: Publish completed task knowledge to Knowledge Hub

**🚀 피드백 반영 핵심 개선사항:**
- **완전 자동화**: `--auto-merge`로 개발자 개입 최소화
- **구조화된 아카이빙**: 가독성 높은 대화 요약
- **정확한 상태 관리**: Notion API 호출 검증 및 재시도
- **구체적 산출물**: 각 Task에 명확한 deliverable 정의
- **즉시 사용 가능**: QUICK_START.md로 5분 내 설정 완료

### Pipeline Execution Commands
- `python main.py workflow-a --fastq-dir <dir> --reference-genome <file> --metadata <file>`: Run FASTQ-based pipeline
- `python main.py workflow-b --count-table <file> --metadata <file> --annotation <file>`: Run count table-based pipeline
- `python main.py results --outdir <dir>`: List and summarize pipeline results

### Development Commands

#### Python Development
```bash
# Install dependencies
uv sync

# Run the main application
python main.py

# Run with uv
uv run python main.py
```

#### Optional: Domain-Specific Tools

For computational workflows (when using Nextflow):
```bash
# Run pipeline locally
nextflow run src/main.nf -profile local

# Run on cluster
nextflow run src/main.nf -profile cluster

# Run with custom output directory
nextflow run src/main.nf --output_dir /path/to/results
```

## Claude Code Optimization Strategies

### 🚀 Tool Usage Optimization
- **Use Task tool for**: Complex analysis, multi-file searches, architectural reviews
- **Use MultiEdit for**: Batch refactoring, consistent style changes, pattern replacements  
- **Use Glob + batch Read**: When analyzing multiple files with similar patterns
- **Combine tools strategically**: Glob → Task analysis → MultiEdit implementation

### 📊 Context Management Best Practices
- **Batch similar operations**: Read multiple files in one go when possible
- **Use Task tool for heavy lifting**: Delegate complex analysis to reduce main context usage
- **Prioritize MultiEdit**: Single tool call vs multiple Edit calls saves significant tokens
- **Strategic file reading**: Read only necessary sections using offset/limit parameters

### ⚡ Performance Optimization Patterns
```python
# Efficient pattern: Batch processing
files = Glob("**/*.py")
for batch in chunk_files(files, 5):
    batch_analysis = Task(f"Analyze these {len(batch)} files for issues")
    apply_fixes_with_multiedit(batch, batch_analysis.fixes)

# Efficient pattern: Targeted operations  
critical_files = Glob("**/telegram/*.py") 
performance_issues = Task("Find performance bottlenecks in telegram modules")
MultiEdit(critical_files, performance_issues.suggested_changes)
```

## Architecture and Structure

### Directory Structure
- `CLAUDE.md`: Central guidance file for Claude Code automation
- `slash_commands/`: Claude Code slash command specifications
  - `project-plan.md`: `/project-plan` command specification
  - `task-start.md`: `/task-start` command specification  
  - `task-archive.md`: `/task-archive` command specification
- `src/`: Contains workflow management and optional domain-specific tools
  - `workflow_manager.py`: Core Notion-Git integration system
  - `workflows/`: Optional domain-specific pipeline implementations
  - `modules/`: Optional modular processes for domain workflows
  - `bin/`: Optional analysis scripts
  - `configs/`: Environment-specific configurations
- `data/`: Input data organized by domain type (optional)
- `prompts/`: System prompt templates for AI workflow automation
- `docs/`: Project documentation including PRDs and proposals
- `pyproject.toml`: Python project configuration with dependencies
- `.env`: Environment variables for API tokens and database IDs
- `.env.example`: Template for environment configuration

### Key Dependencies
- `notion-client>=2.4.0`: For Notion API integration
- `pygithub>=2.6.1`: For GitHub API operations
- `python-dotenv>=1.0.0`: For environment variable management from .env files
- Git-LFS: For managing large result files
- Additional tools may include domain-specific workflow engines (e.g., Nextflow for computational pipelines)

## Output File Management Principles

All outputs follow these management principles:

### A. Git-LFS Management
- **Definition**: Selected core final outputs for papers, reports, PRs
- **Characteristics**: Code-coupled version control essential
- **Examples**: Final result graphs (`final_plot.png`), key statistics (`summary_stats.csv`), final models (`final_model.h5`)
- **Execution**: Use `task add-result` command for Git-LFS tracking with meaningful commit messages

### B. Shared NAS Management  
- **Definition**: Large-scale intermediate/full outputs too large or low-priority for Git
- **Characteristics**: Accessibility and sharing prioritized over version control
- **Examples**: Complete computation `results/` folders, large dataset files, processed outputs
- **Execution**: Configure computation outputs to shared NAS paths initially; record NAS paths as text links in Notion Task anchor pages

### C. Git Exclusions
- **Definition**: Temporary, reproducible files not worth preserving
- **Examples**: Computation work directories, local test logs, cache files
- **Execution**: Specify in project `.gitignore` to completely exclude from Git tracking

## Work Unit Definitions

모든 작업 단위는 **Project → Epic → Task**의 명확한 위계를 따릅니다. `/project-plan` 명령어 실행 시, `prompts/2_create_project_plan.md`에 명시된 기준을 따라 세 단위를 구분하고 페이지 내용을 구성해야 합니다.

- **Project:** **전략적 'Why'에 답하는 독립적인 가치 단위입니다.** (예: 논문 한 편, 제품 출시)
- **Epic:** **Project를 구성하는 기능적 'What'의 묶음입니다.** (예: Figure 1 제작, 인증 시스템 구축)
- **Task:** **Epic을 실행하는 구체적 'How'의 단위입니다.** (예: 특정 스크립트 작성, 데이터 검증)

### Epic Criteria (2+ criteria required)
- **Time**: 2+ weeks completion time?
- **Collaboration**: Multiple assignees needed?
- **Value**: Independent value delivery?
- **Structure**: Clear subdivision into multiple tasks?
- **Communication**: Separate reporting/sharing needed?

### Task Criteria
- **Definition**: Concrete execution units completable by one person within days
- **Page Content**: Include 'Work Objectives', 'Reference Materials', and 'Exploration Journal & Outputs' sections

## Knowledge Creation Workflow

The system follows a 4-stage knowledge creation process detailed in `prompts/1_philosophy_knowledge_creation.md`:

1. **Anchoring (Raw Archive)**: All raw exploration information in Notion Task pages - **`/export` command conversation logs must be preserved in toggle blocks**
2. **AI Summary (1st Restructuring)**: Topic and logic-based information structuring  
3. **Personal Digestion (Full-Stack CREATE)**: Individual insight development and knowledge connection
4. **Team Publication (Core CREATE)**: Final knowledge sharing in Notion Knowledge Hub

### Execution Environment Configuration
When using computational workflow tools, typical execution profiles include:
- `local`: For development and testing (limited resources)  
- `cluster`: For production runs on distributed systems

Always ensure terminal conversation logs are exported and archived in Notion Task toggle blocks using the `/task-archive` slash command.