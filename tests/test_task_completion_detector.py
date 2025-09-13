"""
Test Task Completion Detector

Tests for the enhanced task completion detection system.
"""

import pytest
from datetime import datetime
from claude_ops.utils.task_completion_detector import (
    TaskCompletionDetector,
    TaskType,
    AlertPriority,
    TaskCompletion
)


class TestTaskCompletionDetector:
    """Test suite for task completion detector"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.detector = TaskCompletionDetector()
    
    def test_detect_build_success(self):
        """Test detection of successful build completion"""
        screen_content = """
        > npm run build
        
        Building project...
        Webpack: Compiling modules...
        Build succeeded
        Bundle size: 1.2MB
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.BUILD_PROCESS
        assert completion.priority == AlertPriority.NORMAL
        assert "Build" in completion.message
        assert completion.confidence >= 0.8
    
    def test_detect_build_failure(self):
        """Test detection of build failure"""
        screen_content = """
        > npm run build
        
        Building project...
        Error: Build failed
        SyntaxError: Unexpected token in file.js
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.priority == AlertPriority.CRITICAL
        assert "Error" in completion.message
        assert completion.confidence >= 0.9
    
    def test_detect_test_success(self):
        """Test detection of successful test execution"""
        screen_content = """
        > pytest
        
        ============================= test session starts ==============================
        collected 42 items
        
        tests/test_module.py ..........................................
        
        ============================= 42 tests passed in 3.45s ===========================
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.TEST_EXECUTION
        assert completion.priority == AlertPriority.NORMAL
        assert "Test" in completion.message
        assert "3.45" in completion.details
    
    def test_detect_test_failure(self):
        """Test detection of test failures"""
        screen_content = """
        > pytest
        
        ============================= test session starts ==============================
        collected 10 items
        
        tests/test_module.py .....F....
        
        FAILED tests/test_module.py::test_important_function
        
        ============================= 1 test failed, 9 passed in 1.23s ===========================
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.TEST_EXECUTION
        assert completion.priority == AlertPriority.HIGH
        assert completion.confidence >= 0.9
    
    def test_detect_installation_success(self):
        """Test detection of successful package installation"""
        screen_content = """
        > npm install axios
        
        added 5 packages, and audited 1234 packages in 2s
        
        found 0 vulnerabilities
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.INSTALLATION
        assert completion.priority == AlertPriority.NORMAL
        assert "Installation" in completion.message or "Install" in completion.message
        assert "5" in completion.details
    
    def test_detect_deployment_success(self):
        """Test detection of successful deployment"""
        screen_content = """
        > vercel deploy --prod
        
        Uploading files...
        Building project...
        Deployment successful!
        
        Successfully deployed to https://app.vercel.app
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.DEPLOYMENT
        assert completion.priority == AlertPriority.HIGH
        assert "Deployment" in completion.message or "Deploy" in completion.message
        assert completion.confidence >= 0.9
    
    def test_detect_file_operations(self):
        """Test detection of file operations"""
        screen_content = """
        > Creating components...
        
        File created: src/components/Button.tsx
        File created: src/components/Modal.tsx
        Successfully wrote to 2 files
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.FILE_OPERATION
        assert completion.priority == AlertPriority.LOW
        assert "File" in completion.message
    
    def test_detect_search_completion(self):
        """Test detection of search operation completion"""
        screen_content = """
        > grep -r "TODO" src/
        
        src/app.js:12: // TODO: Implement error handling
        src/utils.js:45: // TODO: Add unit tests
        
        Found 2 matches in 2 files
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert completion.task_type == TaskType.SEARCH_OPERATION
        assert completion.priority == AlertPriority.LOW
        assert "Search" in completion.message or "Found" in completion.message
    
    def test_priority_ordering(self):
        """Test that error patterns take priority over success patterns"""
        screen_content = """
        > npm test
        
        Running tests...
        Test completed
        Error: 1 test failed
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        # Error should take priority even though "completed" is present
        assert completion.priority == AlertPriority.CRITICAL
    
    def test_confidence_calculation(self):
        """Test confidence score calculation"""
        # Short content should have lower confidence
        short_content = "Done!"
        completion = self.detector.detect_completion(short_content)
        if completion:
            assert completion.confidence < 0.8
        
        # Rich content with multiple indicators should have higher confidence
        rich_content = """
        > npm test
        
        Running test suite...
        ✓ Component tests passed
        ✓ Integration tests passed
        ✓ E2E tests passed
        
        All tests passed successfully!
        Test run completed in 5.2s
        0 failures
        
        $ 
        """
        completion = self.detector.detect_completion(rich_content)
        assert completion is not None
        assert completion.confidence >= 0.9
    
    def test_duplicate_detection_prevention(self):
        """Test that duplicate detections are prevented"""
        screen_content = """
        Build succeeded
        All tests passed
        """
        
        # First detection should work
        completion1 = self.detector.detect_completion(screen_content)
        assert completion1 is not None
        
        # Immediate second detection of same pattern should be blocked
        completion2 = self.detector.detect_completion(screen_content)
        assert completion2 is None
        
        # After clearing recent detections, should work again
        self.detector.recent_detections.clear()
        completion3 = self.detector.detect_completion(screen_content)
        assert completion3 is not None
    
    def test_extract_details(self):
        """Test extraction of relevant details from content"""
        screen_content = """
        > npm test
        
        Test Suites: 5 passed, 5 total
        Tests: 42 passed, 42 total
        Time: 3.456s
        Coverage: 85.3%
        
        $ 
        """
        
        completion = self.detector.detect_completion(screen_content)
        assert completion is not None
        assert "3.456" in completion.details
        assert "42" in completion.details
        assert "85.3" in completion.details  # Percentage without % sign
    
    def test_task_type_detection(self):
        """Test correct task type identification"""
        test_cases = [
            ("webpack: Compiled successfully", TaskType.BUILD_PROCESS),
            ("All tests passed", TaskType.TEST_EXECUTION),
            ("Successfully installed packages", TaskType.INSTALLATION),
            ("Deploy complete", TaskType.DEPLOYMENT),
            ("File created: test.js", TaskType.FILE_OPERATION),
            ("Found 5 matches", TaskType.SEARCH_OPERATION),
            ("Bug fixed", TaskType.DEBUGGING),
            ("Generated 3 files", TaskType.CODE_GENERATION),
            ("Task completed", TaskType.GENERAL),
        ]
        
        for content, expected_type in test_cases:
            completion = self.detector.detect_completion(content)
            if completion:
                assert completion.task_type == expected_type, f"Failed for: {content}"
    
    def test_get_priority_emoji(self):
        """Test emoji selection for different priorities"""
        assert self.detector.get_priority_emoji(AlertPriority.CRITICAL) == "🚨"
        assert self.detector.get_priority_emoji(AlertPriority.HIGH) == "⚠️"
        assert self.detector.get_priority_emoji(AlertPriority.NORMAL) == "✅"
        assert self.detector.get_priority_emoji(AlertPriority.LOW) == "ℹ️"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
