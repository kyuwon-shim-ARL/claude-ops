#!/bin/bash

# Completion Monitor - 주기적으로 Claude 세션 상태를 모니터링하여 작업 완료 알림
# Version: 1.0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_OPS_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$CLAUDE_OPS_DIR/completion-monitor.log"
LAST_STATE_FILE="$CLAUDE_OPS_DIR/.last_session_states"

# 로깅 함수
log() {
    echo "$(date): $1" >> "$LOG_FILE"
}

# 환경 변수 로드
if [ -f "$CLAUDE_OPS_DIR/.env" ]; then
    set -a
    source "$CLAUDE_OPS_DIR/.env"
    set +a
fi

log "Completion monitor started"

# 세션 상태 확인 함수
check_session_completion() {
    local session_name="$1"
    
    # tmux에서 해당 세션의 현재 내용 캡처
    local current_content
    current_content=$(tmux capture-pane -t "$session_name" -p 2>/dev/null | tail -5)
    
    # 작업 완료를 나타내는 패턴들
    if echo "$current_content" | grep -qE "(✅|🎉|완료|finished|complete|done|success)" && \
       echo "$current_content" | grep -qE "(\>|❯|$|#)" ; then
        echo "completed"
    elif echo "$current_content" | grep -qE "(running|processing|working|진행)" ; then
        echo "working"
    else
        echo "idle"
    fi
}

# 메인 모니터링 루프
monitor_sessions() {
    # 현재 Claude 세션들 찾기
    local claude_sessions
    claude_sessions=$(tmux list-sessions 2>/dev/null | grep "^claude_" | cut -d: -f1)
    
    if [ -z "$claude_sessions" ]; then
        log "No Claude sessions found"
        return
    fi
    
    # 이전 상태 파일 읽기 (없으면 생성)
    if [ ! -f "$LAST_STATE_FILE" ]; then
        touch "$LAST_STATE_FILE"
    fi
    
    for session in $claude_sessions; do
        current_state=$(check_session_completion "$session")
        last_state=$(grep "^$session:" "$LAST_STATE_FILE" 2>/dev/null | cut -d: -f2 || echo "unknown")
        
        log "Session $session: $last_state -> $current_state"
        
        # 작업 중에서 완료로 상태 변경된 경우 알림 전송
        if [ "$last_state" = "working" ] && [ "$current_state" = "completed" ]; then
            log "🎉 Work completion detected for $session - sending notification"
            
            # 알림 전송
            cd "$CLAUDE_OPS_DIR"
            CLAUDE_SESSION_NAME="$session" python3 -c "
from claude_ops.telegram.notifier import SmartNotifier
from claude_ops.config import ClaudeOpsConfig
try:
    config = ClaudeOpsConfig()
    notifier = SmartNotifier(config)
    success = notifier.send_work_completion_notification()
    print(f'Notification sent for {config.session_name}: {success}')
except Exception as e:
    print(f'Notification error: {e}')
" >> "$LOG_FILE" 2>&1
        fi
        
        # 상태 업데이트
        grep -v "^$session:" "$LAST_STATE_FILE" > "$LAST_STATE_FILE.tmp" 2>/dev/null || touch "$LAST_STATE_FILE.tmp"
        echo "$session:$current_state" >> "$LAST_STATE_FILE.tmp"
        mv "$LAST_STATE_FILE.tmp" "$LAST_STATE_FILE"
    done
}

# 시그널 핸들러
cleanup() {
    log "Completion monitor stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# 메인 실행
log "Starting session monitoring loop (check every 10 seconds)"

while true; do
    monitor_sessions
    sleep 10
done