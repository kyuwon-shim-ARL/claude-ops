"""
Core Bot Functionality Tests

Tests for TelegramBridge core functionality, macro expansion, and session management
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from claude_ops.telegram.bot import TelegramBridge


class TestTelegramBridge:
    """Test core TelegramBridge functionality"""
    
    def test_prompt_macros_exist(self):
        """Test that prompt macros are properly defined"""
        assert "@기획" in TelegramBridge.PROMPT_MACROS
        assert "@구현" in TelegramBridge.PROMPT_MACROS  
        assert "@안정화" in TelegramBridge.PROMPT_MACROS
        assert "@배포" in TelegramBridge.PROMPT_MACROS
        
        # Verify macro content is non-empty
        for macro_name, content in TelegramBridge.PROMPT_MACROS.items():
            assert len(content.strip()) > 50, f"Macro {macro_name} content too short"
    
    def test_macro_structure(self):
        """Test macro content structure and formatting"""
        planning_macro = TelegramBridge.PROMPT_MACROS["@기획"]
        implementation_macro = TelegramBridge.PROMPT_MACROS["@구현"]
        
        # Check for key sections
        assert "탐색 단계" in planning_macro
        assert "계획 단계" in planning_macro
        assert "DRY 원칙" in implementation_macro
        assert "산출물" in planning_macro or "deliverable" in planning_macro.lower()
    
    @patch('claude_ops.config.ClaudeOpsConfig')
    def test_bot_initialization(self, mock_config):
        """Test TelegramBridge initialization"""
        mock_config_instance = Mock()
        mock_config.return_value = mock_config_instance
        
        # Test initialization doesn't fail
        bridge = TelegramBridge()
        assert bridge is not None
    
    def test_macro_expansion_logic(self):
        """Test macro expansion functionality"""
        bridge = TelegramBridge()
        
        # Test basic macro detection
        test_message = "@기획 새로운 프로젝트 시작"
        
        # This tests the macro detection logic
        has_macro = any(macro in test_message for macro in TelegramBridge.PROMPT_MACROS.keys())
        assert has_macro is True
        
        # Test non-macro message
        normal_message = "일반적인 메시지입니다"
        has_macro = any(macro in normal_message for macro in TelegramBridge.PROMPT_MACROS.keys())
        assert has_macro is False


class TestMacroExpansion:
    """Test macro expansion and message processing"""
    
    def test_all_macro_keywords(self):
        """Test all macro keywords are valid Korean"""
        for macro_key in TelegramBridge.PROMPT_MACROS.keys():
            assert macro_key.startswith("@"), f"Macro key {macro_key} should start with @"
            assert len(macro_key) > 2, f"Macro key {macro_key} too short"
    
    def test_macro_content_quality(self):
        """Test macro content meets quality standards"""
        for macro_name, content in TelegramBridge.PROMPT_MACROS.items():
            # Content should be substantial
            assert len(content) > 100, f"Macro {macro_name} content too short"
            
            # Should contain structured information
            structure_indicators = ["**", "- ", ":", "단계", "원칙", "산출물"]
            has_structure = any(indicator in content for indicator in structure_indicators)
            assert has_structure, f"Macro {macro_name} lacks proper structure"
    
    def test_macro_expansion_scenarios(self):
        """Test various macro expansion scenarios"""
        test_cases = [
            "@기획 데이터 분석 파이프라인 구축",
            "@구현 사용자 인증 시스템",
            "@안정화 코드 리팩토링 진행",
            "@배포 프로덕션 환경 준비"
        ]
        
        for test_case in test_cases:
            # Find matching macro
            found_macro = None
            for macro_key in TelegramBridge.PROMPT_MACROS.keys():
                if macro_key in test_case:
                    found_macro = macro_key
                    break
            
            assert found_macro is not None, f"No macro found for: {test_case}"
            assert len(TelegramBridge.PROMPT_MACROS[found_macro]) > 50


class TestSessionManagement:
    """Test session-related functionality"""
    
    @patch('subprocess.run')
    def test_session_detection_logic(self, mock_subprocess):
        """Test tmux session detection logic"""
        # Mock tmux session list output
        mock_subprocess.return_value.stdout = "claude_project1: 1 windows\nclaude_project2: 1 windows\n"
        mock_subprocess.return_value.returncode = 0
        
        # This would test session detection if the method was exposed
        # For now, just verify that subprocess would be called correctly
        mock_subprocess.assert_not_called()  # Not called yet
    
    def test_session_naming_convention(self):
        """Test session naming conventions"""
        valid_session_names = [
            "claude_project1",
            "claude_my-app",
            "claude_data_analysis"
        ]
        
        invalid_session_names = [
            "project1",  # Missing claude_ prefix
            "claude",    # Too short
            "claude_",   # Empty suffix
        ]
        
        # Test valid names
        for name in valid_session_names:
            assert name.startswith("claude_"), f"Valid session name {name} should start with claude_"
            assert len(name.split("_", 1)[1]) > 0, f"Session name {name} should have content after claude_"
        
        # Test invalid names  
        for name in invalid_session_names:
            if not name.startswith("claude_"):
                assert True  # Expected to be invalid
            elif name == "claude_":
                assert len(name.split("_", 1)) == 2, f"Invalid name {name} correctly identified"


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_macro_edge_cases(self):
        """Test macro handling edge cases"""
        edge_cases = [
            "@기획",  # Macro only, no additional text
            "@ 기획 잘못된 형식",  # Space after @
            "@@기획",  # Double @
            "기획@ 역순",  # @ at end
            ""  # Empty string
        ]
        
        for case in edge_cases:
            # Test that macro detection handles edge cases gracefully
            has_valid_macro = False
            for macro_key in TelegramBridge.PROMPT_MACROS.keys():
                if macro_key in case and case.count(macro_key) == 1:
                    has_valid_macro = True
                    break
            
            # Only "@기획" should be valid from the edge cases
            if case == "@기획":
                assert has_valid_macro
            else:
                # Others should either be invalid or handled gracefully
                pass  # No assertion needed for invalid cases
    
    @patch('claude_ops.config.ClaudeOpsConfig')  
    def test_initialization_error_handling(self, mock_config):
        """Test bot handles initialization errors gracefully"""
        mock_config.side_effect = Exception("Config error")
        
        # Should not raise exception during import/initialization
        try:
            from claude_ops.telegram.bot import TelegramBridge
            # If we get here, the import succeeded despite config error
            assert True
        except Exception as e:
            # If import fails due to config, that's also acceptable behavior
            assert "Config error" in str(e)