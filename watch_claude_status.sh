#!/bin/bash

# Claude 상태를 모니터링하여 자동으로 알림을 보내는 스크립트
# 간소화된 로직: Claude 작업 완료 시에만 알림 (중복 제거)

TMUX_SESSION="${TMUX_SESSION:-claude_session}"
WORK_STATUS_FILE="/tmp/claude_work_status"
CHECK_INTERVAL=3  # 3초마다 체크

echo "Claude 상태 모니터링 시작 (작업 완료 감지 모드)..."
echo "tmux 세션: $TMUX_SESSION"
echo "체크 간격: ${CHECK_INTERVAL}초"

# 초기 상태 확인
echo "idle" > "$WORK_STATUS_FILE"

while true; do
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        FULL_TMUX_OUTPUT=$(tmux capture-pane -t "$TMUX_SESSION" -p)
        BOTTOM_LINES=$(echo "$FULL_TMUX_OUTPUT" | tail -n 5)
        
        # 현재 상태 판단
        CURRENT_STATE=""
        
        # 1. Claude 작업 중인지 확인 (esc to interrupt 감지)
        if echo "$FULL_TMUX_OUTPUT" | grep -q "esc to interrupt"; then
            CURRENT_STATE="working"
        # 2. 사용자 타이핑 중인지 확인 (입력창에 텍스트 있음)
        elif echo "$BOTTOM_LINES" | grep -q "╭.*╮" && \
             echo "$BOTTOM_LINES" | grep -q "│ > [^ ]" && \
             echo "$BOTTOM_LINES" | grep -q "auto-accept"; then
            CURRENT_STATE="typing"
        # 3. Claude 응답 중인지 확인 (bullet point 감지)
        elif echo "$BOTTOM_LINES" | grep -q "●"; then
            CURRENT_STATE="responding"
        else
            CURRENT_STATE="idle"
        fi
        
        # 이전 상태 읽기
        PREV_STATE=$([ -f "$WORK_STATUS_FILE" ] && cat "$WORK_STATUS_FILE" || echo "idle")
        
        # 상태 변화 감지 및 알림 로직
        if [ "$PREV_STATE" = "working" ] && [ "$CURRENT_STATE" = "idle" ]; then
            # Claude 작업 완료 → 대기 상태로 변경됨
            echo "$(date): ✅ Claude 작업 완료 감지 - 알림 전송"
            /home/kyuwon/claude-ops/send_smart_notification.sh "Claude 작업 완료"
        elif [ "$PREV_STATE" = "responding" ] && [ "$CURRENT_STATE" = "idle" ]; then
            # Claude 응답 완료 → 대기 상태로 변경됨  
            echo "$(date): 💬 Claude 응답 완료 감지 - 알림 전송"
            /home/kyuwon/claude-ops/send_smart_notification.sh "Claude 응답 완료"
        fi
        
        # 현재 상태를 파일에 저장 (중복 알림 방지)
        echo "$CURRENT_STATE" > "$WORK_STATUS_FILE"
        
        # 디버그 출력 (상태 변화가 있을 때만)
        if [ "$PREV_STATE" != "$CURRENT_STATE" ]; then
            echo "$(date): 상태 변화: $PREV_STATE → $CURRENT_STATE"
        fi
        
    else
        echo "$(date): tmux 세션 '$TMUX_SESSION'이 존재하지 않습니다"
        sleep 10
    fi
    
    sleep $CHECK_INTERVAL
done