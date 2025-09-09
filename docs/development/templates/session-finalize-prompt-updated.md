# 세션 마무리 및 문서화 프롬프트 (보안 강화 버전)

## 실행할 작업

현재 Claude Code 세션을 마무리하고 다음 작업을 순서대로 수행하라:

### 1. 대화 내용 추출 및 보안 정리

- `/export` 명령을 실행하여 현재까지의 대화 내용 추출
- **🔒 중요: 보안 정리 필수**
  ```bash
  ./.claude/hooks/export_sanitize.sh [export된파일명]
  ```
  - 텔레그램 봇 토큰 자동 제거 (`bot123456:AAH...` → `bot[REDACTED]:[REDACTED]`)
  - Notion API 토큰 자동 제거 (`secret_...` → `secret_[REDACTED]`)
  - GitHub 토큰 자동 제거 (`ghp_...` → `ghp_[REDACTED]`)
- 생성된 파일을 `docs/development/conversations/YYYY-MM-DD/` 폴더로 이동
- 파일명을 `raw-conversation-[YYYYMMDD]-[HHMM].txt`로 변경

### 2. 문서 생성 (모두 같은 시간 태그 사용)

동일한 타임스탬프를 사용하여 세 가지 문서를 생성:

#### A. 튜토리얼

- 참조: `@docs/development/templates/tutorial-generation-prompt.md`
- 저장: `docs/development/conversations/YYYY-MM-DD/tutorial-[프로젝트명]-[YYYYMMDD]-[HHMM].md`

#### B. 대화 흐름 기록

- 참조: `@docs/development/templates/conversation-flow-prompt.md`
- 저장: `docs/development/conversations/YYYY-MM-DD/conversation-[프로젝트명]-[YYYYMMDD]-[HHMM].md`

#### C. 프로젝트 요약

- 참조: `@docs/development/templates/project-summary-prompt.md`
- 저장: 프로젝트 루트에 `project-summary-[프로젝트명]-[YYYYMMDD]-[HHMM].md`
- 추가 작업:
    1. 기존 `project-summary-*.md` 파일들을 `archive/` 폴더로 이동
    2. `project-summary-current.md` 심볼릭 링크 업데이트

### 3. 파일 구조 예시

```
project-root/
├── project-summary-current.md → archive/project-summary-paperflow-20250131-1720.md
├── archive/
│   ├── project-summary-paperflow-20250131-0930.md
│   ├── project-summary-paperflow-20250131-1430.md
│   └── project-summary-paperflow-20250131-1720.md (새로 생성)
└── docs/
    └── development/
        └── conversations/
            └── 2025-01-31/
                ├── raw-conversation-20250131-1720.txt (보안 정리 완료)
                ├── tutorial-paperflow-20250131-1720.md
                └── conversation-paperflow-20250131-1720.md
```

## 완료 후 확인 사항

### 체크리스트

- [ ]  날짜 폴더 생성: `docs/development/conversations/YYYY-MM-DD/`
- [ ]  **🔒 export 파일 보안 정리 (토큰 제거) 완료**
- [ ]  동일 시간대 파일 3개 생성 (raw, tutorial, conversation)
- [ ]  프로젝트 요약 생성 및 archive 이동
- [ ]  심볼릭 링크 업데이트
- [ ]  모든 문서에 Git 메타데이터 포함
- [ ]  **보안 정리 로그 확인** (몇 개 토큰이 제거되었는지 확인)

### 확인 명령어

```bash
# 오늘 작업 확인
ls -la docs/development/conversations/$(date +%Y-%m-%d)/

# 프로젝트 요약 확인
ls -la project-summary-current.md archive/

# 최근 변경사항
find . -name "*.md" -mmin -10

# 보안 정리 검증 (토큰이 남아있지 않은지 확인)
grep -r "bot[0-9]\{8,\}:AAH\|secret_[A-Za-z0-9]\{43\}\|ghp_[A-Za-z0-9]\{36\}" docs/development/conversations/$(date +%Y-%m-%d)/ || echo "✅ 보안 정리 완료"
```

## 프로젝트 정보

- 프로젝트명: [현재 디렉토리명 또는 사용자 지정]
- 특정 주제: [있다면 명시 - 파일명에 추가 가능]

## 보안 정리 스크립트 상세

`export_sanitize.sh` 스크립트가 처리하는 민감한 정보:
- 텔레그램 봇 토큰: `bot123456789:AAH...` → `bot[REDACTED]:[REDACTED]`
- Notion API 토큰: `secret_...` → `secret_[REDACTED]`  
- GitHub 개인 토큰: `ghp_...` → `ghp_[REDACTED]`
- GitHub 앱 토큰: `github_pat_...` → `github_pat_[REDACTED]`

**중요**: 보안 정리는 git commit 전에 반드시 수행해야 합니다!