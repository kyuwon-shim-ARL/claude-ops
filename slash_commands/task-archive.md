# /task-archive

## 목적
현재 작업 중인 Task의 AI 대화 기록을 Notion Task 페이지에 자동 아카이빙

## 실행 방법
```
/task-archive 12346
/task-archive  # 현재 Git 브랜치 기반 자동 감지
```

## 시스템 동작

### 1. Task 식별
- TID 제공 시: 해당 Task 직접 사용
- TID 미제공 시: 현재 Git 브랜치에서 TID 추출
- `feature/TID-12346-api-integration` → TID: 12346

### 2. 대화 기록 수집
- `/export` 명령어 자동 실행 (최신 대화만)
- 대화 내용 전처리 및 정리
- 중요 코드/결과물 식별 및 하이라이트

### 3. Notion 아카이빙
- Task 페이지의 "AI 대화 기록" 토글 블록 찾기
- 타임스탬프와 함께 대화 내용 추가
- 코드 블록 및 결과물 정리하여 저장

### 4. 연관 자료 처리
- 생성된 파일들 Git 커밋 여부 확인
- 중요 산출물은 별도 섹션에 링크
- Git 커밋 로그와 연동

## 출력 예시
```
📦 Archiving conversation for Task: API 연동 구현
📋 TID: 12346
🕐 Timestamp: 2025-07-24 14:30:25

✅ Exported conversation (2,340 characters)
✅ Found Notion toggle block
✅ Archived to Task page
📁 Related files: api_client.py, test_api.py
📝 Git commits: 3 commits since task start

💡 Archive summary:
- API 클라이언트 기본 구조 설계
- 에러 핸들링 로직 구현
- 단위 테스트 작성 완료
```

## 핵심 개선사항
- **자동 Task 감지**: Git 브랜치 기반 TID 추출
- **스마트 아카이빙**: 중요 내용 자동 하이라이트
- **연관 자료 관리**: Git 커밋과 연동
- **구조화된 저장**: 타임스탬프와 카테고리별 정리