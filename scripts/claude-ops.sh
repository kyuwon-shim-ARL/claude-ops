#!/bin/bash

# Claude-Ops CLI Tool
# Usage: claude-ops <command> [args...]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_OPS_DIR="$(dirname "$SCRIPT_DIR")"

# Show help
show_help() {
    printf "${BLUE}🚀 Claude-Ops CLI${NC}\n"
    printf "\n"
    printf "${YELLOW}Usage:${NC}\n"
    printf "  claude-ops <command> [args...]\n"
    printf "\n"
    printf "${YELLOW}Commands:${NC}\n"
    printf "  ${GREEN}new-project${NC} <name> [path]     Create new Claude project session\n"
    printf "  ${GREEN}kill-session${NC} <name>          Kill specific Claude session\n"
    printf "  ${GREEN}start-monitoring${NC}             Start multi-session monitoring\n"
    printf "  ${GREEN}stop-monitoring${NC}              Stop all monitoring processes\n"
    printf "  ${GREEN}status${NC}                       Show system status\n"
    printf "  ${GREEN}sessions${NC}                     List all Claude sessions\n"
    printf "  ${GREEN}help${NC}                         Show this help message\n"
    printf "\n"
    printf "${YELLOW}Examples:${NC}\n"
    printf "  claude-ops new-project my-ai-app\n"
    printf "  claude-ops new-project web-scraper ~/work/client\n"
    printf "  claude-ops kill-session claude_my-ai-app\n"
    printf "  claude-ops start-monitoring\n"
    printf "  claude-ops status\n"
    printf "\n"
    printf "${BLUE}💡 Tip:${NC} Add to PATH with: claude-ops install\n"
}

# Install to PATH
install_to_path() {
    printf "${BLUE}🔧 Installing claude-ops to PATH...${NC}\n"
    
    # Add to ~/.bashrc
    BASHRC_ENTRY="# Claude-Ops CLI
export PATH=\"$SCRIPT_DIR:\$PATH\"
alias claude-ops='$SCRIPT_DIR/claude-ops.sh'"
    
    if ! grep -q "Claude-Ops CLI" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "$BASHRC_ENTRY" >> ~/.bashrc
        printf "${GREEN}✅ Added to ~/.bashrc${NC}\n"
    else
        printf "${YELLOW}⚠️  Already installed in ~/.bashrc${NC}\n"
    fi
    
    # Create symlink in /usr/local/bin if possible (optional)
    if [ -w "/usr/local/bin" ] 2>/dev/null; then
        ln -sf "$SCRIPT_DIR/claude-ops.sh" "/usr/local/bin/claude-ops" 2>/dev/null && \
        printf "${GREEN}✅ Created symlink in /usr/local/bin${NC}\n" || \
        printf "${YELLOW}⚠️  Could not create symlink in /usr/local/bin${NC}\n"
    fi
    
    printf "\n"
    printf "${GREEN}🎉 Installation complete!${NC}\n"
    printf "Run: ${YELLOW}source ~/.bashrc${NC} or restart your terminal\n"
    printf "Then try: ${YELLOW}claude-ops help${NC}\n"
}

# Create new project
new_project() {
    if [ $# -eq 0 ]; then
        printf "${RED}Error: Project name required${NC}\n"
        printf "Usage: claude-ops new-project <name> [path]\n"
        exit 1
    fi
    
    "$SCRIPT_DIR/new-project.sh" "$@"
}

# Kill specific session
kill_session() {
    if [ $# -eq 0 ]; then
        printf "${RED}Error: Session name required${NC}\n"
        printf "Usage: claude-ops kill-session <session-name>\n"
        printf "\n"
        printf "Available sessions:\n"
        CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1 || true)
        if [ -n "$CLAUDE_SESSIONS" ]; then
            echo "$CLAUDE_SESSIONS" | while read session; do
                printf "  🎯 $session\n"
            done
        else
            printf "  ${YELLOW}No Claude sessions found${NC}\n"
        fi
        exit 1
    fi
    
    SESSION_NAME="$1"
    
    # Add claude_ prefix if not present
    if [[ "$SESSION_NAME" != claude_* ]] && [[ "$SESSION_NAME" != claude-* ]]; then
        SESSION_NAME="claude_${SESSION_NAME}"
    fi
    
    # Check if session exists
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        printf "${RED}❌ Session '$SESSION_NAME' not found${NC}\n"
        printf "\n"
        printf "Available sessions:\n"
        CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1 || true)
        if [ -n "$CLAUDE_SESSIONS" ]; then
            echo "$CLAUDE_SESSIONS" | while read session; do
                printf "  🎯 $session\n"
            done
        else
            printf "  ${YELLOW}No Claude sessions found${NC}\n"
        fi
        exit 1
    fi
    
    # Confirm before killing
    printf "${YELLOW}⚠️  Are you sure you want to kill session '${SESSION_NAME}'? [y/N] ${NC}"
    read -r confirm
    
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        tmux kill-session -t "$SESSION_NAME" 2>/dev/null && \
            printf "${GREEN}✅ Session '$SESSION_NAME' killed successfully${NC}\n" || \
            printf "${RED}❌ Failed to kill session '$SESSION_NAME'${NC}\n"
    else
        printf "${YELLOW}❌ Operation cancelled${NC}\n"
    fi
}

# Start monitoring
start_monitoring() {
    cd "$CLAUDE_OPS_DIR"
    
    # Check if already running
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "${YELLOW}Multi-session monitor is already running${NC}\n"
        return 0
    fi
    
    # Kill single-session monitor if running
    tmux kill-session -t claude-monitor 2>/dev/null || true
    
    # Kill any orphaned monitoring processes
    printf "${YELLOW}Checking for orphaned monitoring processes...${NC}\n"
    if pgrep -f "multi_monitor" > /dev/null 2>&1; then
        printf "${YELLOW}Found orphaned multi_monitor processes, cleaning up...${NC}\n"
        pkill -f "multi_monitor" || true
        sleep 2
    fi
    
    # Load environment and check required variables
    if [ ! -f .env ]; then
        printf "${RED}Error: .env file not found${NC}\n"
        return 1
    fi
    
    set -a
    source .env
    set +a
    
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        printf "${RED}Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env${NC}\n"
        return 1
    fi
    
    # Start the multi-session monitor in tmux
    printf "${GREEN}Starting Multi-Session Claude Code Monitor...${NC}\n"
    tmux new-session -d -s claude-multi-monitor \
        "cd $(pwd) && uv run python -m claude_ops.telegram.multi_monitor"
    
    # Give tmux a moment to start
    sleep 3
    
    # Check if started successfully
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "${GREEN}✅ Multi-Session Monitor started successfully${NC}\n"
        
        # Also start telegram bot if not already running
        if ! tmux has-session -t telegram-bot 2>/dev/null; then
            printf "${GREEN}Starting Telegram Bot...${NC}\n"
            tmux new-session -d -s telegram-bot \
                "cd $(pwd) && uv run python -m claude_ops.telegram.bot"
            sleep 2
            
            if tmux has-session -t telegram-bot 2>/dev/null; then
                printf "${GREEN}✅ Telegram Bot started successfully${NC}\n"
            else
                printf "${YELLOW}⚠️  Telegram Bot failed to start${NC}\n"
            fi
        else
            printf "${GREEN}✅ Telegram Bot already running${NC}\n"
        fi
        
        printf "\n🎯 Now monitoring ALL Claude sessions simultaneously!\n\n"
        printf "Commands:\n"
        printf "  - View monitor logs: tmux attach -t claude-multi-monitor\n"
        printf "  - View bot logs: tmux attach -t telegram-bot\n"
        printf "  - Stop monitor: tmux kill-session -t claude-multi-monitor\n"
        printf "  - Stop bot: tmux kill-session -t telegram-bot\n\n"
        printf "🚀 The monitor will automatically detect new sessions and send\n"
        printf "   notifications when ANY Claude Code task completes!\n"
        printf "📱 You can now send messages via Telegram bot!\n"
        return 0
    else
        printf "${RED}❌ Failed to start Multi-Session Monitor${NC}\n"
        return 1
    fi
}

# Stop monitoring
stop_monitoring() {
    printf "${YELLOW}🛑 Stopping all monitoring processes...${NC}\n"
    
    # Kill monitoring sessions
    tmux kill-session -t claude-multi-monitor 2>/dev/null && \
        printf "${GREEN}✅ Stopped multi-monitor${NC}\n" || \
        printf "${YELLOW}ℹ️  Multi-monitor not running${NC}\n"
    
    tmux kill-session -t claude-monitor 2>/dev/null && \
        printf "${GREEN}✅ Stopped single monitor${NC}\n" || \
        printf "${YELLOW}ℹ️  Single monitor not running${NC}\n"
    
    # Kill telegram bot session
    tmux kill-session -t telegram-bot 2>/dev/null && \
        printf "${GREEN}✅ Stopped telegram bot${NC}\n" || \
        printf "${YELLOW}ℹ️  Telegram bot not running${NC}\n"
    
    # Kill background processes
    pkill -f "multi_monitor" 2>/dev/null && \
        printf "${GREEN}✅ Killed background processes${NC}\n" || \
        printf "${YELLOW}ℹ️  No background processes found${NC}\n"
    
    printf "${GREEN}🎉 All monitoring stopped${NC}\n"
}

# Show status
show_status() {
    printf "${BLUE}📊 Claude-Ops Status${NC}\n"
    printf "\n"
    
    # Check monitoring sessions
    printf "${YELLOW}Monitoring:${NC}\n"
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "  ✅ Multi-session monitoring: ${GREEN}Running${NC}\n"
    else
        printf "  ❌ Multi-session monitoring: ${RED}Stopped${NC}\n"
    fi
    
    if tmux has-session -t claude-monitor 2>/dev/null; then
        printf "  ⚠️  Single-session monitoring: ${YELLOW}Running (should stop)${NC}\n"
    fi
    
    if tmux has-session -t telegram-bot 2>/dev/null; then
        printf "  📱 Telegram bot: ${GREEN}Running${NC}\n"
    else
        printf "  📱 Telegram bot: ${RED}Stopped${NC}\n"
    fi
    
    # Check Claude sessions
    printf "\n"
    printf "${YELLOW}Claude Sessions:${NC}\n"
    CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1 || true)
    if [ -n "$CLAUDE_SESSIONS" ]; then
        echo "$CLAUDE_SESSIONS" | while read session; do
            printf "  🎯 $session\n"
        done
    else
        printf "  ${YELLOW}No Claude sessions found${NC}\n"
    fi
    
    # Check environment
    printf "\n"
    printf "${YELLOW}Environment:${NC}\n"
    printf "  📁 Claude-Ops Directory: $CLAUDE_OPS_DIR\n"
    
    if [ -f "$CLAUDE_OPS_DIR/.env" ]; then
        printf "  ⚙️  Configuration: ${GREEN}Found${NC}\n"
    else
        printf "  ⚙️  Configuration: ${RED}Missing .env file${NC}\n"
    fi
}

# List sessions
list_sessions() {
    printf "${BLUE}🔄 Active Claude Sessions${NC}\n"
    printf "\n"
    
    CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' || true)
    if [ -n "$CLAUDE_SESSIONS" ]; then
        echo "$CLAUDE_SESSIONS" | while IFS=: read session rest; do
            # Extract directory info if possible
            DIR_INFO=$(tmux display-message -t "$session" -p "#{pane_current_path}" 2>/dev/null || echo "Unknown")
            printf "  🎯 ${GREEN}$session${NC}\n"
            printf "     📁 $DIR_INFO\n"
        done
    else
        printf "${YELLOW}No Claude sessions found${NC}\n"
        printf "\n"
        printf "Create one with: ${BLUE}claude-ops new-project my-project${NC}\n"
    fi
}

# Main command dispatcher
case "${1:-help}" in
    "new-project")
        shift
        new_project "$@"
        ;;
    "kill-session")
        shift
        kill_session "$@"
        ;;
    "start-monitoring")
        start_monitoring
        ;;
    "stop-monitoring")
        stop_monitoring
        ;;
    "status")
        show_status
        ;;
    "sessions")
        list_sessions
        ;;
    "install")
        install_to_path
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    *)
        printf "${RED}Unknown command: $1${NC}\n"
        printf "\n"
        show_help
        exit 1
        ;;
esac