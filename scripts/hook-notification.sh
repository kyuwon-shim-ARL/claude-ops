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
SESSION_NAME="${CLAUDE_SESSION_NAME:-claude_unknown}"
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
from claude_ops.session_manager import session_manager

try:
    # Get current active session or use provided session name
    current_session = session_manager.get_active_session()
    if not current_session or current_session == 'claude_claude-ops':
        # Try to detect which session might have completed work
        all_sessions = session_manager.get_all_claude_sessions()
        if all_sessions:
            current_session = all_sessions[0]  # Use first available session
    
    # Temporarily switch to detected session for notification context
    if current_session:
        session_manager.switch_session(current_session)
    
    config = ClaudeOpsConfig()
    notifier = SmartNotifier(config)
    success = notifier.send_work_completion_notification()
    
    if success:
        print(f'Hook notification sent for session: {current_session}')
    else:
        print(f'Hook notification skipped for session: {current_session}')
        
except Exception as e:
    print(f'Hook notification error: {e}')
    import traceback
    traceback.print_exc()
" >> "$CLAUDE_OPS_DIR/hook.log" 2>&1

echo "$(date): Hook notification script completed" >> "$CLAUDE_OPS_DIR/hook.log"
exit 0