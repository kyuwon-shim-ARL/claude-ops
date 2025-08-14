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
# Claude Code 4단계 개발 워크플로우

## 개발 워크플로우

이 프로젝트는 4단계 키워드 기반 개발을 사용합니다:
- **"기획"** → Structured Discovery & Planning Loop:
  - 탐색: 전체 구조 파악, As-Is/To-Be/Gap 분석
  - 계획: MECE 기반 작업분해, 우선순위 설정
  - 수렴: 탐색↔계획 반복 until PRD 완성
- **"구현"** → Implementation with DRY:
  - 기존 코드 검색 → 재사용 → 없으면 생성
  - TodoWrite 기반 체계적 진행
  - 단위 테스트 & 기본 검증
- **"안정화"** → **Structural Sustainability Protocol v2.0**:
  - 구조 스캔: 전체 파일 분석, 중복/임시 파일 식별
  - 구조 최적화: 디렉토리 정리, 파일 분류, 네이밍 표준화
  - 의존성 해결: Import 수정, 참조 오류 해결
  - 통합 테스트: 모듈 검증, API 테스트, 시스템 무결성
  - 문서 동기화: CLAUDE.md 반영, README 업데이트
  - 품질 검증: MECE 분석, 성능 벤치마크 (ZERO 이슈까지)
- **"배포"** → Deployment: 최종검증 + 구조화커밋 + 푸시 + 태깅

## 구현 체크리스트

### 구현 전 확인사항
- ☐ **기존 코드 검색**: 비슷한 기능이 이미 있는가?
- ☐ **재사용성 검토**: 이 기능을 다른 곳에서도 사용할 수 있는가?
- ☐ **중앙화 고려**: 공통 모듈로 배치할가?
- ☐ **인터페이스 설계**: 모듈 간 명확한 계약이 있는가?
- ☐ **테스트 가능성**: 단위 테스트하기 쉬운 구조인가?

### 코드 품질 체크
- ☐ **DRY 원칙**: 코드 중복이 없는가?
- ☐ **Single Source of Truth**: 동일 기능이 여러 곳에 있지 않는가?
- ☐ **의존성 최소화**: 불필요한 결합이 없는가?
- ☐ **명확한 네이밍**: 기능을 잘 나타내는 이름인가?

## 구조적 지속가능성 원칙

### 📁 Repository 구조 관리
- **Root 정리**: 필수 진입점만 유지, 도구는 scripts/
- **계층구조**: 기능별 적절한 디렉토리 배치
- **임시 파일 관리**: *.tmp, *.bak 등 정기적 정리

### 🔄 예방적 관리 시스템
**자동 트리거 조건:**
- 루트 디렉토리 파일 20개 이상
- 임시 파일 5개 이상
- Import 오류 3개 이상
- 매 5번째 커밋마다

## important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
