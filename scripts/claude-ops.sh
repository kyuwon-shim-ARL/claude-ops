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
    printf "${BLUE}🌉 Claude-Telegram-Bridge CLI${NC}\n"
    printf "\n"
    printf "${YELLOW}Usage:${NC}\n"
    printf "  ctb <command> [args...]${NC}\n"
    printf "\n"
    printf "${YELLOW}Commands:${NC}\n"
    printf "  ${GREEN}new-project${NC} <name> [path]     Create new Claude project session\n"
    printf "  ${GREEN}connect${NC} <path>               Connect to existing project directory\n"
    printf "  ${GREEN}kill-session${NC} <name>          Kill specific Claude session\n"
    printf "  ${GREEN}start-monitoring${NC}             Start multi-session monitoring\n"
    printf "  ${GREEN}stop-monitoring${NC}              Stop all monitoring processes\n"
    printf "  ${GREEN}restart-all${NC}                  Restart all monitoring services\n"
    printf "  ${GREEN}restart${NC}                      Alias for restart-all\n"
    printf "  ${GREEN}status${NC}                       Show system status\n"
    printf "  ${GREEN}sessions${NC}                     List all Claude sessions\n"
    printf "  ${GREEN}help${NC}                         Show this help message\n"
    printf "\n"
    printf "${YELLOW}Examples:${NC}\n"
    printf "  ctb new-project my-ai-app\n"
    printf "  ctb connect ~/projects/my-existing-app\n"
    printf "  ctb new-project web-scraper ~/work/client\n"
    printf "  ctb kill-session claude_my-ai-app\n"
    printf "  ctb start-monitoring\n"
    printf "  ctb status\n"
    printf "\n"
    printf "${BLUE}💡 Tip:${NC} Add to PATH with: ctb install\n"
}

# Install to PATH
install_to_path() {
    printf "${BLUE}🔧 Installing claude-telegram-bridge CLI to PATH...${NC}\n"

    # Remove old claude-ops entry if exists
    if grep -q "# Claude-Ops CLI" ~/.bashrc 2>/dev/null; then
        printf "${YELLOW}⚠️  Removing old claude-ops entry...${NC}\n"
        sed -i '/# Claude-Ops CLI/,+2d' ~/.bashrc
    fi

    # Add to ~/.bashrc
    BASHRC_ENTRY="# Claude-Telegram-Bridge CLI
export PATH=\"$SCRIPT_DIR:\$PATH\"
alias ctb='$SCRIPT_DIR/ctb'
alias claude-bridge='$SCRIPT_DIR/claude-bridge'
alias claude-telegram-bridge='$SCRIPT_DIR/claude-telegram-bridge'"

    if ! grep -q "# Claude-Telegram-Bridge CLI" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "$BASHRC_ENTRY" >> ~/.bashrc
        printf "${GREEN}✅ Added to ~/.bashrc${NC}\n"
    else
        printf "${YELLOW}⚠️  Already installed in ~/.bashrc${NC}\n"
    fi

    # Create symlinks in /usr/local/bin if possible (optional)
    if [ -w "/usr/local/bin" ] 2>/dev/null; then
        ln -sf "$SCRIPT_DIR/ctb" "/usr/local/bin/ctb" 2>/dev/null && \
        printf "${GREEN}✅ Created symlink: /usr/local/bin/ctb${NC}\n" || true

        ln -sf "$SCRIPT_DIR/claude-bridge" "/usr/local/bin/claude-bridge" 2>/dev/null && \
        printf "${GREEN}✅ Created symlink: /usr/local/bin/claude-bridge${NC}\n" || true

        ln -sf "$SCRIPT_DIR/claude-telegram-bridge" "/usr/local/bin/claude-telegram-bridge" 2>/dev/null && \
        printf "${GREEN}✅ Created symlink: /usr/local/bin/claude-telegram-bridge${NC}\n" || true

        # Remove old claude-ops symlink if exists
        if [ -L "/usr/local/bin/claude-ops" ]; then
            rm -f "/usr/local/bin/claude-ops" 2>/dev/null && \
            printf "${YELLOW}🗑️  Removed old symlink: /usr/local/bin/claude-ops${NC}\n" || true
        fi
    fi

    printf "\n"
    printf "${GREEN}🎉 Installation complete!${NC}\n"
    printf "Run: ${YELLOW}source ~/.bashrc${NC} or restart your terminal\n"
    printf "\n"
    printf "${YELLOW}Available commands:${NC}\n"
    printf "  ${GREEN}ctb${NC}                      - Short alias (recommended)\n"
    printf "  ${GREEN}claude-bridge${NC}            - Medium length\n"
    printf "  ${GREEN}claude-telegram-bridge${NC}   - Full name\n"
    printf "\n"
    printf "Try: ${YELLOW}ctb help${NC}\n"
}

# Create new project
new_project() {
    if [ $# -eq 0 ]; then
        printf "${RED}Error: Project name required${NC}\n"
        printf "Usage: ctb new-project <name> [path]\n"
        exit 1
    fi

    "$SCRIPT_DIR/new-project.sh" "$@"
}

# Connect to existing project
connect_project() {
    if [ $# -eq 0 ]; then
        printf "${RED}Error: Project path required${NC}\n"
        printf "Usage: ctb connect <project-path>\n"
        printf "\n"
        printf "Examples:\n"
        printf "  ctb connect ~/projects/my-app\n"
        printf "  ctb connect /home/user/work/client-project\n"
        exit 1
    fi

    PROJECT_PATH="$1"

    # Expand ~ to home directory
    PROJECT_PATH="${PROJECT_PATH/#\~/$HOME}"

    # Check if directory exists
    if [ ! -d "$PROJECT_PATH" ]; then
        printf "${RED}❌ Directory not found: $PROJECT_PATH${NC}\n"
        exit 1
    fi

    printf "${BLUE}🔄 Connecting to project: $PROJECT_PATH${NC}\n"

    # Use Python to connect via SessionManager
    cd "$CLAUDE_OPS_DIR"

    uv run python -c "
import sys
sys.path.insert(0, '.')
from claude_ctb.session_manager import session_manager

project_path = '$PROJECT_PATH'
result = session_manager.connect_to_project(project_path)

if result['status'] == 'error':
    print(f\"❌ Error: {result['error']}\")
    exit(1)
elif result['status'] == 'switched':
    print(f\"✅ Switched to existing session\")
    print(f\"🎯 Session: {result['session_name']}\")
    print(f\"📁 Path: {result['project_path']}\")
    print('')
    print('💡 This project already has an active session.')
    exit(0)
elif result['status'] == 'created':
    print(f\"✅ Created new session\")
    print(f\"🎯 Session: {result['session_name']}\")
    print(f\"📁 Path: {result['project_path']}\")
    print('')
    print('${GREEN}Next steps:${NC}')
    print(f\"  1. Connect: ${YELLOW}tmux attach -t {result['session_name']}${NC}\")
    print(f\"  2. Or use Telegram: ${YELLOW}/sessions${NC} to switch to this session\")
    print('')
    print('${GREEN}🎉 Session ready!${NC}')
    exit(0)
"
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
        "cd $(pwd) && uv run python -m claude_ctb.monitoring.multi_monitor"
    
    # Give tmux a moment to start
    sleep 3
    
    # Check if started successfully
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        printf "${GREEN}✅ Multi-Session Monitor started successfully${NC}\n"
        
        # Also start telegram bot if not already running
        if ! tmux has-session -t telegram-bot 2>/dev/null; then
            # 기존 telegram bot 프로세스 강제 정리
            if pgrep -f "telegram.*bot" > /dev/null 2>&1; then
                printf "${YELLOW}Found existing telegram bot processes, cleaning up...${NC}\n"
                pkill -f "telegram.*bot" || true
                sleep 3
            fi
            
            printf "${GREEN}Starting Telegram Bot...${NC}\n"
            tmux new-session -d -s telegram-bot \
                "cd $(pwd) && uv run python -m claude_ctb.telegram.bot"
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
    
    # Kill background processes (강화된 프로세스 정리)
    pkill -f "multi_monitor" 2>/dev/null && \
        printf "${GREEN}✅ Killed background processes${NC}\n" || \
        printf "${YELLOW}ℹ️  No background processes found${NC}\n"
    
    # Force kill telegram bot processes
    pkill -f "telegram.*bot" 2>/dev/null && \
        printf "${GREEN}✅ Force killed telegram bot processes${NC}\n" || \
        printf "${YELLOW}ℹ️  No telegram bot processes found${NC}\n"
    
    # Wait for processes to fully terminate
    sleep 2
    
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
    "connect")
        shift
        connect_project "$@"
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
    "restart-all"|"restart")
        stop_monitoring
        sleep 2
        start_monitoring
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