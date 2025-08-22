# 🚀 Claude-Ops: Pure Telegram Bridge for Claude Code

**순수 텔레그램 브리지 - Claude Code 세션 원격 제어 및 모니터링**

[![Setup Time](https://img.shields.io/badge/Setup-5_minutes-green)](./QUICK_START.md)
[![Architecture](https://img.shields.io/badge/Architecture-Pure_Bridge-purple)](./CLAUDE.md)
[![Commands](https://img.shields.io/badge/Commands-Claude_Dev_Kit-blue)](https://github.com/kyuwon-shim-ARL/claude-dev-kit)
[![Reply Based](https://img.shields.io/badge/Telegram-Reply_Based_Targeting-green)](#telegram-reply-targeting)

**Claude-Ops는 순수 브리지 역할에 집중합니다**

- 🌉 **Pure Bridge**: 텔레그램과 Claude Code 간 순수 연결 다리
- 🎯 **Session Management**: tmux 세션 관리 및 Reply 기반 타겟팅
- 📡 **Remote Control**: 텔레그램으로 Claude 세션 원격 제어
- 🔄 **Workflow Delegation**: 모든 워크플로우는 claude-dev-kit이 처리

## ✨ 최신 기능

### /compact 브리지 시스템 (v2.3.0)
- 🔍 **자동 감지**: claude-dev-kit의 /compact 제안 자동 감지
- 📱 **원클릭 실행**: 텔레그램 버튼으로 즉시 실행
- 📝 **ZED 가이드**: 구조화된 문서 내용 자동 추출 및 전달
- 🚫 **중복 방지**: 콘텐츠 해시 기반 30분 캐시

## ⚡ 빠른 설정

### 1분 설정 (권장)

```bash
# 1. Claude-Ops 설치
cd ~
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git claude-ops
cd claude-ops

# 2. 환경 설정
cp .env.example .env
# .env 파일에 텔레그램 봇 토큰 설정
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id

# 3. 의존성 설치
uv sync

# 4. 봇 시작
python -m claude_ops.telegram.bot
```


## 🚀 기본 사용법

### 세션 생성 및 제어

**텔레그램 명령어**
```
/new_project <name>                # 새 Claude 프로젝트 생성
/sessions                          # 활성 세션 목록
/status                           # 봇 상태 확인
/log [lines]                      # Claude 화면 내용 보기
```

**수동 세션 생성 (고급 사용자)**
```bash
# tmux로 Claude 세션 생성
tmux new-session -d -s claude_my-project -c ~/projects/my-project
tmux send-keys -t claude_my-project 'claude' Enter

# 연결: tmux attach -t claude_my-project
```

**빠른 시작 예시**
```
/start my-ai-app ~/projects/my-ai-app
/start data-analysis ~/work/analysis
/sessions
```

### 🎯 스마트 알림 및 Reply 제어

**1. 실시간 작업 완료 알림**
```
✅ 작업 완료 [claude_my-ai-app]

📁 프로젝트: ~/projects/my-ai-app
🎯 세션: claude_my-ai-app
⏰ 완료 시간: 14:30:25

[주요 작업 내용 요약]

💡 답장하려면 이 메시지에 Reply로 응답하세요!
```

**2. Reply 기반 정확한 타겟팅**
- ✅ 알림 메시지에 Reply → 해당 세션으로 자동 전송
- ✅ 일반 메시지 → 현재 활성 세션으로 전송
- ✅ 세션 혼동 방지: Reply로 정확한 세션 선택
- ✅ 매크로 확장: `@기획`, `@구현`, `@안정화`, `@배포` 자동 전개

## 🔧 시스템 관리

### 🚀 모니터링 시작

**봇 실행**
```bash
# 메인 봇 실행
python -m claude_ops.telegram.bot

# 또는 백그라운드 실행
nohup python -m claude_ops.telegram.bot &
```

**자동 기능:**
- ✅ 모든 `claude_*` 세션 자동 감지
- ✅ 작업 완료 시 텔레그램 알림
- ✅ Reply 기반 정확한 세션 타겟팅
- ✅ 매크로 확장으로 빠른 프롬프트 입력

### 🛑 시스템 제어

**봇 종료**
```bash
# 프로세스 종료
pkill -f "claude_ops.telegram.bot"

# 또는 Ctrl+C로 직접 종료
```

**세션 관리**
```bash
tmux kill-session -t claude_my-project  # 특정 세션 종료
tmux list-sessions | grep claude        # Claude 세션 목록
```

### 📊 상태 확인

**텔레그램 명령어**
```
/sessions    # 활성 세션 목록 및 전환
/status      # 봇 상태 및 현재 세션
```

**터미널 확인**
```bash
tmux list-sessions | grep claude    # Claude 세션 목록
ps aux | grep claude_ops            # 봇 프로세스 확인
```

### 💡 매크로 시스템

**내장 워크플로우 매크로**
- `@기획`: 프로젝트 기획 및 분석 프롬프트
- `@구현`: 구체적 구현 작업 프롬프트
- `@안정화`: 코드 리팩토링 및 최적화 프롬프트
- `@배포`: 배포 준비 및 문서화 프롬프트

**사용 예시**
```
텔레그램에서: @기획 새로운 데이터 분석 파이프라인
→ 자동 확장되어 상세한 기획 프롬프트로 전송
```

## 🎯 핵심 특징

### 🤖 스마트 텔레그램 봇
- **Reply 타겟팅**: Reply로 정확한 세션 지정, 혼동 방지
- **실시간 모니터링**: Claude 작업 완료 시 즉시 알림
- **매크로 확장**: 워크플로우 매크로로 빠른 프롬프트 입력

### ⚡ 세션 관리
- **멀티 세션 지원**: 여러 프로젝트 동시 모니터링
- **자동 세션 감지**: `claude_*` 패턴 세션 자동 인식
- **세션 전환**: 텔레그램에서 원클릭 세션 전환

### 🔧 개발자 친화적
- **최소 설정**: 봇 토큰만으로 즉시 시작
- **안전한 입력**: 위험 명령어 패턴 자동 차단
- **한국어 지원**: 한글 매크로 및 메시지 완벽 지원

## 🏗️ 시스템 아키텍처

### 📱 Telegram Bot Layer
- **사용자 인터페이스**: 모든 제어가 텔레그램에서 가능
- **명령어 처리**: `/start`, `/sessions`, `/status` 등
- **매크로 확장**: 워크플로우 프롬프트 자동 생성

### 🔄 Session Management Layer
- **Tmux 통합**: Claude Code 세션 상태 실시간 감지
- **멀티 세션**: 여러 프로젝트 동시 관리
- **스마트 라우팅**: Reply 기반 정확한 세션 타겟팅

### ⚙️ Core Bridge System
- **상태 감지**: 작업 완료/대기 상태 자동 인식
- **알림 시스템**: 중요 이벤트 즉시 전달
- **안전 검증**: 입력값 보안 검사 및 필터링

## 📋 실사용 시나리오

### 1. 새 프로젝트 시작
```
# 텔레그램에서
/start my-data-analysis ~/projects/data-analysis

# Claude 세션이 자동으로 시작됨
# 작업 완료 시 알림 수신
```

### 2. 멀티 프로젝트 관리
```
# 여러 프로젝트 동시 모니터링
/start frontend ~/work/frontend
/start backend ~/work/backend
/sessions  # 활성 세션 확인

# Reply로 특정 세션에 명령 전송
# 알림 메시지에 Reply → 해당 프로젝트로 전송
```

### 3. 매크로를 활용한 빠른 작업
```
# 텔레그램에서
@기획 새로운 API 엔드포인트 설계
→ 자동으로 상세한 기획 프롬프트로 확장되어 전송

@구현 사용자 인증 시스템
→ 구현 가이드라인 프롬프트로 확장
```

## 📁 Repository 구조

```
claude-ops/
├── 📚 README.md                    # 이 파일
├── 🤖 CLAUDE.md                    # Claude Code 사용 가이드
├── ⚙️ .env.example                 # 환경 설정 템플릿
├── 📦 pyproject.toml               # Python 의존성 (uv 관리)
├── 🤖 claude_ops/                  # 메인 패키지
│   ├── __init__.py                 # 패키지 진입점
│   ├── config.py                   # 환경 설정
│   ├── session_manager.py          # 세션 관리
│   ├── telegram/                   # 텔레그램 봇 모듈
│   │   ├── bot.py                  # 메인 봇 구현
│   │   ├── monitor.py              # 세션 모니터링
│   │   └── notifier.py             # 스마트 알림 시스템
│   └── utils/                      # 유틸리티  
│       └── session_state.py        # 통합 세션 상태 분석
└── 🧪 tests/                       # 테스트 파일
```

## 🔧 고급 기능

### 커스텀 매크로 추가
```python
# claude_ops/telegram/bot.py에서 매크로 추가
PROMPT_MACROS = {
    "@my_custom": "내 커스텀 프롬프트 템플릿...",
    # 기존 매크로들...
}
```

### 세션 자동화 스크립트
```bash
# 여러 세션 자동 시작
sessions=("frontend" "backend" "database")
for session in "${sessions[@]}"; do
    tmux new-session -d -s "claude_$session" -c "~/projects/$session"
    tmux send-keys -t "claude_$session" 'claude' Enter
done
```

### 모니터링 커스터마이징
```python
# 알림 조건 변경
# claude_ops/utils/session_state.py에서 상태 감지 로직 수정
```

## 🎉 주요 개선사항

실제 사용자 피드백을 반영한 개선사항:

- ✅ **즉시 사용 가능**: 1분 설정으로 바로 시작
- ✅ **텔레그램 중심**: 모든 제어가 텔레그램에서 가능
- ✅ **Reply 타겟팅**: 세션 혼동 방지, 정확한 명령 전달
- ✅ **매크로 시스템**: 빠른 워크플로우 프롬프트 입력
- ✅ **안전한 입력**: 위험 명령어 자동 차단, 길이 제한 완화

## 🔗 관련 링크

- [Claude Code 문서](https://docs.anthropic.com/en/docs/claude-code)
- [python-telegram-bot 문서](https://python-telegram-bot.readthedocs.io/)
- [Tmux 가이드](https://github.com/tmux/tmux/wiki)

---

**🎯 목표**: 텔레그램을 통해 Claude Code 세션을 원격으로 제어하고 모니터링하여 개발 효율성을 극대화합니다.

**🚀 시작하기**: `.env` 파일 설정 후 `python -m claude_ops.telegram.bot` 실행!
