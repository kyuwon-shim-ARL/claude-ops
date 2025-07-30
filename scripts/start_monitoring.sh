#!/bin/bash

# Start Claude Code monitoring for Telegram notifications
# This script starts the monitoring system in the background using tmux

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if already running
if tmux has-session -t claude-monitor 2>/dev/null; then
    echo -e "${YELLOW}Monitor is already running${NC}"
    echo "Use 'tmux attach -t claude-monitor' to see the status"
    exit 0
fi

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Check required environment variables
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo -e "${RED}Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env${NC}"
    exit 1
fi

# Start the monitor in tmux
echo -e "${GREEN}Starting Claude Code Monitor...${NC}"
tmux new-session -d -s claude-monitor \
    "cd $(pwd) && uv run python -m claude_ops.telegram.monitor"

sleep 2

# Check if started successfully
if tmux has-session -t claude-monitor 2>/dev/null; then
    echo -e "${GREEN}✓ Claude Code Monitor started successfully${NC}"
    echo ""
    echo "Commands:"
    echo "  - View logs: tmux attach -t claude-monitor"
    echo "  - Stop monitor: tmux kill-session -t claude-monitor"
    echo ""
    echo "Monitor will send notifications when Claude Code tasks complete!"
else
    echo -e "${RED}Failed to start Claude Code Monitor${NC}"
    exit 1
fi