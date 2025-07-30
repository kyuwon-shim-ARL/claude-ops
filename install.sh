#!/bin/bash

# Claude-Ops Complete Installation Script
# Sets up the entire Notion-Git-Claude-Telegram workflow system

set -e

echo "🤖 Claude-Ops Complete Installation"
echo "===================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if we're in the claude-ops directory
if [ ! -f "CLAUDE.md" ]; then
    print_error "This script must be run from the claude-ops repository root"
    print_info "Please run: git clone <repo-url> && cd claude-ops && ./install.sh"
    exit 1
fi

print_info "Current directory: $(pwd)"
print_info "Installing complete Claude-Ops system..."
echo ""

# Step 1: Check and install system dependencies
echo "📦 Step 1: Checking system dependencies..."

# Check for required tools
MISSING_TOOLS=()

if ! command -v python3 &> /dev/null; then
    MISSING_TOOLS+=("python3")
fi

if ! command -v git &> /dev/null; then
    MISSING_TOOLS+=("git")
fi

if ! command -v tmux &> /dev/null; then
    MISSING_TOOLS+=("tmux")
fi

if ! command -v gh &> /dev/null; then
    print_warning "GitHub CLI (gh) not found - GitHub features will be limited"
    print_info "Install with: https://cli.github.com/"
fi

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    print_error "Missing required tools: ${MISSING_TOOLS[*]}"
    print_info "Please install them first:"
    print_info "  Ubuntu/Debian: sudo apt install python3 git tmux"
    print_info "  macOS: brew install python3 git tmux"
    exit 1
fi

print_status "System dependencies check complete"

# Step 2: Python environment setup
echo ""
echo "🐍 Step 2: Setting up Python environment..."

# Check for uv first, fallback to pip
if command -v uv &> /dev/null; then
    print_info "Using uv for Python package management"
    
    # Install main project dependencies
    print_info "Installing main project dependencies..."
    uv sync
    
    # Install telegram bridge
    print_info "Installing telegram bridge..."
    uv add python-telegram-bot python-dotenv requests
    
    PYTHON_CMD="uv run python"
    print_status "uv environment setup complete"
    
elif command -v pip &> /dev/null; then
    print_info "Using pip for Python package management"
    
    # Install from requirements if available
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    fi
    
    # Install telegram bridge dependencies
    pip install python-telegram-bot python-dotenv requests
    
    PYTHON_CMD="python"
    print_status "pip environment setup complete"
    
else
    print_error "Neither uv nor pip found. Please install Python package manager."
    exit 1
fi

# Step 3: Environment configuration
echo ""
echo "⚙️  Step 3: Environment configuration..."

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    print_info "Creating .env configuration file..."
    
    cat > .env << 'EOF'
# Claude-Ops Complete Configuration
# Copy from .env.example and fill in your actual values

# Telegram Bridge Settings (for monitoring and control)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=123456789,987654321

# Notion Workflow Settings (for task management)  
NOTION_API_KEY=your_notion_api_key_here
NOTION_TASKS_DB_ID=your_tasks_database_id
NOTION_PROJECTS_DB_ID=your_projects_database_id
NOTION_KNOWLEDGE_HUB_ID=your_knowledge_hub_page_id

# GitHub Integration Settings (for PR automation)
GITHUB_PAT=your_github_personal_access_token
GITHUB_REPO_OWNER=your_github_username
GITHUB_REPO_NAME=your_repository_name

# System Settings (optional - defaults are fine)
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3
LOG_LEVEL=INFO

# Quick Setup Instructions:
# 1. Telegram: Message @BotFather to create bot, get token
# 2. Notion: Create integration at https://www.notion.so/my-integrations  
# 3. GitHub: Create PAT at https://github.com/settings/tokens
# 4. Replace all 'your_*_here' values above
# 5. Run: ./start.sh to begin using the system
EOF

    print_status ".env template created"
    print_warning "Please edit .env with your actual credentials before using the system"
    
else
    print_status ".env file already exists"
fi

# Step 4: Create convenient start scripts
echo ""
echo "🚀 Step 4: Creating start scripts..."

# Telegram bridge start script
cat > start-telegram.sh << EOF
#!/bin/bash
# Start Telegram Bridge for Claude monitoring

echo "🤖 Starting Telegram Bridge..."
echo "Press Ctrl+C to stop"
echo ""

if command -v uv &> /dev/null; then
    uv run python -m claude_bridge bot
else
    python -m claude_bridge bot
fi
EOF

chmod +x start-telegram.sh

# Telegram monitor start script  
cat > start-monitor.sh << EOF
#!/bin/bash
# Start Claude Monitor (runs in background)

echo "👁️  Starting Claude Monitor..."

if command -v uv &> /dev/null; then
    uv run python -m claude_bridge monitor &
else
    python -m claude_bridge monitor &
fi

echo "Monitor started in background (PID: \$!)"
echo "Use 'pkill -f claude_bridge.monitor' to stop"
EOF

chmod +x start-monitor.sh

# Complete system start script
cat > start.sh << 'EOF'
#!/bin/bash
# Start complete Claude-Ops system

echo "🚀 Starting Claude-Ops Complete System"
echo "======================================"

# Check .env configuration
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please run ./install.sh first."
    exit 1
fi

# Check if configuration looks filled out
if grep -q "your_.*_here" .env; then
    echo "⚠️  Warning: .env still contains placeholder values"
    echo "Please edit .env with your actual credentials"
    echo ""
    echo "Required for Telegram: TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS"
    echo "Required for Notion: NOTION_API_KEY, NOTION_TASKS_DB_ID"  
    echo "Required for GitHub: GITHUB_PAT, GITHUB_REPO_OWNER, GITHUB_REPO_NAME"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🎯 Available Claude-Ops features:"
echo ""
echo "1. 📱 Telegram Bridge: Real-time monitoring and bot control"
echo "   Usage: ./start-telegram.sh"
echo ""
echo "2. 👁️  Background Monitor: Automatic notifications"  
echo "   Usage: ./start-monitor.sh"
echo ""
echo "3. 📝 Notion Workflows: Task management via slash commands"
echo "   Usage: In Claude Code, use /task-start, /task-finish, etc."
echo ""
echo "4. 🔀 Git Integration: Automated branching and PR creation"
echo "   Usage: Integrated with Notion workflows"
echo ""

# Default: start telegram bridge
echo "Starting Telegram Bridge by default..."
echo "Press Ctrl+C to stop, or use other scripts for different features"
echo ""

./start-telegram.sh
EOF

chmod +x start.sh

print_status "Start scripts created"

# Step 5: Verification
echo ""
echo "🧪 Step 5: Installation verification..."

# Test Python imports
print_info "Testing Python imports..."

$PYTHON_CMD -c "
import sys
sys.path.insert(0, '.')

try:
    # Test telegram bridge
    from claude_bridge.config import BridgeConfig
    print('✅ Telegram bridge: OK')
    
    # Test core dependencies
    import telegram, dotenv, requests
    print('✅ Dependencies: OK')
    
    print('✅ All imports successful')
except Exception as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
" && print_status "Python environment verification passed" || {
    print_error "Python environment verification failed"
    exit 1
}

# Final success message
echo ""
echo "🎉 Claude-Ops installation completed successfully!"
echo ""
print_info "📋 Next steps:"
echo "  1. Edit .env with your actual credentials"
echo "  2. Run ./start.sh to begin using the system"
echo "  3. Use Claude Code slash commands: /task-start, /task-finish, etc."  
echo "  4. Access Telegram bot for real-time monitoring"
echo ""
print_info "📖 Documentation:"
echo "  • CLAUDE.md - Complete usage guide"
echo "  • README.md - System overview"
echo "  • ./start.sh - Quick start"
echo ""
print_info "🎯 Quick test:"
echo "  ./start-telegram.sh  # Test Telegram bridge"
echo "  $PYTHON_CMD -c 'from claude_bridge import BridgeConfig; print(\"Works!\")'"
echo ""
echo "Happy coding! 🚀"
EOF

chmod +x install.sh