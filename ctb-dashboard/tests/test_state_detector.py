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
