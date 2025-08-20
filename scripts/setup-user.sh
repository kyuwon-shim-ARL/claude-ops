#!/bin/bash

# Claude-Ops User Setup Script
# Automated onboarding for new team members

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════╗"
echo "║           Claude-Ops User Setup Script           ║"
echo "║                  Version 2.0.0                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Function to print colored messages
print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_step "Checking prerequisites..."
    
    local missing_deps=()
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        print_success "Python $(python3 --version 2>&1) found"
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
    else
        print_success "Git $(git --version | cut -d' ' -f3) found"
    fi
    
    # Check tmux
    if ! command -v tmux &> /dev/null; then
        missing_deps+=("tmux")
    else
        print_success "tmux $(tmux -V | cut -d' ' -f2) found"
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    else
        print_success "curl found"
    fi
    
    # Report missing dependencies
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        print_info "Please install missing dependencies and run again"
        exit 1
    fi
    
    print_success "All prerequisites met!"
    echo
}

# Install uv if needed
install_uv() {
    if command -v uv &> /dev/null; then
        print_success "uv $(uv --version | cut -d' ' -f2) already installed"
        return
    fi
    
    print_step "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        print_success "uv installed successfully"
    else
        print_error "Failed to install uv"
        exit 1
    fi
    echo
}

# Setup Python environment
setup_python_env() {
    print_step "Setting up Python environment..."
    
    if [ -f "pyproject.toml" ]; then
        uv sync
        print_success "Python dependencies installed"
    else
        print_error "pyproject.toml not found. Are you in the claude-ops directory?"
        exit 1
    fi
    echo
}

# Interactive .env configuration
configure_env() {
    print_step "Configuring environment variables..."
    
    # Check if .env already exists
    if [ -f ".env" ]; then
        print_warning ".env file already exists"
        read -p "Do you want to reconfigure it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env configuration"
            return
        fi
        # Backup existing .env
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        print_info "Existing .env backed up"
    fi
    
    # Copy template
    cp .env.example .env
    print_info "Created .env from template"
    
    # Interactive configuration
    echo
    print_info "Let's configure your Telegram bot"
    print_info "You'll need to create a bot first using @BotFather on Telegram"
    echo
    
    # Bot Token
    read -p "Enter your Telegram Bot Token: " bot_token
    if [ -n "$bot_token" ]; then
        sed -i.bak "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$bot_token/" .env
        
        # Test bot token
        print_info "Testing bot token..."
        response=$(curl -s "https://api.telegram.org/bot$bot_token/getMe")
        if echo "$response" | grep -q '"ok":true'; then
            bot_username=$(echo "$response" | grep -oP '"username":"\K[^"]+')
            print_success "Bot verified: @$bot_username"
        else
            print_warning "Could not verify bot token. Please check it's correct."
        fi
    fi
    
    # Get chat updates to help find IDs
    print_info "Please send a message to your bot now, then press Enter"
    read -p "Press Enter after sending a message to your bot..."
    
    if [ -n "$bot_token" ]; then
        updates=$(curl -s "https://api.telegram.org/bot$bot_token/getUpdates")
        
        # Try to extract user ID and chat ID
        user_id=$(echo "$updates" | grep -oP '"from":\s*\{[^}]*"id":\s*\K\d+' | head -1)
        chat_id=$(echo "$updates" | grep -oP '"chat":\s*\{[^}]*"id":\s*\K-?\d+' | head -1)
        
        if [ -n "$user_id" ] && [ -n "$chat_id" ]; then
            print_success "Found IDs from your message:"
            print_info "  User ID: $user_id"
            print_info "  Chat ID: $chat_id"
            
            read -p "Use these IDs? (Y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                sed -i.bak "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$chat_id/" .env
                sed -i.bak "s/ALLOWED_USER_IDS=.*/ALLOWED_USER_IDS=$user_id/" .env
                print_success "IDs configured automatically"
            else
                # Manual entry
                read -p "Enter your Telegram Chat ID: " chat_id
                read -p "Enter your Telegram User ID: " user_id
                sed -i.bak "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$chat_id/" .env
                sed -i.bak "s/ALLOWED_USER_IDS=.*/ALLOWED_USER_IDS=$user_id/" .env
            fi
        else
            print_warning "Could not auto-detect IDs. Please enter manually:"
            read -p "Enter your Telegram Chat ID: " chat_id
            read -p "Enter your Telegram User ID: " user_id
            sed -i.bak "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$chat_id/" .env
            sed -i.bak "s/ALLOWED_USER_IDS=.*/ALLOWED_USER_IDS=$user_id/" .env
        fi
    fi
    
    # Optional: Working directory
    echo
    read -p "Set custom working directory? (default: current directory) (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter working directory path: " work_dir
        if [ -d "$work_dir" ]; then
            sed -i.bak "s|# CLAUDE_WORKING_DIR=.*|CLAUDE_WORKING_DIR=$work_dir|" .env
            print_success "Working directory set to: $work_dir"
        else
            print_warning "Directory doesn't exist. Skipping."
        fi
    fi
    
    # Clean up backup files
    rm -f .env.bak
    
    print_success "Environment configuration complete!"
    echo
}

# Setup Claude Code hooks
setup_hooks() {
    print_step "Setting up Claude Code hooks..."
    
    if [ -f "scripts/setup-hooks.sh" ]; then
        bash scripts/setup-hooks.sh
        print_success "Claude Code hooks configured"
    else
        # Fallback to Python module
        uv run python -m claude_ops.hook_manager setup
        print_success "Claude Code hooks configured via Python"
    fi
    echo
}

# Test bot connection
test_bot() {
    print_step "Testing bot connection..."
    
    # Start bot in test mode
    print_info "Starting bot for testing (will run for 10 seconds)..."
    timeout 10 uv run python -m claude_ops.telegram.bot 2>&1 | head -20 &
    
    sleep 5
    
    print_info "Bot test completed"
    print_info "Please check your Telegram and send /help to verify bot is working"
    echo
}

# Create first project (optional)
create_test_project() {
    read -p "Would you like to create a test project? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter project name (default: test-app): " project_name
        project_name=${project_name:-test-app}
        
        print_step "Creating test project: $project_name"
        uv run python -m claude_ops.project_creator "$project_name"
        
        print_success "Test project created!"
        print_info "Session name: claude_$project_name"
        print_info "Use 'tmux attach -t claude_$project_name' to join the session"
    fi
    echo
}

# Generate startup script
create_startup_script() {
    print_step "Creating startup script..."
    
    cat > start-claude-ops.sh << 'EOF'
#!/bin/bash
# Claude-Ops Startup Script

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Starting Claude-Ops...${NC}"

# Check if already running
if pgrep -f "claude_ops.telegram.bot" > /dev/null; then
    echo -e "${GREEN}Claude-Ops bot is already running${NC}"
else
    # Start in tmux session
    tmux new -d -s claude-ops-bot 'uv run python -m claude_ops.telegram.bot'
    echo -e "${GREEN}Claude-Ops bot started in tmux session 'claude-ops-bot'${NC}"
fi

echo "Use 'tmux attach -t claude-ops-bot' to view bot logs"
EOF

    chmod +x start-claude-ops.sh
    print_success "Created start-claude-ops.sh startup script"
    echo
}

# Main setup flow
main() {
    echo "Welcome to Claude-Ops user setup!"
    echo "This script will help you configure your personal instance."
    echo
    
    # Verify we're in the right directory
    if [ ! -f "pyproject.toml" ] || [ ! -d "claude_ops" ]; then
        print_error "This script must be run from the claude-ops directory"
        print_info "Please cd to claude-ops directory and run again"
        exit 1
    fi
    
    # Run setup steps
    check_prerequisites
    install_uv
    setup_python_env
    configure_env
    setup_hooks
    create_startup_script
    
    # Optional steps
    test_bot
    create_test_project
    
    # Final summary
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║            Setup Complete! 🎉                   ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo "Next steps:"
    echo "1. Start the bot: ./start-claude-ops.sh"
    echo "2. Open Telegram and message your bot"
    echo "3. Send /help to see available commands"
    echo "4. Create projects with /new-project <name>"
    echo
    echo "For more information, see:"
    echo "  - MULTI_USER_GUIDE.md for team deployment"
    echo "  - CLAUDE.md for detailed documentation"
    echo "  - README.md for quick reference"
    echo
    print_success "Happy coding with Claude-Ops! 🚀"
}

# Run main function
main "$@"