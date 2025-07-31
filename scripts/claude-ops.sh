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
    echo -e "${BLUE}🚀 Claude-Ops CLI${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC}"
    echo "  claude-ops <command> [args...]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  ${GREEN}new-project${NC} <name> [path]     Create new Claude project session"
    echo "  ${GREEN}start-monitoring${NC}             Start multi-session monitoring"
    echo "  ${GREEN}stop-monitoring${NC}              Stop all monitoring processes"
    echo "  ${GREEN}status${NC}                       Show system status"
    echo "  ${GREEN}sessions${NC}                     List all Claude sessions"
    echo "  ${GREEN}help${NC}                         Show this help message"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  claude-ops new-project my-ai-app"
    echo "  claude-ops new-project web-scraper ~/work/client"
    echo "  claude-ops start-monitoring"
    echo "  claude-ops status"
    echo ""
    echo -e "${BLUE}💡 Tip:${NC} Add to PATH with: claude-ops install"
}

# Install to PATH
install_to_path() {
    echo -e "${BLUE}🔧 Installing claude-ops to PATH...${NC}"
    
    # Add to ~/.bashrc
    BASHRC_ENTRY="# Claude-Ops CLI
export PATH=\"$SCRIPT_DIR:\$PATH\"
alias claude-ops='$SCRIPT_DIR/claude-ops.sh'"
    
    if ! grep -q "Claude-Ops CLI" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "$BASHRC_ENTRY" >> ~/.bashrc
        echo -e "${GREEN}✅ Added to ~/.bashrc${NC}"
    else
        echo -e "${YELLOW}⚠️  Already installed in ~/.bashrc${NC}"
    fi
    
    # Create symlink in /usr/local/bin if possible (optional)
    if [ -w "/usr/local/bin" ] 2>/dev/null; then
        ln -sf "$SCRIPT_DIR/claude-ops.sh" "/usr/local/bin/claude-ops" 2>/dev/null && \
        echo -e "${GREEN}✅ Created symlink in /usr/local/bin${NC}" || \
        echo -e "${YELLOW}⚠️  Could not create symlink in /usr/local/bin${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}🎉 Installation complete!${NC}"
    echo -e "Run: ${YELLOW}source ~/.bashrc${NC} or restart your terminal"
    echo -e "Then try: ${YELLOW}claude-ops help${NC}"
}

# Create new project
new_project() {
    if [ $# -eq 0 ]; then
        echo -e "${RED}Error: Project name required${NC}"
        echo "Usage: claude-ops new-project <name> [path]"
        exit 1
    fi
    
    "$SCRIPT_DIR/new-project.sh" "$@"
}

# Start monitoring
start_monitoring() {
    cd "$CLAUDE_OPS_DIR"
    ./scripts/start_multi_monitoring.sh
}

# Stop monitoring
stop_monitoring() {
    echo -e "${YELLOW}🛑 Stopping all monitoring processes...${NC}"
    
    # Kill monitoring sessions
    tmux kill-session -t claude-multi-monitor 2>/dev/null && \
        echo -e "${GREEN}✅ Stopped multi-monitor${NC}" || \
        echo -e "${YELLOW}ℹ️  Multi-monitor not running${NC}"
    
    tmux kill-session -t claude-monitor 2>/dev/null && \
        echo -e "${GREEN}✅ Stopped single monitor${NC}" || \
        echo -e "${YELLOW}ℹ️  Single monitor not running${NC}"
    
    # Kill background processes
    pkill -f "multi_monitor" 2>/dev/null && \
        echo -e "${GREEN}✅ Killed background processes${NC}" || \
        echo -e "${YELLOW}ℹ️  No background processes found${NC}"
    
    echo -e "${GREEN}🎉 All monitoring stopped${NC}"
}

# Show status
show_status() {
    echo -e "${BLUE}📊 Claude-Ops Status${NC}"
    echo ""
    
    # Check monitoring sessions
    echo -e "${YELLOW}Monitoring:${NC}"
    if tmux has-session -t claude-multi-monitor 2>/dev/null; then
        echo -e "  ✅ Multi-session monitoring: ${GREEN}Running${NC}"
    else
        echo -e "  ❌ Multi-session monitoring: ${RED}Stopped${NC}"
    fi
    
    if tmux has-session -t claude-monitor 2>/dev/null; then
        echo -e "  ⚠️  Single-session monitoring: ${YELLOW}Running (should stop)${NC}"
    fi
    
    # Check Claude sessions
    echo ""
    echo -e "${YELLOW}Claude Sessions:${NC}"
    CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' | cut -d: -f1 || true)
    if [ -n "$CLAUDE_SESSIONS" ]; then
        echo "$CLAUDE_SESSIONS" | while read session; do
            echo -e "  🎯 $session"
        done
    else
        echo -e "  ${YELLOW}No Claude sessions found${NC}"
    fi
    
    # Check environment
    echo ""
    echo -e "${YELLOW}Environment:${NC}"
    echo -e "  📁 Claude-Ops Directory: $CLAUDE_OPS_DIR"
    
    if [ -f "$CLAUDE_OPS_DIR/.env" ]; then
        echo -e "  ⚙️  Configuration: ${GREEN}Found${NC}"
    else
        echo -e "  ⚙️  Configuration: ${RED}Missing .env file${NC}"
    fi
}

# List sessions
list_sessions() {
    echo -e "${BLUE}🔄 Active Claude Sessions${NC}"
    echo ""
    
    CLAUDE_SESSIONS=$(tmux list-sessions 2>/dev/null | grep '^claude' || true)
    if [ -n "$CLAUDE_SESSIONS" ]; then
        echo "$CLAUDE_SESSIONS" | while IFS=: read session rest; do
            # Extract directory info if possible
            DIR_INFO=$(tmux display-message -t "$session" -p "#{pane_current_path}" 2>/dev/null || echo "Unknown")
            echo -e "  🎯 ${GREEN}$session${NC}"
            echo -e "     📁 $DIR_INFO"
        done
    else
        echo -e "${YELLOW}No Claude sessions found${NC}"
        echo ""
        echo -e "Create one with: ${BLUE}claude-ops new-project my-project${NC}"
    fi
}

# Main command dispatcher
case "${1:-help}" in
    "new-project")
        shift
        new_project "$@"
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
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac