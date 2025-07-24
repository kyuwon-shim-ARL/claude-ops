# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Role and Identity

You are an automation agent for the 'Notion-Git dual-space system' that integrates Claude Code, Notion, and Git for research project workflows. All your actions must follow the core system principles below.

## Core System Principles

- **Dual Architecture**: Notion is the strategic headquarters (Studio) managing "why" and "what", while Git/Terminal is the development workshop managing "how"
- All work starts from Notion `Task` tickets; all Git branches must be linked to Notion Task IDs
- Git branches follow naming convention: `feature/TID-XXXXXXXX-...` using real Notion TIDs
- Pull Requests are formal technical reports, not just code submissions
- **Output files follow the 'Output Management Principles' and must be managed via Git-LFS or shared NAS, ensuring code-result connectivity**
- **All exploration process records (AI conversation logs) must be archived in Notion Task anchor pages as toggle blocks - this serves as the research 'black box' for reproducibility and debugging**
- Knowledge follows the '4-stage Knowledge Creation Principles' detailed in `prompts/1_philosophy_knowledge_creation.md`. The `task publish` command executes the final stage

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

### Core Workflow Commands (Claude Code Slash Commands)
- `/project-plan <file>`: Create Project → Epic → Task hierarchy in Notion from proposal documents
- `/task-start <TID>`: Start Notion task and create Git branch using real Notion TID
- `/task-archive [TID]`: Export conversation log using `/export` and archive in Notion Task anchor page (auto-detects TID from Git branch if not provided)
- `/task-finish <TID> --pr`: Complete task, create PR, and update Notion status to Done
- `/task-publish <TID>`: Publish completed task knowledge to Knowledge Hub

**Key Improvements:**
- **Claude Code Native**: No separate `python main.py` execution needed
- **Notion TID Direct Usage**: Use real Notion Task IDs instead of mapping files
- **Task Ordering System**: Epic 1,2,3... Task 1.1,1.2,1.3... for clear priority
- **Auto-Detection**: `/task-archive` can auto-detect current task from Git branch name

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

When executing `/project-plan` commands, follow `prompts/2_create_project_plan.md` criteria for distinguishing Epics vs Tasks and structuring page content.

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