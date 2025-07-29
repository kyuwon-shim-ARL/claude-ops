#!/bin/bash

# Claude 상태를 모니터링하여 자동으로 알림을 보내는 스크립트

TMUX_SESSION="${TMUX_SESSION:-claude_session}"
LAST_OUTPUT_FILE="/tmp/claude_last_output"
CHECK_INTERVAL=3  # 3초마다 체크

echo "Claude 상태 모니터링 시작..."
echo "tmux 세션: $TMUX_SESSION"
echo "체크 간격: ${CHECK_INTERVAL}초"

while true; do
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        # 현재 출력 캡처
        CURRENT_OUTPUT=$(tmux capture-pane -t "$TMUX_SESSION" -p | tail -n 5)
        
        # 이전 출력과 비교
        if [ -f "$LAST_OUTPUT_FILE" ]; then
            PREVIOUS_OUTPUT=$(cat "$LAST_OUTPUT_FILE")
            
            # 출력이 변경되었고, 특정 패턴이 있는지 확인
            if [ "$CURRENT_OUTPUT" != "$PREVIOUS_OUTPUT" ]; then
                # 질문 패턴 체크
                if echo "$CURRENT_OUTPUT" | grep -q -E "(Do you want|Would you like|Should I|Can I).*\?"; then
                    /home/kyuwon/claude-ops/send_smart_notification.sh "❓ Claude가 질문을 했습니다"
                    echo "$(date): 질문 패턴 감지됨"
                fi
                
                # 완료 패턴 체크  
                if echo "$CURRENT_OUTPUT" | grep -q -E "(완료|완성|성공|✅|🎉|Done|Complete)"; then
                    /home/kyuwon/claude-ops/send_smart_notification.sh "✅ Claude 작업이 완료되었습니다"
                    echo "$(date): 완료 패턴 감지됨"
                fi
                
                # 오류 패턴 체크
                if echo "$CURRENT_OUTPUT" | grep -q -E "(오류|에러|실패|❌|Error|Failed)"; then
                    /home/kyuwon/claude-ops/send_smart_notification.sh "❌ Claude에서 오류가 발생했습니다"
                    echo "$(date): 오류 패턴 감지됨"
                fi
            fi
        fi
        
        # 현재 출력을 파일에 저장
        echo "$CURRENT_OUTPUT" > "$LAST_OUTPUT_FILE"
    else
        echo "$(date): tmux 세션 '$TMUX_SESSION'이 존재하지 않습니다"
        sleep 10
    fi
    
    sleep $CHECK_INTERVAL
done