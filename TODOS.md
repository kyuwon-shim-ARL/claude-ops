
## [TODO] state_detector.py ↔ session_state.py 상태 열거 통일

**What:** `ctb-dashboard/src/ctb_dashboard/state_detector.py`와 `claude_ctb/utils/session_state.py`의 SessionState enum을 단일 소스로 통합하거나, 적어도 둘의 상태 목록을 동기화.

**Why:** 대시보드 `state_detector.py`에 `STUCK_AFTER_AGENT` 상태가 있지만 `session_state.py`에는 없음. 현재 각자 독립적으로 진화 중. 미래에 한쪽에만 새 상태를 추가하면 조용한 동작 차이가 발생.

**Pros:** 상태 불일치 버그 원천 차단. 하나의 파일만 수정하면 됨.

**Cons:** 두 패키지(`claude_ctb`와 `ctb_dashboard`) 간 의존성 추가 또는 공유 패키지 생성 필요.

**Context:** 2026-04-16 eng review에서 발견. 현재 `ctb-dashboard`는 별도 패키지로 pip 설치되므로 직접 import가 어려울 수 있음. 가장 간단한 방법은 `state_detector.py`가 `session_state.py`를 import하도록 변경.

**Depends on:** ctb-dashboard 패키지 빌드 파이프라인 확인
