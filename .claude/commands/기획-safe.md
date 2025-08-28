🎯 **기획-Safe (Gradual Context Management Testing)**

**🛡️ 안전 모드 활성화**
이것은 컨텍스트 관리 시스템의 제한적 테스트 버전입니다.

**📊 성능 측정 시작:**
```bash
python scripts/context_performance_monitor.py start "strategic" "현재_작업_설명"
```

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/status.md 확인 (있으면 읽기)
- docs/CURRENT/context_metrics.json 확인 (성능 데이터 로드)

**🔄 제한된 컨텍스트 관리 (테스트 모드):**
IF (새로운_주제_감지 AND 성능_점수 > 75):
    성능_측정_시작()
    /compact "SAFE MODE: 중요한 아키텍처 결정과 project_rules.md만 보존. 
             구현 세부사항은 선별적으로만 제거. 롤백 가능하도록 보수적 접근"
    성능_변화_추적()
ELSE:
    "컨텍스트 관리 건너뜀 - 안전 임계값 미달 또는 성능 저하 감지"

**⚠️ 안전 장치:**
1. **실시간 모니터링**: 각 응답 후 성능 지표 자동 체크
2. **롤백 트리거**: 
   - 첫시도 성공률 < 70%
   - 품질 점수 < 75
   - 토큰 효율성 감소
3. **보수적 압축**: 의심스러우면 컨텍스트 유지

**📈 측정 지표:**
- 토큰 사용량 변화
- 응답 품질 평가  
- 중복 작업 발생 여부
- 컨텍스트 miss 감지

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

**🧪 테스트 종료 시:**
```bash
python scripts/context_performance_monitor.py score
python scripts/context_performance_monitor.py check
```

**💾 자동 문서화:**
- 기획 결과를 docs/CURRENT/planning.md에 저장
- 성능 데이터를 context_metrics.json에 기록
- TodoWrite 내용을 docs/CURRENT/active-todos.md에 동기화

**산출물:** 성능 데이터와 함께 검증된 기획 문서