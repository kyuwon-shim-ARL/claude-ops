#!/bin/bash

# Claude Code Hook: Send Telegram notification when work completes
# This script is called by Claude Code's built-in hook system
# Version: 2.1 - Enhanced debugging and reliability

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_OPS_DIR="$(dirname "$SCRIPT_DIR")"

# Enhanced logging with environment info
echo "=== $(date): Claude Code Hook TRIGGERED ===" >> "$CLAUDE_OPS_DIR/hook.log"
echo "PWD: $PWD" >> "$CLAUDE_OPS_DIR/hook.log"
echo "CLAUDE_SESSION_NAME: ${CLAUDE_SESSION_NAME:-unset}" >> "$CLAUDE_OPS_DIR/hook.log"
echo "Environment vars:" >> "$CLAUDE_OPS_DIR/hook.log"
env | grep -E "(CLAUDE|TMUX)" >> "$CLAUDE_OPS_DIR/hook.log" 2>/dev/null || echo "No CLAUDE/TMUX vars" >> "$CLAUDE_OPS_DIR/hook.log"

# Read hook data from stdin (JSON format) with timeout
HOOK_DATA=$(timeout 5s cat 2>/dev/null || echo "No hook data")
echo "Hook data: $HOOK_DATA" >> "$CLAUDE_OPS_DIR/hook.log"

# Extract session information from environment or hook data
# Try multiple methods to get session name
if [ -n "$CLAUDE_SESSION_NAME" ]; then
    SESSION_NAME="$CLAUDE_SESSION_NAME"
elif [ -n "$TMUX" ]; then
    # Extract session name from tmux environment
    SESSION_NAME=$(tmux display-message -p '#S' 2>/dev/null || echo "claude_unknown")
else
    SESSION_NAME="claude_unknown"
fi
WORKING_DIR="${PWD:-unknown}"

# Load environment variables for Telegram
if [ -f "$CLAUDE_OPS_DIR/.env" ]; then
    set -a
    source "$CLAUDE_OPS_DIR/.env"
    set +a
fi

# Check if required Telegram credentials exist
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "$(date): Missing Telegram credentials, skipping notification" >> "$CLAUDE_OPS_DIR/hook.log"
    exit 0
fi

# Send notification using Python script
cd "$CLAUDE_OPS_DIR"

# Use existing notifier with current session
export CLAUDE_SESSION_NAME="$SESSION_NAME"
python3 -c "
import os
import sys
sys.path.insert(0, '.')
from claude_ops.telegram.notifier import SmartNotifier
from claude_ops.config import ClaudeOpsConfig
from claude_ops.utils.session_state import is_session_working, get_session_working_info

try:
    # Check if session is actually idle (completed work)
    session_name = '$SESSION_NAME'
    is_working = is_session_working(session_name)
    
    # Only send notification if session has transitioned from working to idle
    if not is_working:
        config = ClaudeOpsConfig()
        notifier = SmartNotifier(config)
        success = notifier.send_work_completion_notification()
        
        if success:
            print(f'Hook notification sent for session: {session_name} (work completed)')
        else:
            print(f'Hook notification skipped for session: {session_name} (no work to report)')
    else:
        print(f'Hook notification skipped for session: {session_name} (still working)')
        
except Exception as e:
    print(f'Hook notification error: {e}')
    import traceback
    traceback.print_exc()
" >> "$CLAUDE_OPS_DIR/hook.log" 2>&1

echo "$(date): Hook notification script completed" >> "$CLAUDE_OPS_DIR/hook.log"
exit 0