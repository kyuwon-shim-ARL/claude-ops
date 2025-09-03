"""
InlineKeyboard 콜백을 처리하는 텔레그램 봇

사용자가 InlineKeyboard 버튼을 클릭했을 때 적절한 액션을 수행합니다.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
import requests
from ..config import ClaudeOpsConfig
from .inline_panel import InlineSessionPanel

logger = logging.getLogger(__name__)


class InlineKeyboardBot:
    """InlineKeyboard 콜백 처리 봇"""
    
    def __init__(self, config: ClaudeOpsConfig = None):
        self.config = config or ClaudeOpsConfig()
        self.bot_token = self.config.telegram_bot_token
        self.chat_id = self.config.telegram_chat_id
        self.panel: Optional[InlineSessionPanel] = None
        self.running = False
        self.last_update_id = 0
        
        # API 엔드포인트
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        if not self.bot_token or not self.chat_id:
            raise ValueError("텔레그램 봇 토큰과 채팅 ID가 필요합니다.")
    
    async def initialize_panel(self):
        """패널 초기화"""
        try:
            self.panel = InlineSessionPanel(self.bot_token, self.chat_id)
            # 기존 세션들 발견하여 패널에 추가
            await self.panel.refresh_sessions()
            logger.info("✅ InlineKeyboard 패널이 봇에 연결되었습니다.")
            return True
        except Exception as e:
            logger.error(f"패널 초기화 실패: {e}")
            return False
    
    def get_updates(self, offset: int = None, timeout: int = 10) -> Dict[str, Any]:
        """텔레그램 업데이트 가져오기"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"]  # 메시지와 콜백 쿼리 받기
            }
            
            if offset:
                params["offset"] = offset
            
            response = requests.get(url, params=params, timeout=timeout + 5)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get updates: {response.text}")
                return {"ok": False}
                
        except requests.exceptions.Timeout:
            logger.debug("Get updates timeout (normal)")
            return {"ok": True, "result": []}
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return {"ok": False}
    
    def answer_callback_query(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
        """콜백 쿼리 응답"""
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            payload = {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
            return False
    
    def send_message(self, text: str) -> bool:
        """메시지 전송"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def handle_message(self, message: Dict[str, Any]) -> bool:
        """텍스트 메시지 처리"""
        try:
            text = message.get("text", "").strip()
            user = message["from"]
            
            logger.info(f"💬 Message received: '{text}' from {user.get('first_name', 'Unknown')}")
            
            # /panel 명령어로 패널 띄우기
            if text in ["/panel", "/패널", "패널", "panel"]:
                if not self.panel:
                    await self.initialize_panel()
                
                if self.panel:
                    # 새 패널 생성 및 전송
                    success = await self.panel.start_panel()
                    if success:
                        self.send_message(f"✅ InlineKeyboard 패널을 전송했습니다! (메시지 ID: {self.panel.panel_message_id})")
                    else:
                        self.send_message("❌ 패널 전송에 실패했습니다.")
                else:
                    self.send_message("❌ 패널 초기화에 실패했습니다.")
                return True
            
            # /help 명령어
            elif text in ["/help", "/도움말", "도움말", "help"]:
                help_text = """🤖 **Claude-Ops InlineKeyboard 봇 사용법**

**패널 명령어:**
• `/panel` 또는 `패널` - InlineKeyboard 패널 띄우기
• `/help` 또는 `도움말` - 이 도움말 보기

**패널 사용법:**
1️⃣ 세션 버튼 클릭 → 액션 메뉴로 이동
2️⃣ 원하는 액션 선택:
   • 🏠 메인세션 설정
   • 📜 로그보기  
   • ⏸️ Pause (ESC)
   • 🗑️ Erase (Ctrl+C)
3️⃣ ◀️ 메인으로 돌아가기

**제어 버튼:**
• 🔄 새로고침 - 세션 목록 갱신
• 📊 전체상태 - 모든 세션 상태 요약
• ⚙️ 설정 - 시스템 설정 확인"""
                
                self.send_message(help_text)
                return True
            
            # /status 명령어
            elif text in ["/status", "/상태", "상태"]:
                if not self.panel:
                    await self.initialize_panel()
                
                if self.panel:
                    sessions = await self.panel.discover_sessions()
                    status_text = f"📊 **현재 상태**\n\n🎛️ **발견된 세션**: {len(sessions)}개\n"
                    
                    if sessions:
                        session_list = []
                        for session in sessions:
                            display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                            session_list.append(f"• {display_name}")
                        status_text += "\n".join(session_list)
                    else:
                        status_text += "❌ 활성 Claude 세션이 없습니다."
                    
                    status_text += "\n\n💡 `/panel` 명령어로 관리 패널을 띄우세요."
                    self.send_message(status_text)
                else:
                    self.send_message("❌ 세션 상태를 확인할 수 없습니다.")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {e}")
            return False
    
    async def handle_callback_query(self, callback_query: Dict[str, Any]) -> bool:
        """콜백 쿼리 처리"""
        try:
            callback_id = callback_query["id"]
            callback_data = callback_query["data"]
            user = callback_query["from"]
            
            logger.info(f"📞 Callback received: {callback_data} from {user.get('first_name', 'Unknown')}")
            
            if not self.panel:
                await self.initialize_panel()
            
            if not self.panel:
                self.answer_callback_query(callback_id, "❌ 패널이 초기화되지 않았습니다.", show_alert=True)
                return False
            
            # 패널을 통해 콜백 처리
            response_message = await self.panel.handle_callback(callback_data)
            
            # 콜백 쿼리 응답 (로딩 스피너 제거)
            success = self.answer_callback_query(callback_id, "✅ 처리됨")
            
            if not success:
                logger.warning(f"Failed to answer callback query: {callback_id}")
            
            # 응답 메시지가 있으면 전송
            if response_message:
                # 너무 긴 메시지는 잘라서 전송
                if len(response_message) > 4000:
                    self.send_message(response_message[:4000] + "...\n\n💡 전체 내용은 로그를 확인하세요.")
                else:
                    self.send_message(response_message)
            
            return True
            
        except Exception as e:
            logger.error(f"콜백 쿼리 처리 중 오류: {e}")
            if "id" in callback_query:
                self.answer_callback_query(callback_query["id"], f"❌ 오류: {e}", show_alert=True)
            return False
    
    async def process_updates(self, updates: list) -> None:
        """업데이트 처리"""
        for update in updates:
            try:
                self.last_update_id = update["update_id"]
                
                # 메시지 처리
                if "message" in update:
                    await self.handle_message(update["message"])
                
                # 콜백 쿼리 처리
                elif "callback_query" in update:
                    await self.handle_callback_query(update["callback_query"])
                
            except Exception as e:
                logger.error(f"업데이트 처리 중 오류: {e}")
    
    async def start_polling(self):
        """봇 폴링 시작"""
        logger.info("🤖 InlineKeyboard 봇 시작...")
        self.running = True
        
        # 패널 초기화
        if not await self.initialize_panel():
            logger.error("❌ 패널 초기화 실패, 봇을 종료합니다.")
            return
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.running:
            try:
                # 업데이트 가져오기
                offset = self.last_update_id + 1 if self.last_update_id > 0 else None
                response = self.get_updates(offset=offset, timeout=10)
                
                if response.get("ok"):
                    updates = response.get("result", [])
                    
                    if updates:
                        logger.debug(f"📨 {len(updates)}개 업데이트 받음")
                        await self.process_updates(updates)
                    
                    consecutive_errors = 0  # 성공 시 에러 카운터 리셋
                    
                else:
                    logger.error(f"Failed to get updates: {response}")
                    consecutive_errors += 1
                
            except KeyboardInterrupt:
                logger.info("🛑 사용자에 의해 봇이 중지되었습니다.")
                break
            except Exception as e:
                logger.error(f"폴링 중 오류: {e}")
                consecutive_errors += 1
                
                # 너무 많은 연속 에러 시 잠시 대기
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(f"⚠️ {consecutive_errors}번 연속 에러, 30초 대기...")
                    await asyncio.sleep(30)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(1)
        
        self.running = False
        logger.info("🏁 InlineKeyboard 봇이 종료되었습니다.")
    
    def stop_polling(self):
        """봇 폴링 중지"""
        self.running = False


async def main():
    """메인 진입점"""
    try:
        config = ClaudeOpsConfig()
        bot = InlineKeyboardBot(config)
        await bot.start_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())