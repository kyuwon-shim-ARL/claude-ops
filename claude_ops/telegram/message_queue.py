"""
파일 기반 메시지 큐 시스템

텔레그램에서 오는 키보드 입력을 파일로 저장하고,
multi_monitor에서 주기적으로 확인하여 처리합니다.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MessageQueue:
    """파일 기반 메시지 큐"""
    
    def __init__(self, queue_dir: str = "/tmp/claude-ops-messages"):
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(exist_ok=True)
        self.processed_dir = self.queue_dir / "processed"
        self.processed_dir.mkdir(exist_ok=True)
    
    def add_message(self, message_text: str, user_id: Optional[str] = None) -> bool:
        """메시지를 큐에 추가"""
        try:
            timestamp = time.time()
            message_id = f"{int(timestamp * 1000)}_{hash(message_text) % 10000}"
            
            message_data = {
                "id": message_id,
                "text": message_text,
                "user_id": user_id,
                "timestamp": timestamp,
                "datetime": datetime.now().isoformat(),
                "processed": False
            }
            
            message_file = self.queue_dir / f"msg_{message_id}.json"
            
            with open(message_file, 'w', encoding='utf-8') as f:
                json.dump(message_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Added message to queue: {message_text[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add message to queue: {e}")
            return False
    
    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """처리 대기 중인 메시지들 반환"""
        try:
            pending = []
            
            for msg_file in self.queue_dir.glob("msg_*.json"):
                try:
                    with open(msg_file, 'r', encoding='utf-8') as f:
                        message_data = json.load(f)
                    
                    if not message_data.get("processed", False):
                        pending.append(message_data)
                        
                except Exception as e:
                    logger.warning(f"Failed to read message file {msg_file}: {e}")
            
            # 시간순 정렬
            pending.sort(key=lambda x: x.get("timestamp", 0))
            return pending
            
        except Exception as e:
            logger.error(f"Failed to get pending messages: {e}")
            return []
    
    def mark_processed(self, message_id: str) -> bool:
        """메시지를 처리 완료로 표시하고 이동"""
        try:
            message_file = self.queue_dir / f"msg_{message_id}.json"
            
            if not message_file.exists():
                return False
            
            # 처리 완료 표시
            with open(message_file, 'r', encoding='utf-8') as f:
                message_data = json.load(f)
            
            message_data["processed"] = True
            message_data["processed_at"] = datetime.now().isoformat()
            
            # processed 디렉토리로 이동
            processed_file = self.processed_dir / f"msg_{message_id}.json"
            
            with open(processed_file, 'w', encoding='utf-8') as f:
                json.dump(message_data, f, ensure_ascii=False, indent=2)
            
            # 원본 파일 삭제
            message_file.unlink()
            
            logger.info(f"Marked message {message_id} as processed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark message {message_id} as processed: {e}")
            return False
    
    def cleanup_old_messages(self, hours: int = 24) -> int:
        """오래된 처리 완료 메시지들 정리"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            cleaned = 0
            
            for msg_file in self.processed_dir.glob("msg_*.json"):
                try:
                    stat = msg_file.stat()
                    if stat.st_mtime < cutoff_time:
                        msg_file.unlink()
                        cleaned += 1
                except Exception as e:
                    logger.warning(f"Failed to clean message file {msg_file}: {e}")
            
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} old processed messages")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup old messages: {e}")
            return 0


# 전역 메시지 큐 인스턴스
message_queue = MessageQueue()


def add_keyboard_message(message_text: str) -> bool:
    """편의 함수: 키보드 메시지 추가"""
    return message_queue.add_message(message_text)


def simulate_keyboard_input(message_text: str) -> bool:
    """테스트용: 키보드 입력 시뮬레이션"""
    print(f"🎛️ 키보드 입력 시뮬레이션: {message_text}")
    return add_keyboard_message(message_text)