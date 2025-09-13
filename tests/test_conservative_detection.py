"""
Test Conservative Working Detection

보수적 탐지 시스템의 동작 검증
"""

import pytest
from unittest.mock import Mock, patch
from claude_ops.utils.conservative_detector import ConservativeWorkingDetector, DetectionContext


class TestConservativeDetection:
    """보수적 탐지 시스템 테스트"""
    
    def setup_method(self):
        """테스트 설정"""
        self.detector = ConservativeWorkingDetector()
    
    def test_esc_to_interrupt_detection(self):
        """'esc to interrupt' 패턴 정확히 감지"""
        screen_content = """
Some output
✻ Working on task... (esc to interrupt)
More output
        """
        
        context = self.detector.detect_working_state("test_session", screen_content)
        
        assert context.decision is True
        assert "esc to interrupt" in context.patterns_found
        assert context.confidence >= 0.90
        assert "Conservative: Found" in context.reasoning
    
    def test_prompt_overrides_esc_interrupt(self):
        """프롬프트가 있으면 esc to interrupt 무시"""
        screen_content = """
Old output (esc to interrupt)
Some other content
>
        """
        
        context = self.detector.detect_working_state("test_session", screen_content)
        
        assert context.decision is False
        assert context.prompt_found is True
        assert "Prompt detected" in context.reasoning
    
    def test_medium_patterns_logged_but_not_detected(self):
        """중간 신뢰도 패턴들은 로깅되지만 탐지 안됨"""
        screen_content = """
Running command...
Building project...
        """
        
        context = self.detector.detect_working_state("test_session", screen_content)
        
        # 보수적이므로 탐지 안됨
        assert context.decision is False
        
        # 하지만 놓친 패턴으로 기록됨
        missed_patterns = [p for p in context.patterns_checked if "MEDIUM:" in p]
        assert len(missed_patterns) > 0
    
    def test_low_patterns_logged_only(self):
        """낮은 신뢰도 패턴들은 로깅만"""
        screen_content = """
Thinking about the problem...
Processing data...
        """
        
        context = self.detector.detect_working_state("test_session", screen_content)
        
        # 탐지 안됨
        assert context.decision is False
        
        # 로깅됨
        missed_patterns = [p for p in context.patterns_checked if "LOW:" in p]
        assert len(missed_patterns) > 0
    
    def test_empty_content(self):
        """빈 화면 처리"""
        context = self.detector.detect_working_state("test_session", "")
        
        assert context.decision is False
        assert context.confidence == 0.0
        assert "Empty screen content" in context.reasoning
    
    def test_various_prompt_types(self):
        """다양한 프롬프트 타입 인식"""
        test_cases = [
            ("Previous output\n>", True),
            ("Some text\n│ >", True),
            ("command output\nuser@host$ ", True),
            ("python session\n>>> ", True),
            ("zsh prompt\nuser@host ❯ ", True),
        ]
        
        for screen_content, should_find_prompt in test_cases:
            context = self.detector.detect_working_state("test_session", screen_content)
            assert context.prompt_found == should_find_prompt
            if should_find_prompt:
                assert context.decision is False
    
    def test_missed_case_logging(self):
        """놓친 케이스 로깅 확인"""
        # 초기 상태
        initial_count = len(self.detector.missed_cases)
        
        # 놓칠만한 케이스 (중간 신뢰도 패턴)
        screen_content = "Building the project..."
        context = self.detector.detect_working_state("test_session", screen_content)
        
        # 탐지 안됨 (보수적)
        assert context.decision is False
        
        # 놓친 케이스로 로깅됨
        assert len(self.detector.missed_cases) > initial_count
    
    def test_summary_generation(self):
        """요약 정보 생성"""
        # 몇 개 놓친 케이스 생성
        test_cases = [
            "Running tests...",
            "Building project...", 
            "Running another command...",
        ]
        
        for case in test_cases:
            self.detector.detect_working_state("test_session", case)
        
        summary = self.detector.get_missed_cases_summary()
        
        assert summary["total"] >= len(test_cases)
        assert "Running" in summary["patterns"] or "Building" in summary["patterns"]
    
    def test_improvement_suggestions(self):
        """개선 제안 생성"""
        # 동일 패턴 여러 번 놓치기
        for _ in range(5):
            self.detector.detect_working_state("test_session", "Running important task...")
        
        suggestions = self.detector.suggest_improvements()
        
        assert len(suggestions) > 0
        # "Running" 패턴 추가 제안이 있어야 함
        running_suggested = any("Running" in s for s in suggestions)
        assert running_suggested
    
    def test_confidence_levels(self):
        """신뢰도 수준 확인"""
        # 높은 신뢰도: esc to interrupt
        high_confidence = self.detector.detect_working_state(
            "test_session", 
            "Task in progress (esc to interrupt)"
        )
        assert high_confidence.confidence >= 0.90
        
        # 낮은 신뢰도: 프롬프트 상태
        low_confidence = self.detector.detect_working_state(
            "test_session",
            "Some output\n>"
        )
        assert low_confidence.confidence >= 0.90  # 프롬프트 감지도 높은 신뢰도
        
        # 불확실: 아무 패턴 없음
        uncertain = self.detector.detect_working_state(
            "test_session",
            "Just some regular output"
        )
        assert uncertain.confidence == 0.0


class TestConservativeIntegration:
    """보수적 탐지의 전체 시스템 통합 테스트"""
    
    def test_session_state_integration(self):
        """SessionStateAnalyzer와의 통합"""
        from claude_ops.utils.session_state import SessionStateAnalyzer
        
        analyzer = SessionStateAnalyzer()
        
        # 보수적 탐지 사용하는지 확인
        result = analyzer._detect_working_state("Task (esc to interrupt)")
        assert isinstance(result, bool)
        
        # 프롬프트 우선 확인
        result_with_prompt = analyzer._detect_working_state("Task (esc to interrupt)\n>")
        assert result_with_prompt is False
    
    def test_backwards_compatibility(self):
        """기존 인터페이스 호환성"""
        from claude_ops.utils.session_state import SessionStateAnalyzer
        
        analyzer = SessionStateAnalyzer()
        
        # 기존 방식대로 호출 가능
        result = analyzer._detect_working_state("Some content")
        assert isinstance(result, bool)
        
        # 기존 get_state 메서드도 동작
        state = analyzer.get_state("test_session", use_cache=False)
        assert state is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])