# Verification Checklist - Claude-CTB v2.1 Reliability Improvements

## Phase 4: Verification & Validation

### 4.1 기존 기능 회귀 테스트 (Regression Testing)

#### 목적
v2.1 신규 기능 추가 후 기존 핵심 기능이 여전히 정상 작동하는지 검증

#### 테스트 항목

##### ✅ **Critical Path (필수)**
- [ ] `/sessions` - 세션 목록 표시
- [ ] `/status` - 봇 상태 확인
- [ ] `/log [N]` - 세션 로그 조회
- [ ] Reply-based targeting - 세션에 메시지 전송
- [ ] 작업 완료 알림 수신
- [ ] 입력 대기 알림 수신
- [ ] `/new-project` - 프로젝트 생성

##### ✅ **Core Monitoring**
- [ ] Multi-session monitoring
- [ ] Session discovery (새 세션 자동 감지)
- [ ] Screen change detection
- [ ] State transition detection

##### ➕ **v2.1 신규 기능**
- [ ] Session reconnection with exponential backoff
- [ ] Restart notification skip (no duplicates)
- [ ] Telegram rate limit handling
- [ ] Dangerous command confirmation
- [ ] 200-line screen history

#### 실행 방법

```bash
# 1. 전체 테스트 실행
PYTHONPATH=. uv run pytest tests/ -v

# 2. 핵심 기능만 (integration + contract)
PYTHONPATH=. uv run pytest tests/integration/ tests/contract/ -v

# 3. 신규 기능만
PYTHONPATH=. uv run pytest tests/integration/ -v
```

#### 성공 기준

- **Integration Tests**: 100% 통과 필수 (17/17)
- **Contract Tests**: 95% 이상 통과 (기존 tmux 동작 차이 허용)
- **Unit Tests**: 90% 이상 통과

#### 현재 상태 (2025-10-02)

```
✅ Integration: 17/17 (100%)
✅ Contract: 18/19 (94.7%)
✅ Unit: 38/38 v2.1 관련 (100%)
⚠️ Legacy Tests: 287/317 (90.6%) - 기존 알림 로직 개선 필요
```

### 4.2 수동 검증 (Manual Testing)

#### 환경 설정
```bash
# 1. 환경 변수 확인
cat .env.example

# 2. 필요 시 .env 업데이트
SESSION_RECONNECT_MAX_DURATION=300
TELEGRAM_RATE_LIMIT_ENABLED=true
COMMAND_CONFIRMATION_TIMEOUT=60
SESSION_SCREEN_HISTORY_LINES=200
```

#### 시나리오 테스트

**Scenario 1: 세션 연결 끊김 복구**
```
1. Claude 세션 실행 중
2. tmux kill-session
3. 로그 확인: "🔄 Retry #N with Ns backoff"
4. 세션 재시작
5. 로그 확인: "✅ Session reconnected successfully"
```

**Scenario 2: 봇 재시작 후 중복 알림 없음**
```
1. 작업 완료 알림 수신
2. 봇 재시작 (pkill + restart)
3. 동일 화면 상태 유지
4. 중복 알림 미발생 확인
```

**Scenario 3: 위험한 명령어 확인**
```
1. /sessions에서 세션 선택
2. Reply: "sudo systemctl restart service"
3. 확인 메시지 표시 확인
4. ✅ Confirm 또는 ❌ Cancel 선택
```

### 4.3 프로덕션 배포 체크리스트

- [ ] 모든 테스트 통과
- [ ] .env 환경변수 설정
- [ ] 로그 레벨 확인 (INFO)
- [ ] 기존 세션 백업
- [ ] 봇 재시작
- [ ] 첫 24시간 모니터링

### 4.4 롤백 계획

문제 발생 시:
```bash
# 1. 이전 버전으로 롤백
git checkout <previous-version>

# 2. 봇 재시작
claude-ctb restart-all

# 3. 상태 파일 정리 (필요 시)
rm -rf /tmp/claude-ctb-state/
```

### 4.5 성공 메트릭

**1주일 모니터링 기간:**
- Zero duplicate notifications after restart
- 95%+ session reconnection success rate
- No Telegram API rate limit errors
- 100% dangerous command confirmation working

---

## Verification Sign-off

- [ ] **개발자**: 모든 자동 테스트 통과
- [ ] **사용자**: 핵심 기능 수동 검증 완료
- [ ] **프로덕션**: 1주일 안정 운영 확인

**Date**: ___________
**Verified by**: ___________
**Status**: [ ] Pass [ ] Fail [ ] Need Fixes
