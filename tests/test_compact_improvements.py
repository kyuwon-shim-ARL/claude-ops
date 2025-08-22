"""
Test improvements for /compact detector - ZED guide and duplicate prevention
"""

import pytest
from unittest.mock import Mock, patch
from claude_ops.utils.compact_detector import CompactPromptDetector


class TestZEDGuideExtraction:
    """Test ZED guide prompt extraction"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.detector = CompactPromptDetector()
    
    def test_extract_zed_block(self):
        """Test extracting ZED code block"""
        screen_content = """
        작업이 완료되었습니다.
        이제 `/compact`를 실행하여 다음 문서를 작성하세요:
        
        ```zed
        ## Overview
        This session implemented the /compact bridge system
        
        ### Key Components
        - CompactPromptDetector: Detects suggestions
        - CompactExecutor: Executes commands
        - TelegramHandler: Sends notifications
        
        ### Results
        - 17/17 tests passing
        - Full integration complete
        ```
        """
        
        guide = self.detector.extract_zed_guide(screen_content)
        assert guide is not None
        assert "## Overview" in guide
        assert "Key Components" in guide
        assert "CompactPromptDetector" in guide
    
    def test_extract_structured_content(self):
        """Test extracting structured content after /compact"""
        screen_content = """
        개발 완료!
        
        이제 `/compact`를 실행하세요.
        
        다음 내용을 문서화합니다:
        
        ## 구현 내용
        - /compact 감지 시스템
        - 텔레그램 알림 통합
        - ZED 가이드 추출
        
        ## 테스트 결과
        - 모든 테스트 통과
        - 성능 최적화 완료
        """
        
        guide = self.detector.extract_zed_guide(screen_content)
        assert guide is not None
        assert "## 구현 내용" in guide
        assert "## 테스트 결과" in guide
    
    def test_no_zed_guide(self):
        """Test when there's no ZED guide"""
        screen_content = """
        작업 중입니다.
        아직 완료되지 않았습니다.
        """
        
        guide = self.detector.extract_zed_guide(screen_content)
        assert guide is None
    
    def test_analyze_context_with_zed(self):
        """Test full context analysis with ZED guide"""
        screen_content = """
        작업 완료!
        
        이제 `/compact --archive`를 실행하세요.
        
        ## Session Summary
        - Implemented /compact bridge
        - Added Telegram integration
        - Created comprehensive tests
        
        ## Next Steps
        - Deploy to production
        - Monitor performance
        """
        
        analysis = self.detector.analyze_context(screen_content)
        
        assert analysis['has_suggestion'] == True
        assert '/compact --archive' in analysis['commands']
        assert analysis['zed_guide'] is not None
        assert "## Session Summary" in analysis['zed_guide']


class TestDuplicatePrevention:
    """Test duplicate notification prevention"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.detector = CompactPromptDetector()
    
    def test_content_hash_based_caching(self):
        """Test that duplicate prevention is based on content hash"""
        screen_content1 = """
        작업 완료!
        이제 `/compact`를 실행하세요.
        """
        
        screen_content2 = """
        작업 완료!
        이제 `/compact`를 실행하세요.
        """  # Same content
        
        screen_content3 = """
        다른 작업 완료!
        이제 `/compact`를 실행하세요.
        """  # Different content
        
        # First check - should notify
        assert self.detector.should_notify("session1", screen_content1) == True
        
        # Same content - should NOT notify
        assert self.detector.should_notify("session1", screen_content2) == False
        
        # Different content - should notify
        assert self.detector.should_notify("session1", screen_content3) == True
    
    def test_different_sessions_independent(self):
        """Test that different sessions have independent caches"""
        screen_content = """
        작업 완료!
        이제 `/compact`를 실행하세요.
        """
        
        # First session - should notify
        assert self.detector.should_notify("session1", screen_content) == True
        
        # Different session, same content - should also notify
        assert self.detector.should_notify("session2", screen_content) == True
        
        # Same session again - should NOT notify
        assert self.detector.should_notify("session1", screen_content) == False
    
    def test_cache_expiration(self):
        """Test that cache entries expire after TTL"""
        from datetime import datetime, timedelta
        
        screen_content = """
        작업 완료!
        이제 `/compact`를 실행하세요.
        """
        
        # First notification
        assert self.detector.should_notify("session1", screen_content) == True
        
        # Manually expire the cache entry
        import hashlib
        lines = screen_content.split('\n')
        relevant_content = '\n'.join(lines[-100:])
        content_hash = hashlib.md5(relevant_content.encode()).hexdigest()
        cache_key = f"session1:{content_hash}"
        
        # Set timestamp to past (beyond TTL)
        self.detector._notification_cache[cache_key] = datetime.now() - timedelta(hours=2)
        
        # Should notify again after expiration
        assert self.detector.should_notify("session1", screen_content) == True


class TestRealScenarios:
    """Test real-world scenarios"""
    
    def test_complete_workflow_with_zed(self):
        """Test complete workflow with ZED guide"""
        detector = CompactPromptDetector()
        
        # Claude outputs /compact with ZED guide
        screen_content = """
        ✅ 모든 구현이 완료되었습니다!
        
        이제 `/compact`를 실행하여 세션을 정리하세요.
        
        다음 내용으로 문서를 작성합니다:
        
        ## 📦 /compact Bridge System Implementation
        
        ### Overview
        Successfully implemented a bridge system that detects /compact suggestions
        from Claude and provides one-click execution via Telegram.
        
        ### Key Features
        - Automatic detection of /compact suggestions
        - Telegram notification with executable buttons
        - Multi-step command support
        - ZED guide extraction and forwarding
        
        ### Technical Details
        - Pattern matching for various /compact formats
        - Content-based duplicate prevention
        - Session-specific notification management
        
        ### Results
        - 17/17 tests passing
        - Integrated with monitoring system
        - Deployed to production
        """
        
        # Analyze the content
        analysis = detector.analyze_context(screen_content)
        
        # Verify detection
        assert analysis['has_suggestion'] == True
        assert '/compact' in analysis['commands']
        
        # Verify ZED guide extraction
        assert analysis['zed_guide'] is not None
        assert "## 📦 /compact Bridge System Implementation" in analysis['zed_guide']
        assert "### Key Features" in analysis['zed_guide']
        assert "ZED guide extraction and forwarding" in analysis['zed_guide']
        
        # Verify notification should be sent
        assert detector.should_notify("claude_project", screen_content) == True
        
        # Verify duplicate prevention
        assert detector.should_notify("claude_project", screen_content) == False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])