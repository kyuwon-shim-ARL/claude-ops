# 🚀 Claude-Ops 2.0 빠른 시작 가이드

**Telegram-Claude Bridge System** - 1분 설정으로 Claude Code 세션을 텔레그램으로 제어하세요!

## ⚡ 초고속 설정 (1분)

### 1단계: 설치 및 설정

```bash
# 1. Repository clone
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git
cd claude-ops

# 2. 의존성 설치
uv sync

# 3. 환경 설정
cp .env.example .env
# .env 파일을 편집하여 텔레그램 봇 토큰 설정
```

### 2단계: 텔레그램 봇 설정 (30초)

1. **@BotFather**에게 메시지 보내기: `/newbot`
2. 봇 이름과 username 설정
3. 받은 토큰을 `.env` 파일에 입력:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```
4. 봇에게 메시지 보내고 chat ID 확인:
   ```
   TELEGRAM_CHAT_ID=your_chat_id_here
   ALLOWED_USER_IDS=your_user_id_here
   ```

### 3단계: 시작! (15초)

```bash
# 봇 시작
python -m claude_ops.telegram.bot
```

## 🎯 즉시 사용 가능한 기능

### 📱 텔레그램 명령어

- `/sessions` - 활성 Claude 세션 목록 보기
- `/board` - 세션 보드 (그리드 뷰)
- `/stop` - Claude 작업 중단 (ESC)
- `/erase` - 현재 입력 지우기 (Ctrl+C)
- `/log [줄수]` - Claude 화면 내용 보기

### 🚀 워크플로우 매크로

- `@기획 새 프로젝트` → 구조적 기획 프롬프트로 자동 확장
- `@구현 사용자 인증` → DRY 원칙 기반 구현 프롬프트
- `@안정화 코드 리뷰` → 구조적 검증 프롬프트  
- `@배포 최종 체크` → 배포 준비 프롬프트

### 🎪 Reply 기반 제어

```
Claude 세션 알림 메시지에 Reply
→ "새로운 API 엔드포인트 구현해줘"
→ 해당 세션에 직접 전송!
```

## 🏃‍♂️ 사용 예시 (실전)

### 1. 새 프로젝트 시작
```bash
# 1. Claude 세션 시작 (tmux)
tmux new-session -s claude_my-project
claude

# 2. 텔레그램에서 확인
/sessions  # claude_my-project 표시됨

# 3. 매크로로 빠른 시작
@기획 웹 애플리케이션 개발
```

### 2. 여러 프로젝트 관리
```bash
# 여러 세션 동시 실행
tmux new-session -d -s claude_frontend
tmux new-session -d -s claude_backend

# 텔레그램에서 전환
/board  # 모든 세션 한눈에 보기
```

### 3. 원격 개발 워크플로우
```
1. 로컬에서 Claude 세션 시작
2. 외출 중 텔레그램으로 진행상황 확인
3. 급한 수정사항 텔레그램으로 지시
4. 집 도착 후 결과 확인
```

## 🔧 고급 설정

### 커스텀 매크로 추가
```python
# claude_ops/telegram/bot.py
PROMPT_MACROS = {
    "@내매크로": "커스텀 프롬프트 내용...",
    # 기존 매크로들...
}
```

### 자동 세션 생성 스크립트
```bash
# start_all_sessions.sh
sessions=("frontend" "backend" "database")
for session in "${sessions[@]}"; do
    tmux new-session -d -s "claude_$session"
    tmux send-keys -t "claude_$session" 'claude' Enter
done
```

## ❓ 문제해결

### 세션이 안 보여요
```bash
# 세션 목록 확인
tmux list-sessions | grep claude

# 세션 이름이 claude_로 시작해야 함
tmux rename-session my-project claude_my-project
```

### 봇이 응답 안 해요
```bash
# .env 파일 확인
cat .env | grep TELEGRAM

# 사용자 ID 확인
echo $ALLOWED_USER_IDS
```

### 매크로가 확장 안 돼요
- `@기획` 앞뒤로 공백 확인
- 정확한 키워드인지 확인 (`@기획`, `@구현`, `@안정화`, `@배포`)

## 📚 더 알아보기

- **[README.md](./README.md)** - 전체 기능 상세 설명
- **[CLAUDE.md](./CLAUDE.md)** - Claude Code 통합 가이드
- **[CHANGELOG.md](./CHANGELOG.md)** - 버전별 변경사항

---

**🎉 축하합니다!** Claude-Ops 2.0 설정이 완료되었습니다. 
이제 텔레그램으로 Claude Code를 원격 제어할 수 있습니다!