#!/bin/bash

# Stop Telegram Bridge for Claude-Ops
# This script stops the Telegram bridge tmux session

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running
if ! tmux has-session -t claude-telegram-bridge 2>/dev/null; then
    echo -e "${YELLOW}Telegram Bridge is not running${NC}"
    exit 0
fi

# Stop the session
echo -e "${YELLOW}Stopping Telegram Bridge...${NC}"
tmux kill-session -t claude-telegram-bridge

# Verify stopped
sleep 1
if ! tmux has-session -t claude-telegram-bridge 2>/dev/null; then
    echo -e "${GREEN}✓ Telegram Bridge stopped successfully${NC}"
else
    echo -e "${RED}Failed to stop Telegram Bridge${NC}"
    exit 1
fi