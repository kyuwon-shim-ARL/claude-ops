#!/bin/bash

# Check status of Claude-Ops components
# This script checks the status of all system components

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Claude-Ops System Status ===${NC}"
echo ""

# Check Telegram Bridge
echo -e "${BLUE}Telegram Bridge:${NC}"
if tmux has-session -t claude-telegram-bridge 2>/dev/null; then
    echo -e "  ${GREEN}✓ Running${NC}"
    # Get last few lines of log
    echo "  Last activity:"
    tmux capture-pane -t claude-telegram-bridge -p | tail -5 | sed 's/^/    /'
else
    echo -e "  ${RED}✗ Not running${NC}"
    echo "  Start with: ./scripts/start_telegram_bridge.sh"
fi
echo ""

# Check Claude Code sessions
echo -e "${BLUE}Claude Code Sessions:${NC}"
sessions=$(tmux list-sessions 2>/dev/null | grep "claude-" | grep -v "telegram-bridge" || true)
if [ -n "$sessions" ]; then
    echo "$sessions" | while read -r session; do
        session_name=$(echo "$session" | cut -d: -f1)
        echo -e "  ${GREEN}✓ $session_name${NC}"
    done
else
    echo -e "  ${YELLOW}No active Claude Code sessions${NC}"
fi
echo ""

# Check environment setup
echo -e "${BLUE}Environment:${NC}"
if [ -f .env ]; then
    echo -e "  ${GREEN}✓ .env file exists${NC}"
    
    # Check key variables (without exposing values)
    source .env
    
    check_var() {
        if [ -n "${!1}" ]; then
            echo -e "  ${GREEN}✓ $1 is set${NC}"
        else
            echo -e "  ${RED}✗ $1 is not set${NC}"
        fi
    }
    
    check_var "TELEGRAM_BOT_TOKEN"
    check_var "TELEGRAM_CHAT_ID"
    check_var "NOTION_API_KEY"
    check_var "GITHUB_PAT"
else
    echo -e "  ${RED}✗ .env file not found${NC}"
fi
echo ""

# Check Python environment
echo -e "${BLUE}Python Environment:${NC}"
if command -v uv &> /dev/null; then
    echo -e "  ${GREEN}✓ uv is installed${NC}"
    if [ -f .venv/bin/python ]; then
        echo -e "  ${GREEN}✓ Virtual environment exists${NC}"
    else
        echo -e "  ${YELLOW}! Virtual environment not found${NC}"
        echo "    Run: uv sync"
    fi
else
    echo -e "  ${YELLOW}! uv not installed${NC}"
    echo "    Run: ./install.sh"
fi
echo ""

# Check Git status
echo -e "${BLUE}Git Status:${NC}"
if [ -d .git ]; then
    branch=$(git branch --show-current 2>/dev/null || echo "unknown")
    echo -e "  Current branch: ${GREEN}$branch${NC}"
    
    # Check for uncommitted changes
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo -e "  ${YELLOW}! Uncommitted changes present${NC}"
    else
        echo -e "  ${GREEN}✓ Working directory clean${NC}"
    fi
else
    echo -e "  ${RED}✗ Not a git repository${NC}"
fi
echo ""

echo -e "${BLUE}================================${NC}"