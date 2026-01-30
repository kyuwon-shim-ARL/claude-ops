# 🌉 Claude-Telegram-Bridge

**Claude Code와 Telegram을 연결하는 원격 제어 및 모니터링 브리지**

[![Setup Time](https://img.shields.io/badge/Setup-1_minute-green)](./QUICK_START.md)
[![Architecture](https://img.shields.io/badge/Architecture-Pure_Bridge-purple)](./CLAUDE.md)
[![Version](https://img.shields.io/badge/Version-2.0.3-blue)](./CHANGELOG.md)

## 🎯 핵심 기능

- 🌉 **Pure Bridge**: 텔레그램 ↔ Claude Code 간 순수 연결 다리
- 📱 **Reply Targeting**: 알림 메시지 Reply로 정확한 세션 타겟팅
- 🎛️ **Multi-Session**: 여러 Claude 세션 동시 제어
- 📊 **Smart Summary**: 대기 중 세션 요약 (`/summary`)
- ⏱️ **Wait Time Tracking**: 작업 완료 시 대기 시간 자동 표시
- 📺 **Reliable Log View**: Markdown-safe log viewing (`/log`)
- 🔄 **Workflow Delegation**: 모든 워크플로우는 [claude-dev-kit](https://github.com/kyuwon-shim-ARL/claude-dev-kit) 처리

## ⚡ 1분 설정

```bash
# 1. 설치
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git && cd claude-ops

# 2. 환경 설정
cp .env.example .env
# .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 설정

# 3. 실행
uv sync && python -m claude_ctb.telegram.bot

# 4. CLI 설치 (선택사항)
./scripts/ctb install
# 이후 ctb, claude-bridge, claude-telegram-bridge 명령 사용 가능
```

## 📱 기본 사용법

### 핵심 명령어
```
/new-project <name>    # 새 Claude 프로젝트 생성
/sessions              # 세션 목록 및 전환
/board                 # 세션 보드 (그리드 뷰)
/summary               # 대기 중 세션 요약
/log [lines]           # Claude 화면 내용 보기
```

### Reply 기반 타겟팅
1. **작업 완료 알림** 수신 → 해당 세션 정보 표시
2. **알림에 Reply** → 정확히 해당 세션으로 명령 전송
3. **세션 혼동 방지** → Reply로 명확한 세션 선택

## 🏗️ 아키텍처

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│   Telegram      │◄──►│ Claude-Telegram-     │◄──►│  Claude Code    │
│     Bot         │    │      Bridge          │    │   Sessions      │
└─────────────────┘    └──────────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Session State  │
                       │    Detection    │
                       └─────────────────┘
```

## 📚 추가 문서

- **[빠른 시작](./QUICK_START.md)**: 상세한 설정 가이드
- **[개발자 가이드](./CLAUDE.md)**: 시스템 구조 및 개발 정보
- **[변경 로그](./CHANGELOG.md)**: 버전별 변경사항
- **[멀티 유저 가이드](./docs/guides/MULTI_USER_GUIDE.md)**: 팀 배포 방법
- **[업데이트 전략](./docs/guides/UPDATE_STRATEGY.md)**: 안전한 업데이트 방법

## 🔧 고급 사용법

### 수동 세션 생성
```bash
tmux new-session -d -s claude_my-project -c ~/projects/my-project
tmux send-keys -t claude_my-project 'claude' Enter
```

### CLI 명령어 (설치 후)
```bash
ctb new-project my-app              # 짧은 명령 (권장)
claude-bridge sessions              # 중간 길이
claude-telegram-bridge status       # 전체 이름
```

### 시스템 관리
```bash
# 봇 상태 확인
ps aux | grep claude_ctb

# 세션 관리
tmux list-sessions | grep claude
tmux kill-session -t claude_my-project
```

## 🤝 기여

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이센스

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Claude-Telegram-Bridge v2.0.1** - Telegram ↔ Claude Code Bridge System