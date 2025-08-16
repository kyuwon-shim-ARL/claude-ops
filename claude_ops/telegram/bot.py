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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton

from ..config import ClaudeOpsConfig

logger = logging.getLogger(__name__)


class TelegramBridge:
    """Claude Telegram Bot with inline keyboard interface"""
    
    # Prompt macro text constants
    PROMPT_MACROS = {
        "@기획": """🎯 **기획 (Structured Discovery & Planning Loop)**

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

**산출물:** 구체적인 실행 계획과 성공 기준이 포함된 PRD""",
        
        "@구현": """⚡ **구현 (Implementation with DRY)**

**DRY 원칙 적용:**
- 기존 코드 검색: Grep, Glob 도구로 유사 기능 탐색
- 재사용 우선: 기존 라이브러리/모듈/함수 활용
- 없으면 생성: 새로운 컴포넌트 개발 시 재사용성 고려

**체계적 진행:**
- TodoWrite 기반 단계별 구현
- 모듈화된 코드 구조 유지
- 코딩 컨벤션 준수 (기존 코드 스타일 분석 후 적용)

**품질 보증:**
- 단위 테스트 작성 및 실행
- 기본 검증: 문법 체크, 타입 체크, 린트
- 동작 확인: 핵심 기능 동작 테스트

**산출물:** 테스트 통과하는 동작 가능한 코드""",
        
        "@안정화": """🔧 **안정화 (Structural Sustainability Protocol v2.0)**

**패러다임 전환:** 기능 중심 → **구조적 지속가능성** 중심

**6단계 통합 검증 루프:**

1. **Repository Structure Scan**
   - 전체 파일 분석: 디렉토리 구조, 파일 목적성 검토
   - 중복/임시 파일 식별 및 정리 방안 수립
   - 파일 크기 및 복잡도 분석

2. **Structural Optimization**
   - 디렉토리 정리: 논리적 그룹핑, 계층 구조 최적화
   - 파일 분류: 목적별, 기능별 체계적 분류
   - 네이밍 표준화: 일관된 명명 규칙 적용

3. **Dependency Resolution**
   - Import 수정: 순환 참조 해결, 의존성 최적화
   - 참조 오류 해결: 깨진 링크, 잘못된 경로 수정
   - 환경 동기화: requirements, configs 일치성 확인

4. **Comprehensive Testing**
   - 모듈 검증: 각 모듈별 단위 테스트
   - API 테스트: 인터페이스 동작 확인
   - 시스템 무결성 확인: 전체 시스템 통합 테스트

5. **Documentation Sync**
   - CLAUDE.md 반영: 변경사항 문서화
   - README 업데이트: 사용법, 설치법 최신화
   - .gitignore 정리: 불필요한 파일 제외 규칙 정비

6. **Quality Assurance**
   - MECE 분석: 빠진 것은 없는지, 중복은 없는지 확인
   - 성능 벤치마크: 기준 성능 대비 측정
   - 정량 평가: 코드 커버리지, 복잡도, 품질 지표

**예방적 관리 트리거:**
- 루트 20개 파일 이상
- 임시 파일 5개 이상
- Import 오류 3개 이상
→ 자동 안정화 프로세스 실행

**산출물:** 지속가능하고 확장 가능한 깔끔한 코드베이스""",
        
        "@배포": """🚀 **배포 (Deployment)**

**최종 검증:**
- 체크리스트 완료 확인: 모든 TODO 완료, 테스트 통과
- 코드 리뷰: 보안, 성능, 코딩 표준 최종 점검
- 배포 전 시나리오 테스트: 프로덕션 환경 시뮬레이션

**구조화 커밋:**
- 의미있는 커밋 메시지: 변경사항의 목적과 영향 명시
- 원자성 보장: 하나의 논리적 변경사항 = 하나의 커밋
- 관련 이슈/티켓 링크: 추적가능성 확보

**원격 배포:**
- 푸시: origin 저장소로 변경사항 전송
- 버전 태깅: semantic versioning (major.minor.patch)
- 배포 스크립트 실행: CI/CD 파이프라인 트리거

**배포 후 모니터링:**
- 서비스 상태 확인: 헬스체크, 로그 모니터링
- 성능 지표 추적: 응답시간, 처리량, 오류율
- 롤백 준비: 문제 발생 시 즉시 이전 버전으로 복구

**산출물:** 안정적으로 운영되는 프로덕션 서비스"""
    }
    
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
        
        # Handle Reply Keyboard remote control buttons
        if await self._handle_remote_button(update, user_input):
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
        project_status = "🔄 기본 세션 재시작"
        
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
                    
                    # Install claude-dev-kit for new projects
                    await self._install_claude_dev_kit(target_directory, project_name, update)
                    project_status = "🆕 새 프로젝트 생성"
                else:
                    # 기존 프로젝트 감지 메시지 (안전한 플레인 텍스트)
                    await update.message.reply_text(
                        f"📂 기존 프로젝트 감지\n\n"
                        f"📁 경로: {target_directory}\n"
                        f"🎯 세션: claude_{project_name}\n\n"
                        f"💡 기존 프로젝트에 연결합니다..."
                    )
                    project_status = "📂 기존 프로젝트 연결"
            
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
            
            # Initialize new session for compatibility
            await self._initialize_new_session(target_session, update)
            status_msg = f"🚀 {target_session} 세션을 시작했습니다!"
            
            # Auto-switch to new session if it's different from current
            if target_session != self.config.session_name:
                await self._auto_switch_to_session(target_session, update)
        else:
            status_msg = f"✅ {target_session} 세션이 이미 실행 중입니다."
            
            # Auto-switch to existing session if it's different from current
            if target_session != self.config.session_name:
                await self._auto_switch_to_session(target_session, update)
        
        # Use standardized keyboard
        reply_markup = self.get_main_keyboard()
        
        welcome_msg = f"""🤖 Claude-Telegram Bridge

{status_msg}
{project_status}

📁 작업 디렉토리: {target_directory}
🎯 세션 이름: {target_session}

제어판을 사용하여 Claude를 제어하세요:"""
        
        await update.message.reply_text(
            welcome_msg,
            reply_markup=reply_markup
        )
        
        # Auto-activate remote control for better UX
        await self._auto_activate_remote(update)
    
    async def _auto_activate_remote(self, update):
        """Auto-activate prompt macro remote control"""
        try:
            reply_markup = self.get_prompt_macro_keyboard()
            await update.message.reply_text(
                "🎛️ 프롬프트 매크로 리모컨이 활성화되었습니다.\n\n"
                "🔗 통합 워크플로우 (우선순위):\n"
                "• 전체: 기획&구현&안정화&배포\n"
                "• 개발: 기획&구현&안정화\n"
                "• 마무리: 안정화&배포\n"
                "• 실행: 구현&안정화&배포\n\n"
                "⚡ 개별 매크로:\n"
                "• @기획: 구조적 탐색 및 계획 수립\n"
                "• @구현: DRY 원칙 기반 체계적 구현\n"
                "• @안정화: 구조적 지속가능성 검증\n"
                "• @배포: 최종 검증 및 배포",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Auto remote activation error: {str(e)}")
            # Silent fail - don't disrupt main flow
    
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
• `/log50`, `/log100`, `/log150`, `/log200`, `/log300` - 빠른 로그 조회
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/erase` - 현재 입력 지우기 (Ctrl+C 전송) 🆕
• `/clear` - 화면 정리 (Ctrl+L 전송) 🆕
• `/sessions` - 활성 세션 목록 보기 및 전환
• `/remote` - 세션 리모컨 켜기/끄기 (화면 하단 고정)
• `/help` - 이 도움말 보기

**Reply 기반 세션 제어:** 🆕
• 알림에 Reply + `/log` → 해당 세션의 로그 표시
• 알림에 Reply + `/session` → 해당 세션으로 바로 전환
• 알림에 Reply + `/erase` → 해당 세션의 입력 지우기
• 알림에 Reply + `/clear` → 해당 세션의 화면 정리

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
                        
                        # Send each part as a separate message with session info
                        session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                        for i, part in enumerate(parts):
                            if i == 0:
                                header = f"📺 **Claude 화면 로그** [{target_session}]\n\n"
                                header += f"📁 **프로젝트**: `{session_display}`\n"
                                header += f"🎯 **세션**: `{target_session}`\n"
                                header += f"📏 **라인 수**: {len(display_lines)}줄 - Part {i+1}/{len(parts)}\n\n"
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
                        header += f"📏 **라인 수**: {len(display_lines)}줄\n\n"
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
                        
                    screen_text = '\n'.join(display_lines)
                    
                    # Send without markdown to avoid parsing errors with session info
                    session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                    header = f"📺 Claude 화면 로그 [{target_session}]\n\n"
                    header += f"📁 프로젝트: {session_display}\n"
                    header += f"🎯 세션: {target_session}\n"
                    header += f"📏 라인 수: {len(display_lines)}줄\n\n"
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
    
    async def remote_command(self, update, context):
        """Toggle prompt macro remote control keyboard"""
        user_id = update.effective_user.id
        
        if not self.check_user_authorization(user_id):
            await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
            return
        
        # Check if reply keyboard is currently active by context or argument
        # For simplicity, we'll toggle: if /remote, activate; if /remote off, deactivate
        args = context.args if context.args else []
        
        if args and args[0].lower() in ['off', 'hide', '끄기']:
            # Deactivate remote control
            await update.message.reply_text(
                "🎛️ 프롬프트 매크로 리모컨이 비활성화되었습니다.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            # Activate remote control
            remote_keyboard = self.get_prompt_macro_keyboard()
            
            await update.message.reply_text(
                "🎛️ 프롬프트 매크로 리모컨 활성화!\n\n"
                "🔗 통합 워크플로우 (우선순위):\n"
                "• 전체: 기획&구현&안정화&배포\n"
                "• 개발: 기획&구현&안정화\n"
                "• 마무리: 안정화&배포\n"
                "• 실행: 구현&안정화&배포\n\n"
                "⚡ 개별 매크로:\n"
                "• @기획: 구조적 탐색 및 계획 수립\n"
                "• @구현: DRY 원칙 기반 체계적 구현\n"
                "• @안정화: 구조적 지속가능성 검증\n"
                "• @배포: 최종 검증 및 배포\n\n"
                "💡 끄려면: /remote off",
                reply_markup=remote_keyboard
            )
    
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
    
    def get_prompt_macro_keyboard(self):
        """Get prompt macro keyboard for development workflows"""
        
        keyboard = [
            # Combined workflow prompts (most frequently used - moved to top)
            [
                KeyboardButton("기획&구현&안정화&배포")
            ],
            [
                KeyboardButton("기획&구현&안정화"),
                KeyboardButton("안정화&배포")
            ],
            [
                KeyboardButton("구현&안정화&배포")
            ],
            
            # Single keyword prompts (2x2 grid - moved to bottom)
            [
                KeyboardButton("@기획"),
                KeyboardButton("@구현")
            ],
            [
                KeyboardButton("@안정화"),
                KeyboardButton("@배포")
            ]
        ]
        
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=False
        )
    
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
            session_name = callback_data.split(":", 1)[1]
            await self._select_session_callback(query, context, session_name)
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
        elif callback_data == "back_to_menu":
            await self._back_to_menu_callback(query, context)
        elif callback_data == "back_to_sessions":
            await self._session_actions_callback(query, context)
    
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
        help_text = """
🤖 **Telegram-Claude Bridge 봇**

Claude Code 세션과 텔레그램 간 양방향 통신 브릿지입니다.

**봇 명령어:**
• `/start` - 현재 세션 시작/재시작
• `/start project_name` - ~/projects/project_name에서 claude_project_name 세션 시작
• `/start project_name /custom/path` - 지정 경로에서 claude_project_name 세션 시작
• `/status` - 봇 및 tmux 세션 상태 확인
• `/log [lines]` - 현재 Claude 화면 확인 (기본 50줄, 최대 2000줄)
• `/log50`, `/log100`, `/log150`, `/log200`, `/log300` - 빠른 로그 조회
• `/stop` - Claude 작업 중단 (ESC 키 전송)
• `/erase` - 현재 입력 지우기 (Ctrl+C 전송) 🆕
• `/clear` - 화면 정리 (Ctrl+L 전송) 🆕
• `/sessions` - 활성 세션 목록 보기 및 전환
• `/remote` - 세션 리모컨 켜기/끄기 (화면 하단 고정)
• `/help` - 이 도움말 보기

**Reply 기반 세션 제어:** 🆕
• 알림에 Reply + `/log` → 해당 세션의 로그 표시
• 알림에 Reply + `/session` → 해당 세션으로 바로 전환
• 알림에 Reply + `/erase` → 해당 세션의 입력 지우기
• 알림에 Reply + `/clear` → 해당 세션의 화면 정리

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
        self.app.add_handler(CommandHandler("log50", self.log50_command))
        self.app.add_handler(CommandHandler("log100", self.log100_command))
        self.app.add_handler(CommandHandler("log150", self.log150_command))
        self.app.add_handler(CommandHandler("log200", self.log200_command))
        self.app.add_handler(CommandHandler("log300", self.log300_command))
        self.app.add_handler(CommandHandler("stop", self.stop_command))
        self.app.add_handler(CommandHandler("erase", self.erase_command))
        self.app.add_handler(CommandHandler("clear", self.clear_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("board", self.board_command))
        self.app.add_handler(CommandHandler("remote", self.remote_command))
        
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
            BotCommand("board", "🎯 세션 보드"),
            BotCommand("status", "📊 봇 및 tmux 세션 상태 확인"),
            BotCommand("log", "📺 현재 Claude 화면 실시간 확인"),
            BotCommand("stop", "⛔ Claude 작업 중단 (ESC 키 전송)"),
            BotCommand("erase", "🧹 현재 입력 지우기 (Ctrl+C 전송)"),
            BotCommand("clear", "🖥️ 화면 정리 (Ctrl+L 전송)"),
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
            
            guide_msg = f"""🎆 **새 프로젝트 생성 가이드**

🚀 **Claude Dev Kit으로 새 프로젝트 생성**:

📝 **명령어 사용법**:
```
/start 프로젝트명
```

📁 **예시**:
• `/start my_web_app` → `~/projects/my_web_app`
• `/start ai_chatbot` → `~/projects/ai_chatbot`
• `/start data_analysis` → `~/projects/data_analysis`

🎯 **자동 설치 내용**:
• 📝 **CLAUDE.md** - 프로젝트 가이드
• 🚀 **main_app.py** - 에플리케이션 시작점
• 📁 **src/, docs/, tests/** - 완전한 프로젝트 구조
• 🔧 **개발 워크플로우 템플릿**

💬 **지금 바로 시작하세요!**
`/start 원하는프로젝트명` 입력하면 끝!"""
            
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
            init_msg = f"🎆 세션 초기화 완료\n\n"
            if has_example_text:
                init_msg += f"✨ 예시 텍스트 제거 후 /init 실행\n"
            else:
                init_msg += f"✨ 빈 세션에 /init 실행\n"
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
    
    async def _install_claude_dev_kit(self, target_directory: str, project_name: str, update) -> bool:
        """Install claude-dev-kit in new project directory"""
        try:
            install_msg = await update.message.reply_text(
                f"🛠️ Claude Dev Kit 설치 중...\n\n"
                f"📁 디렉토리: {target_directory}\n"
                f"💭 프로젝트: {project_name}"
            )
            
            # Execute claude-dev-kit installation script
            import subprocess
            
            # Change to target directory and run installation
            install_command = (
                f"cd {target_directory} && "
                f"curl -sSL https://raw.githubusercontent.com/kyuwon-shim-ARL/claude-dev-kit/main/install.sh | "
                f"bash -s {project_name} 'Claude-managed project with dev-ops automation'"
            )
            
            result = subprocess.run(
                install_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                await install_msg.edit_text(
                    f"✅ Claude Dev Kit 설치 완료!\n\n"
                    f"🎯 프로젝트: {project_name}\n"
                    f"📁 경로: {target_directory}\n\n"
                    f"📝 생성된 파일들:\n"
                    f"• CLAUDE.md - 프로젝트 가이드\n"
                    f"• main_app.py - 애플리케이션 엔트리포인트\n"
                    f"• src/, docs/, tests/ - 프로젝트 구조\n\n"
                    f"🚀 Claude 세션을 시작합니다..."
                )
                logger.info(f"Successfully installed claude-dev-kit in {target_directory}")
                return True
            else:
                error_output = result.stderr[:200] if result.stderr else "Unknown error"
                await install_msg.edit_text(
                    f"⚠️ Claude Dev Kit 설치 실패\n\n"
                    f"❌ 오류: {error_output}\n\n"
                    f"💭 기본 프로젝트로 계속합니다..."
                )
                logger.warning(f"Failed to install claude-dev-kit: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            await install_msg.edit_text(
                f"⏱️ 설치 시간초과\n\n"
                f"⚠️ Claude Dev Kit 설치가 30초를 초과했습니다.\n"
                f"💭 기본 프로젝트로 계속합니다..."
            )
            logger.warning("Claude dev-kit installation timed out")
            return False
        except Exception as e:
            # 안전한 에러 메시지 전송 (마크다운 파싱 에러 방지)
            error_text = f"❌ 예상치 못한 오류\n\n🚫 오류: {str(e)[:100]}\n💭 기본 프로젝트로 계속합니다..."
            await install_msg.edit_text(error_text)
            logger.error(f"Unexpected error during claude-dev-kit installation: {str(e)}")
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
                    f"📤 이전: {old_session}\n"
                    f"📥 현재: {session_name}\n\n"
                    f"✅ 이제 모든 메시지가 새 세션으로 전송됩니다!"
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
            sessions = self.get_all_claude_sessions()
            
            if not sessions:
                await reply_func(
                    "❌ **세션 없음**\n\nClaude 세션을 찾을 수 없습니다.\n\n/start 명령으로 새 세션을 시작하세요.",
                    parse_mode='Markdown'
                )
                return
            
            keyboard = []
            
            # Session rows with direct actions (2 sessions per row max)
            for i in range(0, len(sessions), 2):
                row_sessions = sessions[i:i+2]
                session_row = []
                
                for session in row_sessions:
                    display_name = session.replace('claude_', '') if session.startswith('claude_') else session
                    current_icon = "⭐" if session == self.config.session_name else ""
                    
                    # Get session status
                    from ..utils.session_state import is_session_working
                    is_working = is_session_working(session)
                    status_icon = "🔄" if is_working else "💤"
                    
                    # Get very short prompt hint for button
                    hint = await self._get_session_hint_short(session)
                    button_text = f"{current_icon}{status_icon} {display_name}{hint}"
                    
                    session_row.append(
                        InlineKeyboardButton(
                            button_text,
                            callback_data=f"session_grid:{session}"
                        )
                    )
                
                keyboard.append(session_row)
            
            # Add utility buttons
            keyboard.append([
                InlineKeyboardButton("🚀 새 세션", callback_data="start"),
                InlineKeyboardButton("❓ 도움말", callback_data="help")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await reply_func(
                f"🎯 **세션 보드** ({len(sessions)}개)\n\n"
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
            is_working = is_session_working(session_name)
            info = get_session_working_info(session_name)
            status_emoji = "🔄 작업중" if is_working else "💤 대기중"
            
            # Get full prompt hint for this view
            prompt_hint = await self.get_session_prompt_hint(session_name)
            
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
                    InlineKeyboardButton("⏸️ Pause", callback_data=f"session_pause:{session_name}"),
                    InlineKeyboardButton("🗑️ Erase", callback_data=f"session_erase:{session_name}"),
                    InlineKeyboardButton("◀️ 뒤로", callback_data="session_actions")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🎯 **{display_name}** 세션 액션\n\n"
                f"📊 **상태**: {status_emoji}\n"
                f"🎯 **메인 세션**: {'✅ 현재 메인' if is_current else '❌ 다른 세션'}\n"
                f"{prompt_hint}\n"
                "💆‍♂️ **원클릭 액션 선택**:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Session grid callback error: {str(e)}")
            await query.answer(f"❌ 세션 액션 로드 실패: {str(e)}")
    
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
            from ..utils.session_state import is_session_working, get_session_working_info
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
        """Show logs for specific session"""
        try:
            import subprocess
            
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                await query.edit_message_text(
                    f"❌ 세션 없음\n\n세션 '{session_name}'이 존재하지 않습니다."
                )
                return
            
            # Get screen content with moderate line count
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -100", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                current_screen = result.stdout
                
                if current_screen:
                    display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                    lines = current_screen.split('\n')
                    
                    # Limit message length for Telegram
                    max_length = 3000
                    if len(current_screen) > max_length:
                        # Show last part with truncation notice
                        truncated_lines = []
                        current_length = 0
                        for line in reversed(lines):
                            if current_length + len(line) > max_length:
                                break
                            truncated_lines.insert(0, line)
                            current_length += len(line) + 1
                        
                        screen_text = "...(앞부분 생략)...\n" + '\n'.join(truncated_lines)
                    else:
                        screen_text = current_screen
                    
                    header = f"📜 {display_name} 세션 로그\n\n"
                    header += f"🎛️ 세션: {session_name}\n"
                    header += f"📏 라인 수: ~{len(lines)}줄\n\n"
                    
                    # Use same safe format as log_command (no markdown parsing)
                    message = f"{header}{screen_text.strip()}"
                    await query.edit_message_text(message)
                else:
                    await query.edit_message_text(f"📜 {session_name} 로그\n\n📺 세션 화면이 비어있습니다.")
            else:
                await query.edit_message_text(f"❌ 세션 '{session_name}'의 로그를 가져올 수 없습니다.")
                
        except Exception as e:
            logger.error(f"세션 로그 조회 중 오류: {str(e)}")
            await query.edit_message_text(f"❌ 로그 조회 오류\n\n오류: {str(e)}")
    
    async def _session_switch_callback(self, query, context, session_name):
        """Switch main session"""
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
            
            current_session = self.config.session_name
            
            if session_name == current_session:
                await query.edit_message_text(
                    f"ℹ️ **이미 메인 세션**\n\n"
                    f"'{session_name}'이 이미 메인 세션입니다.",
                    parse_mode='Markdown'
                )
                return
            
            # Switch using session manager
            from ..session_manager import session_manager
            success = session_manager.switch_session(session_name)
            
            if success:
                display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                
                await query.edit_message_text(
                    f"🏠 **메인 세션 변경 완료**\n\n"
                    f"이전: `{current_session}`\n"
                    f"새 메인: `{session_name}`\n\n"
                    f"✅ 이제 `{display_name}` 세션이 메인 세션입니다.\n"
                    f"모니터링 시스템이 자동으로 업데이트됩니다.",
                    parse_mode='Markdown'
                )
                
                # Restart monitoring for new session
                await self._restart_monitoring()
                
            else:
                await query.edit_message_text(
                    f"❌ **세션 전환 실패**\n\n"
                    f"세션 `{session_name}`으로 전환할 수 없습니다.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"세션 전환 중 오류: {str(e)}")
            await query.edit_message_text(
                f"❌ **메인 세션 설정 오류**\n\n오류: {str(e)}",
                parse_mode='Markdown'
            )
    
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
                        
                    screen_text = '\n'.join(display_lines)
                    
                    # Send without markdown to avoid parsing errors with session info
                    session_display = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
                    header = f"📺 빠른 로그 ({line_count}줄) [{session_name}]\n\n"
                    header += f"📁 프로젝트: {session_display}\n"
                    header += f"🎯 세션: {session_name}\n"
                    header += f"📏 라인 수: {len(display_lines)}줄\n\n"
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
    
    async def _handle_remote_button(self, update, user_input: str) -> bool:
        """Handle Reply Keyboard prompt macro button presses"""
        
        # Handle single prompt macros
        if user_input in self.PROMPT_MACROS:
            prompt_text = self.PROMPT_MACROS[user_input]
            target_session = await self._get_target_session_for_macro(update)
            success = await self._send_to_claude_with_session(prompt_text, target_session)
            
            session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
            if success:
                await update.message.reply_text(
                    f"✅ {user_input} 프롬프트가 `{session_display}` 세션에 전송되었습니다."
                )
            else:
                await update.message.reply_text(
                    f"❌ {user_input} 프롬프트를 `{session_display}` 세션에 전송하는데 실패했습니다."
                )
            return True
        
        # Handle combined workflow prompts
        if "&" in user_input:
            # Parse combined prompts like "기획&구현&안정화&배포"
            keywords = user_input.split("&")
            combined_prompt = ""
            
            for keyword in keywords:
                macro_key = f"@{keyword.strip()}"
                if macro_key in self.PROMPT_MACROS:
                    combined_prompt += self.PROMPT_MACROS[macro_key] + "\n\n" + "="*50 + "\n\n"
            
            if combined_prompt:
                # Remove the last separator
                combined_prompt = combined_prompt.rstrip("\n\n" + "="*50 + "\n\n")
                
                target_session = await self._get_target_session_for_macro(update)
                success = await self._send_to_claude_with_session(combined_prompt, target_session)
                
                session_display = target_session.replace('claude_', '') if target_session.startswith('claude_') else target_session
                if success:
                    await update.message.reply_text(
                        f"✅ 통합 워크플로우 프롬프트 ({user_input})가 `{session_display}` 세션에 전송되었습니다."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ 통합 워크플로우 프롬프트 ({user_input})를 `{session_display}` 세션에 전송하는데 실패했습니다."
                    )
                return True
        
        return False
    
    async def _get_session_log_content(self, session_name: str, line_count: int = 50) -> str:
        """Get recent log content from session"""
        try:
            # Check if session exists
            session_exists = os.system(f"tmux has-session -t {session_name}") == 0
            if not session_exists:
                return "세션이 존재하지 않습니다."
            
            # Use tmux capture-pane with -S to specify start line (negative for history)
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{line_count}", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                log_content = result.stdout.strip()
                if not log_content:
                    return "로그 내용이 없습니다."
                
                # Limit content length for Telegram message
                if len(log_content) > 3000:  # Telegram message limit consideration
                    lines = log_content.split('\n')
                    truncated_lines = lines[-30:]  # Show last 30 lines if too long
                    log_content = '\n'.join(truncated_lines)
                    log_content += f"\n\n... (총 {len(lines)}줄 중 마지막 30줄만 표시)"
                
                return log_content
            else:
                logger.error(f"Failed to capture session {session_name}: {result.stderr}")
                return "로그를 가져올 수 없습니다."
                
        except Exception as e:
            logger.error(f"Exception getting session log for {session_name}: {str(e)}")
            return "로그 조회 중 오류가 발생했습니다."
    
    async def _get_target_session_for_macro(self, update) -> str:
        """Get target session for macro button press (reply-based or default)"""
        target_session = None
        
        # Check if this is a reply to a bot message (same logic as forward_to_claude)
        if update.message.reply_to_message and update.message.reply_to_message.from_user.is_bot:
            original_text = update.message.reply_to_message.text
            target_session = self.extract_session_from_message(original_text)
            
            if target_session:
                logger.info(f"📍 Reply 기반 매크로 세션 타겟팅: {target_session}")
                
                # Check if target session exists
                session_exists = os.system(f"tmux has-session -t {target_session}") == 0
                if session_exists:
                    return target_session
                else:
                    logger.warning(f"Reply 타겟 세션 {target_session}이 존재하지 않음, 메인 세션 사용")
        
        # Use main session as fallback
        target_session = self.config.session_name
        logger.info(f"🎯 메인 세션 사용: {target_session}")
        return target_session
    
    async def _send_to_claude_with_session(self, text: str, target_session: str) -> bool:
        """Send text to specific Claude session"""
        try:
            # Ensure target session exists
            session_exists = os.system(f"tmux has-session -t {target_session}") == 0
            if not session_exists:
                logger.error(f"Target session {target_session} does not exist")
                return False
            
            # Send text to tmux session using subprocess for better control
            # Use -l flag to send literal text (handles special characters better)
            result1 = subprocess.run(
                ["tmux", "send-keys", "-t", target_session, "-l", text],
                capture_output=True,
                text=True
            )
            
            # Send Enter key
            result2 = subprocess.run(
                ["tmux", "send-keys", "-t", target_session, "Enter"],
                capture_output=True,
                text=True
            )
            
            # Check if both commands succeeded
            if result1.returncode == 0 and result2.returncode == 0:
                logger.info(f"Successfully sent macro prompt to {target_session}: {text[:100]}...")
                return True
            else:
                logger.error(f"Failed to send to {target_session}. Return codes: {result1.returncode}, {result2.returncode}")
                logger.error(f"Errors: {result1.stderr}, {result2.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exception while sending macro to Claude session {target_session}: {str(e)}")
            return False
    
    async def _send_to_claude(self, text: str) -> bool:
        """Send text to current Claude session"""
        try:
            
            # Get current session name
            session_name = self.config.session_name
            
            # Send text to tmux session using subprocess for better control
            # Use -l flag to send literal text (handles special characters better)
            result1 = subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "-l", text],
                capture_output=True,
                text=True
            )
            
            # Send Enter key
            result2 = subprocess.run(
                ["tmux", "send-keys", "-t", session_name, "Enter"],
                capture_output=True,
                text=True
            )
            
            # Check if both commands succeeded
            if result1.returncode == 0 and result2.returncode == 0:
                logger.info(f"Successfully sent prompt to {session_name}: {text[:100]}...")
                return True
            else:
                logger.error(f"Failed to send to {session_name}. Return codes: {result1.returncode}, {result2.returncode}")
                logger.error(f"Errors: {result1.stderr}, {result2.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exception while sending to Claude: {str(e)}")
            return False
    
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
            import asyncio
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"재시도 중... ({attempt + 1}/{max_retries})")
                        time.sleep(5 * attempt)  # Exponential backoff
                    
                    self.app.run_polling()
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if "terminated by other getUpdates request" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"getUpdates 충돌 감지 (시도 {attempt + 1}), 잠시 후 재시도...")
                        continue
                    else:
                        logger.error(f"봇 실행 실패: {str(e)}")
                        raise
            
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