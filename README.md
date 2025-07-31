# 🚀 Claude-Ops: Multi-Project AI Automation Hub

**Claude Code + Notion + GitHub + Telegram 통합 자동화 시스템**

[![Setup Time](https://img.shields.io/badge/Setup-5_minutes-green)](./QUICK_START.md)
[![Multi Project](https://img.shields.io/badge/Multi_Project-Management-blue)](#multi-project-management)
[![Reply Based](https://img.shields.io/badge/Telegram-Reply_Based_Targeting-green)](#telegram-reply-targeting)
[![Auto Merge](https://img.shields.io/badge/Workflow-Fully_Automated-blue)](#자동화-기능)

**홈 폴더에서 모든 Claude 프로젝트를 중앙 관리하는 완전 자동화 시스템**

- 🏠 **홈 폴더 중앙 관리**: 한 곳에서 모든 프로젝트 제어
- 🎯 **Reply 기반 타겟팅**: 텔레그램 Reply로 정확한 세션 선택
- 🔄 **멀티 세션 모니터링**: 모든 프로젝트 동시 감시
- 📱 **원격 프로젝트 생성**: 텔레그램에서 `/start new-project` 가능

## 🏠 홈 폴더 중앙 관리 설정

### 빠른 설정 (권장)

```bash
# 1. 홈 폴더에 Claude-Ops 설치
cd ~
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git claude-ops
cd claude-ops

# 2. 환경 설정 복사 (기존 설정 재사용 가능)
cp .env.example .env
# .env 파일에 API 키 설정 (Notion, GitHub, Telegram)

# 3. 의존성 설치
uv sync

# 4. 홈 디렉토리 설정
echo "CLAUDE_WORKING_DIR=$HOME" >> .env

# 5. CLI 도구 PATH 추가 (편의성)
./scripts/claude-ops.sh install
source ~/.bashrc

# 6. 멀티 프로젝트 모니터링 시작
claude-ops start-monitoring
```


## ⚡ 멀티 프로젝트 사용법

### 🚀 새 프로젝트 생성

**방법 1: CLI 명령어 (권장)**
```bash
# 새 프로젝트 생성
claude-ops new-project my-ai-app                    # ~/projects/my-ai-app
claude-ops new-project web-scraper ~/work/client   # ~/work/client

# 기존 프로젝트에 Claude 추가
claude-ops new-project existing-app ~/work/existing-project

# 시스템 관리
claude-ops status          # 상태 확인
claude-ops sessions        # 활성 세션 목록
claude-ops stop-monitoring # 모니터링 종료
```

**방법 2: 텔레그램 원격 제어**
```
/start my-ai-app                    # ~/projects/my-ai-app에서 claude_my-ai-app 시작
/start web-scraper ~/work/client    # ~/work/client에서 claude_web-scraper 시작
```

**방법 3: 수동 tmux 세션 (100% 확실)**
```bash
# 수동으로 세션 생성 (가장 확실한 방법)
mkdir -p ~/projects/my-project
tmux new-session -d -s claude_my-project -c ~/projects/my-project
tmux send-keys -t claude_my-project 'claude' Enter

# 연결: tmux attach -t claude_my-project
```

### 🎯 Reply 기반 텔레그램 제어

**1. 작업 완료 알림 받기**
```
✅ 작업 완료 [claude_my-ai-app]

📁 프로젝트: ~/projects/my-ai-app
🎯 세션: claude_my-ai-app
⏰ 완료 시간: 14:30:25

[작업 내용]

💡 답장하려면 이 메시지에 Reply로 응답하세요!
```

**2. Reply로 정확한 세션에 답장**
- 알림 메시지에 Reply → 자동으로 해당 세션으로 전송
- 일반 메시지 → 현재 활성 세션으로 전송
- 세션 혼동 걱정 없음! ✨

## 🔧 시스템 관리

### 🚀 시작하기

**멀티 프로젝트 모니터링 시작**
```bash
# CLI 명령어 (권장)
claude-ops start-monitoring

# 또는 직접 실행
cd ~/claude-ops
./scripts/start_multi_monitoring.sh
```

**단일 명령으로 모든 것 관리됩니다:**
- ✅ 모든 `claude_*` 세션 자동 감지
- ✅ 작업 완료 시 텔레그램 알림
- ✅ Reply 기반 정확한 세션 타겟팅
- ✅ 새 세션 자동 추가 모니터링

### 🛑 종료하기

**모니터링 완전 종료**
```bash
# CLI 명령어 (권장)
claude-ops stop-monitoring

# 또는 수동으로
tmux kill-session -t claude-multi-monitor 2>/dev/null
tmux kill-session -t claude-monitor 2>/dev/null
pkill -f "multi_monitor"
```

**개별 프로젝트 세션 종료**
```bash
tmux kill-session -t claude_my-project  # 특정 프로젝트만
tmux kill-session -t claude_*           # 모든 Claude 세션 (주의!)
```

### 📊 상태 확인

**CLI 명령어로 확인**
```bash
claude-ops status      # 전체 시스템 상태
claude-ops sessions    # 활성 세션 목록
```

**수동 확인**
```bash
tmux list-sessions | grep claude        # 모든 Claude 세션
tmux attach -t claude-multi-monitor     # 모니터링 로그 보기
```

**텔레그램에서**
```
/sessions    # 모든 활성 세션 목록 + 전환
/status      # 현재 봇 상태
```

### 🔧 기존 프로젝트에 추가

**기존 작업 중인 프로젝트에 Claude Code 워크플로우를 추가하려면:**

```bash
# 방법 1: 원클릭 설치 (권장)
curl -sSL https://raw.githubusercontent.com/kyuwon-shim-ARL/claude-ops/main/install-to-existing.sh | bash

# 방법 2: 수동 설치
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git /tmp/claude-ops-template
cp /tmp/claude-ops-template/CLAUDE.md .
cp /tmp/claude-ops-template/.env.example .
cp -r /tmp/claude-ops-template/slash_commands/ .
cp /tmp/claude-ops-template/src/workflow_manager.py ./src/
cat /tmp/claude-ops-template/.gitattributes >> .gitattributes
rm -rf /tmp/claude-ops-template
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