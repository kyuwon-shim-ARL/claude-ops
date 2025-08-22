"""
Telegram handler for /compact command suggestions

Provides Telegram bot integration for easy execution of /compact commands
suggested by Claude Code.
"""

import logging
from typing import Optional, List, Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ..utils.compact_detector import CompactPromptDetector, CompactExecutor
from ..config import ClaudeOpsConfig

logger = logging.getLogger(__name__)


class CompactTelegramHandler:
    """Handles /compact suggestions via Telegram bot"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        self.config = config or ClaudeOpsConfig()
        self.detector = CompactPromptDetector()
        self.executor = CompactExecutor()
        
    def create_notification_message(self, session_name: str, analysis: Dict) -> str:
        """
        Create a formatted notification message for Telegram
        
        Args:
            session_name: The tmux session name
            analysis: Analysis result from CompactPromptDetector
            
        Returns:
            str: Formatted message for Telegram
        """
        commands = analysis.get('commands', [])
        is_multi = analysis.get('is_multi_step', False)
        
        # Format session display name
        display_name = session_name.replace('claude_', '') if session_name.startswith('claude_') else session_name
        
        # Build message
        message = f"📦 **컨텍스트 정리 제안**\n\n"
        message += f"**세션:** {display_name}\n\n"
        
        if is_multi:
            message += "Claude가 다음 명령들을 순서대로 실행하도록 제안했습니다:\n\n"
            for i, cmd in enumerate(commands, 1):
                message += f"{i}. `{cmd}`\n"
        else:
            cmd = commands[0] if commands else '/compact'
            message += f"Claude가 다음 명령 실행을 제안했습니다:\n\n"
            message += f"`{cmd}`\n"
        
        message += "\n💡 버튼을 클릭하여 명령을 실행하세요."
        
        return message
    
    def create_inline_keyboard(self, session_name: str, commands: List[str]) -> InlineKeyboardMarkup:
        """
        Create inline keyboard buttons for command execution
        
        Args:
            session_name: The tmux session name
            commands: List of /compact commands
            
        Returns:
            InlineKeyboardMarkup: Telegram inline keyboard
        """
        keyboard = []
        
        if len(commands) == 1:
            # Single command - simple execution
            keyboard.append([
                InlineKeyboardButton(
                    "🚀 실행",
                    callback_data=f"compact_exec:{session_name}:{commands[0]}"
                ),
                InlineKeyboardButton(
                    "📋 복사",
                    callback_data=f"compact_copy:{commands[0]}"
                )
            ])
        else:
            # Multiple commands - individual and batch options
            for i, cmd in enumerate(commands):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{i+1}. {cmd}",
                        callback_data=f"compact_exec:{session_name}:{cmd}"
                    )
                ])
            
            # Add "execute all" button
            keyboard.append([
                InlineKeyboardButton(
                    "⚡ 모두 실행",
                    callback_data=f"compact_exec_all:{session_name}"
                )
            ])
        
        # Always add cancel button
        keyboard.append([
            InlineKeyboardButton(
                "❌ 무시",
                callback_data="compact_ignore"
            )
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def handle_callback(self, update, context) -> str:
        """
        Handle callback queries from inline keyboard buttons
        
        Args:
            update: Telegram update object
            context: Telegram context object
            
        Returns:
            str: Response message
        """
        query = update.callback_query
        data = query.data
        
        # Parse callback data
        if data.startswith("compact_exec:"):
            # Execute single command
            parts = data.split(":", 2)
            if len(parts) >= 3:
                session_name = parts[1]
                command = parts[2]
                
                success = self.executor.execute_command(session_name, command)
                
                if success:
                    await query.answer("✅ 명령이 실행되었습니다")
                    return f"✅ **실행 완료**\n\n세션: {session_name}\n명령: `{command}`"
                else:
                    await query.answer("❌ 실행 실패", show_alert=True)
                    return f"❌ **실행 실패**\n\n세션: {session_name}\n명령: `{command}`"
        
        elif data.startswith("compact_exec_all:"):
            # Execute all commands in sequence
            session_name = data.split(":", 1)[1]
            
            # Get commands from original message (stored in context)
            commands = context.user_data.get(f"compact_commands_{session_name}", [])
            
            if commands:
                success = self.executor.execute_sequence(session_name, commands)
                
                if success:
                    await query.answer("✅ 모든 명령이 실행되었습니다")
                    return f"✅ **모두 실행 완료**\n\n세션: {session_name}\n실행된 명령: {len(commands)}개"
                else:
                    await query.answer("⚠️ 일부 명령 실행 실패", show_alert=True)
                    return f"⚠️ **일부 실행 실패**\n\n세션: {session_name}\n자세한 내용은 로그를 확인하세요."
            else:
                await query.answer("❌ 명령을 찾을 수 없습니다", show_alert=True)
                return "❌ 명령 목록을 찾을 수 없습니다"
        
        elif data.startswith("compact_copy:"):
            # Copy command to clipboard (show as message)
            command = data.split(":", 1)[1]
            await query.answer("📋 명령이 표시됩니다")
            return f"📋 **복사용 명령:**\n\n`{command}`"
        
        elif data == "compact_ignore":
            # Ignore the suggestion
            await query.answer("무시되었습니다")
            await query.message.delete()
            return None
        
        return "❓ 알 수 없는 작업입니다"
    
    async def send_notification(self, bot, chat_id: str, session_name: str, analysis: Dict) -> bool:
        """
        Send a /compact notification to Telegram
        
        Args:
            bot: Telegram bot instance
            chat_id: Target chat ID
            session_name: The tmux session name
            analysis: Analysis result from CompactPromptDetector
            
        Returns:
            bool: True if notification sent successfully
        """
        try:
            commands = analysis.get('commands', [])
            
            if not commands:
                logger.warning("No commands found in analysis")
                return False
            
            # Create message and keyboard
            message = self.create_notification_message(session_name, analysis)
            keyboard = self.create_inline_keyboard(session_name, commands)
            
            # Store commands for later use in callback
            # This would need to be integrated with bot's context storage
            
            # Send message
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            
            logger.info(f"Sent /compact notification for session {session_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False


# Integration point for monitoring system
class CompactMonitorIntegration:
    """Integrates /compact detection with the monitoring system"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        self.config = config or ClaudeOpsConfig()
        self.detector = CompactPromptDetector()
        self.handler = CompactTelegramHandler(config)
        self.last_check = {}
    
    def check_session_for_compact(self, session_name: str, screen_content: str) -> Optional[Dict]:
        """
        Check a session for /compact suggestions
        
        Args:
            session_name: The tmux session name
            screen_content: Current screen content
            
        Returns:
            Dict: Analysis result if suggestion found, None otherwise
        """
        # Analyze screen content
        analysis = self.detector.analyze_context(screen_content)
        
        if analysis['has_suggestion']:
            # Check if we should notify
            commands = analysis.get('commands', [])
            if commands and self.detector.should_notify(session_name, commands[0]):
                logger.info(f"New /compact suggestion detected in {session_name}")
                return analysis
        
        return None