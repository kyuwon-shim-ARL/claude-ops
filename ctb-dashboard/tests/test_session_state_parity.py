"""Parity test: ctb_dashboard.state_detector.SessionState must match the
canonical claude_ctb.utils.session_state.SessionState when the canonical
module is importable (normal dev layout).

Prevents silent enum divergence regression (TODOS.md 2026-04-16 item,
fixed by P1 S0 of CTB Dashboard UX Overhaul plan).
"""
import pytest


def test_state_detector_imports_canonical_session_state():
    """state_detector.SessionState must be THE canonical enum, not a local fork."""
    try:
        from claude_ctb.utils.session_state import SessionState as Canonical
    except ImportError:
        pytest.skip("claude_ctb not on path — isolated dashboard install, skip parity")

    from ctb_dashboard.state_detector import SessionState as Dashboard

    assert Dashboard is Canonical, (
        "state_detector.SessionState is a local fork, expected canonical import. "
        "See P1 S0 enum consolidation in plan."
    )


def test_canonical_includes_stuck_after_agent():
    """STUCK_AFTER_AGENT must exist in the canonical enum (was dashboard-only)."""
    try:
        from claude_ctb.utils.session_state import SessionState
    except ImportError:
        pytest.skip("claude_ctb not importable in this environment")

    assert hasattr(SessionState, "STUCK_AFTER_AGENT")
    assert SessionState.STUCK_AFTER_AGENT.value == "stuck_after_agent"


def test_required_states_present():
    """Dashboard requires at minimum these states."""
    from ctb_dashboard.state_detector import SessionState

    required = {
        "CONTEXT_LIMIT", "ERROR", "WAITING_INPUT", "WORKING",
        "STUCK_AFTER_AGENT", "IDLE", "UNKNOWN",
    }
    actual = {m.name for m in SessionState}
    missing = required - actual
    assert not missing, f"Missing required states: {missing}"
