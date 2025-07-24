# /task-start

## 목적
Notion TID를 활용하여 특정 Task를 시작하고, Git 브랜치 생성 및 Notion 상태 업데이트를 자동화

## 실행 방법
```
/task-start 12346
/task-start TID-12346
/task-start "API 연동 구현"  # Task name으로도 가능
```

## 시스템 동작

### 1. Task 정보 조회
- Notion TID 또는 Task name으로 Task 검색
- Task 상세 정보 및 Epic 정보 표시
- 실행 순서 및 의존성 확인

### 2. Git 브랜치 생성
- 브랜치명: `feature/TID-{notion_tid}-{task_summary}`
- 예시: `feature/TID-12346-api-integration`
- 기존 브랜치 존재 시 전환

### 3. Notion 상태 업데이트
- Task 상태 → "In progress"
- 시작 시간 타임스탬프 추가
- 담당자 정보 업데이트 (선택사항)

### 4. 작업 환경 준비
- Task 페이지에 작업 시작 로그 추가
- 관련 참고 자료 및 의존성 정보 표시
- AI 대화 기록용 토글 블록 준비

## 출력 예시
```
🚀 Starting Task: API 연동 구현
📋 TID: 12346
🎯 Epic: 데이터 수집 파이프라인 (Epic 1)
📊 Progress: Task 1.1 of 3
🔗 Dependencies: None
✅ Created branch: feature/TID-12346-api-integration
✅ Updated Notion status to 'In progress'
📝 Added start timestamp to Task page

💡 Next steps:
1. Review task requirements in Notion
2. Check Epic dependencies
3. Begin implementation
```

## 핵심 개선사항
- **Notion TID 활용**: 실제 Notion 식별자 사용
- **의존성 체크**: 선행 Task 완료 여부 확인
- **순서 정보 표시**: Epic/Task 순서 명확히 표시
- **작업 컨텍스트 제공**: 관련 정보 자동 표시