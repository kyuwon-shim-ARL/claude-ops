⚡ **구현 (Implementation with DRY)**

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
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