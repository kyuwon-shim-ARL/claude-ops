"""Tests for state_detector module."""

from ctb_dashboard.state_detector import SessionState, SessionStateAnalyzer, StateTransition


def test_session_state_enum_values():
    """SessionState enum has all expected values."""
    assert SessionState.WORKING.value == "working"
    assert SessionState.IDLE.value == "idle"
    assert SessionState.WAITING_INPUT.value == "waiting"
    assert SessionState.ERROR.value == "error"
    assert SessionState.CONTEXT_LIMIT.value == "context_limit"
    assert SessionState.UNKNOWN.value == "unknown"


def test_session_state_analyzer_instantiation():
    """SessionStateAnalyzer can be instantiated without errors."""
    analyzer = SessionStateAnalyzer()
    assert analyzer is not None
    assert hasattr(analyzer, 'get_state')
    assert hasattr(analyzer, 'get_screen_content')


def test_state_priority_ordering():
    """State priority dict covers all states with correct ordering."""
    analyzer = SessionStateAnalyzer()
    priorities = analyzer.STATE_PRIORITY
    assert priorities[SessionState.CONTEXT_LIMIT] < priorities[SessionState.ERROR]
    assert priorities[SessionState.ERROR] < priorities[SessionState.WAITING_INPUT]
    assert priorities[SessionState.WAITING_INPUT] < priorities[SessionState.WORKING]
    assert priorities[SessionState.WORKING] < priorities[SessionState.IDLE]
    assert priorities[SessionState.IDLE] < priorities[SessionState.UNKNOWN]


def test_state_transition():
    """StateTransition records from/to states correctly."""
    t = StateTransition("test_session", SessionState.IDLE, SessionState.WORKING)
    assert t.session == "test_session"
    assert t.from_state == SessionState.IDLE
    assert t.to_state == SessionState.WORKING
    assert t.timestamp is not None


def test_detect_working_empty_content():
    """_detect_working_state returns False for empty content."""
    analyzer = SessionStateAnalyzer()
    assert analyzer._detect_working_state("") is False
    assert analyzer._detect_working_state(None) is False


def test_detect_working_with_interrupt():
    """_detect_working_state detects 'esc to interrupt'."""
    analyzer = SessionStateAnalyzer()
    content = "\n".join(["line"] * 20 + ["esc to interrupt"])
    assert analyzer._detect_working_state(content) is True


def test_detect_idle_with_prompt():
    """_detect_working_state returns False when prompt is at bottom."""
    analyzer = SessionStateAnalyzer()
    content = "\n".join(["some output"] * 5 + ["\u276f"])
    assert analyzer._detect_working_state(content) is False


# --- extract_work_context: source_skill badge tag ---

def test_extract_work_context_source_skill(tmp_path):
    """source_skill from critique-lock.json is used as badge tag."""
    import json
    omc_state = tmp_path / ".omc" / "state"
    omc_state.mkdir(parents=True)
    lock = {
        "final_verdict": "EXECUTING",
        "source_skill": "ca",
        "ticket_summary": "T1+T2 구현",
    }
    (omc_state / "critique-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    analyzer = SessionStateAnalyzer()
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is not None
    assert result.startswith("[ca]"), f"Expected [ca] tag, got: {result}"


def test_extract_work_context_no_source_skill_falls_back(tmp_path):
    """Falls back to [exec]/[plan] when source_skill is absent."""
    import json
    omc_state = tmp_path / ".omc" / "state"
    omc_state.mkdir(parents=True)
    lock = {
        "final_verdict": "EXECUTING",
        "ticket_summary": "작업 중",
    }
    (omc_state / "critique-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    analyzer = SessionStateAnalyzer()
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is not None
    assert result.startswith("[exec]"), f"Expected [exec] tag, got: {result}"


def test_extract_work_context_empty_source_skill_falls_back(tmp_path):
    """Empty string source_skill falls back to [exec]/[plan] via falsy check."""
    import json
    omc_state = tmp_path / ".omc" / "state"
    omc_state.mkdir(parents=True)
    lock = {
        "final_verdict": "CONVERGED",
        "source_skill": "",
        "ticket_summary": "계획 완료",
    }
    (omc_state / "critique-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    analyzer = SessionStateAnalyzer()
    result = analyzer.extract_work_context(str(tmp_path))
    assert result is not None
    assert result.startswith("[plan]"), f"Expected [plan] tag, got: {result}"


def test_extract_work_context_no_lock_file(tmp_path):
    """Returns None (or falls through to next source) when lock file is absent."""
    analyzer = SessionStateAnalyzer()
    # tmp_path has no .omc/state/critique-lock.json — 1b block is skipped
    result = analyzer.extract_work_context(str(tmp_path))
    # No lock, no notepad, no MANIFEST, no CLAUDE.md → falls through to branch name or None
    assert result is None or isinstance(result, str)
