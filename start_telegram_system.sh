#!/bin/bash

echo "🚀 Claude-Telegram 시스템 시작 중..."

# 기존 프로세스 정리
echo "기존 프로세스 정리..."
pkill -f "python telegram_claude_bridge.py" 2>/dev/null
pkill -f "watch_claude_status.sh" 2>/dev/null

# 텔레그램 브릿지 백그라운드 시작
echo "텔레그램 브릿지 시작..."
unset TELEGRAM_BOT_TOKEN
nohup uv run python telegram_claude_bridge.py > telegram_bridge.log 2>&1 &
BRIDGE_PID=$!

# Claude 상태 모니터링 백그라운드 시작  
echo "Claude 상태 모니터링 시작..."
nohup /home/kyuwon/claude-ops/watch_claude_status.sh > claude_monitor.log 2>&1 &
MONITOR_PID=$!

sleep 2

echo "✅ 시스템 시작 완료!"
echo "   - 텔레그램 브릿지 PID: $BRIDGE_PID"
echo "   - Claude 모니터 PID: $MONITOR_PID"
echo ""
echo "📋 상태 확인:"
echo "   - 텔레그램 브릿지 로그: tail -f telegram_bridge.log"
echo "   - Claude 모니터 로그: tail -f claude_monitor.log"
echo ""
echo "🛑 중지하려면: pkill -f 'telegram_claude_bridge.py|watch_claude_status.sh'"