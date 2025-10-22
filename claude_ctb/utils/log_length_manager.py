"""
동적 로그 길이 조절 시스템

사용자가 알림 메시지의 로그 길이를 동적으로 조절할 수 있는 기능을 제공합니다.
100/150/200/300 줄 옵션 중에서 선택 가능합니다.
"""

import os
import json
import logging
from typing import Literal, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

LogLengthOption = Literal[100, 150, 200, 300]


class LogLengthManager:
    """동적 로그 길이 관리자"""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        로그 길이 관리자 초기화
        
        Args:
            config_dir: 설정 파일 저장 디렉토리 (기본값: ~/.claude-ops)
        """
        self.config_dir = Path(config_dir or os.path.expanduser("~/.claude-ops"))
        self.config_file = self.config_dir / "log_length_settings.json"
        self.default_length = 200  # 기본 200줄
        
        # 설정 디렉토리 생성
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 설정 로드
        self._load_settings()
    
    def _load_settings(self) -> None:
        """설정 파일에서 로그 길이 설정 로드"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.current_length = data.get('log_length', self.default_length)
            else:
                self.current_length = self.default_length
                self._save_settings()  # 기본 설정 저장
                
        except Exception as e:
            logger.warning(f"Failed to load log length settings: {e}")
            self.current_length = self.default_length
    
    def _save_settings(self) -> None:
        """현재 로그 길이 설정을 파일에 저장"""
        try:
            settings = {
                'log_length': self.current_length,
                'last_updated': __import__('datetime').datetime.now().isoformat()
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save log length settings: {e}")
    
    def get_current_length(self) -> LogLengthOption:
        """현재 설정된 로그 길이 반환"""
        return self.current_length
    
    def set_log_length(self, length: LogLengthOption) -> bool:
        """
        로그 길이 설정
        
        Args:
            length: 설정할 로그 길이 (100, 150, 200, 300 중 하나)
            
        Returns:
            bool: 설정 성공 여부
        """
        if length not in [100, 150, 200, 300]:
            logger.error(f"Invalid log length: {length}. Must be one of [100, 150, 200, 300]")
            return False
        
        try:
            old_length = self.current_length
            self.current_length = length
            self._save_settings()
            
            logger.info(f"Log length changed from {old_length} to {length}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set log length: {e}")
            return False
    
    def increase_log_length(self) -> LogLengthOption:
        """
        로그 길이를 다음 단계로 증가
        
        Returns:
            LogLengthOption: 새로운 로그 길이
        """
        length_options = [100, 150, 200, 300]
        
        try:
            current_index = length_options.index(self.current_length)
            next_index = (current_index + 1) % len(length_options)
            new_length = length_options[next_index]
            
            self.set_log_length(new_length)
            return new_length
            
        except ValueError:
            # 현재 길이가 옵션에 없으면 기본값으로 설정
            self.set_log_length(self.default_length)
            return self.default_length
    
    def decrease_log_length(self) -> LogLengthOption:
        """
        로그 길이를 이전 단계로 감소
        
        Returns:
            LogLengthOption: 새로운 로그 길이
        """
        length_options = [100, 150, 200, 300]
        
        try:
            current_index = length_options.index(self.current_length)
            prev_index = (current_index - 1) % len(length_options)
            new_length = length_options[prev_index]
            
            self.set_log_length(new_length)
            return new_length
            
        except ValueError:
            # 현재 길이가 옵션에 없으면 기본값으로 설정
            self.set_log_length(self.default_length)
            return self.default_length
    
    def get_status_summary(self) -> str:
        """현재 로그 길이 설정 상태 요약 반환"""
        return f"현재 로그 길이: {self.current_length}줄"
    
    def get_all_options(self) -> list[LogLengthOption]:
        """사용 가능한 모든 로그 길이 옵션 반환"""
        return [100, 150, 200, 300]
    
    def reset_to_default(self) -> LogLengthOption:
        """기본 로그 길이로 재설정"""
        self.set_log_length(self.default_length)
        return self.default_length


# 전역 인스턴스 (싱글톤 패턴)
log_length_manager = LogLengthManager()


def get_current_log_length() -> LogLengthOption:
    """편의 함수: 현재 로그 길이 반환"""
    return log_length_manager.get_current_length()


def set_log_length(length: LogLengthOption) -> bool:
    """편의 함수: 로그 길이 설정"""
    return log_length_manager.set_log_length(length)


def cycle_log_length() -> LogLengthOption:
    """편의 함수: 로그 길이 순환 (100 → 150 → 200 → 300 → 100 → ...)"""
    return log_length_manager.increase_log_length()