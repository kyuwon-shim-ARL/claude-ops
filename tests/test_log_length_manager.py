"""
동적 로그 길이 관리자 테스트

로그 길이 조절 기능의 단위 테스트를 포함합니다.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from claude_ops.utils.log_length_manager import (
    LogLengthManager, 
    get_current_log_length,
    set_log_length,
    cycle_log_length
)


class TestLogLengthManager:
    """LogLengthManager 테스트"""
    
    def test_init_creates_config_directory(self):
        """설정 디렉토리가 생성되는지 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            assert manager.config_dir.exists()
            assert manager.config_file.exists()
    
    def test_default_log_length(self):
        """기본 로그 길이가 200줄인지 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            assert manager.get_current_length() == 200
    
    def test_set_valid_log_length(self):
        """유효한 로그 길이 설정 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            for length in [100, 150, 200, 300]:
                success = manager.set_log_length(length)
                assert success
                assert manager.get_current_length() == length
    
    def test_set_invalid_log_length(self):
        """무효한 로그 길이 설정 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            invalid_lengths = [50, 250, 500, -100, 0]
            for length in invalid_lengths:
                success = manager.set_log_length(length)
                assert not success
                # 기본값 유지
                assert manager.get_current_length() == 200
    
    def test_increase_log_length(self):
        """로그 길이 증가 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            # 100 → 150 → 200 → 300 → 100 순환 테스트
            manager.set_log_length(100)
            assert manager.increase_log_length() == 150
            assert manager.increase_log_length() == 200
            assert manager.increase_log_length() == 300
            assert manager.increase_log_length() == 100  # 순환
    
    def test_decrease_log_length(self):
        """로그 길이 감소 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            # 300 → 200 → 150 → 100 → 300 순환 테스트
            manager.set_log_length(300)
            assert manager.decrease_log_length() == 200
            assert manager.decrease_log_length() == 150
            assert manager.decrease_log_length() == 100
            assert manager.decrease_log_length() == 300  # 순환
    
    def test_settings_persistence(self):
        """설정 파일 저장/로드 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 첫 번째 매니저로 설정
            manager1 = LogLengthManager(temp_dir)
            manager1.set_log_length(300)
            
            # 두 번째 매니저로 로드 확인
            manager2 = LogLengthManager(temp_dir)
            assert manager2.get_current_length() == 300
    
    def test_reset_to_default(self):
        """기본값 재설정 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            # 다른 값으로 설정 후 재설정
            manager.set_log_length(100)
            reset_value = manager.reset_to_default()
            
            assert reset_value == 200
            assert manager.get_current_length() == 200
    
    def test_get_status_summary(self):
        """상태 요약 반환 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            manager.set_log_length(150)
            
            summary = manager.get_status_summary()
            assert "150줄" in summary
    
    def test_get_all_options(self):
        """모든 옵션 반환 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            options = manager.get_all_options()
            
            assert options == [100, 150, 200, 300]
    
    @patch('claude_ops.utils.log_length_manager.json.dump')
    def test_save_error_handling(self, mock_dump):
        """설정 저장 오류 처리 테스트"""
        mock_dump.side_effect = IOError("파일 쓰기 실패")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            # 저장이 실패해도 메모리의 값은 설정됨
            manager.set_log_length(300)
            assert manager.current_length == 300
    
    def test_load_corrupted_settings(self):
        """손상된 설정 파일 로드 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "log_length_settings.json"
            
            # 잘못된 JSON 파일 생성
            with open(config_file, 'w') as f:
                f.write("잘못된 JSON 내용")
            
            manager = LogLengthManager(temp_dir)
            # 기본값으로 fallback
            assert manager.get_current_length() == 200


class TestGlobalFunctions:
    """전역 함수들 테스트"""
    
    @patch('claude_ops.utils.log_length_manager.log_length_manager')
    def test_get_current_log_length(self, mock_manager):
        """전역 get_current_log_length 함수 테스트"""
        mock_manager.get_current_length.return_value = 150
        
        result = get_current_log_length()
        assert result == 150
        mock_manager.get_current_length.assert_called_once()
    
    @patch('claude_ops.utils.log_length_manager.log_length_manager')
    def test_set_log_length_function(self, mock_manager):
        """전역 set_log_length 함수 테스트"""
        mock_manager.set_log_length.return_value = True
        
        result = set_log_length(200)
        assert result is True
        mock_manager.set_log_length.assert_called_once_with(200)
    
    @patch('claude_ops.utils.log_length_manager.log_length_manager')
    def test_cycle_log_length_function(self, mock_manager):
        """전역 cycle_log_length 함수 테스트"""
        mock_manager.increase_log_length.return_value = 300
        
        result = cycle_log_length()
        assert result == 300
        mock_manager.increase_log_length.assert_called_once()


class TestIntegration:
    """통합 테스트"""
    
    def test_concurrent_access(self):
        """동시 접근 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager1 = LogLengthManager(temp_dir)
            manager2 = LogLengthManager(temp_dir)
            
            # 첫 번째 매니저로 설정
            manager1.set_log_length(150)
            
            # 두 번째 매니저는 캐시된 값을 가지고 있을 수 있음
            manager2._load_settings()  # 강제 리로드
            assert manager2.get_current_length() == 150
    
    def test_full_workflow(self):
        """전체 워크플로우 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LogLengthManager(temp_dir)
            
            # 기본값 확인
            assert manager.get_current_length() == 200
            
            # 순환 테스트
            assert manager.increase_log_length() == 300
            assert manager.increase_log_length() == 100
            assert manager.increase_log_length() == 150
            assert manager.increase_log_length() == 200  # 원래 값으로 돌아옴
            
            # 감소 테스트
            assert manager.decrease_log_length() == 150
            
            # 직접 설정 테스트
            assert manager.set_log_length(300)
            assert manager.get_current_length() == 300
            
            # 재설정 테스트
            assert manager.reset_to_default() == 200
            assert manager.get_current_length() == 200