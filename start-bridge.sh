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
