#!/bin/bash
# Claude Code Hook → Telegram Notification
# Usage: Called by Claude Code hooks (idle_prompt/permission_prompt only)
# stdin: JSON from Claude Code hook system
#
# Purpose: Send Telegram notification when Claude needs user input
# - idle_prompt: Fires after 60s idle, signals task completion
# - permission_prompt: Fires when permission needed
#
# This script delegates to hook_notify.py which uses
# SmartNotifier for consistent notification format.

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Read stdin and pass to Python script
INPUT=$(cat)

# Call Python script with same stdin
cd "$PROJECT_DIR"
echo "$INPUT" | uv run python -m claude_ctb.hooks.hook_notify

exit $?
