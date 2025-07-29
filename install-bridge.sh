#!/bin/bash

# Claude-Telegram Bridge Installation Script
# This script sets up the bridge in any repository

set -e

echo "🤖 Claude-Telegram Bridge Installation"
echo "======================================"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "⚠️  Warning: Not in a git repository. Creating .env in current directory."
fi

# Get current directory for session naming
CURRENT_DIR=$(basename "$(pwd)")
echo "📁 Current directory: $CURRENT_DIR"

# Check if .env already exists
if [ -f ".env" ]; then
    echo "✅ .env file already exists"
    echo "🔍 Checking required variables..."
    
    # Check required variables
    missing_vars=()
    
    if ! grep -q "^TELEGRAM_BOT_TOKEN=" .env || [ -z "$(grep "^TELEGRAM_BOT_TOKEN=" .env | cut -d'=' -f2)" ]; then
        missing_vars+=("TELEGRAM_BOT_TOKEN")
    fi
    
    if ! grep -q "^ALLOWED_USER_IDS=" .env || [ -z "$(grep "^ALLOWED_USER_IDS=" .env | cut -d'=' -f2)" ]; then
        missing_vars+=("ALLOWED_USER_IDS")
    fi
    
    if [ ${#missing_vars[@]} -eq 0 ]; then
        echo "✅ All required variables are set"
    else
        echo "❌ Missing required variables: ${missing_vars[*]}"
        echo "Please add them to your .env file:"
        for var in "${missing_vars[@]}"; do
            echo "  $var=your_value_here"
        done
        exit 1
    fi
else
    echo "📝 Creating .env file..."
    
    # Create .env from template
    cat > .env << 'EOF'
# Claude-Telegram Bridge Configuration

# Telegram Bot Settings (Required)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=123456789,987654321

# Session Settings (Optional)
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3

# Logging (Optional)  
LOG_LEVEL=INFO

# Example:
# TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
# TELEGRAM_CHAT_ID=123456789
# ALLOWED_USER_IDS=985052105
EOF

    echo "📝 .env file created!"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env and set the following variables:"
    echo "   - TELEGRAM_BOT_TOKEN: Your Telegram bot token"
    echo "   - TELEGRAM_CHAT_ID: Your Telegram chat ID (for notifications)"  
    echo "   - ALLOWED_USER_IDS: Comma-separated list of allowed user IDs"
    echo ""
    echo "💡 To get your chat ID, message your bot and check: https://api.telegram.org/bot<TOKEN>/getUpdates"
    echo ""
    read -p "Press Enter after configuring .env file..."
fi

# Check Python dependencies
echo "🐍 Checking Python dependencies..."

# Check if python-telegram-bot is installed
if ! python -c "import telegram" 2>/dev/null; then
    echo "📦 Installing Python dependencies..."
    if [ -f "claude_bridge/requirements.txt" ]; then
        uv add -r claude_bridge/requirements.txt
    else
        pip install python-telegram-bot python-dotenv requests
    fi
else
    echo "✅ Python dependencies already installed"
fi

# Check if claude_bridge directory exists
if [ ! -d "claude_bridge" ]; then
    echo "❌ claude_bridge directory not found!"
    echo "💡 This script should be run from the repository root where claude_bridge/ exists."
    exit 1
fi

echo "✅ claude_bridge module found"

# Create a simple start script
echo "📄 Creating start-bridge.sh script..."

cat > start-bridge.sh << 'EOF'
#!/bin/bash

# Start Claude-Telegram Bridge
# Usage: ./start-bridge.sh [bot|monitor|both]

MODE=${1:-both}

# Add current directory to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

case "$MODE" in
  "bot")
    echo "🤖 Starting Telegram Bot..."
    uv run python -m claude_bridge bot
    ;;
  "monitor")  
    echo "👁️  Starting Claude Monitor..."
    uv run python -m claude_bridge monitor
    ;;
  "both")
    echo "🚀 Starting both Bot and Monitor in background..."
    
    # Start monitor in background
    uv run python -m claude_bridge monitor &
    MONITOR_PID=$!
    echo "👁️  Monitor started (PID: $MONITOR_PID)"
    
    # Start bot in foreground
    echo "🤖 Starting Telegram Bot..."
    uv run python -m claude_bridge bot
    
    # Clean up monitor when bot exits
    kill $MONITOR_PID 2>/dev/null || true
    ;;
  *)
    echo "Usage: $0 [bot|monitor|both]"
    echo "  bot     - Start only Telegram bot"
    echo "  monitor - Start only Claude monitor"  
    echo "  both    - Start both (default)"
    exit 1
    ;;
esac
EOF

chmod +x start-bridge.sh

echo "✅ start-bridge.sh created and made executable"

# Test configuration
echo "🧪 Testing configuration..."

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
if uv run python -c "
try:
    from claude_bridge.config import BridgeConfig
    config = BridgeConfig()
    print('✅ Configuration loaded successfully')
    print(f'📁 Working directory: {config.working_directory}')
    print(f'🎯 Session name: {config.session_name}')
    print(f'👥 Allowed users: {len(config.allowed_user_ids)} configured')
except Exception as e:
    print(f'❌ Configuration error: {e}')
    exit(1)
"; then
    echo "✅ Configuration test passed"
else
    echo "❌ Configuration test failed. Please check your .env file."
    exit 1
fi

echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Make sure your .env file has correct values"
echo "2. Start the bridge: ./start-bridge.sh"
echo ""
echo "🎯 Current session will be: claude_${CURRENT_DIR}"
echo "📱 Bot commands: /start, /status, /log, /stop, /help"
echo ""
echo "💡 Usage:"
echo "  ./start-bridge.sh both    # Start bot + monitor (recommended)"
echo "  ./start-bridge.sh bot     # Start only bot"
echo "  ./start-bridge.sh monitor # Start only monitor"