#!/bin/bash

# 수동으로 작업 완료 알림을 전송하는 스크립트
# Usage: ./send-completion-notification.sh [session_name]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_OPS_DIR="$(dirname "$SCRIPT_DIR")"

# 환경 변수 로드
if [ -f "$CLAUDE_OPS_DIR/.env" ]; then
    set -a
    source "$CLAUDE_OPS_DIR/.env"
    set +a
fi

# 세션 이름 결정
SESSION_NAME="${1:-$(tmux display-message -p '#S' 2>/dev/null)}"
if [ -z "$SESSION_NAME" ] || [[ ! "$SESSION_NAME" =~ ^claude_ ]]; then
    # 현재 Claude 세션 찾기
    SESSION_NAME=$(tmux list-sessions 2>/dev/null | grep "^claude_" | head -1 | cut -d: -f1)
fi

if [ -z "$SESSION_NAME" ]; then
    echo "❌ No Claude session found"
    exit 1
fi

echo "📤 Sending completion notification for session: $SESSION_NAME"

cd "$CLAUDE_OPS_DIR"
CLAUDE_SESSION_NAME="$SESSION_NAME" python3 -c "
from claude_ctb.telegram.notifier import SmartNotifier
from claude_ctb.config import ClaudeOpsConfig
import sys

try:
    config = ClaudeOpsConfig()
    notifier = SmartNotifier(config)
    success = notifier.send_work_completion_notification()
    
    if success:
        print(f'✅ Notification sent successfully for {config.session_name}')
        sys.exit(0)
    else:
        print(f'⚠️  Notification skipped for {config.session_name}')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Notification error: {e}')
    sys.exit(1)
"