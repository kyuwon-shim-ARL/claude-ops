# Claude Code Development Workflow

## Keyword-Based Development

### 1. 기획 (Structured Discovery & Planning Loop)
- **탐색**: 전체 구조 파악, As-Is/To-Be/Gap 분석
- **계획**: MECE 기반 작업분해(WBS), 우선순위 매트릭스
- **수렴**: 탐색↔계획 반복 until PRD 완성 & TodoWrite 구조화

### 2. 구현 (Implementation with DRY)  
- **DRY 원칙**: 기존 코드 검색 → 재사용 → 없으면 생성
- **체계적 진행**: TodoWrite 기반 단계별 구현
- **품질 보증**: 단위 테스트 + 기본 검증

### 3. 안정화 (Structural Sustainability Protocol v2.0)
**패러다임 전환**: 기능 중심 → **구조적 지속가능성** 중심

**6단계 통합 검증 루프:**
1. **Repository Structure Scan**: 전체 파일 분석, 중복/임시 파일 식별
2. **Structural Optimization**: 디렉토리 정리, 파일 분류, 네이밍 표준화  
3. **Dependency Resolution**: Import 수정, 참조 오류 해결, 환경 동기화
4. **Comprehensive Testing**: 모듈 검증, API 테스트, 시스템 무결성 확인
5. **Documentation Sync**: CLAUDE.md 반영, README 업데이트, .gitignore 정리
6. **Quality Assurance**: MECE 분석, 성능 벤치마크, 정량 평가

**예방적 관리**: 루트 20개 파일, 임시 파일 5개, Import 오류 3개 이상 시 자동 실행

### 4. 배포 (Deployment)
- **최종 검증**: 체크리스트 완료 확인
- **구조화 커밋**: 의미있는 커밋 메시지 생성
- **원격 배포**: 푸시 + 버전 태깅

## TodoWrite Usage

Always use TodoWrite for tasks with 3+ steps:

```python
todos = [
    {"content": "분석: 현황 파악 + 요구사항 정리", "status": "in_progress", "id": "001"},
    {"content": "시작: 핵심 기능 구현", "status": "pending", "id": "002"},
    {"content": "검증: 테스트 및 문서화", "status": "pending", "id": "003"}
]
```

## MECE Progress Tracking

Provide quantitative, specific progress updates:
- ❌ "거의 다 됐어요"
- ✅ "3/4 주요 기능 완료, 1개 DB 연결 이슈 남음"
