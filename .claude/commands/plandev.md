📋 **기획부터 구현까지 워크플로우**

아이디어부터 동작하는 코드까지 완성합니다:


==================================================

🎯 **기획 (Structured Discovery & Planning Loop)**

**📚 컨텍스트 자동 로딩:**
- docs/guides/project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/status.md 확인 (있으면 읽기)
- 이전 세션 TODO 확인

**탐색 단계:**
- 전체 구조 파악: 현재 시스템 아키텍처와 요구사항 분석
- As-Is/To-Be/Gap 분석: 현재 상태, 목표 상태, 차이점 식별
- 이해관계자 요구사항 수집 및 우선순위화

**계획 단계:**
- MECE 기반 작업분해(WBS): 상호배타적이고 전체포괄적인 업무 구조
- 우선순위 매트릭스: 중요도와 긴급도 기반 작업 순서 결정
- 리소스 및 일정 계획 수립

**수렴 단계:**
- 탐색↔계획 반복 iterative refinement
- PRD(Product Requirements Document) 완성
- TodoWrite를 활용한 구조화된 작업 계획 수립

**📊 작업 규모 평가:**
- 전략적/전술적/운영적 작업 구분

**💾 규모별 차별화된 문서화:**
- 전략적: PRD + planning.md + TodoWrite
- 전술적: planning.md(선택) + TodoWrite
- 운영적: TodoWrite만
- TodoWrite는 항상 docs/CURRENT/active-todos.md에 동기화

**산출물:** 구체적인 실행 계획과 성공 기준이 포함된 PRD

==================================================


📍 **기획 완료 → 구현 시작**
위에서 수립한 계획을 바탕으로 실제 구현을 진행합니다:

⚡ **구현 (Implementation with DRY)**

**📚 컨텍스트 자동 로딩:**
- docs/guides/project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/active-todos.md 확인 (있으면 읽기)

**DRY 원칙 적용:**
- 기존 코드 검색: Grep, Glob 도구로 유사 기능 탐색
- 재사용 우선: 기존 라이브러리/모듈/함수 활용
- 없으면 생성: 새로운 컴포넌트 개발 시 재사용성 고려

**체계적 진행:**
- TodoWrite 기반 단계별 구현
- 모듈화된 코드 구조 유지
- 코딩 컨벤션 준수 (기존 코드 스타일 분석 후 적용)

**품질 보증:**
- 단위 테스트 작성 및 실행
- 기본 검증: 문법 체크, 타입 체크, 린트
- 동작 확인: 핵심 기능 동작 테스트

**💾 자동 문서화:**
- 구현 진행상황을 docs/CURRENT/implementation.md에 기록
- TodoWrite 업데이트를 docs/CURRENT/active-todos.md에 반영

**산출물:** 테스트 통과하는 동작 가능한 코드