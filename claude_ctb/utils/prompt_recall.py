"""
마지막 프롬프트 회상 시스템

사용자의 마지막 프롬프트를 추출하고 스마트 트렁케이션하여
알림 메시지에 컨텍스트 정보를 제공합니다.
"""

import subprocess
import re
import logging
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptRecallSystem:
    """마지막 프롬프트 회상 시스템"""
    
    def __init__(self):
        # Claude Code 환경의 사용자 입력 패턴 (더 정확한 패턴)
        self.user_input_patterns = [
            r'Human:\s*(.+?)(?=\n\n|\nAssistant:|$)',          # Claude Code 대화
            r'^>\s*(.+?)(?=\n|$)',                             # 일반 프롬프트 (줄 시작)
            r'^\s*user:\s*(.+?)(?=\n|$)',                      # 터미널 입력 (줄 시작)
            r'^\s*You:\s*(.+?)(?=\n|$)',                       # 대화 형태 (줄 시작)
            # Claude Code의 실제 프롬프트 입력 패턴들 추가
            r'^\s*@[\w가-힣]+\s+(.+?)(?=\n|$)',               # @명령어 형태
            r'^\s*([가-힣a-zA-Z].{10,}[?!.])\s*$',            # 한글/영문 문장 (10자 이상, 문장 부호 끝)
        ]
    
    def extract_last_user_prompt(self, session_name: str) -> str:
        """
        마지막 사용자 프롬프트 추출 with fallback mechanism

        Args:
            session_name: tmux 세션 이름

        Returns:
            str: 마지막 사용자 프롬프트 또는 오류 메시지
        """
        # Tier 1: Try 200 lines first (fast path)
        prompt = self._extract_prompt_with_lines(session_name, lines=200)

        if prompt and prompt not in ["프롬프트를 찾을 수 없습니다", ""]:
            return prompt

        # Tier 2: Fallback to 500 lines if not found
        logger.debug(f"Prompt not found in 200 lines, trying 500 for {session_name}")
        prompt = self._extract_prompt_with_lines(session_name, lines=500)

        if prompt and prompt not in ["프롬프트를 찾을 수 없습니다", ""]:
            return prompt

        # Final fallback: return explicit failure message
        return "최근 프롬프트 없음 (500줄 내)"

    def _extract_prompt_with_lines(self, session_name: str, lines: int) -> str:
        """
        Internal helper to extract prompt with specified line depth

        Args:
            session_name: tmux 세션 이름
            lines: 검색할 줄 수

        Returns:
            str: 추출된 프롬프트 또는 빈 문자열
        """
        try:
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{lines}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return ""

            prompts = self._detect_user_prompts(result.stdout)
            if prompts:
                return prompts[-1]
            return ""

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout extracting prompt ({lines} lines) for {session_name}")
            return ""
        except Exception as e:
            logger.error(f"Error extracting prompt: {e}")
            return ""
    
    def _detect_user_prompts(self, screen_content: str) -> List[str]:
        """
        화면에서 사용자 프롬프트들 추출
        
        Args:
            screen_content: tmux 화면 내용
            
        Returns:
            List[str]: 발견된 사용자 프롬프트들
        """
        prompts = []
        
        # 일단 줄 단위로 분석하여 실제 사용자 입력만 추출
        lines = screen_content.split('\n')
        
        for line in lines:
            # 간단한 패턴들로 한 줄씩 검사
            simple_patterns = [
                r'^>\s*(.+)$',                    # > 프롬프트
                r'^❯\s*(.+)$',                   # ❯ 프롬프트 
                r'^Human:\s*(.+)$',              # Human: 프롬프트
                r'^사용자:\s*(.+)$',              # 한글 사용자:
                r'^@[\w가-힣]+\s+(.+)$',         # @명령어 형태
            ]
            
            for pattern in simple_patterns:
                match = re.match(pattern, line.strip())
                if match:
                    clean_prompt = match.group(1).strip()
                    # 길이와 의미 검사
                    if (len(clean_prompt) >= 5 and 
                        len(clean_prompt) <= 500 and  # 너무 긴 것도 제외
                        self._is_meaningful_prompt(clean_prompt)):
                        prompts.append(clean_prompt)
                    break  # 한 줄에서 하나의 패턴만 매칭
        
        # 중복 제거하면서 순서 유지 (마지막 5개만 보관)
        unique_prompts = list(dict.fromkeys(prompts))
        return unique_prompts[-5:] if len(unique_prompts) > 5 else unique_prompts
    
    def _is_meaningful_prompt(self, prompt: str) -> bool:
        """
        의미있는 프롬프트인지 판단
        
        Args:
            prompt: 프롬프트 텍스트
            
        Returns:
            bool: 의미있는 프롬프트 여부
        """
        # 너무 짧거나 의미없는 내용 필터링
        meaningless_patterns = [
            r'^[0-9]+$',           # 숫자만
            r'^[yYnN]$',          # 단순 y/n
            r'^(yes|no)$',        # yes/no
            r'^(quit|exit|q)$',   # 종료 명령어
            r'^\s*$',             # 빈 문자열
            r'^[0-9]+\.\s*Yes',   # "1. Yes" 형태의 UI 선택지
            r'^[0-9]+\.\s*No',    # "2. No" 형태의 UI 선택지  
            r'^❯\s*[0-9]+\.',     # "❯ 1." 형태의 UI 선택지
            r'^(Yes|No)\s*등',     # "Yes 등", "No 등" 형태
            r'^\w+\s*등$',        # "단어 등" 형태
            r'^(Continue|Stop|Cancel)\s*\?*$',  # UI 버튼류
        ]
        
        for pattern in meaningless_patterns:
            if re.match(pattern, prompt, re.IGNORECASE):
                return False
        
        # UI 선택지 패턴도 필터링
        ui_choice_patterns = [
            r'[0-9]+\.\s*(Yes|No|Continue|Stop)',
            r'❯.*?(Yes|No|Continue|Stop)',
            r'^(Choose|Select|Pick).*?[0-9]+',
        ]
        
        for pattern in ui_choice_patterns:
            if re.search(pattern, prompt, re.IGNORECASE):
                return False
                
        return True
    
    def smart_truncate_prompt(self, prompt: str, max_length: int = 200) -> str:
        """
        프롬프트 지능형 자르기
        
        Args:
            prompt: 원본 프롬프트
            max_length: 최대 길이 (기본 200자)
            
        Returns:
            str: 트렁케이션된 프롬프트
        """
        if not prompt or len(prompt) <= max_length:
            return f'"{prompt}"' if prompt else '"프롬프트 없음"'
        
        # 앞뒤 보존 전략
        front_keep = max_length // 2 - 15  # 앞 부분 유지할 길이
        back_keep = max_length // 2 - 15   # 뒤 부분 유지할 길이
        
        # 단어 경계에서 자르기 시도
        front_part = self._truncate_at_word_boundary(prompt[:front_keep], front_keep)
        back_part = self._truncate_at_word_boundary(prompt[-back_keep:], back_keep, from_end=True)
        
        return f'"{front_part}...(중간 생략)...{back_part}"'
    
    def _truncate_at_word_boundary(self, text: str, max_length: int, from_end: bool = False) -> str:
        """
        단어 경계에서 자르기
        
        Args:
            text: 자를 텍스트
            max_length: 최대 길이
            from_end: 끝에서부터 자르기 여부
            
        Returns:
            str: 단어 경계에서 잘린 텍스트
        """
        if len(text) <= max_length:
            return text.strip()
        
        if from_end:
            # 끝에서부터 자르는 경우
            truncated = text[-(max_length-10):]  # 여유 공간 확보
            # 첫 번째 공백까지 제거하여 단어 경계 맞추기
            space_idx = truncated.find(' ')
            if space_idx > 0:
                truncated = truncated[space_idx+1:]
        else:
            # 앞에서부터 자르는 경우  
            truncated = text[:max_length-10]  # 여유 공간 확보
            # 마지막 공백까지만 유지하여 단어 경계 맞추기
            space_idx = truncated.rfind(' ')
            if space_idx > 0:
                truncated = truncated[:space_idx]
        
        return truncated.strip()
    
    def get_context_summary(self, session_name: str, include_stats: bool = False) -> dict:
        """
        세션의 컨텍스트 요약 정보 반환
        
        Args:
            session_name: 세션 이름
            include_stats: 통계 정보 포함 여부
            
        Returns:
            dict: 컨텍스트 요약 정보
        """
        last_prompt = self.extract_last_user_prompt(session_name)
        truncated_prompt = self.smart_truncate_prompt(last_prompt)
        
        context = {
            'session_name': session_name,
            'last_prompt': last_prompt,
            'truncated_prompt': truncated_prompt,
            'timestamp': datetime.now().isoformat()
        }
        
        if include_stats:
            context.update({
                'prompt_length': len(last_prompt),
                'truncated_length': len(truncated_prompt),
                'truncated': len(last_prompt) > 200
            })
        
        return context


# 전역 인스턴스 (싱글톤 패턴)
prompt_recall_system = PromptRecallSystem()


def get_last_prompt_for_session(session_name: str) -> str:
    """
    편의 함수: 세션의 마지막 프롬프트 가져오기
    
    Args:
        session_name: 세션 이름
        
    Returns:
        str: 트렁케이션된 마지막 프롬프트
    """
    last_prompt = prompt_recall_system.extract_last_user_prompt(session_name)
    return prompt_recall_system.smart_truncate_prompt(last_prompt)


def get_context_for_notification(session_name: str) -> str:
    """
    편의 함수: 알림용 컨텍스트 정보 생성
    
    Args:
        session_name: 세션 이름
        
    Returns:
        str: 알림에 포함할 컨텍스트 문자열
    """
    truncated_prompt = get_last_prompt_for_session(session_name)
    
    if "프롬프트" in truncated_prompt and ("찾을 수 없습니다" in truncated_prompt or "실패" in truncated_prompt or "오류" in truncated_prompt):
        return ""  # 오류 메시지인 경우 빈 문자열 반환
    
    return f"📤 마지막 요청: {truncated_prompt}\n\n"