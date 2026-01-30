#!/bin/bash
# Clear notification state when user sends input
# This allows next idle_prompt to send notification again

set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Read stdin (hook data)
INPUT=$(cat)

# Extract project name from cwd
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd', ''))" 2>/dev/null || echo "")

if [ -n "$CWD" ]; then
    PROJECT_NAME=$(basename "$CWD")
    SESSION_NAME="claude_${PROJECT_NAME}"
    STATE_FILE="${PROJECT_DIR}/.state/notifications/${SESSION_NAME}.json"

    if [ -f "$STATE_FILE" ]; then
        rm -f "$STATE_FILE"
    fi
fi

exit 0
