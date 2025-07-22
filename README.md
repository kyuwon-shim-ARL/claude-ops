# 🚀 AI-Augmented Research & Development Workflow

이 프로젝트는 Notion, Git, 그리고 터미널 기반 AI(Claude Code 등)를 유기적으로 결합하여, 바이오인포매틱스 연구 개발의 효율성과 재현성을 극대화하기 위해 설계된 워크플로우 시스템입니다.

## 📜 핵심 철학 (Core Philosophy)

우리는 두 개의 분리된 공간에서 작업합니다:

-   **🏛️ Notion (The Studio):** '왜'와 '무엇을'을 관리하는 **전략 본부**입니다. 모든 프로젝트의 목표, 로드맵, 핵심 의사결정, 그리고 최종적으로 발행된 지식 자산이 이곳에 기록됩니다.
-   **🛠️ Git & Terminal (The Workshop):** '어떻게'를 관리하는 **개발 작업실**입니다. 실제 코드, 탐색 과정, 산출물, 그리고 기술적 논의의 모든 디테일이 버전 관리와 함께 이곳에 기록됩니다.

이 시스템의 목표는 '문서 관리'에 들이는 노력을 AI를 통해 자동화하여, 연구원이 가장 중요한 창의적이고 분석적인 업무에만 집중할 수 있도록 하는 것입니다.

## ⚙️ 시작하기 (Getting Started)

### 전제 조건 (Prerequisites)

1.  **도구 설치:** `git`, `git-lfs`, `node.js`, 그리고 터미널 AI(`claude-cod
)가 설치되어 있어야 합니다.
2.  **API 키 발급:**
    -   Notion Integration Token
    -   GitHub Personal Access Token
3.  **`.env` 파일 설정:** 프로젝트 루트에 `.env` 파일을 생성하고, 발급받은 API 키와 Notion 데이터베이스 ID들을 환경 변수로 설정합니다.

### 시스템 설정

이 프로젝트의 모든 자동화는 루트 디렉토리의 `claude.md` 파일과 `prompts/` 디렉토리의 지침서들을 기반으로 작동합니다. 새로운 프로젝트를 시작할 때 이 구조를 그대로 복사하여 사용하세요.

## 🚀 워크플로우 요약 (Workflow in Action)

1.  **계획 수립:** 연구 제안서(`.md`)를 작성한 뒤, 터미널에서 `claude-code project plan ...` 명령어로 Notion에 Epic과 Task를 자동으로 발행합니다.
2.  **작업 착수:** `claude-code task start <TID>` 명령어로 작업을 시작합니다. AI가 자동으로 Git 브랜치를 생성하고 Notion 상태를 업데이트합니다.
3.  **탐색 및 개발:** 터미널에서 AI와 대화하며 코드를 작성, 수정, 실행하고 커밋합니다.
4.  **과정 아카이빙:** `claude-code task archive <TID>` 명령어로, AI와의 모든 대화 기록을 Notion의 해당 `Task` 앵커 페이지에 자동으로 보관합니다.
5.  **작업 완료:** `claude-code task finish <TID> --pr` 명령어로 작업을 마칩니다. AI가 PR을 생성하고(설명까지 자동 요약), Notion 상태를 업데이트합니다.
6.  **지식 발행:** `claude-code task publish <TID>` 명령어로, 완료된 작업의 결과와 통찰을 `지식 저장소`에 공식 문서로 자동 발행합니다.