"""
File upload/download and external service handlers for Telegram bot
"""

import os
import sys
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Add email_agent to path for Gmail integration
EMAIL_AGENT_PATH = '/home/kyuwon/projects/email_agent'


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, project_dir: str) -> None:
    """
    Handle file uploads from Telegram - save to project root

    Args:
        update: Telegram update object
        context: Telegram context
        project_dir: Project directory to save file to
    """
    try:
        # Get file from message
        if update.message.document:
            file = update.message.document
            file_name = file.file_name
        elif update.message.photo:
            # For photos, use the largest size
            file = update.message.photo[-1]
            file_name = f"photo_{file.file_id[:8]}.jpg"
        elif update.message.video:
            file = update.message.video
            file_name = file.file_name or f"video_{file.file_id[:8]}.mp4"
        elif update.message.audio:
            file = update.message.audio
            file_name = file.file_name or f"audio_{file.file_id[:8]}.mp3"
        elif update.message.voice:
            file = update.message.voice
            file_name = f"voice_{file.file_id[:8]}.ogg"
        else:
            await update.message.reply_text("❌ 지원하지 않는 파일 형식입니다.")
            return

        # Download file
        telegram_file = await file.get_file()

        # Save to project root
        save_path = os.path.join(project_dir, file_name)

        # Check if file already exists
        if os.path.exists(save_path):
            base, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join(project_dir, f"{base}_{counter}{ext}")
                counter += 1
            file_name = os.path.basename(save_path)

        await telegram_file.download_to_drive(save_path)

        # Get file size
        file_size = os.path.getsize(save_path)
        size_str = _format_file_size(file_size)

        await update.message.reply_text(
            f"✅ <b>파일 업로드 완료</b>\n\n"
            f"📁 파일명: <code>{file_name}</code>\n"
            f"📂 저장 위치: <code>{save_path}</code>\n"
            f"📏 크기: {size_str}\n\n"
            f"💡 Claude에게 이 파일을 사용하도록 지시하세요.",
            parse_mode='HTML'
        )

        logger.info(f"File uploaded: {save_path} ({size_str})")

    except Exception as e:
        logger.error(f"File upload error: {str(e)}")
        await update.message.reply_text(f"❌ 파일 업로드 실패: {str(e)}")


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Download file from server and send to Telegram

    Usage: /download /path/to/file
    """
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ 파일 경로를 입력하세요.\n\n"
                "사용법: <code>/download /path/to/file</code>",
                parse_mode='HTML'
            )
            return

        file_path = ' '.join(context.args)

        # Expand ~ to home directory
        file_path = os.path.expanduser(file_path)

        if not os.path.exists(file_path):
            await update.message.reply_text(f"❌ 파일을 찾을 수 없습니다: <code>{file_path}</code>", parse_mode='HTML')
            return

        if not os.path.isfile(file_path):
            await update.message.reply_text(f"❌ 디렉토리는 다운로드할 수 없습니다: <code>{file_path}</code>", parse_mode='HTML')
            return

        # Check file size (Telegram limit is 50MB for bots)
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                f"❌ 파일이 너무 큽니다 (최대 50MB)\n"
                f"📏 현재 크기: {_format_file_size(file_size)}"
            )
            return

        # Send file
        file_name = os.path.basename(file_path)
        await update.message.reply_document(
            document=open(file_path, 'rb'),
            filename=file_name,
            caption=f"📁 {file_name}\n📏 {_format_file_size(file_size)}"
        )

        logger.info(f"File downloaded: {file_path}")

    except Exception as e:
        logger.error(f"File download error: {str(e)}")
        await update.message.reply_text(f"❌ 파일 다운로드 실패: {str(e)}")


async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send email via Gmail API (using email_agent)

    Usage: /email recipient@email.com Subject line
    Then reply with email body

    Or: /email recipient@email.com Subject line
    Body text here...
    """
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ 사용법이 올바르지 않습니다.\n\n"
                "<b>사용법:</b>\n"
                "<code>/email 받는사람@email.com 제목</code>\n"
                "본문 내용...\n\n"
                "<b>예시:</b>\n"
                "<code>/email user@example.com 회의 안내</code>\n"
                "안녕하세요, 내일 회의가 있습니다.",
                parse_mode='HTML'
            )
            return

        # Parse arguments
        recipient = context.args[0]

        # Get full message text to extract subject and body
        full_text = update.message.text

        # Remove /email command
        text_after_command = full_text.split(None, 1)[1] if ' ' in full_text else ''

        # Split by newline - first line is "recipient subject", rest is body
        lines = text_after_command.split('\n', 1)
        first_line = lines[0].strip()

        # Extract subject (everything after recipient in first line)
        first_line_parts = first_line.split(None, 1)
        if len(first_line_parts) < 2:
            await update.message.reply_text("❌ 제목을 입력하세요.")
            return

        subject = first_line_parts[1]
        body = lines[1].strip() if len(lines) > 1 else ""

        if not body:
            await update.message.reply_text(
                "❌ 본문을 입력하세요.\n\n"
                "제목 다음 줄에 본문을 입력해주세요."
            )
            return

        # Validate email format
        if '@' not in recipient or '.' not in recipient:
            await update.message.reply_text(f"❌ 올바른 이메일 주소가 아닙니다: {recipient}")
            return

        # Send progress message
        progress_msg = await update.message.reply_text("📧 이메일 전송 중...")

        # Import and use GmailClient
        try:
            sys.path.insert(0, EMAIL_AGENT_PATH)
            from email_classifier.gmail_client import GmailClient

            gmail = GmailClient()
            result = gmail.send_email(
                to=recipient,
                subject=subject,
                body=body.replace('\n', '<br>')  # Convert newlines to HTML
            )

            if result and result.get('id'):
                await progress_msg.edit_text(
                    f"✅ <b>이메일 전송 완료</b>\n\n"
                    f"📬 받는 사람: <code>{recipient}</code>\n"
                    f"📝 제목: {subject}\n"
                    f"📄 본문 길이: {len(body)}자",
                    parse_mode='HTML'
                )
                logger.info(f"Email sent to {recipient}: {subject}")
            else:
                await progress_msg.edit_text(f"❌ 이메일 전송 실패: 응답이 없습니다.")

        except ImportError as e:
            await progress_msg.edit_text(
                f"❌ email_agent를 불러올 수 없습니다.\n"
                f"경로: {EMAIL_AGENT_PATH}\n"
                f"오류: {str(e)}"
            )
        except Exception as e:
            await progress_msg.edit_text(f"❌ 이메일 전송 실패: {str(e)}")

    except Exception as e:
        logger.error(f"Email command error: {str(e)}")
        await update.message.reply_text(f"❌ 이메일 명령 오류: {str(e)}")


# Predefined Google Drive folders
GDRIVE_FOLDERS = {
    'personal': '1tCnbS6Gfk25nou6GQnDN-FvoZtImaJ5q',  # 개인용
    'shared': '1CaheKPyquDuPvTc9vjHGv-QZZmyrHvok',    # 공유용
}


async def gdrive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Upload file to Google Drive

    Usage:
        /gdrive /path/to/file           - Upload to My Drive root
        /gdrive /path/to/file personal  - Upload to personal folder
        /gdrive /path/to/file shared    - Upload to shared folder
    """
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ 파일 경로를 입력하세요.\n\n"
                "<b>사용법:</b>\n"
                "<code>/gdrive /path/to/file</code> - 루트에 업로드\n"
                "<code>/gdrive /path/to/file personal</code> - 개인용 폴더\n"
                "<code>/gdrive /path/to/file shared</code> - 공유용 폴더\n\n"
                "<b>폴더 옵션:</b>\n"
                "• <code>personal</code> - 개인용 폴더\n"
                "• <code>shared</code> - 공유용 폴더",
                parse_mode='HTML'
            )
            return

        file_path = context.args[0]
        folder_option = context.args[1].lower() if len(context.args) > 1 else None

        # Expand ~ to home directory
        file_path = os.path.expanduser(file_path)

        if not os.path.exists(file_path):
            await update.message.reply_text(f"❌ 파일을 찾을 수 없습니다: <code>{file_path}</code>", parse_mode='HTML')
            return

        if not os.path.isfile(file_path):
            await update.message.reply_text(f"❌ 디렉토리는 업로드할 수 없습니다: <code>{file_path}</code>", parse_mode='HTML')
            return

        # Determine folder ID
        folder_id = None
        folder_display_name = "My Drive"

        if folder_option:
            if folder_option in GDRIVE_FOLDERS:
                folder_id = GDRIVE_FOLDERS[folder_option]
                folder_display_name = "개인용" if folder_option == "personal" else "공유용"
            else:
                await update.message.reply_text(
                    f"❌ 알 수 없는 폴더 옵션: {folder_option}\n\n"
                    f"사용 가능한 옵션: <code>personal</code>, <code>shared</code>",
                    parse_mode='HTML'
                )
                return

        # Send progress message
        progress_msg = await update.message.reply_text(f"☁️ Google Drive ({folder_display_name}) 업로드 중...")

        try:
            # Use Google Drive API
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            SCOPES = ['https://www.googleapis.com/auth/drive.file']

            # Look for credentials in email_agent directory
            token_path = os.path.join(EMAIL_AGENT_PATH, 'token.json')
            creds_path = os.path.join(EMAIL_AGENT_PATH, 'credentials.json')

            creds = None

            # Load existing token
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif os.path.exists(creds_path):
                    await progress_msg.edit_text(
                        "❌ Google Drive 인증이 필요합니다.\n"
                        "email_agent 프로젝트에서 먼저 인증을 완료해주세요."
                    )
                    return
                else:
                    await progress_msg.edit_text(
                        f"❌ credentials.json 파일을 찾을 수 없습니다.\n"
                        f"경로: {creds_path}"
                    )
                    return

            # Build Drive service
            service = build('drive', 'v3', credentials=creds)

            # Get file info
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Prepare file metadata
            file_metadata = {'name': file_name}

            # Set parent folder if specified
            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Upload file
            media = MediaFileUpload(file_path, resumable=True)
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            file_link = uploaded_file.get('webViewLink', 'N/A')

            await progress_msg.edit_text(
                f"✅ <b>Google Drive 업로드 완료</b>\n\n"
                f"📁 파일명: <code>{file_name}</code>\n"
                f"📏 크기: {_format_file_size(file_size)}\n"
                f"📂 폴더: {folder_display_name}\n\n"
                f"🔗 <a href='{file_link}'>파일 열기</a>",
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            logger.info(f"File uploaded to Google Drive ({folder_display_name}): {file_name}")

        except ImportError as e:
            await progress_msg.edit_text(
                f"❌ Google API 라이브러리가 설치되지 않았습니다.\n"
                f"pip install google-api-python-client google-auth-oauthlib"
            )
        except Exception as e:
            await progress_msg.edit_text(f"❌ Google Drive 업로드 실패: {str(e)}")
            logger.error(f"Google Drive upload error: {str(e)}")

    except Exception as e:
        logger.error(f"GDrive command error: {str(e)}")
        await update.message.reply_text(f"❌ Google Drive 명령 오류: {str(e)}")


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
