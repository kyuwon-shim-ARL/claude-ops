# Claude-Ops 템플릿 사용 가이드

이 레포지토리는 **Claude Code - Notion - Git 통합 워크플로우 시스템**의 템플릿입니다. 연구 프로젝트를 체계적으로 관리하고 AI와 협업할 수 있는 환경을 제공합니다.

## 🚀 빠른 시작

### 1. 템플릿 복사 및 설정

```bash
# 1. 이 템플릿을 새 레포지토리로 복사
git clone https://github.com/your-username/claude-ops.git my-research-project
cd my-research-project

# 2. 의존성 설치
uv sync

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 실제 API 키와 DB ID 입력
```

### 2. Notion 설정

1. **Notion Integration 생성**
   - [Notion Developers](https://www.notion.so/my-integrations)에서 새 Integration 생성
   - API 키를 `.env` 파일의 `NOTION_API_KEY`에 설정

2. **데이터베이스 생성**
   - Projects 데이터베이스 생성 (Epic 관리용)
   - Tasks 데이터베이스 생성 (Task 관리용)  
   - Knowledge Hub 페이지 생성 (지식 공유용)
   - 각 ID를 `.env` 파일에 설정

3. **데이터베이스 권한 설정**
   - 생성한 데이터베이스들을 Integration과 공유

### 3. GitHub 설정

```bash
# GitHub Personal Access Token 생성
# Repo 권한이 있는 PAT를 .env의 GITHUB_PAT에 설정
```

## 📊 도메인별 예시 활용

### Data Science 프로젝트
메인 템플릿이 일반적인 데이터 사이언스 프로젝트 구조입니다.

```bash
# 데이터 분석 파이프라인 예시 실행
python main.py data-analysis --input-data data/sample_data.csv --metadata data/metadata.csv
```

### Bioinformatics 프로젝트  
`docs/examples/bioinformatics/` 폴더의 예시를 참고하세요.

```bash
# 바이오인포매틱스 예시를 메인으로 복사
cp -r docs/examples/bioinformatics/workflows/* src/workflows/
cp -r docs/examples/bioinformatics/data/* data/
```

## 🔄 워크플로우 사용법

### 1. 프로젝트 계획 생성
```bash
python main.py project-plan --source docs/proposals/your-proposal.md
```

### 2. 태스크 시작
```bash
python main.py task-start T-001
# 자동으로 feature/T-001 브랜치 생성 및 전환
```

### 3. 작업 진행
```bash
# 일반적인 개발 작업 수행
git add .
git commit -m "T-001: 데이터 전처리 모듈 구현"
```

### 4. 대화 아카이빙
```bash
# Claude Code에서 /export 실행 후
python main.py task-archive T-001
```

### 5. 태스크 완료
```bash
python main.py task-finish T-001 --pr
# PR 생성 및 Notion 상태 업데이트
```

### 6. 지식 발행
```bash
python main.py task-publish T-001
# Knowledge Hub에 최종 지식 문서 생성
```

## 🛠 커스터마이징

### 프로젝트 구조 수정
- `src/workflows/`: 분석 파이프라인 수정
- `src/modules/`: 개별 분석 모듈 수정
- `data/`: 프로젝트 데이터로 교체
- `docs/proposals/`: 실제 프로젝트 제안서로 교체

### 워크플로우 설정 수정
- `src/workflow_manager.py`: 태스크 생성 로직 커스터마이징
- `prompts/`: AI 상호작용 프롬프트 수정

## 📁 템플릿 구조

```
claude-ops/
├── main.py                    # 통합 워크플로우 시스템
├── src/
│   ├── workflow_manager.py    # Notion-Git 통합 핵심
│   ├── workflows/            # 데이터 분석 파이프라인 (커스터마이징 대상)
│   └── modules/              # 분석 모듈들 (커스터마이징 대상)
├── data/                     # 샘플 데이터 (교체 대상)
├── docs/
│   ├── proposals/           # 프로젝트 제안서 (교체 대상)
│   └── examples/            # 도메인별 예시
│       ├── bioinformatics/  # 바이오인포매틱스 예시
│       └── data-science/    # 데이터 사이언스 예시
├── prompts/                 # AI 워크플로우 프롬프트
├── .env.example            # 환경 변수 템플릿
└── CLAUDE.md               # Claude Code 가이드
```

## 💡 팁

1. **프로젝트 시작 시**: 먼저 `docs/proposals/`에 프로젝트 제안서를 작성한 후 `project-plan` 명령어 실행
2. **정기적 아카이빙**: 중요한 탐색 과정은 `/export` → `task-archive`로 보존
3. **도메인 특화**: `docs/examples/`의 예시를 참고하여 자신의 연구 분야에 맞게 커스터마이징
4. **팀 협업**: Notion 데이터베이스를 팀원들과 공유하여 협업 환경 구축

## 🚨 주의사항

- `.env` 파일의 API 키는 절대 git에 커밋하지 마세요
- 대용량 데이터는 Git-LFS 또는 별도 스토리지 사용
- Notion 데이터베이스 스키마 변경 시 `workflow_manager.py`도 함께 수정

---

이 템플릿을 사용하여 체계적이고 재현 가능한 연구 환경을 구축하세요! 🎯