# /project-plan

## 목적
PRD 문서를 기반으로 Notion에 Project → Epics → Tasks 계층 구조를 자동 생성하고, 실행 순서를 명확히 하는 명령어

## 실행 방법
```
/project-plan docs/proposals/my-proposal.md
```

## 시스템 동작

### 1. 프로젝트 생성 (Projects DB)
- 프로젝트명과 핵심 목표 설정
- 전체 프로젝트 개요 및 배경 정보 추가

### 2. Epic 생성 (Tasks DB, IsEpic=True)
- PRD 분석을 통한 3-5개 Epic 도출
- Epic별 실행 순서 번호 자동 할당 (Epic 1, Epic 2...)
- Epic간 의존성 관계 설정

### 3. Task 생성 (Tasks DB, ParentTask 연결)
- Epic당 3-5개 SubTask 생성
- Task별 실행 순서 번호 할당 (Task 1.1, 1.2, 1.3...)
- Notion TID 자동 생성 및 활용

### 4. 페이지 내용 자동 생성
- **Epic 페이지**: 목표, 설명, SubTask 리스트, 의존성 정보
- **Task 페이지**: 작업 목표, 체크리스트, 참고 자료, AI 대화 토글

### 5. 출력 정보
```
✅ Created Project: "연구용 데이터 분석 파이프라인"
✅ Created Epic 1: "데이터 수집 파이프라인" (TID: 12345)
  ✅ Created Task 1.1: "API 연동 구현" (TID: 12346)
  ✅ Created Task 1.2: "데이터 검증" (TID: 12347)
✅ Created Epic 2: "분석 시스템" (TID: 12348)
  ✅ Created Task 2.1: "통계 분석" (TID: 12349)

📋 Use these TIDs for task management:
/task-start 12346
/task-archive 12346
```

## 핵심 개선사항
- **Notion TID 직접 활용**: 매핑 파일 불필요
- **순서 체계화**: Epic 1,2,3... Task 1.1,1.2,1.3...
- **의존성 관리**: Epic/Task간 순서 및 의존성 명시
- **Claude Code 네이티브**: Python 스크립트 별도 실행 불필요