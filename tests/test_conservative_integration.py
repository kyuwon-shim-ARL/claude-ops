"""
Integration Test for Conservative Detection System

전체 시스템 통합 테스트
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from claude_ops.utils.conservative_detector import conservative_detector
from claude_ops.monitoring.missed_case_analyzer import MissedCaseAnalyzer
from claude_ops.utils.session_state import SessionStateAnalyzer


class TestConservativeSystemIntegration:
    """전체 시스템 통합 테스트"""
    
    def test_end_to_end_detection_and_analysis(self):
        """탐지부터 분석까지 전체 플로우 테스트"""
        
        # 1. 여러 케이스 탐지
        test_cases = [
            ("Working (esc to interrupt)", True),   # 탐지됨
            ("Running tests...", False),            # 놓침 (로깅)
            ("Building project...", False),         # 놓침 (로깅)
            ("Just normal output", False),          # 정상
            ("Task (esc to interrupt)\n>", False),  # 프롬프트 우선
        ]
        
        for content, expected in test_cases:
            context = conservative_detector.detect_working_state("test_session", content)
            assert context.decision == expected
        
        # 2. 놓친 케이스 요약
        summary = conservative_detector.get_missed_cases_summary()
        assert summary["total"] >= 2  # Running, Building 최소 2개
        
        # 3. 개선 제안 생성
        suggestions = conservative_detector.suggest_improvements()
        assert len(suggestions) > 0
        
        # 4. 분석기로 리포트 생성
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            analyzer = MissedCaseAnalyzer(tmp.name)
            analysis = analyzer.analyze_current_state()
            
            assert "summary" in analysis
            assert "suggestions" in analysis
            assert "analysis" in analysis
            
            # 정리
            Path(tmp.name).unlink(missing_ok=True)
    
    def test_session_state_integration(self):
        """SessionStateAnalyzer와의 완벽한 통합"""
        
        analyzer = SessionStateAnalyzer()
        
        # 보수적 탐지 사용 확인
        test_screens = [
            ("Working on task (esc to interrupt)", True),
            ("Running something", False),  # 보수적이므로 탐지 안함
            ("Idle screen\n>", False),
        ]
        
        for screen, expected in test_screens:
            result = analyzer._detect_working_state(screen)
            assert result == expected
    
    def test_backward_compatibility(self):
        """기존 코드와의 호환성"""
        
        analyzer = SessionStateAnalyzer()
        
        # 기존 메서드들이 여전히 동작
        assert hasattr(analyzer, '_detect_working_state')
        assert hasattr(analyzer, '_detect_working_state_original')
        assert hasattr(analyzer, 'get_state')
        
        # 원본 메서드도 여전히 호출 가능
        original_result = analyzer._detect_working_state_original("Some content")
        assert isinstance(original_result, bool)
    
    def test_configuration_flexibility(self):
        """설정 변경 가능성 테스트"""
        
        # 패턴 추가 가능
        original_count = len(conservative_detector.high_confidence_patterns)
        conservative_detector.high_confidence_patterns.append("TestPattern")
        assert len(conservative_detector.high_confidence_patterns) == original_count + 1
        
        # 원복
        conservative_detector.high_confidence_patterns.pop()
        
        # 임계값 조정 가능
        original_threshold = conservative_detector.confidence_threshold
        conservative_detector.confidence_threshold = 0.85
        assert conservative_detector.confidence_threshold == 0.85
        
        # 원복
        conservative_detector.confidence_threshold = original_threshold
    
    def test_missed_case_persistence(self):
        """놓친 케이스 지속성 테스트"""
        
        # 여러 놓친 케이스 생성
        for i in range(3):
            conservative_detector.detect_working_state(
                f"session_{i}", 
                f"Running task {i}..."
            )
        
        # 요약에 반영 확인
        summary = conservative_detector.get_missed_cases_summary()
        assert summary["total"] >= 3
        assert "Running" in summary["patterns"]
    
    def test_improvement_plan_generation(self):
        """개선 계획 생성 테스트"""
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            analyzer = MissedCaseAnalyzer(tmp.name)
            
            # 명확한 패턴으로 여러 케이스 생성
            for _ in range(10):
                conservative_detector.detect_working_state(
                    "test", 
                    "Building important project..."
                )
            
            plan = analyzer.generate_improvement_plan()
            
            assert "recommendations" in plan
            assert len(plan["recommendations"]) > 0
            
            # 높은 빈도 패턴이 추천되는지 확인
            if plan["recommendations"]:
                rec = plan["recommendations"][0]
                assert "Building" in str(rec) or "pattern" in rec.get("type", "")
            
            # 정리
            Path(tmp.name).unlink(missing_ok=True)


class TestTelegramCommandIntegration:
    """텔레그램 명령어 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_detection_commands_exist(self):
        """명령어 함수들이 존재하는지 확인"""
        from claude_ops.telegram.commands.detection_analysis import DETECTION_COMMANDS
        
        expected_commands = [
            'detection_status',
            'detection_report',
            'detection_trends',
            'detection_improve'
        ]
        
        for cmd in expected_commands:
            assert cmd in DETECTION_COMMANDS
            assert callable(DETECTION_COMMANDS[cmd])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])