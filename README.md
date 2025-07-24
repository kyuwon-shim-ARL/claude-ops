# 🚀 Claude Code 완전 자동화 워크플로우

**5분 설정으로 즉시 사용 가능한 연구 프로젝트 자동화 시스템**

[![Setup Time](https://img.shields.io/badge/Setup-5_minutes-green)](./QUICK_START.md)
[![Auto Merge](https://img.shields.io/badge/Workflow-Fully_Automated-blue)](#자동화-기능)
[![LFS Tracking](https://img.shields.io/badge/Storage-Git_LFS-orange)](#git-lfs-자동-추적)

이 repository는 Claude Code와 Notion, GitHub을 연동한 **완전 자동화 연구 워크플로우**를 제공합니다.

## ⚡ 빠른 시작

**5분 만에 설정하고 바로 사용하세요:**

```bash
# 1. Clone & 의존성 설치
git clone <your-repo>
cd MC_test_ops
uv sync

# 2. 환경 설정
cp .env.example .env
# .env 파일 수정 (Notion API, GitHub PAT)

# 3. 첫 프로젝트 생성
/project-plan docs/proposals/2025-07-24_improved-data-analysis-pipeline.md

# 4. 작업 시작!
/task-start <생성된-TID>
# ... 작업 수행 ...
/task-finish <TID> --pr --auto-merge  # 완전 자동화!
```

**👉 [상세 설정 가이드](./QUICK_START.md)**

## 🎯 핵심 특징

### ✨ 완전 자동화 워크플로우
- **자동 PR 생성 & 병합**: `--auto-merge` 플래그로 개발자 개입 최소화
- **자동 브랜치 정리**: Merge 후 로컬/원격 브랜치 자동 삭제
- **자동 상태 동기화**: Notion Task 상태 실시간 업데이트

### 📊 구조화된 문서화
- **대화 요약**: Raw 로그 대신 읽기 쉬운 구조화된 요약
- **구체적 산출물**: 각 Task에 명확한 deliverable과 success criteria
- **자동 아카이빙**: 모든 탐색 과정이 Notion에 체계적으로 보관

### 🗂️ Git LFS 자동 추적
- **결과물 버전 관리**: `*.txt`, `*.csv`, `*.tsv` 파일 자동 LFS 추적
- **대용량 파일 지원**: 분석 결과, 모델, 데이터셋 등 효율적 관리
- **코드-결과 연결성**: Git 히스토리와 결과물 완벽 연동

## 🏗️ 시스템 아키텍처

### 🏛️ Notion (전략 본부)
- **프로젝트 계획**: Epic → Task 계층 구조
- **진행 상황 추적**: 실시간 상태 업데이트
- **지식 아카이브**: 구조화된 탐색 과정 기록

### 🛠️ Git & Terminal (개발 작업실)  
- **코드 개발**: 브랜치 기반 협업 워크플로우
- **결과물 관리**: Git LFS로 대용량 파일 추적
- **자동화 실행**: Claude Code 슬래시 명령어

## 📋 사용 예시

### 1. 새 프로젝트 시작
```bash
# 프로젝트 계획서 작성
echo "# 새로운 분석 프로젝트" > docs/proposals/my-project.md

# Notion에 프로젝트 구조 생성 (Epic, Task 포함)
/project-plan docs/proposals/my-project.md
```

### 2. Task 실행 (완전 자동화)
```bash
# Task 시작 (브랜치 생성 + Notion 상태 업데이트)
/task-start 23a5d36f-fc73-81ff-xxxx

# 작업 수행
echo "print('Hello Research!')" > analysis.py
python analysis.py > results.txt

# 완전 자동화 완료 (PR 생성 → 병합 → 정리)
/task-finish 23a5d36f-fc73-81ff-xxxx --pr --auto-merge
```

### 3. 대화 아카이빙
```bash
# 현재 작업의 구조화된 요약을 Notion에 저장
/task-archive  # Git 브랜치에서 자동 TID 감지
```

## 📁 Repository 구조

```
MC_test_ops/
├── 📚 README.md                    # 이 파일
├── 🚀 QUICK_START.md               # 5분 설정 가이드
├── 🤖 CLAUDE.md                    # Claude Code 지침 (피드백 반영)
├── ⚙️ .env.example                 # 환경 설정 템플릿
├── 📦 pyproject.toml               # Python 의존성 (uv 관리)
├── 🗂️ data/                        # 입력 데이터
├── 📄 docs/                        # 문서
│   ├── proposals/                  # 프로젝트 제안서
│   │   └── 2025-07-24_improved-data-analysis-pipeline.md
│   └── prds/                       # 상세 요구사항
├── 💻 src/                         # 소스 코드
│   ├── workflow_manager.py         # 핵심 워크플로우 시스템
│   └── modules/                    # 구현 모듈들
├── ⚡ slash_commands/               # Claude Code 명령어
│   ├── project-plan.md
│   ├── task-start.md
│   ├── task-archive.md
│   └── task-finish.md
└── 🎯 prompts/                     # AI 프롬프트 템플릿
```

## 🔧 고급 기능

### 배치 작업
```bash
# 여러 Task 연속 실행
for tid in TID1 TID2 TID3; do
    /task-start $tid
    # 작업 수행
    /task-finish $tid --pr --auto-merge
done
```

### 커스텀 프로젝트
```bash
# 자신만의 프로젝트 템플릿 생성
cp docs/proposals/2025-07-24_improved-data-analysis-pipeline.md docs/proposals/my-custom-project.md
# 내용 수정 후
/project-plan docs/proposals/my-custom-project.md
```

### Git LFS 확인
```bash
git lfs ls-files        # LFS 추적 파일 목록
git lfs status          # LFS 상태 확인
```

## 🎉 피드백 반영 개선사항

이 시스템은 실제 사용자 피드백을 반영하여 다음과 같이 개선되었습니다:

- ✅ **즉시 사용 가능**: 5분 설정으로 바로 시작
- ✅ **완전 자동화**: PR 생성부터 병합까지 자동
- ✅ **구조화된 아카이빙**: Raw 로그 대신 읽기 쉬운 요약
- ✅ **구체적 산출물**: 명확한 deliverable과 success criteria
- ✅ **정확한 상태 관리**: Notion API 호출 검증 및 재시도

## 🔗 관련 링크

- [빠른 시작 가이드](./QUICK_START.md) - 5분 설정
- [Claude Code 문서](https://docs.anthropic.com/en/docs/claude-code)
- [Notion API 문서](https://developers.notion.com/)
- [Git LFS 가이드](https://git-lfs.github.io/)

---

**🎯 목표**: 연구원이 창의적이고 분석적인 업무에만 집중할 수 있도록, 모든 문서화와 프로젝트 관리를 AI가 자동화합니다.

**🚀 시작하기**: [QUICK_START.md](./QUICK_START.md)를 읽고 5분 만에 시작하세요!