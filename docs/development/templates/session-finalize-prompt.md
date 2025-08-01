# 세션 마무리 및 문서화 프롬프트

  

## 실행할 작업

  

현재 Claude Code 세션을 마무리하고 다음 작업을 순서대로 수행하라:

  

### 1. 대화 내용 추출 및 저장

  

#### A. /export 명령 실행

**사용자가 실행**: Claude Code 터미널에서 `/export` 명령 실행

- 명령어: `/export`  

- 결과: 현재 디렉토리에 `YYYY-MM-DD-conversation-[기존파일명]-docs.txt` 형식으로 파일 생성

  

#### B. Export 파일 이동 및 이름 변경

**중요**: export로 생성된 파일을 다음 위치로 이동하고 이름을 변경하라:

  

**이동 프로세스:**

1. **export 파일 확인**: 현재 디렉토리에서 `*-conversation-*-docs.txt` 패턴 파일 찾기

2. **날짜 폴더 확인**: `docs/development/conversations/YYYY-MM-DD/` 폴더 존재 여부 확인

3. **폴더 생성**: 없으면 해당 날짜 폴더를 생성

4. **파일 이동 및 이름 변경**:

   ```bash

   mv [export파일명].txt docs/development/conversations/[YYYY-MM-DD]/raw-conversation-[YYYYMMDD]-[HHMM].txt

   ```

  

**예시:**

```bash

# export로 생성된 파일: 2025-07-31-conversation-2025-07-31-154506txt-docs.txt

# 이동 후: docs/development/conversations/2025-07-31/raw-conversation-20250731-1720.txt

mv 2025-07-31-conversation-*-docs.txt docs/development/conversations/2025-07-31/raw-conversation-20250731-1720.txt

```

  

### 2. 튜토리얼 생성

  

- `@docs/development/templates/tutorial-generation-prompt.md` 파일을 참조

- 추출한 대화 내용을 기반으로 재현 가능한 튜토리얼 작성

- 지정된 경로에 저장

  

### 3. 대화 흐름 기록 생성

  

- `@docs/development/templates/conversation-flow-prompt.md` 파일을 참조

- 대화의 흐름과 의사결정 과정을 문서화

- 지정된 경로에 저장

  

### 4. 프로젝트 요약 업데이트

  

- `@docs/development/templates/project-summary-prompt.md` 파일을 참조

- 현재 프로젝트의 전체 상태를 반영한 요약 문서 생성 또는 업데이트

- 프로젝트 루트 또는 docs 폴더에 저장

  

### 5. 프로젝트 정보

  

- 프로젝트명: [사용자가 지정하거나 현재 디렉토리명 사용]

- 작업 주제: [특정 주제가 있다면 명시]

  

## 완료 후 확인 사항

  

### 필수 확인사항

- [ ]  **날짜별 폴더가 생성되었는가**: `docs/development/conversations/YYYY-MM-DD/` 폴더 존재

- [ ]  **Raw conversation이 저장되었는가**: `/export` 결과가 `raw-conversation-[YYYYMMDD]-[HHMM].txt`로 저장

- [ ]  **세션 문서들이 생성되었는가**:

  - [ ] 튜토리얼: `tutorial-[프로젝트명]-[주제]-[YYYYMMDD].md`

  - [ ] 대화록: `conversation-[프로젝트명]-[주제]-[YYYYMMDD].md`

- [ ]  **프로젝트 요약이 업데이트되었는가**: `docs/core/project-summary.md` 또는 루트의 프로젝트 요약

- [ ]  **모든 파일명이 규칙에 맞게 생성되었는가**: 네이밍 컨벤션 준수

- [ ]  **Git 메타데이터가 포함되었는가**: 브랜치, 커밋 정보 등

  

### 품질 확인사항

- [ ]  **세션 파일 그룹화**: 같은 날짜 폴더에 raw, tutorial, conversation 파일들이 모두 위치

- [ ]  **파일 내용 일관성**: 같은 세션에서 생성된 모든 문서가 일관된 정보 포함

- [ ]  **링크 및 참조**: 문서 간 상호 참조가 올바르게 연결됨

  

### 최종 확인 명령어

```bash

# 생성된 파일 구조 확인

ls -la docs/development/conversations/$(date +%Y-%m-%d)/

  

# 파일명 규칙 확인

find docs/development/conversations/$(date +%Y-%m-%d)/ -name "*.md" -o -name "*.txt"

  

# Git 상태 확인

git status --porcelain

```