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

from ..config import ClaudeOpsConfig

logger = logging.getLogger(__name__)


class TelegramBridge:
    """Claude Telegram Bot with inline keyboard interface"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        """
        Initialize the Telegram bot
        
        Args:
            config: Bridge configuration (creates default if None)
        """
        self.config = config or ClaudeOpsConfig()
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
    
    def get_all_claude_sessions(self) -> list[str]:
        """Get list of all Claude sessions"""
        try:
            import subprocess
            result = subprocess.run(
                "tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
                return sessions
            else:
                return []
        except Exception as e:
            logger.error(f"세션 목록 조회 실패: {str(e)}")
            return []
    
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
    
    def extract_session_from_message(self, message_text: str) -> Optional[str]:
        """Extract session name from notification message"""
        import re
        
        # Look for session patterns in the message
        patterns = [
            r'\*\*🎯 세션 이름\*\*: `([^`]+)`',  # From start command
            r'🎯 \*\*세션\*\*: `([^`]+)`',       # From notification (with markdown bold)
            r'세션: `([^`]+)`',                    # From notification (simple)
            r'\[([^]]+)\]',                        # From completion notification [session_name]
            r'(claude_[\w-]+)',                    # Any claude_xxx pattern (full match)
            r'claude_(\w+)',                       # Any claude_xxx pattern (name only)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_text)
            if match:
                session_name = match.group(1)
                # If it already starts with 'claude_', return as-is
                if session_name.startswith('claude_'):
                    return session_name
                # Otherwise, add 'claude_' prefix
                elif not session_name.startswith('claude'):
                    session_name = f'claude_{session_name}'
                    return session_name
                return session_name
        
        return None
    
    def get_target_session_from_reply(self, update) -> tuple[Optional[str], bool]:
        """
        Extract target session from reply message and determine if we should switch active session
        
        Returns:
            (target_session, should_switch_active): tuple of session name and whether to switch
        """
        if not (update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot):
            return None, False
            
        original_text = update.message.reply_to_message.text
        target_session = self.extract_session_from_message(original_text)
        
        if target_session:
            logger.info(f"📍 Reply 기반 세션 감지: {target_session}")
            # Check if target session exists
            session_exists = os.system(f"tmux has-session -t {target_session}") == 0
            if session_exists:
                return target_session, True
            else:
                logger.warning(f"❌ 대상 세션 {target_session}이 존재하지 않음")
                return None, False
        
        return None, False
    
    async def forward_to_claude(self, update, context):
        """Forward user input to Claude tmux session with reply-based targeting"""
        user_id = update.effective_user.id
        user_input = update.message.text
        target_session = None
        
        logger.info(f"사용자 {user_id}로부터 입력 수신: {user_input[:100]}...")
        
        if not self.check_user_authorization(user_id):
            logger.warning(f"인증되지 않은 사용자 접근 시도: {user_id}")
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Handle slash commands that should be sent to Claude
        if user_input.startswith('/') and not user_input.startswith('//'):
            # Check if it's a Claude slash command (not a Telegram bot command)
            claude_commands = ['/export', '/task-start', '/task-finish', '/task-archive', '/project-plan', '/task-publish']
            if any(user_input.startswith(cmd) for cmd in claude_commands):
                await update.message.reply_text(
                    f"🎯 **Claude 슬래시 명령어 감지**: `{user_input}`\n\n"
                    f"이 명령어를 Claude에게 전달하시겠습니까?\n\n"
                    f"**옵션:**\n"
                    f"• **예** - 이 메시지에 Reply로 `yes` 응답\n"
                    f"• **아니오** - 무시하거나 다른 메시지 전송\n\n"
                    f"💡 **팁**: 슬래시 명령어 앞에 `//`을 붙이면 바로 전송됩니다.\n"
                    f"예: `//{user_input[1:]}`"
                )
                return
            # If it starts with //, remove one slash and send to Claude
            elif user_input.startswith('//'):
                user_input = user_input[1:]  # Remove one slash, keep the other
                logger.info(f"🔄 Double slash detected, sending to Claude: {user_input}")
        
        is_valid, message = self.validate_input(user_input)
        if not is_valid:
            logger.warning(f"유효하지 않은 입력: {message}")
            await update.message.reply_text(f"❌ {message}")
            return
        
        # Check if this is a reply to a bot message (RESTORED ORIGINAL LOGIC)
        target_session = None
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            
            # Check if replying to a slash command confirmation
            if "Claude 슬래시 명령어 감지" in original_text and user_input.lower() in ['yes', 'y', '예', 'ㅇ']:
                # Extract the command from the original message
                import re
                cmd_match = re.search(r'`([^`]+)`', original_text)
                if cmd_match:
                    claude_command = cmd_match.group(1)
                    logger.info(f"✅ 사용자가 슬래시 명령어 전송 확인: {claude_command}")
                    user_input = claude_command  # Use the original command
                else:
                    await update.message.reply_text("❌ 명령어를 찾을 수 없습니다.")
                    return
            else:
                # Regular session targeting
                target_session = self.extract_session_from_message(original_text)
                
                if target_session:
                    logger.info(f"📍 Reply 기반 세션 타겟팅: {target_session}")
                    
                    # Check if target session exists
                    session_exists = os.system(f"tmux has-session -t {target_session}") == 0
                    if not session_exists:
                        await update.message.reply_text(
                            f"❌ 대상 세션 `{target_session}`이 존재하지 않습니다.\n"
                            f"먼저 해당 세션을 시작해주세요."
                        )
                        return
                else:
                    logger.debug("Reply 대상 메시지에서 세션 정보를 찾을 수 없음")
        
        # Use target session if found, otherwise use current active session
        if not target_session:
            target_session = self.config.session_name
            logger.info(f"🎯 기본 활성 세션 사용: {target_session}")
        
        # Ensure target session exists
        session_exists = os.system(f"tmux has-session -t {target_session}") == 0
        if not session_exists:
            logger.info(f"세션 {target_session}을 자동 생성합니다...")
            
            # Extract directory from session name for auto-creation
            if target_session.startswith('claude_'):
                project_name = target_session[7:]  # Remove 'claude_' prefix
                home_dir = os.path.expanduser("~")
                target_directory = os.path.join(home_dir, "projects", project_name)
                os.makedirs(target_directory, exist_ok=True)
                
                os.system(f"cd {target_directory} && tmux new-session -d -s {target_session}")
                os.system(f"tmux send-keys -t {target_session} -l 'claude'")
                os.system(f"tmux send-keys -t {target_session} Enter")
                
                await update.message.reply_text(f"🆕 {target_session} 세션을 새로 시작했습니다")
            else:
                await update.message.reply_text(f"❌ 세션 {target_session}이 존재하지 않습니다.")
                return
        
        try:
            result1 = os.system(f"tmux send-keys -t {target_session} -l '{user_input}'")
            result2 = os.system(f"tmux send-keys -t {target_session} Enter")
            result = result1 or result2
            
            if result == 0:
                logger.info(f"성공적으로 전송됨: {user_input} -> {target_session}")
                session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                await update.message.reply_text(f"✅ `{session_display}`에 입력이 전송되었습니다.")
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
        
        # Parse command arguments for project path support
        args = context.args if context.args else []
        
        # Default behavior - use current session
        target_session = self.config.session_name
        target_directory = self.config.working_directory
        
        # If arguments provided, create new session
        if args:
            project_name = args[0]
            
            # Second argument is custom directory path
            if len(args) > 1:
                custom_dir = os.path.expanduser(args[1])
                if os.path.exists(custom_dir):
                    target_directory = custom_dir
                else:
                    await update.message.reply_text(f"❌ 디렉토리를 찾을 수 없습니다: {custom_dir}")
                    return
            else:
                # Default to ~/projects/<project_name>
                home_dir = os.path.expanduser("~")
                target_directory = os.path.join(home_dir, "projects", project_name)
                
                # Create directory if it doesn't exist
                if not os.path.exists(target_directory):
                    os.makedirs(target_directory, exist_ok=True)
                    logger.info(f"Created project directory: {target_directory}")
            
            # Create session name with claude_ prefix
            target_session = f"claude_{project_name}"
        
        # Check if target session exists
        session_exists = os.system(f"tmux has-session -t {target_session}") == 0
        
        if not session_exists:
            logger.info(f"사용자 요청으로 {target_session} 세션을 시작합니다...")
            # Start tmux session in the target directory
            os.system(f"cd {target_directory} && tmux new-session -d -s {target_session}")
            os.system(f"tmux send-keys -t {target_session} -l 'claude'")
            os.system(f"tmux send-keys -t {target_session} Enter")
            status_msg = f"🚀 {target_session} 세션을 시작했습니다!"
        else:
            status_msg = f"✅ {target_session} 세션이 이미 실행 중입니다."
        
        # Use standardized keyboard
        reply_markup = self.get_main_keyboard()
        
        welcome_msg = f"""🤖 **Claude-Telegram Bridge**

{status_msg}

**📁 작업 디렉토리**: `{target_directory}`
**🎯 세션 이름**: `{target_session}`

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

**텔레그램 봇 명령어:**
• `/start` - 현재 세션 시작/재시작
• `/start project_name` - ~/projects/project_name에서 claude_project_name 세션 시작
• `/start project_name /custom/path` - 지정 경로에서 claude_project_name 세션 시작
• `/status` - 봇 및 tmux 세션 상태 확인
• `/log [lines]` - 현재 Claude 화면 확인 (기본 50줄, 최대 2000줄)
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/sessions` - 활성 세션 목록 보기 및 전환
• `/help` - 이 도움말 보기

**Claude 슬래시 명령어 전달:**
• `//export` - Claude에게 /export 명령어 바로 전달
• `//task-start TID-xxx` - Claude에게 /task-start 명령어 바로 전달
• `/export` → 확인 메시지 → Reply로 `yes` - 단계별 안전 전송

**사용법:**
• 일반 텍스트 메시지를 보내면 Claude Code에 전달됩니다
• 알림 메시지에 Reply하면 해당 세션으로 정확히 전송됩니다
• Claude 작업 완료 시 자동 알림을 받습니다
• 위험한 명령어는 자동으로 차단됩니다
• 최대 500자까지 입력 가능합니다

**보안:**
• 인증된 사용자만 사용 가능
• 입력값 검증 및 필터링 적용
• 모든 활동이 로그에 기록됩니다
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    
    async def log_command(self, update, context):
        """Show current Claude screen command with optional line count"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check if replying to a message - if so, use that session for log
        target_session = self.config.session_name
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                # Check if target session exists
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    target_session = reply_session
                    logger.info(f"📍 Reply 기반 로그 조회: {target_session}")
                else:
                    await update.message.reply_text(f"❌ 세션 `{reply_session}`이 존재하지 않습니다.")
                    return
        
        # Parse line count parameter (default: 50)
        line_count = 50
        logger.info(f"🔍 Log command - context.args: {context.args}")
        if context.args:
            try:
                line_count = int(context.args[0])
                line_count = max(10, min(line_count, 2000))  # Limit between 10-2000 lines
                logger.info(f"📏 Parsed line_count: {line_count}")
            except (ValueError, IndexError):
                await update.message.reply_text("❌ 올바른 숫자를 입력하세요. 예: `/log 100`")
                return
        else:
            logger.info("📏 No args provided, using default line_count: 50")
        
        try:
            import subprocess
            
            # Use tmux capture-pane with -S to specify start line (negative for history)
            result = subprocess.run(
                f"tmux capture-pane -t {target_session} -p -S -{line_count}", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                current_screen = result.stdout  # Don't strip - keep all original spacing
                
                if current_screen:
                    lines = current_screen.split('\n')
                    
                    # Always show the requested number of lines
                    if len(lines) > line_count:
                        display_lines = lines[-line_count:]
                    else:
                        display_lines = lines
                        
                    screen_text = '\n'.join(display_lines)
                    
                    # Check if we need to split the message due to Telegram limits
                    max_length = 3500
                    if len(screen_text) > max_length:
                        # Split into multiple messages
                        parts = []
                        current_part = ""
                        
                        for line in display_lines:
                            if len(current_part + line + "\n") > max_length:
                                if current_part:
                                    parts.append(current_part)
                                current_part = line + "\n"
                            else:
                                current_part += line + "\n"
                        
                        if current_part:
                            parts.append(current_part)
                        
                        # Send each part as a separate message
                        for i, part in enumerate(parts):
                            if i == 0:
                                header = f"📺 **Claude 화면** ({len(display_lines)}줄) - Part {i+1}/{len(parts)}:\n\n"
                            else:
                                header = f"📺 **Part {i+1}/{len(parts)}**:\n\n"
                            # Send without markdown to avoid parsing errors
                            message = f"{header}{part.strip()}"
                            await update.message.reply_text(message, parse_mode=None)
                    else:
                        # Send without markdown to avoid parsing errors
                        message = f"📺 Claude 현재 화면 ({len(display_lines)}줄):\n\n{screen_text}"
                        await update.message.reply_text(message, parse_mode=None)
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
    
    async def sessions_command(self, update, context):
        """Show active sessions command or switch to reply session directly"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check if replying to a message - if so, switch to that session directly
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                # Check if target session exists
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    # Switch active session using session_manager
                    from ..session_manager import session_manager
                    
                    old_session = self.config.session_name
                    success = session_manager.switch_session(reply_session)
                    
                    if success:
                        logger.info(f"🔄 Reply 기반 세션 전환: {old_session} → {reply_session}")
                        
                        session_display = reply_session.replace('claude_', '') if reply_session.startswith('claude_') else reply_session
                        await update.message.reply_text(
                            f"🔄 **활성 세션 전환 완료**\n\n"
                            f"이전: `{old_session}`\n"
                            f"현재: `{reply_session}`\n\n"
                            f"이제 `{session_display}` 세션이 활성화되었습니다."
                        )
                    else:
                        await update.message.reply_text(f"❌ 세션 전환에 실패했습니다: {reply_session}")
                    return
                else:
                    await update.message.reply_text(f"❌ 세션 `{reply_session}`이 존재하지 않습니다.")
                    return
        
        # Normal session list display (when not replying)
        try:
            from ..session_manager import session_manager
            
            sessions = session_manager.get_all_claude_sessions()
            active_session = session_manager.get_active_session()
            
            if not sessions:
                await update.message.reply_text("🔍 활성 Claude 세션이 없습니다.")
                return
            
            message = "🔄 활성 Claude 세션 목록\n\n"
            
            for session in sessions:
                if session == active_session:
                    message += f"▶️ {session} (현재 활성)\n"
                else:
                    message += f"⏸️ {session}\n"
            
            # Add inline keyboard for session switching
            keyboard = []
            for session in sessions:
                if session != active_session:
                    keyboard.append([InlineKeyboardButton(
                        f"🔄 {session}로 전환",
                        callback_data=f"select_session:{session}"
                    )])
            
            if keyboard:
                keyboard.append([InlineKeyboardButton("🔙 뒤로", callback_data="back_to_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message)
                
        except Exception as e:
            logger.error(f"세션 목록 조회 중 오류: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")
    
    def get_main_keyboard(self):
        """Get standardized keyboard layout"""
        keyboard = [
            [
                InlineKeyboardButton("📺 Log", callback_data="log"),
                InlineKeyboardButton("⛔ Stop", callback_data="stop")
            ],
            [
                InlineKeyboardButton("🔄 Sessions", callback_data="sessions"),
                InlineKeyboardButton("📊 Status", callback_data="status")
            ],
            [
                InlineKeyboardButton("🚀 Start", callback_data="start"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
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
        elif callback_data == "sessions":
            await self._sessions_callback(query, context)
        elif callback_data == "start":
            await self._start_callback(query, context)
        elif callback_data == "help":
            await self._help_callback(query, context)
        elif callback_data.startswith("select_session:"):
            session_name = callback_data.split(":", 1)[1]
            await self._select_session_callback(query, context, session_name)
        elif callback_data == "back_to_menu":
            await self._back_to_menu_callback(query, context)
    
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
        """Log check callback - Simple raw tmux output"""
        try:
            import subprocess
            
            # Check if this is a reply to determine target session
            # Note: For callback queries, we use the current active session
            # Reply-based targeting is handled by the command version
            target_session = self.config.session_name
            
            # Simple tmux capture - just current screen
            result = subprocess.run(
                f"tmux capture-pane -t {target_session} -p", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                current_screen = result.stdout  # Don't strip - keep all original spacing
                
                if current_screen:
                    # Just show raw output - no processing
                    message = f"📺 Claude 현재 화면:\n\n{current_screen}"
                    await query.edit_message_text(message, parse_mode=None)
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

**봇 명령어:**
• `/start` - 현재 세션 시작/재시작
• `/start project_name` - ~/projects/project_name에서 claude_project_name 세션 시작
• `/start project_name /custom/path` - 지정 경로에서 claude_project_name 세션 시작
• `/status` - 봇 및 tmux 세션 상태 확인
• `/log [lines]` - 현재 Claude 화면 확인 (기본 50줄, 최대 2000줄)
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/sessions` - 활성 세션 목록 보기 및 전환
• `/help` - 이 도움말 보기

**Claude 명령어:**
• 일반 텍스트 메시지 → Claude Code에 직접 전달
• **슬래시 명령어** (`/project-plan`, `/task-start` 등) → Claude Code에 직접 전달
• 알려지지 않은 `/command` → Claude Code에 자동 전달

**사용법:**
• 텔레그램 알림에 Reply로 답장 → 해당 세션에 정확히 전달
• Claude 작업 완료 시 hook을 통해 자동 알림 수신
• 위험한 명령어는 자동으로 차단됩니다
• 최대 500자까지 입력 가능

**보안:**
• 인증된 사용자만 사용 가능
• 입력값 검증 및 필터링 적용
• 모든 활동이 로그에 기록됩니다
        """
        
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    async def unknown_command_handler(self, update, context):
        """Handle unknown commands by forwarding to Claude"""
        user_id = update.effective_user.id
        command_text = update.message.text
        
        logger.info(f"Unknown command received: {command_text}")
        
        # Forward unknown commands to Claude with a prefix explanation
        await self.forward_to_claude(update, context)
    
    def setup_handlers(self):
        """Setup all command and callback handlers"""
        if not self.app:
            raise ValueError("Application not initialized")
            
        # Command handlers (known bot commands)
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("start", self.start_claude_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("log", self.log_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        
        # Callback query handler for inline buttons
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler for forwarding regular text to Claude
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.forward_to_claude
        ))
        
        # Handler for unknown commands - forward to Claude
        # This must be added AFTER known commands to catch unhandled ones
        self.app.add_handler(MessageHandler(
            filters.COMMAND,
            self.unknown_command_handler
        ))
    
    async def setup_bot_commands(self):
        """Setup bot command menu"""
        commands = [
            BotCommand("start", "🚀 Claude 세션 시작 (옵션: project_name [path])"),
            BotCommand("status", "📊 봇 및 tmux 세션 상태 확인"),
            BotCommand("log", "📺 현재 Claude 화면 실시간 확인"),
            BotCommand("stop", "⛔ Claude 작업 중단 (ESC 키 전송)"),
            BotCommand("sessions", "🔄 활성 세션 목록 보기"),
            BotCommand("help", "❓ 도움말 보기")
        ]
        
        await self.app.bot.set_my_commands(commands)
        logger.info("봇 명령어 메뉴가 설정되었습니다.")
    
    async def _sessions_callback(self, query, context):
        """Sessions list callback"""
        try:
            from ..session_manager import session_manager
            
            sessions = session_manager.get_all_claude_sessions()
            active_session = session_manager.get_active_session()
            
            if not sessions:
                await query.edit_message_text(
                    "🔄 **세션 목록**\n\n❌ 활성 Claude 세션이 없습니다.\n\n"
                    "/start 명령으로 새 세션을 시작하세요.",
                    parse_mode='Markdown'
                )
                return
            
            # Create session selection keyboard
            keyboard = []
            for session in sessions:
                session_info = session_manager.get_session_info(session)
                
                # Display name (remove claude_ prefix)
                display_name = session_info["directory"]
                
                # Status icons
                status_icon = "✅" if session_info["exists"] else "❌"
                current_icon = "🎯 " if session_info["is_active"] else ""
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{current_icon}{status_icon} {display_name}",
                        callback_data=f"select_session:{session}"
                    )
                ])
            
            # Add back button
            keyboard.append([InlineKeyboardButton("🔙 메뉴로", callback_data="back_to_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Get status file info
            status_file = session_manager.get_status_file_for_session(active_session)
            
            await query.edit_message_text(
                f"🔄 **세션 목록** ({len(sessions)}개)\n\n"
                f"🎯 현재 활성: `{active_session}`\n"
                f"📁 상태 파일: `{status_file}`\n\n"
                "전환할 세션을 선택하세요:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"세션 목록 조회 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **세션 목록 조회 실패**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _select_session_callback(self, query, context, session_name):
        """Session selection callback"""
        try:
            from ..session_manager import session_manager
            
            # Get current active session
            current_session = session_manager.get_active_session()
            
            if session_name == current_session:
                await query.edit_message_text(
                    f"✅ **이미 활성 세션**\n\n"
                    f"현재 세션: `{session_name}`\n\n"
                    f"이미 이 세션에 연결되어 있습니다.",
                    parse_mode='Markdown'
                )
                return
            
            # Check if target session exists
            if not session_manager.session_exists(session_name):
                await query.edit_message_text(
                    f"❌ **세션 없음**\n\n"
                    f"세션 `{session_name}`이 존재하지 않습니다.\n"
                    f"먼저 해당 디렉토리에서 Claude Code를 시작해주세요.",
                    parse_mode='Markdown'
                )
                return
            
            # Switch session
            success = session_manager.switch_session(session_name)
            
            if success:
                # Get session info
                old_status_file = session_manager.get_status_file_for_session(current_session)
                new_status_file = session_manager.get_status_file_for_session(session_name)
                
                await query.edit_message_text(
                    f"✅ **세션 전환 완료**\n\n"
                    f"이전 세션: `{current_session}`\n"
                    f"새 세션: `{session_name}`\n\n"
                    f"📁 상태 파일: `{new_status_file}`\n\n"
                    f"이제 `{session_name}` 세션을 모니터링합니다.\n"
                    f"모니터링 시스템이 자동으로 업데이트됩니다.",
                    parse_mode='Markdown'
                )
                
                # Restart monitoring for new session
                await self._restart_monitoring()
                
            else:
                await query.edit_message_text(
                    f"❌ **세션 전환 실패**\n\n"
                    f"세션 `{session_name}`으로 전환할 수 없습니다.\n"
                    f"세션이 존재하는지 확인해주세요.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"세션 전환 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **내부 오류**\n\n"
                f"세션 전환 중 오류가 발생했습니다.\n"
                f"오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _start_callback(self, query, context):
        """Start Claude session callback"""
        try:
            session_ok, message = self.check_claude_session()
            if not session_ok:
                logger.info("사용자 요청으로 Claude 세션을 시작합니다...")
                # Start tmux session in the configured working directory
                os.system(f"cd {self.config.working_directory} && tmux new-session -d -s {self.config.session_name}")
                os.system(f"tmux send-keys -t {self.config.session_name} -l 'claude'")
                os.system(f"tmux send-keys -t {self.config.session_name} Enter")
                status_msg = "🚀 Claude 세션을 시작했습니다!"
            else:
                status_msg = "✅ Claude 세션이 이미 실행 중입니다."
            
            reply_markup = self.get_main_keyboard()
            
            welcome_msg = f"""🤖 **Claude-Telegram Bridge**

{status_msg}

**📁 작업 디렉토리**: `{self.config.working_directory}`
**🎯 세션 이름**: `{self.config.session_name}`

**제어판을 사용하여 Claude를 제어하세요:**"""
            
            await query.edit_message_text(
                welcome_msg,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Claude 세션 시작 중 오류: {str(e)}")
            await query.edit_message_text("❌ 내부 오류가 발생했습니다.")
    
    async def _back_to_menu_callback(self, query, context):
        """Back to main menu callback"""
        reply_markup = self.get_main_keyboard()
        
        await query.edit_message_text(
            "🤖 **Telegram-Claude Bridge 제어판**\n\n"
            "원하는 명령어를 버튼으로 선택하세요:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _restart_monitoring(self):
        """Restart monitoring system for new session"""
        try:
            import subprocess
            
            # Kill existing monitor
            subprocess.run("tmux kill-session -t claude-monitor 2>/dev/null", shell=True)
            
            # Wait a moment
            import asyncio
            await asyncio.sleep(1)
            
            # Start new monitor
            subprocess.run(
                "cd /home/kyuwon/claude-ops && ./scripts/start_monitoring.sh > /dev/null 2>&1 &",
                shell=True
            )
            
            logger.info("모니터링 시스템이 새 세션으로 재시작되었습니다")
            
        except Exception as e:
            logger.error(f"모니터링 재시작 중 오류: {str(e)}")
    
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
        config = ClaudeOpsConfig()
        bot = TelegramBridge(config)
        bot.run()
    except KeyboardInterrupt:
        logger.info("봇이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {str(e)}")


if __name__ == "__main__":
    main()