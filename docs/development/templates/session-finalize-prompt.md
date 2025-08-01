# 세션 마무리 및 문서화 프롬프트

## 실행할 작업

현재 Claude Code 세션을 마무리하고 다음 작업을 순서대로 수행하라:

### 1. 대화 내용 추출

- `/export` 명령을 실행하여 현재까지의 대화 내용 추출
- 생성된 파일을 `docs/development/conversations/YYYY-MM-DD/` 폴더로 이동
- 파일명을 `raw-conversation-[YYYYMMDD]-[HHMM].txt`로 변경

### 2. 문서 생성 (모두 같은 시간 태그 사용)

동일한 타임스탬프를 사용하여 세 가지 문서를 생성:

#### A. 튜토리얼

- 참조: `@docs/development/prompts/tutorial-generation-prompt.md`
- 저장: `docs/development/conversations/YYYY-MM-DD/tutorial-[프로젝트명]-[YYYYMMDD]-[HHMM].md`

#### B. 대화 흐름 기록

- 참조: `@docs/development/prompts/conversation-flow-prompt.md`
- 저장: `docs/development/conversations/YYYY-MM-DD/conversation-[프로젝트명]-[YYYYMMDD]-[HHMM].md`

#### C. 프로젝트 요약

- 참조: `@docs/development/prompts/project-summary-prompt.md`
- 저장: 프로젝트 루트에 `project-summary-[프로젝트명]-[YYYYMMDD]-[HHMM].md`
- 추가 작업:
    1. 기존 `project-summary-*.md` 파일들을 `archive/` 폴더로 이동
    2. `project-summary-current.md` 심볼릭 링크 업데이트

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
                ├── raw-conversation-20250131-1720.txt
                ├── tutorial-paperflow-20250131-1720.md
                └── conversation-paperflow-20250131-1720.md
```

## 완료 후 확인 사항

### 체크리스트

- [ ]  날짜 폴더 생성: `docs/development/conversations/YYYY-MM-DD/`
- [ ]  동일 시간대 파일 3개 생성 (raw, tutorial, conversation)
- [ ]  프로젝트 요약 생성 및 archive 이동
- [ ]  심볼릭 링크 업데이트
- [ ]  모든 문서에 Git 메타데이터 포함

### 확인 명령어

bash

```bash
# 오늘 작업 확인
ls -la docs/development/conversations/$(date +%Y-%m-%d)/

# 프로젝트 요약 확인
ls -la project-summary-current.md archive/

# 최근 변경사항
find . -name "*.md" -mmin -10
```

## 프로젝트 정보

- 프로젝트명: [현재 디렉토리명 또는 사용자 지정]
- 특정 주제: [있다면 명시 - 파일명에 추가 가능]