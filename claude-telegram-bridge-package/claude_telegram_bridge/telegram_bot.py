"""
Claude Telegram Bot Module

Modular version of the original telegram_claude_bridge.py with improved structure
and configuration management.
"""

import os
import logging
import subprocess
from typing import Optional
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand

from .config import BridgeConfig

logger = logging.getLogger(__name__)


class ClaudeTelegramBot:
    """Claude Telegram Bot with inline keyboard interface"""
    
    def __init__(self, config: Optional[BridgeConfig] = None):
        """
        Initialize the Telegram bot
        
        Args:
            config: Bridge configuration (creates default if None)
        """
        self.config = config or BridgeConfig()
        self.app: Optional[Application] = None
        
    def validate_input(self, user_input: str) -> tuple[bool, str]:
        """Validate and filter dangerous commands"""
        dangerous_patterns = [
            'rm -rf', 'sudo', 'chmod', 'chown', 'passwd', 'shutdown', 'reboot',
            '>', '>>', '|', '&', ';', '$(', '`', 'eval', 'exec'
        ]
        
        user_input_lower = user_input.lower()
        for pattern in dangerous_patterns:
            if pattern in user_input_lower:
                return False, f"위험한 명령어 패턴이 감지되었습니다: {pattern}"
        
        if len(user_input) > 500:
            return False, "입력값이 너무 깁니다 (최대 500자)"
        
        return True, "OK"
    
    def check_user_authorization(self, user_id: int) -> bool:
        """Check if user is authorized"""
        allowed_ids = self.config.allowed_user_ids
        if not allowed_ids:
            logger.warning("허용된 사용자 ID가 설정되지 않았습니다!")
            return False
        return user_id in allowed_ids
    
    def check_claude_session(self) -> tuple[bool, str]:
        """Check Claude tmux session status"""
        result = os.system(f"tmux has-session -t {self.config.session_name}")
        if result != 0:
            return False, "tmux 세션이 존재하지 않습니다"
        return True, "세션이 활성 상태입니다"
    
    def ensure_claude_session(self) -> Optional[str]:
        """Ensure Claude session exists, create if not"""
        session_ok, message = self.check_claude_session()
        if not session_ok:
            logger.info("Claude 세션을 자동 생성합니다...")
            os.system(f"tmux new-session -d -s {self.config.session_name}")
            os.system(f"tmux send-keys -t {self.config.session_name} -l 'claude'")
            os.system(f"tmux send-keys -t {self.config.session_name} Enter")
            return "🆕 Claude 세션을 새로 시작했습니다"
        return None
    
    async def forward_to_claude(self, update, context):
        """Forward user input to Claude tmux session"""
        user_id = update.effective_user.id
        user_input = update.message.text
        
        logger.info(f"사용자 {user_id}로부터 입력 수신: {user_input[:100]}...")
        
        if not self.check_user_authorization(user_id):
            logger.warning(f"인증되지 않은 사용자 접근 시도: {user_id}")
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        is_valid, message = self.validate_input(user_input)
        if not is_valid:
            logger.warning(f"유효하지 않은 입력: {message}")
            await update.message.reply_text(f"❌ {message}")
            return
        
        session_msg = self.ensure_claude_session()
        if session_msg:
            await update.message.reply_text(session_msg)
        
        try:
            result1 = os.system(f"tmux send-keys -t {self.config.session_name} -l '{user_input}'")
            result2 = os.system(f"tmux send-keys -t {self.config.session_name} Enter")
            result = result1 or result2
            
            if result == 0:
                logger.info(f"성공적으로 전송됨: {user_input}")
                await update.message.reply_text("✅ Claude에 입력이 전송되었습니다.")
            else:
                logger.error(f"tmux 명령어 실행 실패: exit code {result}")
                await update.message.reply_text("❌ 명령어 전송에 실패했습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"예외 발생: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def status_command(self, update, context):
        """Bot status check command"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        result = os.system(f"tmux has-session -t {self.config.session_name}")
        session_status = "✅ 활성" if result == 0 else "❌ 비활성"
        
        status_message = f"""
🤖 **Telegram-Claude Bridge 상태**

• tmux 세션: {session_status}
• 세션 이름: `{self.config.session_name}`
• 작업 디렉토리: `{self.config.working_directory}`
• 인증된 사용자: {len(self.config.allowed_user_ids)}명
• 사용자 ID: `{user_id}`
        """
        
        await update.message.reply_text(status_message, parse_mode='Markdown')
    
    async def start_claude_command(self, update, context):
        """Start Claude session with auto menu display"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        session_ok, message = self.check_claude_session()
        if not session_ok:
            logger.info("사용자 요청으로 Claude 세션을 시작합니다...")
            os.system(f"tmux new-session -d -s {self.config.session_name}")
            os.system(f"tmux send-keys -t {self.config.session_name} -l 'claude'")
            os.system(f"tmux send-keys -t {self.config.session_name} Enter")
            status_msg = "🚀 Claude 세션을 시작했습니다!"
        else:
            status_msg = "✅ Claude 세션이 이미 실행 중입니다."
        
        # Inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📺 Log", callback_data="log")
            ],
            [
                InlineKeyboardButton("⛔ Stop", callback_data="stop"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_msg = f"""🤖 **Claude-Telegram Bridge**

{status_msg}

**📁 작업 디렉토리**: `{self.config.working_directory}`
**🎯 세션 이름**: `{self.config.session_name}`

**제어판을 사용하여 Claude를 제어하세요:**"""
        
        await update.message.reply_text(
            welcome_msg,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def help_command(self, update, context):
        """Help command handler"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
            
        help_text = """
🤖 **Telegram-Claude Bridge 봇**

Claude Code 세션과 텔레그램 간 양방향 통신 브릿지입니다.

**명령어:**
• `/start` - Claude 세션 시작 및 제어판 표시
• `/status` - 봇 및 tmux 세션 상태 확인
• `/log` - 현재 Claude 화면 실시간 확인
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/help` - 이 도움말 보기

**사용법:**
• 일반 텍스트 메시지를 보내면 Claude Code에 전달됩니다
• Claude 작업 완료 시 hook을 통해 자동 알림을 받습니다
• 위험한 명령어는 자동으로 차단됩니다
• 최대 500자까지 입력 가능합니다

**보안:**
• 인증된 사용자만 사용 가능
• 입력값 검증 및 필터링 적용
• 모든 활동이 로그에 기록됩니다
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def clear_command(self, update, context):
        """Clear Claude screen command"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        try:
            result1 = os.system(f"tmux send-keys -t {self.config.session_name} -l 'clear'")
            result2 = os.system(f"tmux send-keys -t {self.config.session_name} Enter")
            result = result1 or result2
            if result == 0:
                await update.message.reply_text("🧹 Claude 화면이 정리되었습니다.")
            else:
                await update.message.reply_text("❌ 화면 정리에 실패했습니다.")
        except Exception as e:
            logger.error(f"화면 정리 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def log_command(self, update, context):
        """Show current Claude screen command"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        try:
            import subprocess
            result = subprocess.run(
                f"tmux capture-pane -t {self.config.session_name} -p", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                current_screen = result.stdout.strip()
                
                if current_screen:
                    lines = current_screen.split('\n')
                    if len(lines) > 30:
                        display_lines = lines[-30:]
                        screen_text = '\n'.join(display_lines)
                        message = f"📺 **Claude 현재 화면** (마지막 30줄):\n\n```\n{screen_text}\n```"
                    else:
                        message = f"📺 **Claude 현재 화면**:\n\n```\n{current_screen}\n```"
                    
                    if len(message) > 4000:
                        message = message[:3500] + "\n...\n(내용이 길어서 일부만 표시됨)\n```"
                    
                    await update.message.reply_text(message, parse_mode='Markdown')
                else:
                    await update.message.reply_text("📺 Claude 화면이 비어있습니다.")
            else:
                await update.message.reply_text("❌ Claude 화면을 캡처할 수 없습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"화면 캡처 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def stop_command(self, update, context):
        """Stop Claude work command (send ESC key)"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        try:
            result = os.system(f"tmux send-keys -t {self.config.session_name} Escape")
            
            if result == 0:
                logger.info("ESC 키 전송 완료")
                await update.message.reply_text("⛔ Claude 작업 중단 명령(ESC)을 보냈습니다")
            else:
                logger.error(f"ESC 키 전송 실패: exit code {result}")
                await update.message.reply_text("❌ 작업 중단 명령 전송에 실패했습니다.")
        except Exception as e:
            logger.error(f"작업 중단 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def menu_command(self, update, context):
        """Show inline keyboard menu"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📺 Log", callback_data="log")
            ],
            [
                InlineKeyboardButton("⛔ Stop", callback_data="stop"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 **Telegram-Claude Bridge 제어판**\n\n"
            "원하는 명령어를 버튼으로 선택하세요:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def button_callback(self, update, context):
        """Handle inline keyboard button callbacks"""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self.check_user_authorization(user_id):
            await query.answer("❌ 인증되지 않은 사용자입니다.")
            return
        
        callback_data = query.data
        await query.answer()  # Acknowledge button click
        
        if callback_data == "status":
            await self._status_callback(query, context)
        elif callback_data == "log":
            await self._log_callback(query, context)
        elif callback_data == "stop":
            await self._stop_callback(query, context)
        elif callback_data == "help":
            await self._help_callback(query, context)
    
    async def _status_callback(self, query, context):
        """Status check callback"""
        result = os.system(f"tmux has-session -t {self.config.session_name}")
        session_status = "✅ 활성" if result == 0 else "❌ 비활성"
        
        status_message = f"""
🤖 **Telegram-Claude Bridge 상태**

• tmux 세션: {session_status}
• 세션 이름: `{self.config.session_name}`
• 작업 디렉토리: `{self.config.working_directory}`
• 인증된 사용자: {len(self.config.allowed_user_ids)}명
• 사용자 ID: `{query.from_user.id}`
        """
        
        await query.edit_message_text(status_message, parse_mode='Markdown')
    
    async def _log_callback(self, query, context):
        """Log check callback"""
        try:
            import subprocess
            result = subprocess.run(
                f"tmux capture-pane -t {self.config.session_name} -p", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                current_screen = result.stdout.strip()
                
                if current_screen:
                    lines = current_screen.split('\n')
                    if len(lines) > 30:
                        display_lines = lines[-30:]
                        screen_text = '\n'.join(display_lines)
                        message = f"📺 **Claude 현재 화면** (마지막 30줄):\n\n```\n{screen_text}\n```"
                    else:
                        message = f"📺 **Claude 현재 화면**:\n\n```\n{current_screen}\n```"
                    
                    if len(message) > 4000:
                        message = message[:3500] + "\n...\n(내용이 길어서 일부만 표시됨)\n```"
                    
                    await query.edit_message_text(message, parse_mode='Markdown')
                else:
                    await query.edit_message_text("📺 Claude 화면이 비어있습니다.")
            else:
                await query.edit_message_text("❌ Claude 화면을 캡처할 수 없습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"화면 캡처 중 오류: {str(e)}")
            await query.edit_message_text("❌ 내부 오류가 발생했습니다.")
    
    async def _stop_callback(self, query, context):
        """Stop work callback"""
        try:
            result = os.system(f"tmux send-keys -t {self.config.session_name} Escape")
            
            if result == 0:
                logger.info("ESC 키 전송 완료")
                await query.edit_message_text("⛔ Claude 작업 중단 명령(ESC)을 보냈습니다")
            else:
                logger.error(f"ESC 키 전송 실패: exit code {result}")
                await query.edit_message_text("❌ 작업 중단 명령 전송에 실패했습니다.")
        except Exception as e:
            logger.error(f"작업 중단 중 오류: {str(e)}")
            await query.edit_message_text("❌ 내부 오류가 발생했습니다.")
    
    async def _help_callback(self, query, context):
        """Help callback"""
        help_text = """
🤖 **Telegram-Claude Bridge 봇**

Claude Code 세션과 텔레그램 간 양방향 통신 브릿지입니다.

**명령어:**
• `/start` - Claude 세션 시작 및 제어판 표시
• `/status` - 봇 및 tmux 세션 상태 확인
• `/log` - 현재 Claude 화면 실시간 확인
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/help` - 이 도움말 보기

**사용법:**
• 일반 텍스트 메시지를 보내면 Claude Code에 전달됩니다
• Claude 작업 완료 시 hook을 통해 자동 알림을 받습니다
• 위험한 명령어는 자동으로 차단됩니다
• 최대 500자까지 입력 가능합니다

**보안:**
• 인증된 사용자만 사용 가능
• 입력값 검증 및 필터링 적용
• 모든 활동이 로그에 기록됩니다
        """
        
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    def setup_handlers(self):
        """Setup all command and callback handlers"""
        if not self.app:
            raise ValueError("Application not initialized")
            
        # Command handlers
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("start", self.start_claude_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("log", self.log_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("clear", self.clear_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        
        # Callback query handler for inline buttons
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler for forwarding to Claude
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.forward_to_claude
        ))
    
    async def setup_bot_commands(self):
        """Setup bot command menu"""
        commands = [
            BotCommand("start", "🚀 Claude 세션 시작 및 제어판 표시"),
            BotCommand("status", "📊 봇 및 tmux 세션 상태 확인"),
            BotCommand("log", "📺 현재 Claude 화면 실시간 확인"),
            BotCommand("stop", "⛔ Claude 작업 중단 (ESC 키 전송)"),
            BotCommand("help", "❓ 도움말 보기"),
            BotCommand("clear", "🧹 Claude 화면 정리"),
            BotCommand("menu", "📋 인라인 키보드 메뉴 표시")
        ]
        
        await self.app.bot.set_my_commands(commands)
        logger.info("봇 명령어 메뉴가 설정되었습니다.")
    
    def run(self):
        """Start the Telegram bot"""
        try:
            # Initialize application
            self.app = Application.builder().token(self.config.telegram_bot_token).build()
            
            # Setup handlers
            self.setup_handlers()
            
            # Setup post-init hook for bot commands
            async def post_init(application):
                await self.setup_bot_commands()
            
            self.app.post_init = post_init
            
            # Start bot
            logger.info(f"텔레그램 봇이 시작되었습니다. 세션: {self.config.session_name}")
            self.app.run_polling()
            
        except Exception as e:
            logger.error(f"봇 실행 중 오류 발생: {str(e)}")
            raise


def main():
    """Main entry point for standalone execution"""
    try:
        config = BridgeConfig()
        bot = ClaudeTelegramBot(config)
        bot.run()
    except KeyboardInterrupt:
        logger.info("봇이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {str(e)}")


if __name__ == "__main__":
    main()