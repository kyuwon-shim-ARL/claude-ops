# Terminal Health Monitor System Design

## 🎯 목표
tmux 세션의 터미널 크기 이상을 자동으로 감지하고 안전하게 복구

## 🏗️ 아키텍처

### 1. 감지 메커니즘 (Detection)
```python
class TerminalHealthChecker:
    def check_terminal_health(self, session_name):
        """터미널 건강 상태 확인"""
        # 1. 예상 크기 vs 실제 크기 비교
        expected_width = self.get_expected_width(session_name)
        actual_output = self.capture_screen(session_name)
        
        # 2. 이상 패턴 감지
        anomalies = {
            'vertical_text': self.detect_vertical_text(actual_output),
            'narrow_width': self.detect_narrow_width(actual_output),
            'broken_layout': self.detect_broken_layout(actual_output)
        }
        
        return any(anomalies.values()), anomalies
```

### 2. 복구 전략 (Recovery Strategy)

#### Option A: Soft Recovery (권장)
```python
def soft_recovery(session_name):
    """작업 중단 없이 터미널 크기 조정"""
    steps = [
        # 1. 현재 상태 백업
        backup_current_state(session_name),
        
        # 2. 터미널 크기 재설정
        reset_terminal_size(session_name),
        
        # 3. 화면 리프레시
        refresh_display(session_name),
        
        # 4. 검증
        verify_recovery(session_name)
    ]
```

#### Option B: Safe Restart with Resume
```python
def safe_restart_with_resume(session_name):
    """안전한 재시작 with 대화 연속성"""
    steps = [
        # 1. 현재 대화 ID 저장
        conversation_id = get_conversation_id(session_name),
        
        # 2. 작업 상태 저장
        save_working_state(session_name),
        
        # 3. Graceful shutdown
        send_keys(session_name, "Ctrl+C"),
        wait(2),
        
        # 4. 패널 재생성
        respawn_pane(session_name),
        
        # 5. Claude 재시작 with resume
        start_claude_with_resume(session_name, conversation_id),
        
        # 6. 상태 복원
        restore_working_state(session_name)
    ]
```

### 3. 자동화 통합

```python
class AutoTerminalHealthMonitor:
    def __init__(self):
        self.check_interval = 30  # 초
        self.recovery_threshold = 3  # 연속 실패 횟수
        
    def monitor_loop(self):
        while True:
            for session in self.get_active_sessions():
                is_unhealthy, issues = self.check_health(session)
                
                if is_unhealthy:
                    # 경고 알림
                    self.send_warning(session, issues)
                    
                    # 자동 복구 시도
                    if self.should_auto_recover(session):
                        self.auto_recover(session)
                        
            time.sleep(self.check_interval)
```

## 🔧 구현 세부사항

### 터미널 크기 이상 감지 패턴
1. **Vertical Text Pattern**: 한 글자씩 세로 배열
2. **Narrow Width Pattern**: 예상 너비의 10% 미만
3. **Broken Box Drawing**: 박스 문자 깨짐

### 복구 우선순위
1. **Level 1**: stty 명령으로 크기 재설정
2. **Level 2**: tmux refresh-client
3. **Level 3**: 패널 재생성 (작업 보존)
4. **Level 4**: Claude 재시작 with resume

### 데이터 보존 전략
```python
class SessionStatePreserver:
    def preserve_state(self, session_name):
        return {
            'conversation_id': self.get_conversation_id(),
            'working_directory': self.get_cwd(),
            'environment_vars': self.get_env(),
            'last_command': self.get_last_command(),
            'timestamp': datetime.now()
        }
    
    def restore_state(self, session_name, state):
        # 디렉토리 복원
        self.change_directory(state['working_directory'])
        
        # Claude resume
        self.resume_conversation(state['conversation_id'])
        
        # 환경 복원
        self.restore_environment(state['environment_vars'])
```

## 🚀 배포 계획

### Phase 1: 감지 시스템
- 터미널 건강 상태 모니터링
- 이상 패턴 로깅
- 텔레그램 경고 알림

### Phase 2: 수동 복구 도구
- `/fix-terminal [session]` 명령 추가
- Soft recovery 우선 시도
- 실패 시 사용자 승인 후 재시작

### Phase 3: 자동 복구
- 자동 감지 및 복구
- 복구 히스토리 추적
- 성공률 모니터링

## 📊 성공 지표
- 터미널 이상 감지율: > 95%
- 자동 복구 성공률: > 80%
- 작업 중단 시간: < 10초
- 데이터 손실: 0%

## ⚠️ 위험 관리
- **위험**: 잘못된 복구로 작업 손실
- **대책**: 항상 백업 후 복구, 사용자 승인 옵션

- **위험**: 빈번한 재시작으로 생산성 저하
- **대책**: Soft recovery 우선, 임계값 설정

- **위험**: Resume 실패로 대화 연속성 상실
- **대책**: 대화 ID 저장, 수동 복구 옵션