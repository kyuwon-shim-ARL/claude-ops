"""
Claude Telegram Bot Module

Modular version of the original telegram_claude_bridge.py with improved structure
and configuration management.
"""

import os
import logging
import subprocess
import re
import asyncio
from typing import Optional
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand

from ..config import ClaudeOpsConfig
from ..project_creator import ProjectCreator
from .dangerous_commands import (
    DANGEROUS_PATTERNS,
    is_dangerous_command,
    PendingConfirmation,
    pending_confirmations,
    create_confirmation,
    get_confirmation,
    cleanup_expired_confirmations
)

logger = logging.getLogger(__name__)


class TelegramBridge:
    """Claude Telegram Bot with claude-dev-kit prompt integration"""
    
    # Legacy workflow shortcuts removed - use /fullcycle command instead
    
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
        # More targeted dangerous patterns - exclude common text characters
        dangerous_patterns = [
            'rm -rf', 'sudo ', 'chmod ', 'chown ', 'passwd', 'shutdown', 'reboot',
            ' > /', ' >> /', '$(', '`rm', '`sudo', 'eval(', 'exec('
        ]
        
        user_input_lower = user_input.lower()
        for pattern in dangerous_patterns:
            if pattern in user_input_lower:
                return False, f"위험한 명령어 패턴이 감지되었습니다: {pattern}"
        
        # Increased length limit for expanded prompts
        if len(user_input) > 10000:
            return False, "입력값이 너무 깁니다 (최대 10,000자)"
        
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
        """Get list of all Claude Code sessions (excluding monitoring/management sessions)"""
        try:
            import subprocess
            result = subprocess.run(
                "tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                all_sessions = [s.strip() for s in result.stdout.split('\n') if s.strip()]
                
                # Filter out monitoring and management sessions
                excluded_patterns = [
                    'claude-monitor',  # Monitoring sessions
                    'claude-ops',      # Management sessions  
                    'claude_monitor',  # Alternative naming
                    'claude_ops'       # Alternative naming
                ]
                
                claude_code_sessions = []
                for session in all_sessions:
                    # Exclude sessions that match monitoring/management patterns
                    if not any(pattern in session for pattern in excluded_patterns):
                        claude_code_sessions.append(session)
                
                return claude_code_sessions
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
        
        # Priority patterns - look for current/active session first
        priority_patterns = [
            r'📍 현재 활성: `([^`]+)`',           # New switch format - current active
            r'현재: `([^`]+)`',                    # Old switch format - current
            r'새 세션: `([^`]+)`',                 # New session in switch
        ]
        
        # Try priority patterns first
        for pattern in priority_patterns:
            match = re.search(pattern, message_text)
            if match:
                session_name = match.group(1)
                if session_name.startswith('claude_'):
                    return session_name
                elif not session_name.startswith('claude'):
                    return f'claude_{session_name}'
                return session_name
        
        # Look for session patterns in the message (updated for all formats)
        patterns = [
            r'🎛️ 세션: ([^\n]+)',                    # Log format: 🎛️ 세션: claude_claude-ops
            r'\[`([^`]+)`\]',                      # Notification format: [`session_name`]
            r'\*\*세션\*\*: `([^`]+)`',             # Bold with backticks: **세션**: `session_name`
            r'🎯 \*\*세션\*\*: `([^`]+)`',       # With emoji: 🎯 **세션**: `session_name`
            r'\*\*🎯 세션 이름\*\*: `([^`]+)`',  # From start command
            r'세션: `([^`]+)`',                    # Simple with backticks: 세션: `session_name`
            r'세션: ([^\n\s]+)',                  # Simple without backticks: 세션: claude_ops
            r'\[([^]]+)\]',                        # Fallback: [session_name]
            r'\*\*Claude 화면 로그\*\* \[([^\]]+)\]',  # From new log format
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
        """Start Claude session using unified ProjectCreator"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Parse command arguments for project path support
        args = context.args if context.args else []
        
        # If no arguments, show simple usage only
        if not args:
            logger.info(f"User {user_id} called /new_project without arguments - showing usage")
            await update.message.reply_text(
                "🚀 **새 프로젝트 생성**\n\n"
                "📋 **사용법:**\n"
                "`/new_project <프로젝트명>`\n\n"
                "💡 **예시:**\n"
                "• `/new_project my-app`\n"
                "• `/new_project api-server`\n"
                "• `/new_project webapp2024`\n\n"
                "📝 **프로젝트명 규칙:**\n"
                "• 영문, 숫자, 하이픈(-), 언더스코어(_)만 사용\n"
                "• 공백 사용 불가\n\n"
                "💬 바로 시작하려면:\n"
                "`/new_project 원하는_프로젝트명`",
                parse_mode='Markdown'
            )
            return
        
        # Check for help flags and invalid project names
        first_arg = args[0]
        if first_arg in ['--help', '-h', 'help']:
            await update.message.reply_text(
                "🚀 **새 프로젝트 생성 도움말**\n\n"
                "📝 **사용법:**\n"
                "• `/new_project` - 대화형 프로젝트 선택\n"
                "• `/new_project [프로젝트명]` - 간단한 프로젝트 생성\n"
                "• `/new_project [프로젝트명] [경로]` - 사용자 지정 경로에 생성\n\n"
                "📁 **예시:**\n"
                "• `/new_project my-app` - ~/my-app 생성\n"
                "• `/new_project api-server ~/work` - ~/work/api-server 생성\n\n"
                "💡 **프로젝트명 규칙:**\n"
                "• 영문, 숫자, 하이픈(-), 언더스코어(_)만 사용\n"
                "• 공백이나 특수문자는 사용할 수 없습니다"
            )
            return
        
        # Validate project name
        if not re.match(r'^[a-zA-Z0-9_-]+$', first_arg):
            await update.message.reply_text(
                f"❌ **잘못된 프로젝트명**: `{first_arg}`\n\n"
                "📋 **프로젝트명 규칙:**\n"
                "• 영문, 숫자, 하이픈(-), 언더스코어(_)만 사용 가능\n"
                "• 공백이나 특수문자는 사용할 수 없습니다\n\n"
                "💡 **올바른 예시:** `my-app`, `api_server`, `webapp2024`\n"
                "❌ **잘못된 예시:** `my app`, `--help`, `@project`"
            )
            return
            
        project_name = first_arg
        project_path = None
        
        # Second argument is custom directory path
        if len(args) > 1:
            custom_dir = os.path.expanduser(args[1])
            project_path = os.path.join(custom_dir, project_name)
        
        # Show project creation progress
        progress_msg = await update.message.reply_text(
            f"🚀 프로젝트 생성 중...\n\n"
            f"📁 프로젝트: {project_name}\n"
            f"📦 Git 저장소 초기화\n"
            f"🎯 tmux 세션 생성\n"
            f"🤖 Claude Code 시작"
        )
        
        try:
            # Use unified ProjectCreator
            logger.info(f"Creating project using ProjectCreator: {project_name}")
            result = ProjectCreator.create_project_simple(
                project_name=project_name,
                project_path=project_path,
                initialize_git=True,
                install_dev_kit=True
            )
            
            if result['status'] == 'success':
                target_session = result['session_name']
                target_directory = result['project_path']
                
                # Auto-switch to new session if it's different from current
                if target_session != self.config.session_name:
                    await self._auto_switch_to_session(target_session, update)
                
                # Success status indicators
                git_status = "📦 Git 저장소 초기화됨" if result.get('git_initialized') else "⚠️ Git 초기화 건너뜀"
                session_status = "🎯 세션 생성됨" if result.get('session_created') else "✅ 기존 세션 사용"
                
                success_msg = f"""✅ 프로젝트 생성 완료!

📁 프로젝트: {project_name}
📂 경로: {target_directory}
🎯 세션: {target_session}
{git_status}
{session_status}

🎉 모든 기능이 준비되었습니다!"""
                
                # Use standardized keyboard
                reply_markup = self.get_main_keyboard()
                
                await progress_msg.edit_text(
                    success_msg,
                    reply_markup=reply_markup
                )
                
                
            else:
                error_msg = f"""❌ 프로젝트 생성 실패

오류: {result.get('error', 'Unknown error')}

💡 다시 시도하거나 관리자에게 문의하세요."""
                
                await progress_msg.edit_text(error_msg)
                logger.error(f"Project creation failed: {result}")
                
        except Exception as e:
            error_msg = f"""❌ 프로젝트 생성 중 오류 발생

오류: {str(e)}

💡 다시 시도하거나 관리자에게 문의하세요."""
            
            await progress_msg.edit_text(error_msg)
            logger.error(f"ProjectCreator exception: {e}")
            import traceback
            traceback.print_exc()
    
    
    async def help_command(self, update, context):
        """Help command handler"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
            
        help_text = """🤖 **Claude-Ops Telegram Bot**

📝 **주요 명령어:**
• `/sessions` - 활성 세션 목록 보기
• `/summary` - 대기 중 세션 요약
• `/board` - 세션 보드 (그리드 뷰)
• `/log` - Claude 화면 실시간 확인
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/erase` - 현재 입력 지우기 (Ctrl+C 전송)
• `/status` - 봇 및 tmux 세션 상태 확인
• `/help` - 도움말 보기
• `/new_project` - 새 Claude 프로젝트 생성

🚀 **워크플로우 사용법:**
**프롬프트와 함께 사용** (예: `/기획 사용자 인증 시스템 개선`):
• `/기획 [내용]` - 구조적 기획 및 계획 수립
• `/구현 [내용]` - DRY 원칙 기반 체계적 구현
• `/안정화 [내용]` - 구조적 지속가능성 검증
• `/배포 [내용]` - 최종 검증 및 배포
• `/전체사이클 [내용]` - 전체 워크플로우 실행

💡 빠른 시작:
1. `/new_project my_app` - 프로젝트 생성
2. 일반 텍스트로 Claude와 대화
3. `/log` - Claude 화면 확인
4. `/전체사이클 새 기능 개발` - 워크플로우 실행

❓ 메시지에 Reply하면 해당 세션으로 명령 전송"""
        
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

                    # Filter out prompt separator lines (─────────────)
                    filtered_lines = []
                    for line in display_lines:
                        # Skip lines that are mostly horizontal line characters
                        # These are Claude Code's prompt separators
                        stripped = line.strip()
                        if stripped and len(stripped) > 10:
                            # Check if line is mostly composed of box drawing characters
                            box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                            if box_chars / len(stripped) > 0.8:
                                # This line is mostly separator characters, skip it
                                continue
                        filtered_lines.append(line)

                    screen_text = '\n'.join(filtered_lines)

                    # Check if we need to split the message due to Telegram limits
                    max_length = 3500
                    if len(screen_text) > max_length:
                        # Split into multiple messages
                        parts = []
                        current_part = ""

                        for line in filtered_lines:
                            if len(current_part + line + "\n") > max_length:
                                if current_part:
                                    parts.append(current_part)
                                current_part = line + "\n"
                            else:
                                current_part += line + "\n"
                        
                        if current_part:
                            parts.append(current_part)
                        
                        # Send each part as a separate message with session info
                        session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                        for i, part in enumerate(parts):
                            if i == 0:
                                header = f"📺 **Claude 화면 로그** [{target_session}]\n\n"
                                header += f"📁 **프로젝트**: `{session_display}`\n"
                                header += f"🎯 **세션**: `{target_session}`\n"
                                header += f"📏 **라인 수**: {len(filtered_lines)}줄 - Part {i+1}/{len(parts)}\n\n"
                                header += "**로그 내용:**\n"
                            else:
                                header = f"📺 **Part {i+1}/{len(parts)}** [{target_session}]\n\n"
                            # Send without markdown to avoid parsing errors
                            message = f"{header}{part.strip()}"
                            await update.message.reply_text(message, parse_mode=None)
                    else:
                        # Send without markdown to avoid parsing errors with session info
                        session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                        header = f"📺 **Claude 화면 로그** [{target_session}]\n\n"
                        header += f"📁 **프로젝트**: `{session_display}`\n"
                        header += f"🎯 **세션**: `{target_session}`\n"
                        header += f"📏 **라인 수**: {len(filtered_lines)}줄\n\n"
                        header += "**로그 내용:**\n"
                        message = f"{header}{screen_text}"
                        await update.message.reply_text(message, parse_mode=None)
                else:
                    await update.message.reply_text("📺 Claude 화면이 비어있습니다.")
            else:
                await update.message.reply_text("❌ Claude 화면을 캡처할 수 없습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"화면 캡처 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def _log_with_lines(self, update, context, line_count: int):
        """Common log function with specific line count"""
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

                    # Filter out prompt separator lines (─────────────)
                    filtered_lines = []
                    for line in display_lines:
                        # Skip lines that are mostly horizontal line characters
                        # These are Claude Code's prompt separators
                        stripped = line.strip()
                        if stripped and len(stripped) > 10:
                            # Check if line is mostly composed of box drawing characters
                            box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                            if box_chars / len(stripped) > 0.8:
                                # This line is mostly separator characters, skip it
                                continue
                        filtered_lines.append(line)

                    screen_text = '\n'.join(filtered_lines)

                    # Send without markdown to avoid parsing errors with session info
                    session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                    header = f"📺 Claude 화면 로그 [{target_session}]\n\n"
                    header += f"📁 프로젝트: {session_display}\n"
                    header += f"🎯 세션: {target_session}\n"
                    header += f"📏 라인 수: {len(filtered_lines)}줄\n\n"
                    header += "로그 내용:\n"
                    
                    # Check if we need to split the message due to Telegram limits
                    max_length = 3500
                    if len(header + screen_text) > max_length:
                        # Truncate the content
                        available_space = max_length - len(header) - 50  # 50 chars for truncation message
                        truncated_text = screen_text[:available_space] + "\n\n... (내용이 길어 일부 생략됨)"
                        message = f"{header}{truncated_text}"
                    else:
                        message = f"{header}{screen_text}"
                    
                    await update.message.reply_text(message, parse_mode=None)
                else:
                    await update.message.reply_text("📺 Claude 화면이 비어있습니다.")
            else:
                await update.message.reply_text("❌ Claude 화면을 캡처할 수 없습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"화면 캡처 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def log50_command(self, update, context):
        """Show 50 lines of Claude screen"""
        await self._log_with_lines(update, context, 50)
    
    async def log100_command(self, update, context):
        """Show 100 lines of Claude screen"""
        await self._log_with_lines(update, context, 100)
    
    async def log150_command(self, update, context):
        """Show 150 lines of Claude screen"""
        await self._log_with_lines(update, context, 150)
    
    async def log200_command(self, update, context):
        """Show 200 lines of Claude screen"""
        await self._log_with_lines(update, context, 200)
    
    async def log300_command(self, update, context):
        """Show 300 lines of Claude screen"""
        await self._log_with_lines(update, context, 300)
    
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
    
    async def erase_command(self, update, context):
        """Clear current input line (send Ctrl+C)"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check for reply-based session targeting
        target_session = self.config.session_name
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    target_session = reply_session
                    logger.info(f"📍 Reply 기반 erase: {target_session}")
        
        try:
            # Send Ctrl+C to clear current input
            result = os.system(f"tmux send-keys -t {target_session} C-c")
            
            if result == 0:
                logger.info(f"Ctrl+C 키 전송 완료: {target_session}")
                session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                await update.message.reply_text(f"🧹 `{session_display}` 세션의 현재 입력을 지웠습니다 (Ctrl+C)")
            else:
                logger.error(f"Ctrl+C 키 전송 실패: exit code {result}")
                await update.message.reply_text("❌ 입력 지우기 명령 전송에 실패했습니다.")
        except Exception as e:
            logger.error(f"입력 지우기 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def restart_command(self, update, context):
        """Restart Claude Code session with conversation continuity"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check for reply-based session targeting
        target_session = self.config.session_name
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    target_session = reply_session
                    logger.info(f"📍 Reply 기반 restart: {target_session}")
        
        # Check if target session exists
        session_exists = os.system(f"tmux has-session -t {target_session}") == 0
        if not session_exists:
            await update.message.reply_text(
                f"❌ 세션 `{target_session}`을 찾을 수 없습니다.\n"
                f"먼저 `/new_project`로 세션을 생성해주세요."
            )
            return
        
        try:
            # Show restart progress message
            session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
            progress_msg = await update.message.reply_text(
                f"🔄 `{session_display}` 세션 재시작 중...\n\n"
                f"📝 기존 대화 컨텍스트 보존\n"
                f"⚙️ 슬래시 커맨드 변경사항 반영\n"
                f"🔄 Claude Code 재시작 진행..."
            )
            
            # Step 1: Gracefully exit Claude Code
            logger.info(f"Gracefully exiting Claude Code in session: {target_session}")
            exit_result = os.system(f"tmux send-keys -t {target_session} 'exit' Enter")
            
            if exit_result != 0:
                logger.warning(f"Exit command failed, trying Ctrl+C: {target_session}")
                os.system(f"tmux send-keys -t {target_session} C-c")
            
            # Step 2: Wait for Claude Code to fully exit
            await asyncio.sleep(3)
            
            # Step 3: Resume with conversation continuity
            logger.info(f"Resuming Claude Code with --continue: {target_session}")
            resume_result = os.system(f"tmux send-keys -t {target_session} 'claude --continue' Enter")
            
            if resume_result == 0:
                # Wait a moment for Claude to start
                await asyncio.sleep(2)
                
                # Success message with enhanced features
                await progress_msg.edit_text(
                    f"✅ `{session_display}` 세션 재시작 완료!\n\n"
                    f"🎯 **기존 대화 컨텍스트 복원됨**\n"
                    f"📄 이전 작업 내역 및 파일 상태 보존\n"
                    f"⚡ 새로운 슬래시 커맨드 반영\n"
                    f"🚀 세션 연속성 보장\n\n"
                    f"💡 이제 변경된 기능을 바로 사용할 수 있습니다!"
                )
                logger.info(f"Successfully restarted Claude session with continuity: {target_session}")
            else:
                # Fallback to regular restart
                logger.warning(f"Resume failed, falling back to regular restart: {target_session}")
                fallback_result = os.system(f"tmux send-keys -t {target_session} 'claude' Enter")
                
                if fallback_result == 0:
                    await progress_msg.edit_text(
                        f"⚠️ `{session_display}` 세션 재시작 완료 (기본 모드)\n\n"
                        f"🔄 Claude Code가 새로 시작되었습니다\n"
                        f"⚡ 슬래시 커맨드 변경사항 반영\n"
                        f"📝 새로운 세션으로 초기화됨\n\n"
                        f"💡 기존 대화를 계속하려면 이전 작업 내역을 다시 알려주세요."
                    )
                else:
                    await progress_msg.edit_text(
                        f"❌ `{session_display}` 세션 재시작 실패\n\n"
                        f"🔧 수동으로 `claude` 명령어를 입력해주세요\n"
                        f"또는 `/new_project`로 새 세션을 생성하세요."
                    )
                    
        except Exception as e:
            logger.error(f"Claude 재시작 중 오류: {str(e)}")
            await update.message.reply_text(
                "❌ 세션 재시작 중 오류가 발생했습니다.\n"
                "수동으로 `claude` 명령어를 실행해주세요."
            )
    
    # REMOVED: fix_terminal command - non-functional
    async def fix_terminal_command_DEPRECATED(self, update, context):
        """DEPRECATED: Fix terminal command removed"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check for reply-based session targeting
        target_session = self.config.session_name
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    target_session = reply_session
                    logger.info(f"📍 Reply 기반 터미널 복구: {target_session}")
        
        # Parse optional arguments
        force_respawn = False
        if context.args:
            if "--force" in context.args:
                force_respawn = True
        
        # Check if target session exists
        session_exists = os.system(f"tmux has-session -t {target_session}") == 0
        if not session_exists:
            await update.message.reply_text(
                f"❌ 세션 `{target_session}`을 찾을 수 없습니다.\n"
                f"먼저 `/new_project`로 세션을 생성해주세요."
            )
            return
        
        try:
            from ..utils.terminal_health import TerminalRecovery, TerminalHealthChecker
            
            # Show progress message
            session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
            progress_msg = await update.message.reply_text(
                f"🔧 `{session_display}` 터미널 진단 중...\n\n"
                f"🔍 터미널 크기 및 출력 분석\n"
                f"⚙️ 복구 방법 결정\n"
                f"🔄 복구 진행 중..."
            )
            
            # Perform diagnosis and recovery
            result = TerminalRecovery.fix_terminal(target_session, force_respawn=force_respawn)
            
            if result['success']:
                health = result['health']
                recovery_method = result.get('recovery_method', 'diagnosis_only')
                
                # Create detailed success message
                success_msg = f"✅ `{session_display}` 터미널 복구 완료!\n\n"
                
                if recovery_method == 'soft_reset':
                    success_msg += "🔧 **복구 방법**: Soft Reset\n"
                    success_msg += "⚡ 작업 중단 없이 터미널 크기 재설정\n"
                    success_msg += "📐 새 크기: `165x73`\n\n"
                elif recovery_method == 'respawn_pane':
                    success_msg += "🔧 **복구 방법**: Pane Respawn\n"
                    success_msg += "🔄 패널 재생성 및 Claude 재시작\n"
                    success_msg += "📐 새 크기: `165x73`\n\n"
                else:
                    success_msg += "🔧 **복구 방법**: 진단만 수행\n"
                
                success_msg += f"📊 **현재 상태**: {health.actual_width}x{health.actual_height}\n"
                success_msg += "💡 터미널이 정상적으로 작동합니다"
                
                await progress_msg.edit_text(success_msg)
                logger.info(f"Successfully fixed terminal for {target_session}")
                
            else:
                # Show diagnostic information
                health = result['health']
                issues = health.issues if health.issues else ["알 수 없는 문제"]
                
                failure_msg = f"❌ `{session_display}` 터미널 복구 실패\n\n"
                failure_msg += "🔍 **감지된 문제들**:\n"
                for issue in issues:
                    failure_msg += f"  • {issue}\n"
                
                failure_msg += f"\n📊 **현재 상태**: {health.actual_width or '?'}x{health.actual_height or '?'}\n"
                failure_msg += f"🎯 **목표 크기**: {health.expected_width}x{health.expected_height}\n\n"
                
                failure_msg += "🔧 **수동 복구 방법**:\n"
                failure_msg += "1. `/fix_terminal --force` (강제 패널 재생성)\n"
                failure_msg += "2. 또는 `/restart` (Claude 재시작)\n"
                
                if health.screen_sample:
                    failure_msg += f"\n📺 **화면 샘플**:\n```\n{health.screen_sample[:200]}...\n```"
                
                await progress_msg.edit_text(failure_msg, parse_mode='Markdown')
                
        except ImportError:
            await progress_msg.edit_text(
                "❌ 터미널 복구 모듈을 찾을 수 없습니다.\n"
                "시스템 업데이트가 필요할 수 있습니다."
            )
        except Exception as e:
            logger.error(f"터미널 복구 중 오류: {str(e)}")
            await progress_msg.edit_text(
                f"❌ 터미널 복구 중 오류가 발생했습니다:\n{str(e)}"
            )
    
    async def clear_command(self, update, context):
        """Clear terminal screen (send Ctrl+L)"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check for reply-based session targeting
        target_session = self.config.session_name
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                session_exists = os.system(f"tmux has-session -t {reply_session}") == 0
                if session_exists:
                    target_session = reply_session
                    logger.info(f"📍 Reply 기반 clear: {target_session}")
        
        try:
            # Send Ctrl+L to clear screen
            result = os.system(f"tmux send-keys -t {target_session} C-l")
            
            if result == 0:
                logger.info(f"Ctrl+L 키 전송 완료: {target_session}")
                session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                await update.message.reply_text(f"🖥️ `{session_display}` 세션의 화면을 정리했습니다 (Ctrl+L)")
            else:
                logger.error(f"Ctrl+L 키 전송 실패: exit code {result}")
                await update.message.reply_text("❌ 화면 정리 명령 전송에 실패했습니다.")
        except Exception as e:
            logger.error(f"화면 정리 중 오류: {str(e)}")
            await update.message.reply_text("❌ 내부 오류가 발생했습니다.")
    
    async def board_command(self, update, context):
        """Session board - one-click access to all sessions and commands"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Show session board grid
        await self._show_session_action_grid(update.message.reply_text, None)
    
    async def summary_command(self, update, context):
        """Show summary of waiting sessions with wait times"""
        user_id = update.effective_user.id

        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return

        try:
            from ..utils.session_summary import summary_helper
            from ..telegram.message_utils import safe_send_message

            # Generate summary
            summary_message = summary_helper.generate_summary()

            # Use safe_send_message to handle long messages (auto-split)
            await safe_send_message(
                send_func=update.message.reply_text,
                text=summary_message,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"세션 요약 생성 오류: {str(e)}")
            await update.message.reply_text("❌ 세션 요약 생성 중 오류가 발생했습니다.")
    
    async def _switch_to_session(self, update, target_session: str, switch_type: str = "direct"):
        """Switch to specified session with common logic"""
        try:
            # Check if target session exists
            session_exists = os.system(f"tmux has-session -t {target_session}") == 0
            if not session_exists:
                await update.message.reply_text(f"❌ 세션 `{target_session}`이 존재하지 않습니다.")
                return
            
            # Switch active session using session_manager
            from ..session_manager import session_manager
            
            old_session = self.config.session_name
            success = session_manager.switch_session(target_session)
            
            if success:
                logger.info(f"🔄 {switch_type} 세션 전환: {old_session} → {target_session}")
                
                session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                
                # Get last 100 lines of log from the new session (will display 50)
                import subprocess
                result = subprocess.run(
                    f"tmux capture-pane -t {target_session} -p -S -100",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                log_content = ""
                if result.returncode == 0 and result.stdout:
                    # Use same safe approach as /log command - keep original spacing
                    current_screen = result.stdout
                    lines = current_screen.split('\n')

                    # Show last 50 lines initially
                    if len(lines) > 50:
                        display_lines = lines[-50:]
                    else:
                        display_lines = lines

                    # Filter out prompt separator lines (─────────────)
                    filtered_lines = []
                    for line in display_lines:
                        # Skip lines that are mostly horizontal line characters
                        stripped = line.strip()
                        if stripped and len(stripped) > 10:
                            # Check if line is mostly composed of box drawing characters
                            box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                            if box_chars / len(stripped) > 0.8:
                                # This line is mostly separator characters, skip it
                                continue
                        filtered_lines.append(line)

                    log_content = '\n'.join(filtered_lines)
                
                # Build message parts separately
                switch_message = (
                    f"🔄 **활성 세션 전환 완료**\n\n"
                    f"📍 현재 활성: `{target_session}`\n"
                    f"📁 프로젝트: `{session_display}`\n\n"
                    f"이제 `{session_display}` 세션이 활성화되었습니다.\n"
                    f"_(이전 세션: {old_session})_"
                )
                
                if log_content:
                    # Add log header
                    log_header = "\n\n📺 **최근 로그 (50줄)**:\n"
                    # Combine without markdown code blocks to avoid parsing errors
                    full_message = f"{switch_message}{log_header}{log_content}"
                else:
                    full_message = f"{switch_message}\n\n📺 화면이 비어있습니다."
                
                # Add quick log buttons like in board
                # Note: Use active session (empty string) instead of session name to avoid 64-byte limit
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = [
                    [
                        InlineKeyboardButton("📜 50줄", callback_data="quick_log_50:"),
                        InlineKeyboardButton("📜 100줄", callback_data="quick_log_100:"),
                        InlineKeyboardButton("📜 150줄", callback_data="quick_log_150:"),
                        InlineKeyboardButton("📜 200줄", callback_data="quick_log_200:")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Check message length and split if needed
                from .message_utils import safe_send_message, get_telegram_max_length
                
                if len(full_message) > get_telegram_max_length():
                    # Split long message
                    await safe_send_message(
                        update.message.reply_text,
                        full_message,
                        parse_mode=None,
                        reply_markup=reply_markup,
                        preserve_markdown=False  # 로그 내용이므로 마크다운 보존 불필요
                    )
                else:
                    # Send as single message
                    await update.message.reply_text(full_message, parse_mode=None, reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"❌ 세션 전환에 실패했습니다: {target_session}")
                
        except Exception as e:
            logger.error(f"세션 전환 중 오류: {str(e)}")
            await update.message.reply_text(f"❌ 세션 전환 중 오류가 발생했습니다: {str(e)}")
    
    async def sessions_command(self, update, context):
        """Show active sessions, switch to session, or send text to specific session
        
        Usage:
        - /sessions - Show all sessions
        - /sessions session_name - Switch to session
        - /sessions session_name text... - Send text to specific session
        """
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check for direct session name argument
        if context.args and len(context.args) > 0:
            target_session = context.args[0]
            
            # If more than one argument, treat the rest as text to send
            if len(context.args) > 1:
                # Join all arguments after the first as the message
                text_to_send = ' '.join(context.args[1:])
                
                # Check if session exists
                session_exists = os.system(f"tmux has-session -t {target_session}") == 0
                if not session_exists:
                    await update.message.reply_text(
                        f"❌ 세션 `{target_session}`이 존재하지 않습니다.\n"
                        f"사용 가능한 세션을 보려면 `/sessions`를 입력하세요."
                    )
                    return
                
                # Send text to the specific session
                import subprocess
                try:
                    # Use tmux send-keys to send the text
                    result = subprocess.run(
                        ["tmux", "send-keys", "-t", target_session, "-l", text_to_send],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        # Also send Enter to execute the command
                        subprocess.run(
                            ["tmux", "send-keys", "-t", target_session, "Enter"],
                            timeout=5
                        )
                        
                        session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                        await update.message.reply_text(
                            f"✅ 텍스트 전송 완료\n\n"
                            f"📍 대상 세션: {target_session}\n"
                            f"📁 프로젝트: {session_display}\n"
                            f"📝 전송된 텍스트: {text_to_send}\n\n"
                            f"💡 세션 로그를 보려면 /log를 사용하세요.",
                            parse_mode=None
                        )
                        
                        logger.info(f"텍스트 전송 성공: {target_session} <- {text_to_send[:100]}")
                    else:
                        error_msg = result.stderr if result.stderr else "Unknown error"
                        await update.message.reply_text(
                            f"❌ 텍스트 전송 실패\n\n"
                            f"오류: {error_msg}"
                        )
                        logger.error(f"텍스트 전송 실패: {error_msg}")
                        
                except subprocess.TimeoutExpired:
                    await update.message.reply_text("❌ 명령 실행 시간 초과")
                except Exception as e:
                    await update.message.reply_text(f"❌ 텍스트 전송 중 오류 발생: {str(e)}")
                    logger.error(f"텍스트 전송 예외: {str(e)}")
                
                return
            else:
                # Single argument - switch to session
                return await self._switch_to_session(update, target_session, "direct command")
        
        # Check if replying to a message - if so, switch to that session directly
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            reply_session = self.extract_session_from_message(original_text)
            if reply_session:
                return await self._switch_to_session(update, reply_session, "reply")
        
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
            for idx, session in enumerate(sessions):
                if session != active_session:
                    # Use index instead of full session name to avoid 64-byte limit
                    keyboard.append([InlineKeyboardButton(
                        f"🔄 {session}로 전환",
                        callback_data=f"select_session:{idx}"
                    )])
            
            # Use safe message sending to handle long session lists
            from .message_utils import safe_send_message
            
            if keyboard:
                keyboard.append([InlineKeyboardButton("🔙 뒤로", callback_data="back_to_menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await safe_send_message(update.message.reply_text, message,
                                      reply_markup=reply_markup, parse_mode=None)
            else:
                await safe_send_message(update.message.reply_text, message,
                                      parse_mode=None)
                
        except Exception as e:
            logger.error(f"세션 목록 조회 중 오류: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")

    async def connect_command(self, update, context):
        """Connect to an existing project directory.

        Usage:
        - /connect - Show list of available projects
        - /connect <path> - Connect to specific project path
        """
        user_id = update.effective_user.id

        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return

        from ..session_manager import session_manager

        # If path provided, connect directly
        if context.args and len(context.args) > 0:
            project_path = ' '.join(context.args)

            # Expand ~ to home directory
            project_path = os.path.expanduser(project_path)

            await update.message.reply_text(f"🔄 프로젝트에 연결 중: {project_path}")

            result = session_manager.connect_to_project(project_path)

            if result["status"] == "error":
                await update.message.reply_text(f"❌ {result['error']}")
            elif result["status"] == "switched":
                await update.message.reply_text(
                    f"✅ 기존 세션으로 전환됨\n\n"
                    f"🎯 세션: {result['session_name']}\n"
                    f"📁 경로: {result['project_path']}\n\n"
                    f"💡 이미 이 프로젝트에 활성 세션이 있어서 해당 세션으로 전환했습니다."
                )
            elif result["status"] == "created":
                await update.message.reply_text(
                    f"✅ 새 세션 생성 완료\n\n"
                    f"🎯 세션: {result['session_name']}\n"
                    f"📁 경로: {result['project_path']}\n\n"
                    f"💡 세션에서 Claude가 시작되었습니다."
                )

            return

        # No path provided - show project list
        try:
            # Get project scan directories from config
            scan_dirs = [os.path.expanduser("~/projects")]

            # Add current working directories from active sessions
            for session in session_manager.get_all_claude_sessions():
                session_path = session_manager.get_session_path(session)
                if session_path:
                    parent_dir = os.path.dirname(session_path)
                    if parent_dir and parent_dir not in scan_dirs:
                        scan_dirs.append(parent_dir)

            projects = session_manager.get_available_projects(scan_dirs)

            if not projects:
                await update.message.reply_text(
                    "📁 연결 가능한 프로젝트가 없습니다.\n\n"
                    "직접 경로를 지정하려면:\n"
                    "`/connect ~/path/to/project`",
                    parse_mode='Markdown'
                )
                return

            # Build message and keyboard
            message = "📁 연결 가능한 프로젝트\n\n"
            message += "프로젝트를 선택하거나 `/connect <경로>`로 직접 지정하세요.\n\n"

            keyboard = []
            for idx, project in enumerate(projects[:20]):  # Limit to 20 projects
                status_icon = "🟢" if project['has_session'] else "⚪"
                button_text = f"{status_icon} {project['name']}"

                # Store project path in callback data (use index to avoid 64-byte limit)
                keyboard.append([InlineKeyboardButton(
                    button_text,
                    callback_data=f"connect_project:{idx}"
                )])

                # Show preview in message
                status_text = "(활성 세션 있음)" if project['has_session'] else ""
                message += f"{status_icon} `{project['path']}` {status_text}\n"

            keyboard.append([InlineKeyboardButton("🔙 취소", callback_data="back_to_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Store projects in context for callback
            context.user_data['connect_projects'] = projects

            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"프로젝트 목록 조회 중 오류: {str(e)}", exc_info=True)
            await update.message.reply_text(f"❌ 오류 발생: {str(e)}")

    def get_main_keyboard(self):
        """Get traditional main keyboard layout (deprecated, use get_enhanced_main_keyboard)"""
        keyboard = [
            [
                InlineKeyboardButton("🎛️ Session Actions", callback_data="session_actions"),
                InlineKeyboardButton("📊 Status", callback_data="status")
            ],
            [
                InlineKeyboardButton("📺 Quick Log", callback_data="log"),
                InlineKeyboardButton("🚀 Start New", callback_data="start")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def get_enhanced_main_keyboard(self):
        """Get enhanced main keyboard with direct session actions"""
        current_session = self.config.session_name
        
        keyboard = [
            # Direct actions for current session (top priority)
            [InlineKeyboardButton("📊 Status", callback_data=f"direct_status:{current_session}"),
             InlineKeyboardButton("📺 Logs", callback_data=f"direct_logs:{current_session}")],
            [InlineKeyboardButton("⏸️ Pause", callback_data=f"direct_pause:{current_session}"),
             InlineKeyboardButton("🗑️ Erase", callback_data=f"direct_erase:{current_session}")],
            
            # Advanced features (secondary priority)
            [InlineKeyboardButton("🎛️ All Sessions", callback_data="session_actions")],
            [InlineKeyboardButton("🚀 Start New", callback_data="start"),
             InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    
    
    
    async def get_session_prompt_hint(self, session_name: str) -> str:
        """Get last prompt hint for session"""
        try:
            from ..utils.prompt_recall import PromptRecallSystem
            prompt_system = PromptRecallSystem()
            last_prompt = prompt_system.extract_last_user_prompt(session_name)
            
            if last_prompt and len(last_prompt.strip()) > 5:
                # Smart truncation for hint (max 60 chars)
                if len(last_prompt) > 60:
                    hint = last_prompt[:57] + "..."
                else:
                    hint = last_prompt
                return f"\n*마지막 프롬프트*: `{hint}`\n"
            else:
                return ""
        except Exception as e:
            logger.debug(f"Failed to get prompt hint: {str(e)}")
            return ""
    
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
        elif callback_data == "session_actions":
            await self._session_actions_callback(query, context)
        elif callback_data == "start":
            await self._start_callback(query, context)
        elif callback_data == "restart_session":
            await self._restart_session_callback(query, context)
        elif callback_data == "new_project_guide":
            await self._new_project_guide_callback(query, context)
        elif callback_data == "help":
            await self._help_callback(query, context)
        elif callback_data.startswith("select_session:"):
            # Get session index from callback_data
            session_idx_str = callback_data.split(":", 1)[1]
            try:
                session_idx = int(session_idx_str)
                # Get current session list to map index to name
                from ..session_manager import session_manager
                sessions = session_manager.get_all_claude_sessions()
                if 0 <= session_idx < len(sessions):
                    session_name = sessions[session_idx]
                    await self._select_session_callback(query, context, session_name)
                else:
                    await query.edit_message_text("❌ 세션을 찾을 수 없습니다.", parse_mode=None)
            except (ValueError, IndexError) as e:
                logger.error(f"Invalid session index: {session_idx_str}, error: {e}")
                await query.edit_message_text("❌ 잘못된 세션 선택입니다.", parse_mode=None)
        elif callback_data.startswith("session_menu:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_menu_callback(query, context, session_name)
        elif callback_data.startswith("direct_"):
            await self._direct_action_callback(query, context, callback_data)
        elif callback_data.startswith("session_grid:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_grid_callback(query, context, session_name)
        elif callback_data.startswith("session_log:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_log_callback(query, context, session_name)
        elif callback_data.startswith("session_switch:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_switch_callback(query, context, session_name)
        elif callback_data.startswith("session_stop:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_stop_callback(query, context, session_name)
        elif callback_data.startswith("session_pause:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_pause_callback(query, context, session_name)
        elif callback_data.startswith("session_erase:"):
            session_name = callback_data.split(":", 1)[1]
            await self._session_erase_callback(query, context, session_name)
        elif callback_data.startswith("quick_log_"):
            # Format: quick_log_150:session_name
            parts = callback_data.split(":", 1)
            line_count = int(parts[0].split("_")[-1])  # Extract number from quick_log_150
            session_name = parts[1]
            await self._quick_log_callback(query, context, line_count, session_name)
        elif callback_data.startswith("connect_project:"):
            # Get project index from callback_data
            project_idx_str = callback_data.split(":", 1)[1]
            try:
                project_idx = int(project_idx_str)
                # Get projects from user_data
                projects = context.user_data.get('connect_projects', [])
                if 0 <= project_idx < len(projects):
                    project = projects[project_idx]
                    await self._connect_project_callback(query, context, project['path'])
                else:
                    await query.edit_message_text("❌ 프로젝트를 찾을 수 없습니다.")
            except (ValueError, IndexError, KeyError) as e:
                logger.error(f"Invalid project index: {project_idx_str}, error: {e}")
                await query.edit_message_text("❌ 잘못된 프로젝트 선택입니다.")
        elif callback_data == "back_to_menu":
            await self._back_to_menu_callback(query, context)
        elif callback_data == "back_to_sessions":
            await self._session_actions_callback(query, context)
        elif callback_data.startswith("compact_"):
            # Handle /compact related callbacks
            await self._compact_callback(query, context)
    
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
                    # Show with session info for proper reply targeting
                    session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                    lines = current_screen.split('\n')
                    header = f"📺 **Claude 화면 로그** [{target_session}]\n\n"
                    header += f"📁 **프로젝트**: `{session_display}`\n"
                    header += f"🎯 **세션**: `{target_session}`\n"
                    header += f"📏 **라인 수**: {len(lines)}줄\n\n"
                    header += "**로그 내용:**\n"
                    message = f"{header}{current_screen}"
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
        help_text = """🤖 Claude-Ops Telegram Bot

📝 주요 명령어:
• /new_project - 새 프로젝트 생성
• /sessions - 세션 목록 보기
• /log - Claude 화면 확인
• /status - 봇 상태 확인

🎮 세션 제어:
• /stop - 작업 중단
• /restart - 세션 재시작
• /erase - 입력 지우기

🚀 워크플로우 (프롬프트와 함께):
• /기획 [내용] - 구조적 기획
• /구현 [내용] - 체계적 구현
• /안정화 [내용] - 지속가능성 검증
• /배포 [내용] - 최종 검증 및 배포
• /전체사이클 [내용] - 전체 워크플로우

💡 빠른 시작:
1. /new_project my_app - 프로젝트 생성
2. 텍스트 메시지로 Claude와 대화
3. /log - Claude 화면 확인
4. /전체사이클 새 기능 개발 - 워크플로우

❓ 메시지에 Reply하면 해당 세션으로 명령 전송"""
        
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    async def unknown_command_handler(self, update, context):
        """Handle unknown commands - check for Korean workflow commands first"""
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
        self.app.add_handler(CommandHandler("new_project", self.start_claude_command))  # Primary command
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("log", self.log_command))
        self.app.add_handler(CommandHandler("logs", self.log_command))  # Alias for common typo
        self.app.add_handler(CommandHandler("log50", self.log50_command))
        self.app.add_handler(CommandHandler("log100", self.log100_command))
        self.app.add_handler(CommandHandler("log150", self.log150_command))
        self.app.add_handler(CommandHandler("log200", self.log200_command))
        self.app.add_handler(CommandHandler("log300", self.log300_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("erase", self.erase_command))
        self.app.add_handler(CommandHandler("restart", self.restart_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("connect", self.connect_command))
        self.app.add_handler(CommandHandler("board", self.board_command))
        self.app.add_handler(CommandHandler("summary", self.summary_command))
        # REMOVED: fix_terminal command handler
        # self.app.add_handler(CommandHandler("fix_terminal", self.fix_terminal_command))
        
        # TADD Workflow Commands
        self.app.add_handler(CommandHandler("planning", self.workflow_planning_command))
        self.app.add_handler(CommandHandler("implementation", self.workflow_implementation_command))
        self.app.add_handler(CommandHandler("stabilization", self.workflow_stabilization_command))
        self.app.add_handler(CommandHandler("deployment", self.workflow_deployment_command))
        self.app.add_handler(CommandHandler("fullcycle", self.workflow_fullcycle_command))
        
        # REMOVED: Detection analysis commands - non-functional
        # self.app.add_handler(CommandHandler("detection_status", self.detection_status_command))
        # self.app.add_handler(CommandHandler("detection_report", self.detection_report_command))
        # self.app.add_handler(CommandHandler("detection_trends", self.detection_trends_command))
        # self.app.add_handler(CommandHandler("detection_improve", self.detection_improve_command))
        
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
            BotCommand("sessions", "🔄 활성 세션 목록 보기"),
            BotCommand("connect", "📁 기존 프로젝트에 세션 연결"),
            BotCommand("board", "🎯 세션 보드"),
            BotCommand("summary", "📊 대기 중 세션 요약"),
            BotCommand("log", "📺 현재 Claude 화면 실시간 확인"),
            BotCommand("stop", "⛔ Claude 작업 중단 (ESC 키 전송)"),
            BotCommand("erase", "🧹 현재 입력 지우기 (Ctrl+C 전송)"),
            BotCommand("status", "📊 봇 및 tmux 세션 상태 확인"),
            BotCommand("help", "❓ 도움말 보기"),
            BotCommand("new_project", "🆕 새 Claude 프로젝트 생성")
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
                    "/new_project 명령으로 새 세션을 시작하세요.",
                    parse_mode='Markdown'
                )
                return
            
            # Create session selection keyboard
            keyboard = []
            for idx, session in enumerate(sessions):
                session_info = session_manager.get_session_info(session)

                # Display name (remove claude_ prefix)
                display_name = session_info["directory"]

                # Status icons
                status_icon = "✅" if session_info["exists"] else "❌"
                current_icon = "🎯 " if session_info["is_active"] else ""

                # Use index instead of full session name to avoid 64-byte limit
                keyboard.append([
                    InlineKeyboardButton(
                        f"{current_icon}{status_icon} {display_name}",
                        callback_data=f"select_session:{idx}"
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
                
                # Get last 30 lines of log from the new session
                import subprocess
                result = subprocess.run(
                    f"tmux capture-pane -t {session_name} -p -S -30",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                log_content = ""
                if result.returncode == 0 and result.stdout.strip():
                    log_content = result.stdout.strip()
                    # Limit to last 20 lines for cleaner display
                    lines = log_content.split('\n')
                    if len(lines) > 20:
                        log_content = '\n'.join(lines[-20:])
                
                switch_message = (
                    f"✅ **세션 전환 완료**\n\n"
                    f"📍 현재 활성: `{session_name}`\n"
                    f"📁 상태 파일: `{new_status_file}`\n\n"
                    f"이제 `{session_name}` 세션을 모니터링합니다.\n"
                    f"_(이전: {current_session})_\n"
                )
                
                if log_content:
                    switch_message += f"\n📺 **최근 로그 (20줄)**:\n```\n{log_content}\n```"
                else:
                    switch_message += "\n📺 화면이 비어있습니다."
                
                await query.edit_message_text(
                    switch_message,
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
                
                # Initialize session for compatibility  
                await self._initialize_new_session_callback(self.config.session_name, query)
                status_msg = "🚀 Claude 세션을 시작했습니다!"
            else:
                status_msg = "✅ Claude 세션이 이미 실행 중입니다."
            
            reply_markup = self.get_main_keyboard()
            
            welcome_msg = f"""🤖 **Claude-Telegram Bridge**

{status_msg}

**📁 작업 디렉토리**: `{self.config.working_directory}`
**🎯 세션 이름**: `{self.config.session_name}`

🎯 **세션 제어판** 사용 가능!"""
            
            await query.edit_message_text(
                welcome_msg,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Restart session callback error: {str(e)}")
            await query.answer("❌ 세션 재시작 실패")
    
    async def _new_project_guide_callback(self, query, context):
        """Show new project creation guide"""
        try:
            keyboard = [
                [InlineKeyboardButton("🔙 뒤로", callback_data="start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            guide_msg = """🎆 **새 프로젝트 생성 가이드**

🚀 **Claude Dev Kit으로 새 프로젝트 생성**:

📝 **명령어 사용법**:
```
/new-project 프로젝트명
```

📁 **예시**:
• `/new-project my_web_app` → `~/projects/my_web_app`
• `/new-project ai_chatbot` → `~/projects/ai_chatbot`
• `/new-project data_analysis` → `~/projects/data_analysis`

🎯 **자동 설치 내용**:
• 📝 **CLAUDE.md** - 프로젝트 가이드
• 🚀 **main_app.py** - 애플리케이션 시작점
• 📁 **src/, docs/, tests/** - 완전한 프로젝트 구조
• 🔧 **개발 워크플로우 템플릿**
• 📦 **Git 저장소** - 자동 초기화
• 🛠️ **claude-dev-kit** - 원격 설치

💬 **지금 바로 시작하세요!**
`/new-project 원하는프로젝트명` 입력하면 끝!
"""
            
            await query.edit_message_text(
                guide_msg,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"New project guide callback error: {str(e)}")
            await query.answer("❌ 가이드 로드 실패")
        except Exception as e:
            logger.error(f"Claude 세션 시작 중 오류: {str(e)}")
            await query.edit_message_text("❌ 내부 오류가 발생했습니다.")
    
    async def _back_to_menu_callback(self, query, context):
        """Back to one-click session menu (no longer needed - redirect to session grid)"""
        await self._show_session_action_grid(query.edit_message_text, query)

    async def _connect_project_callback(self, query, context, project_path: str):
        """Connect to project callback"""
        try:
            from ..session_manager import session_manager

            await query.edit_message_text(f"🔄 프로젝트에 연결 중: {project_path}")

            result = session_manager.connect_to_project(project_path)

            if result["status"] == "error":
                await query.edit_message_text(f"❌ {result['error']}")
            elif result["status"] == "switched":
                await query.edit_message_text(
                    f"✅ 기존 세션으로 전환됨\n\n"
                    f"🎯 세션: {result['session_name']}\n"
                    f"📁 경로: {result['project_path']}\n\n"
                    f"💡 이미 이 프로젝트에 활성 세션이 있어서 해당 세션으로 전환했습니다."
                )
            elif result["status"] == "created":
                await query.edit_message_text(
                    f"✅ 새 세션 생성 완료\n\n"
                    f"🎯 세션: {result['session_name']}\n"
                    f"📁 경로: {result['project_path']}\n\n"
                    f"💡 세션에서 Claude가 시작되었습니다."
                )

        except Exception as e:
            logger.error(f"Connect project callback error: {str(e)}")
            await query.edit_message_text(f"❌ 프로젝트 연결 실패: {str(e)}")

    async def _compact_callback(self, query, context):
        """Handle /compact related callbacks"""
        callback_data = query.data
        
        # Route to compact handler
        response = await self.compact_handler.handle_callback(query, context)
        
        # If response is None (ignored), do nothing
        if response is None:
            return
        
        # Otherwise, update the message with the response
        if response:
            await query.edit_message_text(response, parse_mode='Markdown')
    
    async def _initialize_new_session(self, session_name: str, update) -> bool:
        """Initialize new Claude session with smart detection and setup"""
        try:
            # Wait a moment for Claude to fully start
            import time
            time.sleep(2)
            
            # Capture current screen to analyze state
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to capture screen for {session_name}")
                return False
            
            screen_content = result.stdout.strip()
            logger.info(f"Screen content length: {len(screen_content)}")
            
            # Check if screen has example text or prompts
            has_example_text = self._detect_example_text(screen_content)
            
            if has_example_text:
                logger.info(f"Detected example text in {session_name}, clearing with Ctrl+C")
                # Clear example text with Ctrl+C
                os.system(f"tmux send-keys -t {session_name} C-c")
                time.sleep(1)
            
            # Send /init to establish proper message cycle
            logger.info(f"Sending /init to {session_name} for proper initialization")
            os.system(f"tmux send-keys -t {session_name} '/init'")
            os.system(f"tmux send-keys -t {session_name} Enter")
            
            # Send initialization notification
            init_msg = "🎆 세션 초기화 완료\n\n"
            if has_example_text:
                init_msg += "✨ 예시 텍스트 제거 후 /init 실행\n"
            else:
                init_msg += "✨ 빈 세션에 /init 실행\n"
            init_msg += f"🎯 세션: {session_name}\n\n🚀 이제 정상적으로 사용 가능합니다!"
            
            await update.message.reply_text(init_msg)
            
        except Exception as e:
            logger.error(f"Session initialization failed: {str(e)}")
            return False
    
    async def _initialize_new_session_callback(self, session_name: str, query) -> bool:
        """Initialize new Claude session (callback version)"""
        try:
            # Wait a moment for Claude to fully start
            import time
            time.sleep(2)
            
            # Capture current screen to analyze state
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to capture screen for {session_name}")
                return False
            
            screen_content = result.stdout.strip()
            logger.info(f"Screen content length: {len(screen_content)}")
            
            # Check if screen has example text or prompts
            has_example_text = self._detect_example_text(screen_content)
            
            if has_example_text:
                logger.info(f"Detected example text in {session_name}, clearing with Ctrl+C")
                # Clear example text with Ctrl+C
                os.system(f"tmux send-keys -t {session_name} C-c")
                time.sleep(1)
            
            # Send /init to establish proper message cycle
            logger.info(f"Sending /init to {session_name} for proper initialization")
            os.system(f"tmux send-keys -t {session_name} '/init'")
            os.system(f"tmux send-keys -t {session_name} Enter")
            
            return True
            
            return True
            
        except Exception as e:
            logger.error(f"Session initialization failed: {str(e)}")
            return False
    
    def _detect_example_text(self, screen_content: str) -> bool:
        """Detect if screen contains example text or prompts that should be cleared"""
        # Common Claude Code example patterns
        example_patterns = [
            "write a python script",
            "create a simple",
            "help me with",
            "example usage",
            "sample code", 
            "Try asking",
            "For example",
            "You can ask",
            "Here are some things you can try:",
            "I'm Claude, an AI assistant",
        ]
        
        screen_lower = screen_content.lower()
        
        # Check if any example patterns exist
        for pattern in example_patterns:
            if pattern.lower() in screen_lower:
                logger.info(f"Found example pattern: {pattern}")
                return True
        
        # Check if there's substantial text (more than just prompt)
        lines = [line.strip() for line in screen_content.split('\n') if line.strip()]
        non_empty_lines = [line for line in lines if line and line != '>' and not line.startswith('claude')]
        
        if len(non_empty_lines) > 2:  # More than basic prompt suggests example content
            logger.info(f"Detected substantial content ({len(non_empty_lines)} lines), treating as example")
            return True
        
        return False
    
    
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
    
    async def _auto_switch_to_session(self, session_name: str, update) -> bool:
        """Automatically switch main session to the new session"""
        try:
            from ..session_manager import session_manager
            
            old_session = session_manager.get_active_session() 
            success = session_manager.switch_session(session_name)
            
            if success:
                logger.info(f"🔄 자동 세션 전환: {old_session} → {session_name}")
                
                # Send confirmation message
                await update.message.reply_text(
                    f"🔄 메인 세션 자동 전환 완료\n\n"
                    f"📍 현재 활성: `{session_name}`\n\n"
                    f"✅ 이제 모든 메시지가 새 세션으로 전송됩니다!\n"
                    f"_(이전: {old_session})_",
                    parse_mode='Markdown'
                )
                return True
            else:
                logger.warning(f"자동 세션 전환 실패: {session_name}")
                return False
                
        except Exception as e:
            logger.error(f"자동 세션 전환 중 오류: {str(e)}")
            return False
    
    async def _session_actions_callback(self, query, context):
        """Show one-click session action grid (same as menu command now)"""
        await self._show_session_action_grid(query.edit_message_text, query)
    
    async def _show_session_action_grid(self, reply_func, query=None):
        """Show one-click session action grid with all sessions and direct actions"""
        try:
            # Use same session list as summary for consistency (ALL sessions)
            from ..utils.session_summary import summary_helper
            all_sessions = summary_helper.get_all_sessions_with_status()
            
            # Extract session info - unpack 5-tuple correctly
            # Reverse order for board: recent sessions (short wait time) at bottom
            sessions_info = [(session_name, wait_time, status, has_record) for session_name, wait_time, _, status, has_record in reversed(all_sessions)]
            
            if not sessions_info:
                await reply_func(
                    "❌ **세션 없음**\n\nClaude 세션을 찾을 수 없습니다.\n\n/new_project 명령으로 새 세션을 시작하세요.",
                    parse_mode='Markdown'
                )
                return
            
            keyboard = []
            
            # Session rows with direct actions (2 sessions per row max)
            for i in range(0, len(sessions_info), 2):
                row_sessions = sessions_info[i:i+2]
                session_row = []
                
                for session_name, wait_time, status, has_record in row_sessions:
                    display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                    current_icon = "⭐" if session_name == self.config.session_name else ""
                    
                    # Use status from summary helper for consistency
                    status_icon = "🔨" if status == 'working' else "💤"
                    
                    # Format wait time for button
                    if status == 'waiting' and wait_time > 0:
                        wait_str = summary_helper.format_wait_time(wait_time)
                        # Add transparency indicator for estimates
                        if not has_record:
                            wait_str = f"~{wait_str}"
                    else:
                        wait_str = ""
                    
                    # Get very short prompt hint for button
                    hint = await self._get_session_hint_short(session_name)
                    
                    # Build button text with wait time
                    if wait_str:
                        button_text = f"{current_icon}{status_icon} {display_name} ({wait_str}){hint}"
                    else:
                        button_text = f"{current_icon}{status_icon} {display_name}{hint}"
                    
                    session_row.append(
                        InlineKeyboardButton(
                            button_text,
                            callback_data=f"session_grid:{session_name}"
                        )
                    )
                
                keyboard.append(session_row)
            
            # No utility buttons needed - sessions are the main content
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Count working and waiting sessions
            waiting_count = sum(1 for _, _, status, _ in sessions_info if status == 'waiting')
            working_count = sum(1 for _, _, status, _ in sessions_info if status == 'working')
            
            await reply_func(
                f"🎯 **세션 보드** (전체: {len(sessions_info)}개)\n"
                f"대기: {waiting_count}개 | 작업중: {working_count}개\n\n"
                f"🎯 현재 메인: `{self.config.session_name}`\n\n"
                "💆‍♂️ 세션 클릭 → 직접 액션 메뉴:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Session action grid error: {str(e)}")
            await reply_func(
                f"❌ **세션 조회 실패**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _get_session_hint_short(self, session_name: str) -> str:
        """Get very short hint for session (max 15 chars for button)"""
        try:
            from ..utils.prompt_recall import PromptRecallSystem
            prompt_system = PromptRecallSystem()
            last_prompt = prompt_system.extract_last_user_prompt(session_name)
            
            if last_prompt and len(last_prompt.strip()) > 3:
                if len(last_prompt) > 12:
                    hint = last_prompt[:9] + "..."
                else:
                    hint = last_prompt
                return f"\n📝{hint}"
            return ""
        except:
            return ""
    
    async def _session_grid_callback(self, query, context, session_name):
        """Show direct action menu for selected session from grid"""
        try:
            display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
            is_current = session_name == self.config.session_name
            
            # Get session status and prompt hint
            from ..utils.session_state import is_session_working, get_session_working_info
            from ..utils.session_summary import summary_helper
            is_working = is_session_working(session_name)
            info = get_session_working_info(session_name)
            
            # Get wait time
            wait_time = summary_helper.tracker.get_wait_time_since_completion(session_name)
            has_record = summary_helper.tracker.has_completion_record(session_name)
            
            if is_working:
                status_emoji = "🔄 작업중"
            else:
                if wait_time > 0:
                    wait_str = summary_helper.format_wait_time(wait_time)
                    if not has_record:
                        status_emoji = f"💤 대기중 (~{wait_str} 추정)"
                    else:
                        status_emoji = f"💤 대기중 ({wait_str})"
                else:
                    status_emoji = "💤 대기중"
            
            # Get full prompt hint for this view
            prompt_hint = await self.get_session_prompt_hint(session_name)
            
            # Get recent log (30 lines for session action view)
            recent_log = await self._get_session_log_content(session_name, 30)
            
            # Create quick log buttons grid (useful actions)
            keyboard = [
                [
                    InlineKeyboardButton("📺50", callback_data=f"quick_log_50:{session_name}"),
                    InlineKeyboardButton("📺100", callback_data=f"quick_log_100:{session_name}"),
                    InlineKeyboardButton("📺150", callback_data=f"quick_log_150:{session_name}")
                ],
                [
                    InlineKeyboardButton("📺200", callback_data=f"quick_log_200:{session_name}"),
                    InlineKeyboardButton("📺300", callback_data=f"quick_log_300:{session_name}"),
                    InlineKeyboardButton("🏠 메인설정", callback_data=f"session_switch:{session_name}")
                ],
                [
                    InlineKeyboardButton("⏸️ Stop", callback_data=f"session_stop:{session_name}"),
                    InlineKeyboardButton("🗑️ Erase", callback_data=f"session_erase:{session_name}"),
                    InlineKeyboardButton("◀️ 뒤로", callback_data="session_actions")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Create reply-targeting optimized message format
            session_action_msg = f"""🎯 **{display_name}** 세션 액션

📊 **상태**: {status_emoji}
🎯 **메인 세션**: {'✅ 현재 메인' if is_current else '❌ 다른 세션'}
🎛️ 세션: `{session_name}`

{prompt_hint}

📺 **최근 진행사항 (30줄)**:
```
{recent_log}
```

💆‍♂️ **원클릭 액션 선택**:
이 메시지에 답장하여 `{session_name}` 세션에 직접 명령어를 전송할 수 있습니다."""
            
            await query.edit_message_text(
                session_action_msg,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Session grid callback error for {session_name}: {str(e)}", exc_info=True)
            try:
                await query.answer("❌ 세션 액션 로드 실패")
            except:
                pass  # Already answered
    
    async def _direct_action_callback(self, query, context, callback_data):
        """Handle direct action callbacks from enhanced main menu"""
        try:
            # Parse callback data: direct_{action}:{session_name}
            parts = callback_data.split(":", 1)
            if len(parts) != 2:
                await query.answer("❌ 잘못된 액션 데이터입니다.")
                return
                
            action_part = parts[0]  # direct_{action}
            session_name = parts[1]
            action = action_part.split("_", 1)[1]  # Extract action from direct_{action}
            
            # Route to appropriate action handler
            if action == "status":
                from ..utils.session_state import is_session_working, get_session_working_info
                
                is_working = is_session_working(session_name)
                info = get_session_working_info(session_name)
                
                status_msg = f"""📊 **세션 상태**: `{session_name}`

• **상태**: {'🔄 작업 중' if is_working else '💤 대기 중'}
• **상태 세부**: {info.get('logic', 'unknown')}
• **감지 패턴**: {len(info.get('working_patterns_found', []))}개

*직접 액션으로 빠르게 접근!*"""
                
                await query.edit_message_text(
                    status_msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 새로고침", callback_data=f"direct_status:{session_name}")],
                        [InlineKeyboardButton("🔙 메뉴로", callback_data="back_to_menu")]
                    ]),
                    parse_mode='Markdown'
                )
                
            elif action == "logs":
                await self._session_log_callback(query, context, session_name)
                
            elif action == "pause":
                await self._session_pause_callback(query, context, session_name)
                
            elif action == "erase":
                await self._session_erase_callback(query, context, session_name)
                
            else:
                await query.answer(f"❌ 알 수 없는 액션: {action}")
                
        except Exception as e:
            logger.error(f"Direct action callback error: {str(e)}")
            await query.answer("❌ 액션 처리 중 오류가 발생했습니다.")
    
    async def _session_menu_callback(self, query, context, session_name):
        """Show action menu for specific session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ **세션 없음**\n\n"
                    f"세션 `{session_name}`이 존재하지 않습니다.",
                    parse_mode='Markdown'
                )
                return
            
            display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
            is_current = session_name == self.config.session_name
            
            # Get session status and prompt hint
            from ..utils.session_state import is_session_working
            is_working = is_session_working(session_name)
            status_emoji = "🔄 작업중" if is_working else "💤 대기중"
            
            # Get prompt hint
            prompt_hint = await self.get_session_prompt_hint(session_name)
            
            # Get recent log (50 lines)
            recent_log = await self._get_session_log_content(session_name, 50)
            
            # Create action buttons
            keyboard = [
                [
                    InlineKeyboardButton("🏠 메인세션 설정", callback_data=f"session_switch:{session_name}"),
                    InlineKeyboardButton("📜 더 많은 로그", callback_data=f"session_log:{session_name}")
                ],
                [
                    InlineKeyboardButton("⏸️ Pause (ESC)", callback_data=f"session_pause:{session_name}"),
                    InlineKeyboardButton("🗑️ Erase (Ctrl+C)", callback_data=f"session_erase:{session_name}")
                ],
                [
                    InlineKeyboardButton("◀️ 세션 목록으로", callback_data="back_to_sessions"),
                    InlineKeyboardButton("🔙 메뉴로", callback_data="back_to_menu")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status_text = "🎯 현재 메인" if is_current else "일반 세션"
            
            # Create comprehensive session info with auto-log
            session_info = f"""🎛️ **{display_name} 세션 제어판**

📊 **세션 정보**:
• **세션명**: `{session_name}`
• **상태**: {status_text} | {status_emoji}

💡 **마지막 작업**:
{prompt_hint}

📺 **최근 화면 (50줄)**:
```
{recent_log}
```

🎛️ **액션을 선택하세요:**"""
            
            await query.edit_message_text(
                session_info,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"세션 메뉴 표시 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **세션 메뉴 오류**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _session_log_callback(self, query, context, session_name):
        """Show logs for specific session with enhanced error handling"""
        logger.info(f"📜 로그 콜백 시작 - 세션: {session_name}")
        
        try:
            import subprocess
            
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                logger.warning(f"세션 '{session_name}' 존재하지 않음")
                await query.edit_message_text(
                    f"❌ 세션 없음\n\n세션 '{session_name}'이 존재하지 않습니다."
                )
                return
            
            logger.info(f"✅ 세션 '{session_name}' 존재 확인됨")
            
            # Get screen content with moderate line count - use safer approach
            try:
                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-100"], 
                    capture_output=True, 
                    text=True,
                    timeout=10,  # Add timeout to prevent hanging
                    check=False  # Don't raise exception on non-zero exit
                )
                
                logger.info(f"📊 tmux 명령어 실행 완료 - returncode: {result.returncode}")
                
                if result.returncode == 0:
                    current_screen = result.stdout
                    logger.info(f"📏 캡처된 로그 길이: {len(current_screen)} characters")
                    
                    if current_screen and current_screen.strip():
                        display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                        lines = current_screen.split('\n')

                        # Filter out prompt separator lines (─────────────)
                        filtered_lines = []
                        for line in lines:
                            # Skip lines that are mostly horizontal line characters
                            stripped = line.strip()
                            if stripped and len(stripped) > 10:
                                # Check if line is mostly composed of box drawing characters
                                box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                                if box_chars / len(stripped) > 0.8:
                                    # This line is mostly separator characters, skip it
                                    continue
                            filtered_lines.append(line)

                        lines = filtered_lines  # Use filtered lines from now on

                        # More conservative length limit (considering header)
                        header = f"📜 {display_name} 세션 로그\n\n🎛️ 세션: {session_name}\n📏 라인 수: ~{len(lines)}줄\n\n"
                        max_content_length = 3500 - len(header)  # Leave room for header

                        filtered_screen = '\n'.join(lines)  # Use filtered lines

                        if len(filtered_screen) > max_content_length:
                            logger.info("📝 로그가 길어서 잘라내기 실행")
                            # Show last part with truncation notice
                            truncated_lines = []
                            current_length = len("...(앞부분 생략)...\n")

                            for line in reversed(lines):
                                line_length = len(line) + 1  # +1 for newline
                                if current_length + line_length > max_content_length:
                                    break
                                truncated_lines.insert(0, line)
                                current_length += line_length

                            screen_text = "...(앞부분 생략)...\n" + '\n'.join(truncated_lines)
                        else:
                            screen_text = filtered_screen
                        
                        # Escape potential problematic characters for safety
                        screen_text = screen_text.replace('```', '｀｀｀')  # Replace markdown code blocks
                        screen_text = screen_text.strip()
                        
                        message = f"{header}{screen_text}"

                        logger.info(f"📤 최종 메시지 길이: {len(message)} characters")
                        await query.edit_message_text(message, parse_mode=None)
                        logger.info("✅ 로그 메시지 전송 완료")
                        
                    else:
                        logger.info("📺 세션 화면이 비어있음")
                        display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                        await query.edit_message_text(f"📜 {display_name} 로그\n\n📺 세션 화면이 비어있습니다.")
                        
                else:
                    error_msg = result.stderr.strip() if result.stderr else "알 수 없는 오류"
                    logger.error(f"tmux capture-pane 실패 - stderr: {error_msg}")
                    await query.edit_message_text(
                        f"❌ 로그 캡처 실패\n\n세션 '{session_name}'의 로그를 가져올 수 없습니다.\n\n"
                        f"오류: {error_msg[:200]}..."  # Limit error message length
                    )
                    
            except subprocess.TimeoutExpired:
                logger.error("tmux 명령어 타임아웃")
                await query.edit_message_text("❌ 시간 초과\n\n로그 조회 시간이 초과되었습니다.")
                
            except subprocess.SubprocessError as se:
                logger.error(f"subprocess 오류: {str(se)}")
                await query.edit_message_text(f"❌ 명령어 실행 오류\n\n{str(se)[:200]}...")
                
        except Exception as e:
            logger.error(f"세션 로그 조회 중 예외 발생: {str(e)}", exc_info=True)
            await query.edit_message_text(
                f"❌ 로그 조회 오류\n\n예상치 못한 오류가 발생했습니다.\n\n"
                f"오류: {str(e)[:200]}..."
            )
    
    async def _session_switch_callback(self, query, context, session_name):
        """Switch main session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ 세션 없음\n\n"
                    f"세션 {session_name}이 존재하지 않습니다.",
                    parse_mode=None
                )
                return
            
            current_session = self.config.session_name
            
            if session_name == current_session:
                await query.edit_message_text(
                    f"ℹ️ 이미 메인 세션\n\n"
                    f"{session_name}이 이미 메인 세션입니다.",
                    parse_mode=None
                )
                return
            
            # Switch using session manager
            from ..session_manager import session_manager
            success = session_manager.switch_session(session_name)
            
            if success:
                display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                
                await query.edit_message_text(
                    f"🏠 메인 세션 변경 완료\n\n"
                    f"📍 현재 메인: {session_name}\n"
                    f"📁 프로젝트: {display_name}\n\n"
                    f"✅ 이제 {display_name} 세션이 메인 세션입니다.\n"
                    f"모니터링 시스템이 자동으로 업데이트됩니다.\n"
                    f"(이전: {current_session})",
                    parse_mode=None
                )
                
                # Restart monitoring for new session
                await self._restart_monitoring()
                
            else:
                await query.edit_message_text(
                    f"❌ 세션 전환 실패\n\n"
                    f"세션 {session_name}으로 전환할 수 없습니다.",
                    parse_mode=None
                )
                
        except Exception as e:
            logger.error(f"세션 전환 중 오류: {str(e)}")
            # Escape special characters in error message to prevent parse errors
            error_msg = str(e).replace('_', ' ').replace('*', ' ').replace('[', ' ').replace(']', ' ')
            await query.edit_message_text(
                f"❌ 내부 오류\n\n세션 전환 중 오류가 발생했습니다.\n오류: {error_msg}",
                parse_mode=None
            )
    
    async def _session_stop_callback(self, query, context, session_name):
        """Send stop (ESC) to specific session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ **세션 없음**\n\n"
                    f"세션 `{session_name}`이 존재하지 않습니다.",
                    parse_mode='Markdown'
                )
                return
            
            # Send ESC key
            result = os.system(f"tmux send-keys -t {session_name} Escape")
            
            if result == 0:
                display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                
                await query.edit_message_text(
                    f"⛔ **Stop 명령 전송**\n\n"
                    f"📍 세션: `{display_name}`\n"
                    f"⏸️ ESC 키를 전송했습니다.\n\n"
                    f"Claude 작업이 중단됩니다.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 세션 액션으로", callback_data=f"session_grid:{session_name}")],
                        [InlineKeyboardButton("🏠 메인 메뉴로", callback_data="back_to_menu")]
                    ]),
                    parse_mode='Markdown'
                )
                
                logger.info(f"ESC sent to session {session_name}")
            else:
                await query.answer("❌ Stop 명령 전송 실패")
                logger.error(f"Failed to send ESC to session {session_name}")
                
        except Exception as e:
            logger.error(f"Stop callback error: {str(e)}")
            await query.answer("❌ Stop 처리 중 오류 발생")
    
    async def _session_pause_callback(self, query, context, session_name):
        """Send pause (ESC) to specific session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ **세션 없음**\n\n"
                    f"세션 `{session_name}`이 존재하지 않습니다.",
                    parse_mode='Markdown'
                )
                return
            
            # Send ESC key
            result = os.system(f"tmux send-keys -t {session_name} Escape")
            
            if result == 0:
                display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                
                await query.edit_message_text(
                    f"⏸️ **Pause 명령 전송**\n\n"
                    f"🎛️ **대상 세션**: {display_name}\n"
                    f"⌨️ **전송된 키**: ESC\n\n"
                    f"✅ `{session_name}` 세션에 ESC 키를 전송했습니다.\n"
                    f"Claude 작업이 일시정지됩니다.",
                    parse_mode='Markdown'
                )
                
                logger.info(f"ESC 키 전송 완료: {session_name}")
            else:
                await query.edit_message_text(
                    f"❌ **Pause 실패**\n\n"
                    f"세션 `{session_name}`에 ESC 키를 전송할 수 없습니다.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"세션 pause 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **Pause 오류**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _session_erase_callback(self, query, context, session_name):
        """Send erase (Ctrl+C) to specific session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ **세션 없음**\n\n"
                    f"세션 `{session_name}`이 존재하지 않습니다.",
                    parse_mode='Markdown'
                )
                return
            
            # Send Ctrl+C key
            result = os.system(f"tmux send-keys -t {session_name} C-c")
            
            if result == 0:
                display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                
                await query.edit_message_text(
                    f"🗑️ **Erase 명령 전송**\n\n"
                    f"🎛️ **대상 세션**: {display_name}\n"
                    f"⌨️ **전송된 키**: Ctrl+C\n\n"
                    f"✅ `{session_name}` 세션에 Ctrl+C 키를 전송했습니다.\n"
                    f"현재 작업이 중단됩니다.",
                    parse_mode='Markdown'
                )
                
                logger.info(f"Ctrl+C 키 전송 완료: {session_name}")
            else:
                await query.edit_message_text(
                    f"❌ **Erase 실패**\n\n"
                    f"세션 `{session_name}`에 Ctrl+C 키를 전송할 수 없습니다.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"세션 erase 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **Erase 오류**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def _quick_log_callback(self, query, context, line_count: int, session_name: str):
        """Quick log callback with predefined line count"""
        try:
            import subprocess

            # If session_name is empty, use active session (for long session names that exceed 64-byte callback_data limit)
            if not session_name:
                session_name = self.config.session_name
            
            # Use tmux capture-pane with -S to specify start line (negative for history)
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{line_count}", 
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

                    # Filter out prompt separator lines (─────────────)
                    filtered_lines = []
                    for line in display_lines:
                        # Skip lines that are mostly horizontal line characters
                        stripped = line.strip()
                        if stripped and len(stripped) > 10:
                            # Check if line is mostly composed of box drawing characters
                            box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                            if box_chars / len(stripped) > 0.8:
                                # This line is mostly separator characters, skip it
                                continue
                        filtered_lines.append(line)

                    screen_text = '\n'.join(filtered_lines)
                    
                    # Send without markdown to avoid parsing errors with session info
                    session_display = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                    header = f"📺 빠른 로그 ({line_count}줄) [{session_name}]\n\n"
                    header += f"📁 프로젝트: {session_display}\n"
                    header += f"🎯 세션: {session_name}\n"
                    header += f"📏 라인 수: {len(filtered_lines)}줄\n\n"
                    header += "로그 내용:\n"
                    
                    # Check if we need to split the message due to Telegram limits
                    max_length = 3500
                    if len(header + screen_text) > max_length:
                        # Truncate the content
                        available_space = max_length - len(header) - 50  # 50 chars for truncation message
                        truncated_text = screen_text[:available_space] + "\n\n... (내용이 길어 일부 생략됨)"
                        message = f"{header}{truncated_text}"
                    else:
                        message = f"{header}{screen_text}"
                    
                    await query.edit_message_text(message, parse_mode=None)
                else:
                    await query.edit_message_text("📺 Claude 화면이 비어있습니다.")
            else:
                await query.edit_message_text("❌ Claude 화면을 캡처할 수 없습니다. tmux 세션을 확인해주세요.")
                
        except Exception as e:
            logger.error(f"빠른 로그 조회 중 오류: {str(e)}")
            await query.edit_message_text("❌ 내부 오류가 발생했습니다.")
    
    
    async def _get_session_log_content(self, session_name: str, line_count: int = 50) -> str:
        """Get recent log content from session with retry logic"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                return "세션이 존재하지 않습니다."
            
            # Try to capture with retry logic for attached sessions
            max_retries = 3
            for attempt in range(max_retries):
                # Use tmux capture-pane without -e to avoid ANSI escape codes
                result = subprocess.run(
                    f"tmux capture-pane -t {session_name} -p -S -{line_count}", 
                    shell=True, 
                    capture_output=True, 
                    text=True,
                    timeout=5  # Increased timeout for better reliability
                )
                
                if result.returncode == 0:
                    log_content = result.stdout.strip()
                    if not log_content and attempt < max_retries - 1:
                        # Empty content might be timing issue, retry
                        await asyncio.sleep(0.2)
                        continue
                    
                    if not log_content:
                        return "로그 내용이 없습니다."

                    # Filter out prompt separator lines (─────────────)
                    lines = log_content.split('\n')
                    filtered_lines = []
                    for line in lines:
                        # Skip lines that are mostly horizontal line characters
                        stripped = line.strip()
                        if stripped and len(stripped) > 10:
                            # Check if line is mostly composed of box drawing characters
                            box_chars = sum(1 for c in stripped if c in '─━═▀▄█├┤┴┬┼╭╮╯╰│')
                            if box_chars / len(stripped) > 0.8:
                                # This line is mostly separator characters, skip it
                                continue
                        filtered_lines.append(line)

                    log_content = '\n'.join(filtered_lines)

                    # Limit content length for Telegram message
                    if len(log_content) > 3000:  # Telegram message limit consideration
                        lines = filtered_lines  # Use already filtered lines
                        truncated_lines = lines[-30:]  # Show last 30 lines if too long
                        log_content = '\n'.join(truncated_lines)
                        log_content += f"\n\n... (총 {len(lines)}줄 중 마지막 30줄만 표시)"

                    return log_content
                else:
                    if attempt < max_retries - 1:
                        logger.warning(f"Capture attempt {attempt+1} failed for {session_name}, retrying...")
                        await asyncio.sleep(0.2)
                    else:
                        logger.error(f"Failed to capture session {session_name} after {max_retries} attempts: {result.stderr}")
                        
                        # Fallback: try basic info
                        info_result = subprocess.run(
                            f"tmux list-sessions | grep {session_name}",
                            shell=True,
                            capture_output=True,
                            text=True
                        )
                        
                        if info_result.returncode == 0:
                            return f"세션 정보: {info_result.stdout.strip()}\n(화면 캡처 실패 - 세션이 다른 터미널에 연결되어 있을 수 있습니다)"
                        
                        return "로그를 가져올 수 없습니다."
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout capturing session {session_name}")
            return "로그 조회 시간 초과 (세션이 응답하지 않음)"
        except Exception as e:
            logger.error(f"Exception getting session log for {session_name}: {str(e)}")
            return "로그 조회 중 오류가 발생했습니다."
    
    
    async def _send_to_claude_with_session(self, text: str, target_session: str) -> bool:
        """Send text to specific Claude session with improved reliability"""
        try:
            # Ensure target session exists
            session_exists = os.system(f"tmux has-session -t {target_session}") == 0
            if not session_exists:
                logger.error(f"Target session {target_session} does not exist")
                return False
            
            logger.info(f"Sending text to {target_session}: {text[:100]}...")
            
            # Send text to tmux session using subprocess for better control
            # Use -l flag to send literal text (handles special characters better)
            result1 = subprocess.run(
                ["tmux", "send-keys", "-t", target_session, "-l", text],
                capture_output=True,
                text=True,
                timeout=10  # Add timeout for reliability
            )
            
            if result1.returncode != 0:
                logger.error(f"Failed to send text to {target_session}. Return code: {result1.returncode}")
                logger.error(f"Text send error: {result1.stderr}")
                return False
            
            # Small delay to ensure text is processed
            import asyncio
            await asyncio.sleep(0.1)
            
            # Send Enter key
            result2 = subprocess.run(
                ["tmux", "send-keys", "-t", target_session, "Enter"],
                capture_output=True,
                text=True,
                timeout=10  # Add timeout for reliability
            )
            
            if result2.returncode != 0:
                logger.error(f"Failed to send Enter to {target_session}. Return code: {result2.returncode}")
                logger.error(f"Enter send error: {result2.stderr}")
                return False
            
            logger.info(f"Successfully sent text with Enter to {target_session}")
            return True
                
        except Exception as e:
            logger.error(f"Exception while sending text to Claude session {target_session}: {str(e)}")
            return False
    
    # TADD Workflow Command Handlers
    
    async def workflow_planning_command(self, update, context):
        """Handle /기획 command with TADD integration"""
        if not await self._basic_auth_check(update):
            return
        
        args_text = ' '.join(context.args) if context.args else ""
        
        # Import TADD modules
        try:
            import sys
            import os
            tadd_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tadd')
            if tadd_path not in sys.path:
                sys.path.insert(0, tadd_path)
            from tadd.task_manager import TADDTaskManager, TADD_TEMPLATES, TaskStatus
            from tadd.document_generator import TADDDocumentGenerator
            
            # Initialize TADD components
            task_manager = TADDTaskManager()
            doc_generator = TADDDocumentGenerator()
            
            # Create planning tasks from template
            planning_tasks = task_manager.create_task_template("기획", TADD_TEMPLATES["기획"])
            
            # Start first task
            if planning_tasks:
                task_manager.update_task_status(planning_tasks[0], TaskStatus.IN_PROGRESS)
            
            # Prepare TADD planning prompt
            tadd_prompt = f"""
🎯 **전체 개발 워크플로우 실행**

==================================================

🎯 **기획 (Structured Discovery & Planning Loop)**

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/status.md 확인 (있으면 읽기)  
- 이전 세션 TODO 확인

**탐색 단계:**
- 전체 구조 파악: 현재 시스템 아키텍처와 요구사항 분석
- As-Is/To-Be/Gap 분석: 현재 상태, 목표 상태, 차이점 식별
- 이해관계자 요구사항 수집 및 우선순위화

**계획 단계:**
- MECE 기반 작업분해(WBS): 상호배타적이고 전체포괄적인 업무 구조
- 우선순위 매트릭스: 중요도와 긴급도 기반 작업 순서 결정
- 리소스 및 일정 계획 수립

**수렴 단계:**
- 탐색↔계획 반복 iterative refinement
- PRD(Product Requirements Document) 완성
- TodoWrite를 활용한 구조화된 작업 계획 수립

ARGUMENTS: {args_text}
"""
            
            # Send to Claude session
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(tadd_prompt, target_session)
            
            if success:
                await update.message.reply_text(
                    f"🎯 **기획 단계 시작**\\n"
                    f"📋 **{len(planning_tasks)}개 작업** 추가됨\\n"
                    f"🔄 **세션**: {target_session}\\n"
                    f"📝 **인수**: {args_text or '없음'}"
                )
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
                
        except ImportError as e:
            logger.error(f"TADD module import failed: {e}")
            # Fallback to basic command
            basic_prompt = f"/planning {args_text}"
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(basic_prompt, target_session)
            
            if success:
                await update.message.reply_text("🎯 기획 명령어 전송됨 (기본 모드)")
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
        
    async def workflow_implementation_command(self, update, context):
        """Handle /구현 command with TADD integration"""
        if not await self._basic_auth_check(update):
            return
        
        args_text = ' '.join(context.args) if context.args else ""
        
        try:
            import sys
            import os
            tadd_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tadd')
            if tadd_path not in sys.path:
                sys.path.insert(0, tadd_path)
            from tadd.task_manager import TADDTaskManager, TADD_TEMPLATES, TaskStatus
            
            task_manager = TADDTaskManager()
            impl_tasks = task_manager.create_task_template("구현", TADD_TEMPLATES["구현"])
            
            if impl_tasks:
                task_manager.update_task_status(impl_tasks[0], TaskStatus.IN_PROGRESS)
            
            tadd_prompt = f"""
📍 **기획 완료 → 구현 시작**

⚡ **구현 (Implementation with DRY)**

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/active-todos.md 확인 (있으면 읽기)

**DRY 원칙 적용:**
- 기존 코드 검색: Grep, Glob 도구로 유사 기능 탐색
- 재사용 우선: 기존 라이브러리/모듈/함수 활용
- 없으면 생성: 새로운 컴포넌트 개발 시 재사용성 고려

**체계적 진행:**
- TodoWrite 기반 단계별 구현
- 모듈화된 코드 구조 유지
- 코딩 컨벤션 준수 (기존 코드 스타일 분석 후 적용)

ARGUMENTS: {args_text}
"""
            
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(tadd_prompt, target_session)
            
            if success:
                await update.message.reply_text(
                    f"⚡ **구현 단계 시작**\\n"
                    f"📋 **{len(impl_tasks)}개 작업** 추가됨\\n"
                    f"🔄 **세션**: {target_session}"
                )
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
                
        except ImportError:
            # Fallback
            basic_prompt = f"/implementation {args_text}"
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(basic_prompt, target_session)
            
            if success:
                await update.message.reply_text("⚡ 구현 명령어 전송됨 (기본 모드)")
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
    
    async def workflow_stabilization_command(self, update, context):
        """Handle /안정화 command with TADD integration"""
        if not await self._basic_auth_check(update):
            return
        
        args_text = ' '.join(context.args) if context.args else ""
        
        try:
            import sys
            import os
            tadd_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tadd')
            if tadd_path not in sys.path:
                sys.path.insert(0, tadd_path)
            from tadd.task_manager import TADDTaskManager, TADD_TEMPLATES, TaskStatus
            
            task_manager = TADDTaskManager()
            stab_tasks = task_manager.create_task_template("안정화", TADD_TEMPLATES["안정화"])
            
            if stab_tasks:
                task_manager.update_task_status(stab_tasks[0], TaskStatus.IN_PROGRESS)
            
            tadd_prompt = f"""
📍 **구현 완료 → 안정화 시작**

🔧 **안정화 (Structural Sustainability Protocol v2.0)**

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/test-report.md 확인 (이전 테스트 결과)

**6단계 통합 검증 루프:**
1. **Repository Structure Scan** - 전체 파일 분석
2. **Structural Optimization** - 디렉토리 정리 및 최적화
3. **Dependency Resolution** - Import 수정 및 의존성 해결
4. **User-Centric Comprehensive Testing** ⚠️ **Mock 테스트 금지**
5. **Documentation Sync** - 문서 동기화
6. **Quality Assurance** - 품질 보증

**실제 시나리오 기반 테스트 필수:**
- PRD 기반 사용자 스토리 검증
- 실제 데이터 사용 (Mock 금지)
- 정량적 성능 측정

ARGUMENTS: {args_text}
"""
            
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(tadd_prompt, target_session)
            
            if success:
                await update.message.reply_text(
                    f"🔧 **안정화 단계 시작**\\n"
                    f"📋 **{len(stab_tasks)}개 작업** 추가됨\\n"
                    f"⚠️ **실제 테스트 필수** (Mock 금지)\\n"
                    f"🔄 **세션**: {target_session}"
                )
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
                
        except ImportError:
            # Fallback
            basic_prompt = f"/stabilization {args_text}"
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(basic_prompt, target_session)
            
            if success:
                await update.message.reply_text("🔧 안정화 명령어 전송됨 (기본 모드)")
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
    
    async def workflow_deployment_command(self, update, context):
        """Handle /배포 command with TADD integration"""
        if not await self._basic_auth_check(update):
            return
        
        args_text = ' '.join(context.args) if context.args else ""
        
        try:
            import sys
            import os
            tadd_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tadd')
            if tadd_path not in sys.path:
                sys.path.insert(0, tadd_path)
            from tadd.task_manager import TADDTaskManager, TADD_TEMPLATES, TaskStatus
            from tadd.session_archiver import TADDSessionArchiver
            
            task_manager = TADDTaskManager()
            archiver = TADDSessionArchiver()
            
            deploy_tasks = task_manager.create_task_template("배포", TADD_TEMPLATES["배포"])
            
            if deploy_tasks:
                task_manager.update_task_status(deploy_tasks[0], TaskStatus.IN_PROGRESS)
            
            tadd_prompt = f"""
📍 **안정화 완료 → 배포 시작**

🚀 **배포 (Deployment)**

**📚 컨텍스트 자동 로딩:**
- project_rules.md 확인 (있으면 읽기)
- docs/CURRENT/ 전체 상태 확인

**배포 프로세스:**
1. **최종 검증** - 체크리스트 완료 확인
2. **구조화 커밋** - 의미있는 커밋 메시지
3. **⚠️ 필수: 원격 배포 실행**
   - **반드시 git push 실행**
   - **git push origin main** 
   - **버전 태깅 및 푸시**
4. **배포 후 검증** - 원격 저장소 확인
5. **📦 세션 아카이빙** - CURRENT/ → sessions/YYYY-MM/

**💡 배포 = 커밋 + 푸시 + 태깅 + 검증의 완전한 과정**

ARGUMENTS: {args_text}
"""
            
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(tadd_prompt, target_session)
            
            if success:
                await update.message.reply_text(
                    f"🚀 **배포 단계 시작**\\n"
                    f"📋 **{len(deploy_tasks)}개 작업** 추가됨\\n"
                    f"⚠️ **git push 필수**\\n"
                    f"📦 **세션 아카이빙 자동 실행**\\n"
                    f"🔄 **세션**: {target_session}"
                )
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
                
        except ImportError:
            # Fallback
            basic_prompt = f"/deployment {args_text}"
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(basic_prompt, target_session)
            
            if success:
                await update.message.reply_text("🚀 배포 명령어 전송됨 (기본 모드)")
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
    
    async def workflow_fullcycle_command(self, update, context):
        """Handle /전체사이클 command with TADD integration"""
        if not await self._basic_auth_check(update):
            return
        
        args_text = ' '.join(context.args) if context.args else ""
        
        try:
            import sys
            import os
            tadd_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tadd')
            if tadd_path not in sys.path:
                sys.path.insert(0, tadd_path)
            from tadd.task_manager import TADDTaskManager, TaskStatus
            from tadd.prd_manager import TADDPRDManager
            
            task_manager = TADDTaskManager()
            prd_manager = TADDPRDManager()
            
            # Create comprehensive task list for full cycle
            full_cycle_tasks = [
                ("컨텍스트 로딩 및 현재 상태 분석", "컨텍스트를 로딩하고 현재 상태를 분석하는 중"),
                ("As-Is/To-Be/Gap 분석", "As-Is/To-Be/Gap을 분석하는 중"),
                ("PRD 작성 및 기획 완료", "PRD를 작성하고 기획을 완료하는 중"),
                ("DRY 원칙 기반 구현", "DRY 원칙을 기반으로 구현하는 중"),
                ("실제 시나리오 테스트", "실제 시나리오로 테스트하는 중"),
                ("구조적 안정화", "구조적 안정화를 진행하는 중"),
                ("Git 커밋 및 원격 푸시", "Git 커밋 및 원격 푸시를 진행하는 중"),
                ("세션 아카이빙", "세션 아카이빙을 진행하는 중")
            ]
            
            cycle_task_ids = task_manager.create_task_template("전체사이클", full_cycle_tasks)
            
            if cycle_task_ids:
                task_manager.update_task_status(cycle_task_ids[0], TaskStatus.IN_PROGRESS)
            
            tadd_prompt = f"""
🔄 **전체 개발 워크플로우 실행**

다음 4단계를 순차적으로 진행하되, 현재 프로젝트 상태를 고려하여 필요한 단계에 집중해주세요:

==================================================

🎯 **기획 (Structured Discovery & Planning Loop)**
- 컨텍스트 자동 로딩 (project_rules.md, status.md)
- As-Is/To-Be/Gap 분석
- MECE 기반 작업분해
- PRD 작성 및 TodoWrite 계획

📍 **기획 완료 → 구현 시작**

⚡ **구현 (Implementation with DRY)**
- DRY 원칙 적용
- 기존 코드 재사용 우선
- TodoWrite 기반 단계별 구현
- 품질 보증 및 테스트

📍 **구현 완료 → 안정화 시작**

🔧 **안정화 (Structural Sustainability Protocol v2.0)**
- 6단계 통합 검증
- ⚠️ **실제 시나리오 테스트 필수** (Mock 금지)
- 정량적 성능 측정
- 구조적 최적화

📍 **안정화 완료 → 배포 시작**

🚀 **배포 (Deployment)**
- 최종 검증 및 커밋
- ⚠️ **필수: git push origin main**
- 버전 태깅 및 원격 배포
- 📦 **세션 아카이빙 자동 실행**

ARGUMENTS: {args_text}
"""
            
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(tadd_prompt, target_session)
            
            if success:
                await update.message.reply_text(
                    f"🔄 **전체 사이클 시작**\\n"
                    f"📋 **{len(cycle_task_ids)}개 작업** 생성됨\\n"
                    f"🎯 **4단계 순차 진행**: 기획 → 구현 → 안정화 → 배포\\n"
                    f"⚠️ **실제 테스트 & git push 필수**\\n"
                    f"📦 **자동 세션 아카이빙**\\n"
                    f"🔄 **세션**: {target_session}"
                )
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
                
        except ImportError:
            # Fallback - send as basic command
            basic_prompt = f"/fullcycle {args_text}"
            target_session = await self._get_target_session_from_context(update, context)
            success = await self._send_to_claude_with_session(basic_prompt, target_session)
            
            if success:
                await update.message.reply_text("🔄 전체사이클 명령어 전송됨 (기본 모드)")
            else:
                await update.message.reply_text("❌ Claude 세션으로 전송 실패")
    
    # Detection Analysis Commands
    async def detection_status_command(self, update, context):
        """Handle /detection_status command"""
        from .commands.detection_analysis import detection_status
        await detection_status(update, context)
    
    async def detection_report_command(self, update, context):
        """Handle /detection_report command"""
        from .commands.detection_analysis import detection_report
        await detection_report(update, context)
    
    async def detection_trends_command(self, update, context):
        """Handle /detection_trends command"""
        from .commands.detection_analysis import detection_trends
        await detection_trends(update, context)
    
    async def detection_improve_command(self, update, context):
        """Handle /detection_improve command"""
        from .commands.detection_analysis import detection_improve
        await detection_improve(update, context)
    
    async def _send_to_claude(self, text: str) -> bool:
        """Send text to current Claude session (legacy function - now uses _send_to_claude_with_session)"""
        session_name = self.config.session_name
        return await self._send_to_claude_with_session(text, session_name)
    
    def run(self):
        """Start the Telegram bot"""
        try:
            # Initialize application
            self.app = Application.builder().token(self.config.telegram_bot_token).build()
            
            # Setup handlers
            self.setup_handlers()
            
            # Setup post-init hook for bot commands and webhook cleanup
            async def post_init(application):
                try:
                    # Clear any webhook that might cause conflicts with polling
                    await application.bot.delete_webhook(drop_pending_updates=True)
                    logger.info("Webhook cleared successfully")
                except Exception as e:
                    logger.info(f"Webhook clear attempt (may not have existed): {e}")
                
                await self.setup_bot_commands()
            
            self.app.post_init = post_init
            
            # Start bot with conflict handling
            logger.info(f"텔레그램 봇이 시작되었습니다. 세션: {self.config.session_name}")
            
            # Add some retry logic for conflicts
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"재시도 중... ({attempt + 1}/{max_retries})")
                        time.sleep(5 * attempt)  # Exponential backoff
                    
                    self.app.run_polling(drop_pending_updates=True)
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if "terminated by other getUpdates request" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"getUpdates 충돌 감지 (시도 {attempt + 1}), 잠시 후 재시도...")
                        # Kill any existing bot processes to prevent conflicts
                        import subprocess
                        subprocess.run("pkill -f 'claude_ctb.telegram.bot'", shell=True)
                        time.sleep(3)
                        continue
                    else:
                        logger.error(f"봇 실행 실패: {str(e)}")
                        raise
            
        except Exception as e:
            logger.error(f"봇 실행 중 오류 발생: {str(e)}")
            # Don't expose raw error to users
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
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