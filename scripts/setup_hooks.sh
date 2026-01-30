#!/bin/bash
# Setup Claude Code hooks for a project
# Usage: ./setup_hooks.sh /path/to/project

set -e

# Validate jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed"
    echo "Install with: sudo apt-get install jq (Debian/Ubuntu)"
    echo "            : brew install jq (macOS)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_SCRIPT="${SCRIPT_DIR}/../claude_ctb/hooks/notify_telegram.sh"

# Validate arguments
if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/project"
    echo ""
    echo "This script sets up Claude Code hooks for Notification events (idle_prompt, permission_prompt)."
    exit 1
fi

PROJECT_PATH="$1"
CLAUDE_DIR="${PROJECT_PATH}/.claude"
SETTINGS_FILE="${CLAUDE_DIR}/settings.local.json"

# Validate project path
if [ ! -d "$PROJECT_PATH" ]; then
    echo "Error: Project directory not found: $PROJECT_PATH"
    exit 1
fi

# Validate hooks script
if [ ! -x "$HOOKS_SCRIPT" ]; then
    echo "Error: Hooks script not found or not executable: $HOOKS_SCRIPT"
    exit 1
fi

# Create .claude directory if needed
mkdir -p "$CLAUDE_DIR"

# Backup existing settings
if [ -f "$SETTINGS_FILE" ]; then
    BACKUP_FILE="${SETTINGS_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$SETTINGS_FILE" "$BACKUP_FILE"
    echo "📦 Backed up existing settings to: $BACKUP_FILE"

    # Read existing settings
    EXISTING=$(cat "$SETTINGS_FILE")
else
    EXISTING="{}"
fi

# Build hooks configuration
HOOKS_CONFIG=$(cat <<EOF
{
  "hooks": {
    "Notification": [
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "${HOOKS_SCRIPT}",
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "${HOOKS_SCRIPT}",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
EOF
)

# Merge with existing settings (hooks takes precedence)
MERGED=$(echo "$EXISTING" "$HOOKS_CONFIG" | jq -s '.[0] * .[1]')

# Write settings
echo "$MERGED" > "$SETTINGS_FILE"

echo "✅ Hooks configured for: $PROJECT_PATH"
echo ""
echo "Settings file: $SETTINGS_FILE"
echo ""
echo "Configured hooks:"
echo "  - Notification (idle_prompt): Telegram notification after 60s idle"
echo "  - Notification (permission_prompt): Telegram notification on permission request"
echo ""
echo "⚠️  Restart Claude Code session to apply changes"
