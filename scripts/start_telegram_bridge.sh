#!/bin/bash

# Start Telegram Bridge for Claude-Ops
# This script starts the Telegram bridge in the background using tmux

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if already running
if tmux has-session -t claude-telegram-bridge 2>/dev/null; then
    echo -e "${YELLOW}Telegram Bridge is already running${NC}"
    echo "Use './scripts/check_status.sh' to see the status"
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

# Start the bridge in tmux
echo -e "${GREEN}Starting Telegram Bridge...${NC}"
tmux new-session -d -s claude-telegram-bridge \
    "cd $(pwd) && uv run python -m claude_ops.telegram.bot"

sleep 2

# Check if started successfully
if tmux has-session -t claude-telegram-bridge 2>/dev/null; then
    echo -e "${GREEN}✓ Telegram Bridge started successfully${NC}"
    echo ""
    echo "Commands:"
    echo "  - View logs: tmux attach -t claude-telegram-bridge"
    echo "  - Check status: ./scripts/check_status.sh"
    echo "  - Stop bridge: ./scripts/stop_telegram_bridge.sh"
    echo ""
    echo "You can now use your Telegram bot!"
else
    echo -e "${RED}Failed to start Telegram Bridge${NC}"
    exit 1
fi