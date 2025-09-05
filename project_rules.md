# Project Rules - Claude-Ops

## 🎯 Core Mission
**Telegram으로 Claude Code 세션을 원격 제어하는 스마트 브리지 시스템**

## 📋 Development Principles

### 1. Architecture Principles
- **Telegram-First Architecture**: 모든 제어는 Telegram 봇을 통해
- **Session-Centric Workflow**: tmux 세션 단위로 작업 관리
- **Hybrid Monitoring**: Hook 기반 + 폴링 백업으로 100% 안정성
- **Reply-Based Targeting**: 정확한 세션 타겟팅으로 혼동 방지

### 2. Code Quality Standards
- **MECE Principle**: 상호배타적이고 전체포괄적인 구조 유지
- **DRY Principle**: 코드 중복 제거, 재사용성 최대화
- **Fail-Safe Design**: 오류 시 안전한 상태로 복구
- **Comprehensive Testing**: 모든 기능에 대한 테스트 코드 작성

### 3. Documentation Standards
- **Auto-Documentation**: 모든 워크플로우 결과 자동 문서화
- **Living Documentation**: 코드 변경 시 문서 동기 업데이트
- **User-Centric**: 5분 내 설정 가능한 사용자 경험
- **CURRENT/ Structure**: 현재 상태 추적을 위한 표준 디렉토리

### 4. Workflow Standards
- **Structured Workflows**: /기획, /구현, /안정화, /배포 단계별 접근
- **Context Loading**: project_rules.md, status.md, active-todos.md 자동 로딩
- **PRD-Driven**: 모든 기능은 Product Requirements Document 기반
- **TODO Integration**: TodoWrite 도구 활용한 작업 추적

## 🛠️ Technical Standards

### File Structure
```
claude-ops/
├── project_rules.md              # 이 파일 - 프로젝트 규칙
├── docs/CURRENT/                 # 현재 상태 추적
│   ├── status.md                # 현재 시스템 상태
│   ├── active-todos.md          # 활성 TODO 목록
│   └── planning.md              # 기획 결과 저장
├── claude_ops/                   # 핵심 Python 패키지
├── scripts/                      # CLI 도구
└── slash_commands/              # Claude Code 명령어
```

### Environment Requirements
- Python 3.11+ with uv package manager
- tmux for session management  
- Git with LFS support
- Telegram Bot API access

### Security Requirements
- Environment variables in .env file only
- No secrets in code repository
- User authentication via Telegram user ID
- Input validation and sanitization

## 🎯 Success Metrics

### Performance Targets
- ⚡ Setup time: < 5 minutes
- 🚀 Command response: < 2 seconds  
- 📊 System uptime: > 99%
- 🔄 Session recovery: < 30 seconds

### Quality Targets
- 📝 Documentation coverage: 100%
- 🧪 Test coverage: > 80%
- 🔧 Code complexity: Low (< 10 cyclomatic)
- 📦 Package size: < 1MB

## 🚨 Critical Rules

### Never Break These
1. **No Direct File System Access**: 모든 작업은 적절한 API 통해서만
2. **No Hardcoded Paths**: 환경변수나 설정파일 사용
3. **No Silent Failures**: 모든 에러는 로깅 및 사용자 알림
4. **No Session Mixup**: Reply 기반 타겟팅으로 세션 혼동 방지

### Always Do These  
1. **Context Loading**: 워크플로우 시작 시 필수 문서 확인
2. **TODO Tracking**: 모든 작업은 TodoWrite로 추적
3. **Auto Documentation**: 결과물은 CURRENT/ 디렉토리에 저장
4. **User Notification**: 중요한 상태 변화는 Telegram 알림

---

**Last Updated**: 2025-08-20
**Next Review**: Monthly or on major changes