"""
Claude Dev Kit Prompt Loader

Centralized prompt management system that loads prompts from claude-dev-kit repository.
Provides caching, fallback mechanisms, and error handling.
"""

import requests
import json
import logging
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class ClaudeDevKitPrompts:
    """Load and cache prompts from claude-dev-kit repository"""
    
    BASE_URL = "https://raw.githubusercontent.com/kyuwon-shim-ARL/claude-dev-kit/main/prompts"
    CACHE_TTL = 3600  # 1 hour cache
    
    def __init__(self):
        self.cache = {}
        self.cache_timestamps = {}
        self.fallback_prompts = self._get_fallback_prompts()
        self.load_prompts()
    
    def _get_fallback_prompts(self) -> Dict[str, str]:
        """Fallback prompts in case remote loading fails"""
        return {
            "@기획": """🎯 **기획 (Structured Discovery & Planning Loop)**

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

**산출물:** 구체적인 실행 계획과 성공 기준이 포함된 PRD""",
            
            "@구현": """⚡ **구현 (Implementation with DRY)**

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

**산출물:** 테스트 통과하는 동작 가능한 코드""",
            
            "@안정화": """🔧 **안정화 (Structural Sustainability Protocol v2.0)**

**패러다임 전환:** 기능 중심 → **구조적 지속가능성** 중심

**6단계 통합 검증 루프:**

1. **Repository Structure Scan**
   - 전체 파일 분석: 디렉토리 구조, 파일 목적성 검토
   - 중복/임시 파일 식별 및 정리 방안 수립
   - 파일 크기 및 복잡도 분석

2. **Structural Optimization**
   - 디렉토리 정리: 논리적 그룹핑, 계층 구조 최적화
   - 파일 분류: 목적별, 기능별 체계적 분류
   - 네이밍 표준화: 일관된 명명 규칙 적용

3. **Dependency Resolution**
   - Import 수정: 순환 참조 해결, 의존성 최적화
   - 참조 오류 해결: 깨진 링크, 잘못된 경로 수정
   - 환경 동기화: requirements, configs 일치성 확인

4. **Comprehensive Testing**
   - 모듈 검증: 각 모듈별 단위 테스트
   - API 테스트: 인터페이스 동작 확인
   - 시스템 무결성 확인: 전체 시스템 통합 테스트

5. **Documentation Sync**
   - CLAUDE.md 반영: 변경사항 문서화
   - README 업데이트: 사용법, 설치법 최신화
   - .gitignore 정리: 불필요한 파일 제외 규칙 정비

6. **Quality Assurance**
   - MECE 분석: 빠진 것은 없는지, 중복은 없는지 확인
   - 성능 벤치마크: 기준 성능 대비 측정
   - 정량 평가: 코드 커버리지, 복잡도, 품질 지표

**예방적 관리 트리거:**
- 루트 20개 파일 이상
- 임시 파일 5개 이상
- Import 오류 3개 이상
→ 자동 안정화 프로세스 실행

**산출물:** 지속가능하고 확장 가능한 깔끔한 코드베이스""",
            
            "@배포": """🚀 **배포 (Deployment)**

**최종 검증:**
- 체크리스트 완료 확인: 모든 TODO 완료, 테스트 통과
- 코드 리뷰: 보안, 성능, 코딩 표준 최종 점검
- 배포 전 시나리오 테스트: 프로덕션 환경 시뮬레이션

**구조화 커밋:**
- 의미있는 커밋 메시지: 변경사항의 목적과 영향 명시
- 원자성 보장: 하나의 논리적 변경사항 = 하나의 커밋
- 관련 이슈/티켓 링크: 추적가능성 확보

**원격 배포:**
- 푸시: origin 저장소로 변경사항 전송
- 버전 태깅: semantic versioning (major.minor.patch)
- 배포 스크립트 실행: CI/CD 파이프라인 트리거

**배포 후 모니터링:**
- 서비스 상태 확인: 헬스체크, 로그 모니터링
- 성능 지표 추적: 응답시간, 처리량, 오류율
- 롤백 준비: 문제 발생 시 즉시 이전 버전으로 복구

**산출물:** 안정적으로 운영되는 프로덕션 서비스"""
        }
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached prompt is still valid"""
        if key not in self.cache_timestamps:
            return False
        return (time.time() - self.cache_timestamps[key]) < self.CACHE_TTL
    
    def load_prompts(self) -> None:
        """Load prompts from claude-dev-kit repository"""
        try:
            logger.info("🔄 Loading prompts from claude-dev-kit...")
            
            # Load individual prompts
            keywords = ["기획", "구현", "안정화", "배포"]
            for keyword in keywords:
                try:
                    url = f"{self.BASE_URL}/telegram-format/{keyword}.json"
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        prompt_key = f"@{keyword}"
                        self.cache[prompt_key] = data["message"]
                        self.cache_timestamps[prompt_key] = time.time()
                        logger.debug(f"✅ Loaded prompt: {prompt_key}")
                    else:
                        logger.warning(f"⚠️ Failed to load {keyword}: HTTP {response.status_code}")
                except Exception as e:
                    logger.warning(f"⚠️ Error loading {keyword}: {e}")
            
            # Load workflow combinations if available
            workflows = ["전체사이클", "개발완료", "품질보증", "기획구현"]
            for workflow in workflows:
                try:
                    url = f"{self.BASE_URL}/raw/{workflow}.txt"
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        workflow_key = f"@{workflow}"
                        self.cache[workflow_key] = response.text
                        self.cache_timestamps[workflow_key] = time.time()
                        logger.debug(f"✅ Loaded workflow: {workflow_key}")
                except Exception as e:
                    logger.debug(f"📝 Workflow {workflow} not available: {e}")
            
            logger.info(f"✅ Loaded {len(self.cache)} prompts from claude-dev-kit")
                    
        except Exception as e:
            logger.error(f"❌ Error loading prompts from claude-dev-kit: {e}")
            logger.info("🔄 Using fallback prompts")
    
    def get_prompt(self, keyword: str) -> str:
        """Get prompt by keyword with cache and fallback support"""
        # Check cache first
        if keyword in self.cache and self._is_cache_valid(keyword):
            return self.cache[keyword]
        
        # Try to reload if cache is stale
        if keyword not in self.cache or not self._is_cache_valid(keyword):
            self.load_prompts()
            if keyword in self.cache:
                return self.cache[keyword]
        
        # Fallback to local prompts
        if keyword in self.fallback_prompts:
            logger.info(f"🔄 Using fallback prompt for {keyword}")
            return self.fallback_prompts[keyword]
        
        return f"프롬프트 '{keyword}'를 찾을 수 없습니다."
    
    def refresh_cache(self) -> None:
        """Manually refresh the prompt cache"""
        logger.info("🔄 Manually refreshing prompt cache...")
        self.load_prompts()
    
    def get_available_prompts(self) -> list:
        """Get list of available prompt keywords"""
        all_prompts = set(self.cache.keys()) | set(self.fallback_prompts.keys())
        return sorted(list(all_prompts))