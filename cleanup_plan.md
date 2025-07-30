# Repository 정리 계획

## 삭제할 디렉토리/파일들:
1. **Phase 1 잔재**: 
   - `claude_bridge/` - Phase 1에서 만든 모듈화 버전
   
2. **Phase 2 잔재**:
   - `claude-telegram-bridge-package/` - 독립 패키지 버전
   
3. **원본 파일들** (claude_ops에 통합됨):
   - `telegram_claude_bridge.py`
   - `ClaudeTelegramBot.py` (있다면)

## 보존할 구조:
- `claude_ops/` - 통합된 최종 버전
- `scripts/` - 실행 스크립트들
- `src/` - 기존 workflow 관련 파일들
- 문서 및 설정 파일들

## 정리 후 구조:
```
claude-ops/
├── claude_ops/          # 통합 Python 패키지
│   ├── telegram/        # Telegram 봇 기능
│   ├── notion/          # Notion 통합
│   └── config.py        # 통합 설정
├── scripts/             # 실행 스크립트
├── src/                 # 기존 workflow
├── docs/                # 문서
└── slash_commands/      # Claude Code 명령
```