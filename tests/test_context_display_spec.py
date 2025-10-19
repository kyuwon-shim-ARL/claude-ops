"""
컨텍스트 잔량 표시 기능 테스트 스펙
Tests for context window remaining display in summary command
"""
import unittest
from unittest.mock import patch, MagicMock
from claude_ctb.utils.session_summary import SessionSummaryHelper

class TestContextDisplaySpec(unittest.TestCase):
    """컨텍스트 잔량 표시 기능 테스트 스펙"""
    
    def setUp(self):
        self.summary_helper = SessionSummaryHelper()
    
    def test_context_status_shows_comfortable_when_no_warning(self):
        """경고 없을 때 '여유' 상태 표시"""
        # Given: 컨텍스트 경고가 없는 상태
        with patch.object(self.summary_helper, '_detect_context_warning', return_value=None):
            # When: summary 생성
            result = self.summary_helper.generate_summary("test-session")
            
            # Then: '여유' 상태 표시
            self.assertIn("📊 컨텍스트: 여유", result)
            self.assertNotIn("경고", result)
    
    def test_context_status_shows_percentage_when_warning_exists(self):
        """경고 있을 때 구체적 사용률 표시"""
        # Given: 85% 사용 경고 상태
        warning_info = {
            'usage_percent': 85,
            'remaining_tokens': 15000,
            'total_tokens': 100000
        }
        with patch.object(self.summary_helper, '_detect_context_warning', return_value=warning_info):
            # When: summary 생성
            result = self.summary_helper.generate_summary("test-session")
            
            # Then: 구체적 사용률 표시
            self.assertIn("📊 컨텍스트: 85% 사용됨", result)
            self.assertIn("(15K 토큰 남음)", result)
    
    def test_context_status_shows_critical_warning_at_90_percent(self):
        """90% 이상 사용 시 주의 메시지"""
        # Given: 92% 사용 상태
        warning_info = {
            'usage_percent': 92,
            'remaining_tokens': 8000,
            'total_tokens': 100000
        }
        with patch.object(self.summary_helper, '_detect_context_warning', return_value=warning_info):
            # When: summary 생성
            result = self.summary_helper.generate_summary("test-session")
            
            # Then: 주의 표시와 함께 잔량 표시
            self.assertIn("⚠️ 컨텍스트: 92% 사용됨", result)
            self.assertIn("(8K 토큰 남음)", result)
            self.assertIn("곧 정리 필요", result)
    
    def test_context_detection_failure_shows_fallback_message(self):
        """컨텍스트 감지 실패 시 기본 메시지"""
        # Given: 컨텍스트 감지 실패 (예외 발생)
        with patch.object(self.summary_helper, '_detect_context_warning', side_effect=Exception("감지 실패")):
            # When: summary 생성
            result = self.summary_helper.generate_summary("test-session")
            
            # Then: 기본 메시지 표시
            self.assertIn("📊 컨텍스트: 상태 확인 불가", result)
    
    def test_context_display_preserves_existing_summary_content(self):
        """기존 summary 내용이 보존됨"""
        # Given: 정상적인 세션 상태
        with patch.object(self.summary_helper, '_detect_context_warning', return_value=None):
            # When: summary 생성
            result = self.summary_helper.generate_summary("test-session")
            
            # Then: 기존 정보 + 컨텍스트 정보 모두 포함
            self.assertIn("test-session", result)
            self.assertIn("상태:", result)
            self.assertIn("컨텍스트:", result)


class TestContextDetectionSpec(unittest.TestCase):
    """컨텍스트 감지 기능 테스트 스펙"""
    
    def test_detect_context_warning_from_tmux_output(self):
        """tmux 출력에서 컨텍스트 경고 감지"""
        # Given: 컨텍스트 경고가 포함된 tmux 출력
        tmux_output = """
        [Previous conversation content...]
        ⚠️ Context window approaching limit (85% used, ~15K tokens remaining)
        [Current conversation...]
        """
        
        helper = SessionSummaryHelper()
        
        # When: 컨텍스트 경고 감지
        result = helper._detect_context_warning(tmux_output)
        
        # Then: 올바른 정보 추출
        self.assertEqual(result['usage_percent'], 85)
        self.assertEqual(result['remaining_tokens'], 15000)
    
    def test_detect_context_warning_returns_none_when_no_warning(self):
        """경고 없을 때 None 반환"""
        # Given: 경고가 없는 tmux 출력
        tmux_output = "Normal conversation content without warnings"
        
        helper = SessionSummaryHelper()
        
        # When: 컨텍스트 경고 감지
        result = helper._detect_context_warning(tmux_output)
        
        # Then: None 반환
        self.assertIsNone(result)