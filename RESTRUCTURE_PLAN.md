# Claude-Telegram Bridge 구조 개선 계획

## 🎯 목표
현재 번잡한 구조를 **배포 가능한 독립 패키지**로 개선:
1. **Template Repository**: 새 프로젝트에서 바로 사용
2. **Install Script**: 기존 프로젝트에 설치
3. **Clean Architecture**: 관리 용이한 구조

## 📁 **개선된 디렉토리 구조**

### Option A: 독립 패키지 (권장)
```
claude-telegram-bridge/
├── README.md                    # 설치 및 사용법
├── requirements.txt             # Python 의존성
├── setup.py                    # 패키지 설치 스크립트
├── .env.example                # 환경변수 템플릿
├── claude_bridge/              # 메인 패키지
│   ├── __init__.py
│   ├── bot.py                  # 텔레그램 봇 (현재 telegram_claude_bridge.py)
│   ├── monitor.py              # 모니터링 (현재 watch_claude_status.sh)
│   ├── notifier.py             # 알림 (현재 send_smart_notification.sh)
│   └── config.py               # 설정 관리
├── scripts/                    # 실행 스크립트
│   ├── install.sh              # 자동 설치
│   ├── start.sh                # 시스템 시작
│   └── stop.sh                 # 시스템 종료
└── docs/                       # 문서
    ├── INSTALL.md
    ├── USAGE.md
    └── TROUBLESHOOTING.md
```

### Option B: 기존 프로젝트 통합
```
your-project/
├── .claude-bridge/             # 브릿지 전용 디렉토리
│   ├── bot.py
│   ├── monitor.py
│   ├── notifier.py
│   ├── config.py
│   └── .env
├── scripts/
│   └── start-claude-bridge.sh
└── your-existing-files...
```

## 🚀 **구현 방법**

### 1. **독립 패키지 생성 (Option A)**
```bash
# 새 저장소 생성
git clone <template-repo> my-new-project
cd my-new-project
./scripts/install.sh

# 환경 설정
cp .env.example .env
# TELEGRAM_BOT_TOKEN 등 설정

# 시작
./scripts/start.sh
```

### 2. **기존 프로젝트 설치 (Option B)**
```bash
# 기존 프로젝트에서
curl -sSL https://raw.githubusercontent.com/user/claude-bridge/main/install.sh | bash

# 또는
git submodule add <bridge-repo> .claude-bridge
./.claude-bridge/scripts/install.sh
```

## 📦 **패키지 구성 요소**

### A. 메인 모듈들
- **bot.py**: 텔레그램 봇 (인라인 키보드 포함)
- **monitor.py**: Claude 상태 모니터링
- **notifier.py**: 스마트 알림 시스템
- **config.py**: 환경변수 및 설정 관리

### B. 설치 스크립트
- **install.sh**: 의존성 설치, 환경 설정
- **start.sh**: 모든 서비스 시작
- **stop.sh**: 모든 서비스 종료

### C. 설정 파일
- **.env.example**: 환경변수 템플릿
- **requirements.txt**: Python 의존성
- **config.yaml**: 선택적 고급 설정

## 🔧 **핵심 기능 보존**
- ✅ 인라인 키보드 버튼 (Status, Log, Stop, Help)
- ✅ Bot Commands Menu (/ 버튼)
- ✅ 자동 알림 시스템
- ✅ 다중 세션 지원 (Option 2)
- ✅ ESC 작업 중단

## 📝 **다음 단계**
1. **패키지 구조 생성**
2. **Python 모듈로 변환**
3. **설치 스크립트 작성**
4. **문서 정리**
5. **테스트 및 배포**

## 💡 **장점**
- **Template 사용**: `git clone` 후 바로 사용
- **기존 프로젝트 통합**: 한 줄 설치 스크립트
- **깔끔한 구조**: 필요한 파일만 포함
- **쉬운 관리**: 모듈화된 구조
- **문서화**: 사용법 명확히 정리