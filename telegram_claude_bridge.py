import os
import logging
import shlex
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, CommandHandler, filters

# 환경변수 로드
load_dotenv()

# 설정 로딩
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TMUX_SESSION = os.getenv("TMUX_SESSION", "claude_session")
ALLOWED_USER_IDS = [int(id.strip()) for id in os.getenv("ALLOWED_USER_IDS", "").split(",") if id.strip()]

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_input(user_input):
    """입력값 검증 및 위험한 명령어 필터링"""
    # 위험한 패턴들
    dangerous_patterns = [
        'rm -rf', 'sudo', 'chmod', 'chown', 'passwd', 'shutdown', 'reboot',
        '>', '>>', '|', '&', ';', '$(', '`', 'eval', 'exec'
    ]
    
    user_input_lower = user_input.lower()
    for pattern in dangerous_patterns:
        if pattern in user_input_lower:
            return False, f"위험한 명령어 패턴이 감지되었습니다: {pattern}"
    
    # 길이 제한
    if len(user_input) > 500:
        return False, "입력값이 너무 깁니다 (최대 500자)"
    
    return True, "OK"

def check_user_authorization(user_id):
    """사용자 인증 확인"""
    if not ALLOWED_USER_IDS:
        logger.warning("허용된 사용자 ID가 설정되지 않았습니다!")
        return False
    
    return user_id in ALLOWED_USER_IDS

def check_claude_session():
    """Claude tmux 세션 상태 확인"""
    result = os.system(f"tmux has-session -t {TMUX_SESSION}")
    if result != 0:
        return False, "tmux 세션이 존재하지 않습니다"
    
    return True, "세션이 활성 상태입니다"

def ensure_claude_session():
    """Claude 세션이 없으면 자동 생성"""
    session_ok, message = check_claude_session()
    if not session_ok:
        logger.info("Claude 세션을 자동 생성합니다...")
        os.system(f"tmux new-session -d -s {TMUX_SESSION}")
        os.system(f"tmux send-keys -t {TMUX_SESSION} -l 'claude'")
        os.system(f"tmux send-keys -t {TMUX_SESSION} Enter")
        return "🆕 Claude 세션을 새로 시작했습니다"
    return None

async def forward_to_claude(update, context):
    """사용자가 보낸 텍스트를 tmux 세션으로 전달"""
    user_id = update.effective_user.id
    user_input = update.message.text
    
    logger.info(f"사용자 {user_id}로부터 입력 수신: {user_input[:100]}...")
    
    # 사용자 인증 확인
    if not check_user_authorization(user_id):
        logger.warning(f"인증되지 않은 사용자 접근 시도: {user_id}")
        await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
        return
    
    # 입력값 검증
    is_valid, message = validate_input(user_input)
    if not is_valid:
        logger.warning(f"유효하지 않은 입력: {message}")
        await update.message.reply_text(f"❌ {message}")
        return
    
    # Claude 세션 확인 및 자동 생성
    session_msg = ensure_claude_session()
    if session_msg:
        await update.message.reply_text(session_msg)
    
    try:
        # tmux 세션에 명령어 전송 (Claude Code용: 리터럴 입력 후 Enter)
        result1 = os.system(f"tmux send-keys -t {TMUX_SESSION} -l '{user_input}'")
        result2 = os.system(f"tmux send-keys -t {TMUX_SESSION} Enter")
        result = result1 or result2
        
        if result == 0:
            logger.info(f"성공적으로 전송됨: {user_input}")
            await update.message.reply_text(f"✅ Claude에 입력이 전송되었습니다.")
        else:
            logger.error(f"tmux 명령어 실행 실패: exit code {result}")
            await update.message.reply_text("❌ 명령어 전송에 실패했습니다. tmux 세션을 확인해주세요.")
            
    except Exception as e:
        logger.error(f"예외 발생: {str(e)}")
        await update.message.reply_text("❌ 내부 오류가 발생했습니다.")

async def status_command(update, context):
    """봇 상태 확인 명령어"""
    user_id = update.effective_user.id
    
    if not check_user_authorization(user_id):
        await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
        return
    
    # tmux 세션 상태 확인
    result = os.system(f"tmux has-session -t {TMUX_SESSION}")
    session_status = "✅ 활성" if result == 0 else "❌ 비활성"
    
    status_message = f"""
🤖 **Telegram-Claude Bridge 상태**

• tmux 세션: {session_status}
• 세션 이름: `{TMUX_SESSION}`
• 인증된 사용자: {len(ALLOWED_USER_IDS)}명
• 사용자 ID: `{user_id}`
    """
    
    await update.message.reply_text(status_message, parse_mode='Markdown')

async def start_claude_command(update, context):
    """Claude 세션 시작 명령어"""
    user_id = update.effective_user.id
    
    if not check_user_authorization(user_id):
        await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
        return
    
    session_ok, message = check_claude_session()
    if session_ok:
        await update.message.reply_text("✅ Claude 세션이 이미 실행 중입니다.")
    else:
        logger.info("사용자 요청으로 Claude 세션을 시작합니다...")
        os.system(f"tmux new-session -d -s {TMUX_SESSION}")
        os.system(f"tmux send-keys -t {TMUX_SESSION} -l 'claude'")
        os.system(f"tmux send-keys -t {TMUX_SESSION} Enter")
        await update.message.reply_text("🚀 Claude 세션을 시작했습니다!")

async def help_command(update, context):
    """도움말 명령어"""
    help_text = """
🤖 **Telegram-Claude Bridge 봇**

Claude Code 세션과 텔레그램 간 양방향 통신 브릿지입니다.

**명령어:**
• `/status` - 봇 및 tmux 세션 상태 확인
• `/start` - Claude 세션 시작 (tmux가 없을 때)
• `/help` - 이 도움말 보기
• `/clear` - Claude 화면 정리 (clear 명령어 전송)

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

async def clear_command(update, context):
    """Claude 화면 정리 명령어"""
    user_id = update.effective_user.id
    
    if not check_user_authorization(user_id):
        await update.message.reply_text("❌ 인증되지 않은 사용자입니다.")
        return
    
    try:
        result1 = os.system(f"tmux send-keys -t {TMUX_SESSION} -l 'clear'")
        result2 = os.system(f"tmux send-keys -t {TMUX_SESSION} Enter")
        result = result1 or result2
        if result == 0:
            await update.message.reply_text("🧹 Claude 화면이 정리되었습니다.")
        else:
            await update.message.reply_text("❌ 화면 정리에 실패했습니다.")
    except Exception as e:
        logger.error(f"화면 정리 중 오류: {str(e)}")
        await update.message.reply_text("❌ 내부 오류가 발생했습니다.")

def main():
    """메인 함수"""
    # 필수 환경변수 확인
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다!")
        return
    
    if not ALLOWED_USER_IDS:
        logger.error("ALLOWED_USER_IDS 환경변수가 설정되지 않았습니다!")
        return
    
    logger.info(f"봇 시작 중... 허용된 사용자: {ALLOWED_USER_IDS}")
    
    try:
        # 봇 초기화
        app = Application.builder().token(BOT_TOKEN).build()
        
        # 핸들러 등록
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("start", start_claude_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("clear", clear_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_claude))
        
        # 봇 시작
        logger.info("텔레그램 봇이 시작되었습니다.")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"봇 실행 중 오류 발생: {str(e)}")

if __name__ == '__main__':
    main()