● 좋습니다! 테스트를 위한 상세한 가이드를 제공해드리겠습니다:

  🧪 Claude Code 슬래시 명령어 시스템 테스트 가이드

  1. 테스트 환경 설정

  .env 파일 생성

  # Notion API 설정
  NOTION_API_KEY=secret_xxxxxxxxx  # Notion Integration Token
  NOTION_TASKS_DB_ID=xxxxxxxxx    # Tasks 데이터베이스 ID
  NOTION_PROJECTS_DB_ID=xxxxxxxxx # Projects 데이터베이스 ID
  NOTION_KNOWLEDGE_HUB_ID=xxxxxxxxx # Knowledge Hub 페이지 ID

  # GitHub API 설정  
  GITHUB_PAT=ghp_xxxxxxxxx        # GitHub Personal Access Token
  GITHUB_REPO_OWNER=your-username # GitHub 사용자명
  GITHUB_REPO_NAME=claude-ops-test # 테스트 repo 이름

  Notion 데이터베이스 확인

  - Projects DB: "Project name" (title), "Key Goal" (rich_text) 속성 필요
  - Tasks DB: "Task name" (title), "Text" (rich_text), "Projects" (relation), "ParentTask" (relation), "Priority" (select), "Status" (status) 속성 필요

  2. 테스트 시나리오

  Phase 1: 프로젝트 계획 생성

  /project-plan docs/proposals/2025-07-22_data-analysis-pipeline-template.md

  예상 결과:
  - Notion Projects DB에 새 프로젝트 생성
  - 3개 Epic 생성 (Epic 1, Epic 2, Epic 3)
  - 각 Epic당 3개 SubTask 생성 (Task 1.1, 1.2, 1.3...)
  - TID 목록 출력

  Phase 2: 첫 번째 Task 시작

  /task-start [첫_번째_TID]

  예상 결과:
  - Git branch 생성: feature/TID-xxxxxxxx-task-summary
  - Notion Task 상태 → "In progress"
  - Task 페이지에 시작 시간 기록

  Phase 3: 작업 수행 및 아카이빙

  # 간단한 파일 편집
  echo "# Test Work" > test_file.md
  git add test_file.md
  git commit -m "Add test work file"

  # 대화 기록 아카이빙 (TID 자동 감지)
  /task-archive

  예상 결과:
  - 현재 Git branch에서 TID 자동 감지
  - 대화 내용을 Notion Task 페이지의 토글 블록에 저장

  Phase 4: 작업 완료

  /task-finish [TID] --pr

  예상 결과:
  - GitHub PR 생성
  - Notion Task 상태 → "Done"
  - PR 제목: [TID-xxxxxxxx] Task 1.1: 데이터 수집 모듈 구현

  3. 확인 포인트

  ✅ Notion 확인사항:
  - Project 페이지 생성 및 내용 확인
  - Epic 페이지들의 목표, SubTask 목록 확인
  - Task 페이지들의 작업 목표, 참고 자료, AI 대화 토글 확인
  - Task 상태 변화 확인 (Pending → In progress → Done)

  ✅ Git 확인사항:
  - 올바른 branch 명명 규칙: feature/TID-xxxxxxxx-summary
  - Branch가 main에서 분기되었는지 확인
  - 커밋이 올바른 branch에 기록되었는지 확인

  ✅ GitHub 확인사항:
  - PR이 생성되었는지 확인
  - PR 제목과 설명이 적절한지 확인
  - PR이 올바른 base branch(main)를 대상으로 하는지 확인

  4. 예상 이슈 및 해결방법

  이슈 1: Notion API 권한 오류
  - Integration이 해당 데이터베이스에 접근 권한이 있는지 확인
  - 데이터베이스를 Integration과 공유했는지 확인

  이슈 2: GitHub API 오류
  - PAT가 repo 권한을 가지고 있는지 확인
  - GITHUB_REPO_OWNER, GITHUB_REPO_NAME이 정확한지 확인

  이슈 3: TID 자동 감지 실패
  - Git branch 이름이 feature/TID- 형식인지 확인
  - /task-archive [TID]로 수동 지정 시도

  이렇게 단계별로 테스트하시면 전체 워크플로우가 올바르게 작동하는지 확인할 수 있습니다!

● Update Todos
  ⎿  ☒ Set up current repo as GitHub Template                    
     ☒ Create new test repo from template (User will do manually)
     ☒ Provide environment setup guide for test repo
     ☒ Create detailed test scenario documentation
     ☒ Provide troubleshooting guide for common issues

● 완료했습니다!

  ✅ 준비 완료:
  1. GitHub Template 설정: 현재 repo가 template으로 설정됨
  2. 상세한 테스트 가이드 제공: 환경 설정부터 전체 워크플로우 테스트까지
  3. 확인 포인트 정리: Notion, Git, GitHub 각각의 확인사항
  4. 트러블슈팅 가이드: 예상되는 이슈들과 해결방법

  이제 수작업으로 새 repo를 만들어서 위의 가이드대로 테스트해보시면 됩니다.

  핵심 테스트 플로우:
  /project-plan → /task-start → 작업 수행 → /task-archive → /task-finish --pr