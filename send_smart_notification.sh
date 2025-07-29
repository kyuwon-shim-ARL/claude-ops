#!/bin/bash

# .env 파일에서 환경변수 로드
if [ -f "/home/kyuwon/claude-ops/.env" ]; then
    export $(grep -v '^#' /home/kyuwon/claude-ops/.env | xargs)
fi

# tmux 세션에서 Claude의 실제 응답만 지능적으로 추출
TMUX_SESSION="${TMUX_SESSION:-claude_session}"
CLAUDE_RESPONSE=""

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    # 전체 화면 캡처
    FULL_CAPTURE=$(tmux capture-pane -t "$TMUX_SESSION" -p)
    
    # 마지막 bullet point (●) 이후의 모든 내용 추출 (기존 방식 복원)
    LAST_BULLET_LINE=$(echo "$FULL_CAPTURE" | grep -n '●' | tail -n 1 | cut -d: -f1)
    
    if [ -n "$LAST_BULLET_LINE" ]; then
        # bullet point부터 화면 끝까지 모든 내용 포함
        RAW_RESPONSE=$(echo "$FULL_CAPTURE" | tail -n +$LAST_BULLET_LINE | grep -v 'Running' | grep -v 'Frolicking' | grep -v 'esc to interrupt')
        
        # 단순한 처리: 박스 문자만 제거하고 모든 내용 표시
        CLAUDE_RESPONSE=""
        
        while IFS= read -r line; do
            # 박스 문자 제거하되 선택지 구조 보존
            CLEAN_LINE=$(echo "$line" | sed 's/[│─╭╮╯╰┌┐┘└┤├┬┴┼]//g' | sed 's/^[ \t]*//')
            
            # 빈 줄이 아니거나 선택지 관련 줄이면 추가
            if [ -n "$CLEAN_LINE" ] || echo "$line" | grep -q -E '(❯|[0-9]+\.|Yes|No)'; then
                CLAUDE_RESPONSE="$CLAUDE_RESPONSE
$CLEAN_LINE"
            fi
        done <<< "$RAW_RESPONSE"
        
        # 응답 타입 결정
        if [ -n "$CLAUDE_RESPONSE" ] && [ ${#CLAUDE_RESPONSE} -gt 10 ]; then
            if echo "$CLAUDE_RESPONSE" | grep -q -E '(완료|완성|성공|실패|✅|❌|🎉)'; then
                RESPONSE_TYPE="완료"
            elif echo "$CLAUDE_RESPONSE" | grep -q -E '([0-9]+\.|Yes|No|keep planning|manually approve)'; then
                RESPONSE_TYPE="질문"
            else
                RESPONSE_TYPE="응답"
            fi
        else
            CLAUDE_RESPONSE=""
        fi
        
        # 앞뒤 공백 정리
        CLAUDE_RESPONSE=$(echo "$CLAUDE_RESPONSE" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    fi
    
    # bullet point가 없거나 이후 내용이 없다면 대체 방법
    if [ -z "$CLAUDE_RESPONSE" ]; then
        # 화면 전체에서 마지막 의미있는 내용 찾기
        CLAUDE_RESPONSE=$(echo "$FULL_CAPTURE" | grep -E '^[^│─╭╮╯╰┌┐┘└┤├┬┴┼]*[A-Za-z가-힣]' | grep -v -E 'Running|Frolicking|tokens|esc to interrupt|Update\(|Edit\(|Bash\(|^\s*[0-9]+\s*[-+]' | tail -n 3)
        
        if [ -n "$CLAUDE_RESPONSE" ] && [ ${#CLAUDE_RESPONSE} -gt 20 ]; then
            RESPONSE_TYPE="상태"
        else
            # 의미있는 응답이 없으면 알림을 보내지 않음
            exit 0
        fi
    fi
    
    # 응답 정리 및 길이 제한
    CLAUDE_RESPONSE=$(echo "$CLAUDE_RESPONSE" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    
    # 텔레그램 메시지 길이 제한 (4096자) 고려
    if [ ${#CLAUDE_RESPONSE} -gt 3000 ]; then
        CLAUDE_RESPONSE=$(echo "$CLAUDE_RESPONSE" | head -c 3000)
        CLAUDE_RESPONSE="$CLAUDE_RESPONSE

(내용이 길어서 일부가 생략되었습니다)"
    fi
fi

# 메시지 구성
MESSAGE="${1:-✅ Claude 작업 알림}"

# 의미있는 응답이 있을 때만 메시지 구성
FULL_MESSAGE="$MESSAGE

🤖 Claude 응답 (${RESPONSE_TYPE}):
$CLAUDE_RESPONSE"

# 최종 메시지 길이 체크 (텔레그램 한도: 4096자)
if [ ${#FULL_MESSAGE} -gt 4000 ]; then
    # 메시지가 너무 길면 Claude 응답 부분을 더 줄임
    SHORT_RESPONSE=$(echo "$CLAUDE_RESPONSE" | head -c 2000)
    FULL_MESSAGE="$MESSAGE

🤖 Claude 응답 (${RESPONSE_TYPE}):
$SHORT_RESPONSE

(응답이 길어서 축약되었습니다)"
fi

# 텔레그램 메시지 전송 (마크다운 문제 방지를 위해 일반 텍스트로)
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
     -d "chat_id=${TELEGRAM_CHAT_ID}" \
     -d "text=$FULL_MESSAGE"