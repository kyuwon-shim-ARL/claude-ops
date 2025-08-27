🎯 **기획 (Structured Discovery & Planning Loop)**

**📚 컨텍스트 자동 로딩 (우선순위 순):**
- docs/specs/docs/guides/project_rules.md 확인 (없으면 루트에서 찾기)
- docs/specs/PRD-v*.md 확인 (최신 버전)
- docs/CURRENT/status.md 확인 (있으면 읽기)
- 이전 세션 TODO 확인

**🔄 기획 시작 시 컨텍스트 정리 (확정적 실행):**
IF (새로운_주제_감지 OR 로드맵_전환_감지):
    /compact "Strategic 영속 컨텍스트와 docs/guides/project_rules.md만 유지. 이전 구현 세부사항과 Tactical/Operational 컨텍스트는 아카이브하여 새로운 기획에 집중할 수 있도록 정리"

**🧠 지능형 컨텍스트 관리 (자동 실행):**
1. **로드맵 전환 감지**: 현재 요청과 이전 3-5개 메시지 비교
   - Semantic distance > 0.7 → 새로운 로드맵으로 판단
   - 명시적 전환 키워드 ("다음으로", "새로운 기능", "이제 다른") 감지
   - /배포 완료 후 10분+ 경과 + 새 주제 → 자동 경계 설정

2. **기획 위계 자동 분류** (임팩트 기반 MECE):
   
   **Strategic (전략층 - 90% 컨텍스트 유지)**:
   - 판단기준: "사용자 경험의 근본이 바뀌는가?"
   - 시그널: 새 인증시스템, DB마이그레이션, 새 플랫폼, 비즈니스로직 근본변경
   - 예시: "소셜로그인 추가", "결제시스템 구축", "모바일앱 출시"
   - ❌반례: "전체 UI 개선"(실제로는 일부), "시스템 전체 테스트"
   
   **Tactical (전술층 - 60% 관련 컨텍스트)**:
   - 판단기준: "특정 사용자 그룹의 워크플로우가 바뀌는가?"  
   - 시그널: 기능옵션 추가, 새 API, UI컴포넌트 추가, 특정그룹 개선
   - 예시: "대시보드 차트 추가", "파일업로드 용량확장", "새 필터옵션"
   - ❌반례: "로그인 버그수정"(워크플로우 무변화)
   
   **Operational (운영층 - 30% 핵심만)**:
   - 판단기준: "기존 기능이 더 안정적/빠르게 동작하는가?"
   - 시그널: 버그수정, 성능튜닝, 설정조정, 에러핸들링개선, 리팩토링
   - 예시: "로그인 에러메시지 개선", "DB쿼리 최적화", "CSS버그 수정"
   - ❌반례: "새 로그분석도구"(기능추가=Tactical)

3. **컨텍스트 상속 적용**:
   - 영속 유지: docs/specs/* (docs/guides/project_rules.md, PRD, requirements.md, architecture.md)
   - 관련성 필터: 새 주제와 연관성 기반 선별 보존  
   - 자동 아카이브: 완료 작업 + 미채택 대안 → sessions/

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
- 전략적 (Strategic): 제품 전체, 메이저 기능, v2.0 등 → PRD 생성
- 전술적 (Tactical): 중간 기능, 모듈 개선 → planning.md 선택적
- 운영적 (Operational): 버그 수정, 작은 개선 → TodoWrite만

**💾 규모별 차별화된 문서화 + PRD 자동 분해:**

**📋 PRD 기반 사양서 자동 생성 (조건부 실행):**
```python
def auto_generate_specs():
    # 트리거 조건
    if (not exists('docs/specs/requirements.md') or 
        not exists('docs/specs/architecture.md') or
        prd_newer_than_specs() or
        detect_major_changes()):
        
        extract_requirements(PRD) → docs/specs/requirements.md
        extract_architecture(PRD) → docs/specs/architecture.md
        move_project_rules() → docs/specs/docs/guides/project_rules.md
```

**자동 생성 트리거:**
- 초기 실행: requirements.md, architecture.md 미존재
- 변경 감지: PRD 파일이 specs 문서들보다 최신
- 키워드 감지: "아키텍처 변경", "요구사항 업데이트", "큰 변화"
- 명시적 요청: 사용자가 직접 업데이트 요청

**생성 내용:**
- **requirements.md**: 기능 요구사항, 비기능 요구사항, 제약사항 추출
- **architecture.md**: 시스템 구조, 기술 스택, 데이터 흐름, 인터페이스 설계
- **docs/guides/project_rules.md**: 루트에서 docs/specs/로 이동 (최초 1회)

**문서화 계층:**
- **전략적 기획**: PRD 생성/업데이트 → 자동 specs 분해 + planning.md + TodoWrite
- **전술적 기획**: planning.md 선택적 생성 + TodoWrite 
- **운영적 작업**: TodoWrite만 사용 (문서 생성 최소화)
- TodoWrite는 항상 docs/CURRENT/active-todos.md에 동기화

**산출물:** 구체적인 실행 계획과 성공 기준이 포함된 PRD