"""
Conservative Working State Detector

사용자 피드백 반영: "esc to interrupt만 검출하고 나머지는 놓치는게 차라리 더 체감 오류가 적었어"

핵심 철학:
1. 확실하지 않으면 작업 안함으로 판단 (놓치는 것 > 오탐지)
2. "esc to interrupt"만 신뢰할 수 있는 신호로 간주
3. 상세한 로깅으로 놓친 케이스 학습
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DetectionContext:
    """Working state detection의 컨텍스트 정보"""
    session_name: str
    timestamp: float
    screen_content: str
    lines_analyzed: int
    prompt_found: bool
    patterns_found: List[str]
    patterns_checked: List[str]
    decision: bool
    confidence: float
    reasoning: str


class ConservativeWorkingDetector:
    """
    보수적 작업 상태 감지기
    
    "esc to interrupt" 위주의 안정적 감지 + 상세한 놓침 로깅
    """
    
    def __init__(self):
        # 1순위: 가장 신뢰할 수 있는 패턴 (보수적)
        self.high_confidence_patterns = [
            "esc to interrupt"  # Claude Code의 가장 안정적 신호
        ]
        
        # 2순위: 명확한 작업 신호들 (추후 점진적 추가용)
        self.medium_confidence_patterns = [
            "Running",          # 명령 실행 (포괄적)
            "Building",         # 빌드 진행  
            "Installing",       # 설치 진행
            "Downloading",      # 다운로드 진행
        ]
        
        # 3순위: 가변적 패턴들 (현재는 로깅만, 탐지 안함)
        self.low_confidence_patterns = [
            "Thinking…",        # Claude 사고 과정
            "Processing",       # 일반적 처리
            "Analyzing",        # 분석 과정
            "Searching",        # 검색 과정
            "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"  # 스피너
        ]
        
        # 프롬프트 패턴들
        self.prompt_patterns = [
            '>',               # Claude 편집 프롬프트
            '│ >',            # 박스 프롬프트  
            '$ ',             # Bash 프롬프트
            '❯ ',             # Zsh 프롬프트
            '>>> ',           # Python 프롬프트
        ]
        
        # 놓친 케이스 로깅을 위한 저장소
        self.missed_cases: List[DetectionContext] = []
        self.max_missed_cases = 100
        
        # 설정
        self.confidence_threshold = 0.90  # 보수적 임계값
        self.analysis_lines = 8           # 분석할 최근 라인 수
    
    def detect_working_state(self, session_name: str, screen_content: str) -> DetectionContext:
        """
        보수적 작업 상태 감지 + 상세 로깅
        
        Returns:
            DetectionContext: 판단 결과와 상세 컨텍스트
        """
        start_time = time.time()
        
        if not screen_content:
            return DetectionContext(
                session_name=session_name,
                timestamp=start_time,
                screen_content="",
                lines_analyzed=0,
                prompt_found=False,
                patterns_found=[],
                patterns_checked=[],
                decision=False,
                confidence=0.0,
                reasoning="Empty screen content"
            )
        
        lines = screen_content.split('\n')
        recent_lines = lines[-self.analysis_lines:]
        recent_content = '\n'.join(recent_lines)
        
        # 1순위: 프롬프트 체크
        prompt_found, prompt_reasoning = self._check_for_prompts(recent_lines)
        if prompt_found:
            return DetectionContext(
                session_name=session_name,
                timestamp=start_time,
                screen_content=screen_content,
                lines_analyzed=len(recent_lines),
                prompt_found=True,
                patterns_found=[],
                patterns_checked=self.high_confidence_patterns,
                decision=False,
                confidence=0.95,
                reasoning=f"Prompt detected: {prompt_reasoning}"
            )
        
        # 2순위: 높은 신뢰도 패턴만 체크 (보수적)
        patterns_found = []
        all_patterns_checked = []
        
        for pattern in self.high_confidence_patterns:
            all_patterns_checked.append(pattern)
            if pattern in recent_content:
                patterns_found.append(pattern)
        
        # 놓친 패턴들도 로깅 (학습용)
        missed_patterns = self._log_missed_patterns(recent_content)
        all_patterns_checked.extend(missed_patterns)
        
        # 결정
        working = len(patterns_found) > 0
        confidence = 0.95 if working else 0.0
        
        reasoning = f"Conservative: Found {patterns_found}" if working else "Conservative: No high-confidence patterns"
        
        context = DetectionContext(
            session_name=session_name,
            timestamp=start_time,
            screen_content=screen_content,
            lines_analyzed=len(recent_lines),
            prompt_found=False,
            patterns_found=patterns_found,
            patterns_checked=all_patterns_checked,
            decision=working,
            confidence=confidence,
            reasoning=reasoning
        )
        
        # 놓친 케이스라면 로깅
        if not working and self._might_be_missed_case(recent_content):
            self._log_missed_case(context, recent_content)
        
        return context
    
    def _check_for_prompts(self, lines: List[str]) -> tuple[bool, str]:
        """프롬프트 존재 확인"""
        for i in range(len(lines) - 1, max(len(lines) - 5, -1), -1):
            if i < 0 or i >= len(lines):
                continue
                
            line = lines[i]
            stripped = line.strip()
            
            if not stripped:
                continue
            
            # 다양한 프롬프트 패턴 체크
            if stripped == '>':
                return True, "Claude edit prompt"
            if stripped == '│ >':
                return True, "Claude boxed prompt"
            if line.endswith('$ '):
                return True, "Bash prompt"
            if line.endswith('❯ '):
                return True, "Zsh prompt"
            if line.endswith('>>> '):
                return True, "Python prompt"
            if stripped.endswith('>'):
                return True, f"Generic prompt: {stripped}"
        
        return False, ""
    
    def _log_missed_patterns(self, content: str) -> List[str]:
        """놓칠 수 있는 패턴들을 로깅 (학습용)"""
        missed = []
        
        # 중간 신뢰도 패턴들 체크
        for pattern in self.medium_confidence_patterns:
            if pattern in content:
                missed.append(f"MEDIUM:{pattern}")
        
        # 낮은 신뢰도 패턴들 체크  
        for pattern in self.low_confidence_patterns:
            if pattern in content:
                missed.append(f"LOW:{pattern}")
        
        return missed
    
    def _might_be_missed_case(self, content: str) -> bool:
        """놓친 케이스일 가능성이 있는지 확인"""
        # 중간/낮은 신뢰도 패턴이 있으면 놓친 케이스일 수 있음
        for pattern in self.medium_confidence_patterns + self.low_confidence_patterns:
            if pattern in content:
                return True
        return False
    
    def _log_missed_case(self, context: DetectionContext, content: str):
        """놓친 케이스 로깅"""
        self.missed_cases.append(context)
        
        # 로그 크기 제한
        if len(self.missed_cases) > self.max_missed_cases:
            self.missed_cases.pop(0)
        
        # 상세 로깅
        logger.info(f"🔍 Potential missed case for {context.session_name}")
        logger.debug(f"Content: {content[-200:]}")  # 마지막 200자만
        
        # 놓친 패턴들 분석
        missed_medium = [p for p in self.medium_confidence_patterns if p in content]
        missed_low = [p for p in self.low_confidence_patterns if p in content]
        
        if missed_medium:
            logger.info(f"📊 Missed MEDIUM confidence patterns: {missed_medium}")
        if missed_low:
            logger.debug(f"📊 Missed LOW confidence patterns: {missed_low}")
    
    def get_missed_cases_summary(self) -> Dict[str, Any]:
        """놓친 케이스들의 요약 정보"""
        if not self.missed_cases:
            return {"total": 0, "patterns": {}}
        
        pattern_count = {}
        for case in self.missed_cases:
            content = case.screen_content[-500:]  # 마지막 500자 분석
            
            for pattern in self.medium_confidence_patterns + self.low_confidence_patterns:
                if pattern in content:
                    pattern_count[pattern] = pattern_count.get(pattern, 0) + 1
        
        # 빈도 순 정렬
        sorted_patterns = sorted(pattern_count.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "total": len(self.missed_cases),
            "patterns": dict(sorted_patterns),
            "recent_sessions": [case.session_name for case in self.missed_cases[-5:]],
            "time_range": {
                "start": min(case.timestamp for case in self.missed_cases),
                "end": max(case.timestamp for case in self.missed_cases)
            }
        }
    
    def suggest_improvements(self) -> List[str]:
        """놓친 케이스 분석 기반 개선 제안"""
        summary = self.get_missed_cases_summary()
        suggestions = []
        
        if summary["total"] == 0:
            return ["No missed cases detected. Conservative approach working well."]
        
        # 자주 놓친 패턴 상위 3개
        top_patterns = list(summary["patterns"].items())[:3]
        
        for pattern, count in top_patterns:
            percentage = (count / summary["total"]) * 100
            if percentage > 20:  # 20% 이상 놓친 패턴
                suggestions.append(
                    f"Consider adding '{pattern}' to high-confidence patterns "
                    f"(missed in {count}/{summary['total']} cases, {percentage:.1f}%)"
                )
        
        return suggestions if suggestions else [
            "Missed cases are diverse - current conservative approach is appropriate"
        ]


# 글로벌 인스턴스
conservative_detector = ConservativeWorkingDetector()