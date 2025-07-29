#!/bin/bash

# Claude tmux 세션 관리 스크립트

CLAUDE_SESSION="claude_session"
CLAUDE_CMD="claude"

# 함수: 세션 존재 확인
session_exists() {
    tmux has-session -t "$CLAUDE_SESSION" 2>/dev/null
}

# 함수: Claude가 실행 중인지 확인
claude_running() {
    if session_exists; then
        # tmux 세션에서 실행 중인 프로세스 확인
        tmux capture-pane -t "$CLAUDE_SESSION" -p | grep -q "claude" || \
        tmux list-panes -t "$CLAUDE_SESSION" -F "#{pane_current_command}" | grep -q "claude"
    else
        return 1
    fi
}

# 함수: Claude 세션 시작
start_claude() {
    if session_exists; then
        echo "✅ tmux 세션이 이미 존재합니다: $CLAUDE_SESSION"
        if claude_running; then
            echo "✅ Claude가 이미 실행 중입니다"
        else
            echo "🚀 Claude를 시작합니다..."
            tmux send-keys -t "$CLAUDE_SESSION" "$CLAUDE_CMD" C-m
        fi
    else
        echo "🆕 새 tmux 세션을 생성하고 Claude를 시작합니다..."
        tmux new-session -d -s "$CLAUDE_SESSION"
        sleep 1
        tmux send-keys -t "$CLAUDE_SESSION" "$CLAUDE_CMD" C-m
    fi
}

# 함수: 상태 확인
status() {
    echo "=== Claude tmux 상태 ==="
    echo "세션 이름: $CLAUDE_SESSION"
    
    if session_exists; then
        echo "tmux 세션: ✅ 활성"
        if claude_running; then
            echo "Claude 상태: ✅ 실행 중"
        else
            echo "Claude 상태: ❌ 비활성"
        fi
        echo ""
        echo "=== 현재 세션 정보 ==="
        tmux list-sessions | grep "$CLAUDE_SESSION"
    else
        echo "tmux 세션: ❌ 없음"
        echo "Claude 상태: ❌ 비활성"
    fi
}

# 함수: 세션 연결
attach() {
    if session_exists; then
        tmux attach-session -t "$CLAUDE_SESSION"
    else
        echo "❌ 세션이 존재하지 않습니다. 먼저 'start' 명령을 사용하세요."
    fi
}

# 함수: 세션 종료
stop() {
    if session_exists; then
        tmux kill-session -t "$CLAUDE_SESSION"
        echo "✅ Claude 세션이 종료되었습니다"
    else
        echo "❌ 종료할 세션이 없습니다"
    fi
}

# 메인 로직
case "$1" in
    "start")
        start_claude
        ;;
    "status")
        status
        ;;
    "attach")
        attach
        ;;
    "stop")
        stop
        ;;
    *)
        echo "사용법: $0 {start|status|attach|stop}"
        echo ""
        echo "명령어:"
        echo "  start  - Claude tmux 세션 시작"
        echo "  status - 현재 상태 확인"  
        echo "  attach - 세션에 연결"
        echo "  stop   - 세션 종료"
        exit 1
        ;;
esac