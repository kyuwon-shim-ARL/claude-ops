# 다중 세션 지원 구현 계획

## 목표:
여러 디렉토리에서 독립적인 Claude Code 세션을 실행하고 Telegram으로 제어

## 구현 방식 (Option 2 from NEXT_SESSION_CONTEXT.md):

### 1. 세션 이름 동적 생성:
```python
# 현재: claude_session (하드코딩)
# 개선: claude_<directory_name>
# 예시: claude_project1, claude_ops, claude_research
```

### 2. 수정 필요 사항:

#### A. ClaudeOpsConfig 개선:
```python
class ClaudeOpsConfig:
    @property
    def session_name(self):
        # 현재 디렉토리 기반 세션 이름 생성
        current_dir = os.path.basename(os.getcwd())
        return f"claude_{current_dir}"
    
    @property
    def status_file(self):
        # 세션별 독립적인 상태 파일
        return f"/tmp/claude_work_status_{self.session_name}"
```

#### B. Telegram Bot 개선:
- 여러 세션 목록 표시
- 세션 선택 인터페이스
- 세션별 독립적인 제어

### 3. 새로운 기능:
- `/sessions` - 활성 세션 목록 보기
- 세션 선택 버튼
- 디렉토리별 자동 세션 생성

### 4. 호환성:
- 기존 단일 세션 방식도 계속 작동
- 점진적 마이그레이션 가능