"""
텔레그램 메시지 유틸리티 함수들
Utilities for handling telegram message length limits and formatting
"""
import re
from typing import List, Callable, Any, Optional


def split_long_message(
    text: str, 
    max_length: int = 4000, 
    preserve_markdown: bool = False
) -> List[str]:
    """
    긴 텍스트를 텔레그램 메시지 길이 제한에 맞게 분할
    
    Args:
        text: 분할할 텍스트
        max_length: 최대 메시지 길이 (기본: 5000자)
        preserve_markdown: 마크다운 서식 보존 여부
        
    Returns:
        분할된 메시지 목록
    """
    if len(text) <= max_length:
        return [text]
    
    messages = []
    current_pos = 0
    
    while current_pos < len(text):
        # 남은 텍스트가 제한보다 작으면 그대로 추가
        if current_pos + max_length >= len(text):
            messages.append(text[current_pos:])
            break
        
        # 자연스러운 분할 지점 찾기
        chunk = text[current_pos:current_pos + max_length]
        
        # 줄바꿈을 기준으로 분할 (우선순위 1)
        last_newline = chunk.rfind('\n')
        if last_newline > max_length * 0.7:  # 70% 이상 위치에서 줄바꿈 발견
            split_point = last_newline
        else:
            # 단어 경계에서 분할 (우선순위 2)
            last_space = chunk.rfind(' ')
            if last_space > max_length * 0.7:
                split_point = last_space
            else:
                # 강제 분할
                split_point = max_length - 3  # "..." 를 위한 공간
                chunk = chunk[:split_point] + "..."
        
        # 현재 청크를 메시지에 추가
        current_chunk = text[current_pos:current_pos + split_point]
        
        # 마크다운 보존이 필요한 경우 처리
        if preserve_markdown:
            current_chunk = _balance_markdown(current_chunk)
        
        messages.append(current_chunk)
        current_pos += split_point
        
        # 줄바꿈으로 분할된 경우 다음 문자가 줄바꿈이면 건너뛰기
        if current_pos < len(text) and text[current_pos] == '\n':
            current_pos += 1
    
    # 연속 메시지임을 표시 (길이 제한 내에서)
    if len(messages) > 1:
        continuation_start = "\n_(계속)_\n"  # 12 chars
        continuation_end = "\n_(계속...)_"    # 12 chars
        
        for i, msg in enumerate(messages):
            available_space = max_length - len(msg)
            
            if i == 0 and available_space >= 12:
                messages[i] = f"{msg}{continuation_end}"
            elif i == len(messages) - 1 and available_space >= 12:
                messages[i] = f"{continuation_start}{msg}"
            elif i > 0 and i < len(messages) - 1 and available_space >= 24:
                messages[i] = f"{continuation_start}{msg}{continuation_end}"
            # 공간이 부족하면 표시 생략
    
    return messages


def _balance_markdown(text: str) -> str:
    """
    텍스트에서 불완전한 마크다운 서식을 균형맞춤
    
    Args:
        text: 균형을 맞출 텍스트
        
    Returns:
        균형이 맞춰진 텍스트
    """
    # ** (bold) 균형 맞추기
    bold_count = text.count('**')
    if bold_count % 2 == 1:
        # 마지막 ** 제거하거나 끝에 추가
        last_bold = text.rfind('**')
        if last_bold > len(text) * 0.8:  # 끝부분에 있으면 제거
            text = text[:last_bold] + text[last_bold + 2:]
        else:  # 앞부분에 있으면 끝에 추가
            text += "**"
    
    # ` (code) 균형 맞추기
    code_count = text.count('`')
    if code_count % 2 == 1:
        last_code = text.rfind('`')
        if last_code > len(text) * 0.8:
            text = text[:last_code] + text[last_code + 1:]
        else:
            text += "`"
    
    # * (italic) 균형 맞추기
    # ** 가 아닌 단일 * 를 찾기
    single_asterisks = re.findall(r'(?<!\*)\*(?!\*)', text)
    if len(single_asterisks) % 2 == 1:
        # 간단히 마지막 단일 * 제거
        text = re.sub(r'(?<!\*)\*(?!\*)(?=.*(?<!\*)\*(?!\*))', '', text, count=1)
    
    return text


async def safe_send_message(
    send_func: Callable, 
    text: str, 
    max_length: int = 4000,
    preserve_markdown: bool = True,
    **kwargs
) -> None:
    """
    안전한 텔레그램 메시지 전송 (자동 분할 지원)
    
    Args:
        send_func: 메시지 전송 함수 (일반적으로 update.message.reply_text)
        text: 전송할 텍스트
        max_length: 최대 메시지 길이
        preserve_markdown: 마크다운 보존 여부
        **kwargs: send_func에 전달할 추가 인자들
    """
    if len(text) <= max_length:
        # 단일 메시지로 전송
        await send_func(text, **kwargs)
        return
    
    # 메시지 분할 후 전송
    messages = split_long_message(text, max_length, preserve_markdown)
    
    # reply_markup은 마지막 메시지에만 추가
    reply_markup = kwargs.pop('reply_markup', None)
    
    for i, message in enumerate(messages):
        if i == len(messages) - 1 and reply_markup:
            # 마지막 메시지에만 버튼 추가
            await send_func(message, reply_markup=reply_markup, **kwargs)
        else:
            await send_func(message, **kwargs)


def get_telegram_max_length() -> int:
    """
    현재 설정된 텔레그램 메시지 최대 길이 반환
    
    Returns:
        최대 메시지 길이 (문자 수)
    """
    return 4000  # 텔레그램 실제 제한(4096)에서 약간 여유를 둠


def is_message_too_long(text: str, max_length: Optional[int] = None) -> bool:
    """
    메시지가 텔레그램 제한을 초과하는지 확인
    
    Args:
        text: 확인할 텍스트
        max_length: 최대 길이 (None이면 기본값 사용)
        
    Returns:
        길이 초과 여부
    """
    if max_length is None:
        max_length = get_telegram_max_length()
    
    return len(text) > max_length