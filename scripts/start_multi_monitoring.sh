#!/bin/bash

# Start Multi-Session Claude Code monitoring for Telegram notifications
# This script monitors ALL Claude sessions simultaneously

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if already running
if tmux has-session -t claude-multi-monitor 2>/dev/null; then
    echo -e "${YELLOW}Multi-session monitor is already running${NC}"
    echo "Use 'tmux attach -t claude-multi-monitor' to see the status"
    exit 0
fi

# Kill single-session monitor if running
if tmux has-session -t claude-monitor 2>/dev/null; then
    echo -e "${YELLOW}Stopping single-session monitor...${NC}"
    tmux kill-session -t claude-monitor 2>/dev/null
fi

# Kill any orphaned monitoring processes
echo -e "${YELLOW}Checking for orphaned monitoring processes...${NC}"
if pgrep -f "multi_monitor" > /dev/null; then
    echo -e "${YELLOW}Found orphaned multi_monitor processes, cleaning up...${NC}"
    pkill -f "multi_monitor" 2>/dev/null || true
    sleep 2
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

# Start the multi-session monitor in tmux
echo -e "${GREEN}Starting Multi-Session Claude Code Monitor...${NC}"
tmux new-session -d -s claude-multi-monitor \
    "cd $(pwd) && uv run python -m claude_ops.telegram.multi_monitor"

sleep 2

# Check if started successfully
if tmux has-session -t claude-multi-monitor 2>/dev/null; then
    echo -e "${GREEN}✓ Multi-Session Monitor started successfully${NC}"
    echo ""
    echo "🎯 Now monitoring ALL Claude sessions simultaneously!"
    echo ""
    echo "Commands:"
    echo "  - View logs: tmux attach -t claude-multi-monitor"
    echo "  - Stop monitor: tmux kill-session -t claude-multi-monitor"
    echo ""
    echo "🚀 The monitor will automatically detect new sessions and send"
    echo "   notifications when ANY Claude Code task completes!"
else
    echo -e "${RED}Failed to start Multi-Session Monitor${NC}"
    exit 1
fi