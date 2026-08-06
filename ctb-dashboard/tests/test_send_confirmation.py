"""A prompt must never disappear quietly.

tmux send-keys returns success no matter what is on the pane, so a send into a
shell, a permission prompt, or a busy session looks identical to a real one.
That is tolerable at a desk and not tolerable from a phone, where the screen is
not visible. Hence: refuse up front on a bad state, and confirm afterwards that
the pane actually changed.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app
from ctb_dashboard.session_readiness import (
    classify_readiness,
    is_shell,
)
from ctb_dashboard.state_detector import SessionState

_SECRET = "confirm-secret"
AUTH = {"X-CTB-Secret": _SECRET}

CLAUDE_SCREEN = "\n".join([
    "· Thinking…",
    "╭──────────────────────────────────────╮",
    "│ >                                    │",
    "╰──────────────────────────────────────╯",
])
SHELL_SCREEN = "\n".join([
    "total 24",
    "drwxr-xr-x. 3 kyuwon kyuwon 4096 Jul 30 18:00 .",
    "[kyuwon@arl claude-ops]$ ",
])


# --- pure readiness classification -----------------------------------------

def test_idle_claude_session_can_send():
    can, reason, _ = classify_readiness(SessionState.IDLE, CLAUDE_SCREEN, "claude")
    assert (can, reason) == (True, "ready")


def test_working_is_refused():
    can, reason, msg = classify_readiness(SessionState.WORKING, CLAUDE_SCREEN, "claude")
    assert can is False
    assert reason == "working"
    assert msg


def test_awaiting_choice_is_refused_and_points_at_key_sending():
    can, reason, msg = classify_readiness(SessionState.WAITING_INPUT, CLAUDE_SCREEN, "claude")
    assert can is False
    assert reason == "awaiting_choice"
    assert "키" in msg, "should tell the user to send a key instead"


def test_shell_is_refused_even_though_state_looks_idle():
    """A bare shell reads as IDLE to the detector; the pane command is what catches it."""
    can, reason, _ = classify_readiness(SessionState.IDLE, SHELL_SCREEN, "bash")
    assert (can, reason) == (False, "shell")


@pytest.mark.parametrize("cmd", ["bash", "zsh", "sh", "fish", "-bash", "BASH"])
def test_every_shell_flavour_is_refused(cmd):
    can, reason, _ = classify_readiness(SessionState.IDLE, SHELL_SCREEN, cmd)
    assert (can, reason) == (False, "shell")


@pytest.mark.parametrize("cmd", ["claude", "node", "python3", "uv", "vim"])
def test_non_shell_commands_are_allowed(cmd):
    """Denylist, not allowlist -- a tool we have not heard of must not block work."""
    can, _, _ = classify_readiness(SessionState.IDLE, CLAUDE_SCREEN, cmd)
    assert can is True


def test_unavailable_pane_command_does_not_block():
    """A failed tmux query is not evidence of a shell."""
    assert classify_readiness(SessionState.IDLE, CLAUDE_SCREEN, None)[0] is True
    assert classify_readiness(SessionState.IDLE, CLAUDE_SCREEN, "")[0] is True


# --- pane_current_command reports the process group leader -------------------
#
# Field incident (2026-08-06): sends from the phone were refused as 'shell' on
# sessions where Claude was plainly running and drawing its UI. tmux's
# pane_current_command names the foreground process *group leader*, and when
# claude ends up in the same group as the bash that launched it, that leader is
# bash. Ten live sessions were blocked this way; the audit log shows four
# refusals in five minutes on one of them.
#
# So the pane command alone cannot decide this. A claude process running in the
# pane is a fact that outranks the reported name.

def test_a_shell_name_is_not_a_shell_when_claude_runs_in_the_pane():
    can, reason, _ = classify_readiness(
        SessionState.IDLE, CLAUDE_SCREEN, "bash", claude_running=True)
    assert (can, reason) == (True, "ready"), (
        "blocked a session that has Claude running in it"
    )


def test_a_shell_with_no_claude_process_is_still_refused():
    """The guard has to keep working: this is the case it exists for."""
    can, reason, _ = classify_readiness(
        SessionState.IDLE, SHELL_SCREEN, "bash", claude_running=False)
    assert (can, reason) == (False, "shell")


def test_claude_running_is_assumed_false_when_not_supplied():
    """Callers that never learned about this must not accidentally open it up."""
    can, reason, _ = classify_readiness(SessionState.IDLE, SHELL_SCREEN, "bash")
    assert (can, reason) == (False, "shell")


def test_a_busy_session_is_still_refused_even_with_claude_running():
    """The process check answers 'is this a shell', not 'is this a good time'."""
    can, reason, _ = classify_readiness(
        SessionState.WORKING, CLAUDE_SCREEN, "bash", claude_running=True)
    assert (can, reason) == (False, "working")


def test_real_claude_screen_is_not_mistaken_for_a_shell():
    """Regression: the first implementation guessed the wrong glyphs.

    Claude Code draws '❯' and └┴┘ box characters, not the ╭╰ set that was
    assumed, so every live session was refused as 'shell'. Captured from a real
    pane; the decision must not depend on these characters at all now.
    """
    real = "\n".join([
        "  └────────┴──────────┘",
        "",
        "────────────────────────────",
        "❯ 뭐를 위한",
        "────────────────────────────",
        "  [OMC#4.14.1] | Model: Opus 5 | ctx:26%",
        "  ⏵⏵ bypass permissions on (shift+tab to cycle)",
    ])
    can, reason, _ = classify_readiness(SessionState.IDLE, real, "claude")
    assert (can, reason) == (True, "ready"), "a real Claude pane must be sendable"


@pytest.mark.parametrize("state", [
    SessionState.ERROR,
    SessionState.CONTEXT_LIMIT,
    SessionState.STUCK_AFTER_AGENT,
])
def test_broken_states_are_refused(state):
    can, reason, _ = classify_readiness(state, CLAUDE_SCREEN, "claude")
    assert can is False
    assert reason == state.value


def test_unknown_state_is_allowed_when_ui_is_present():
    """Transient read failures must not brick remote control."""
    can, _, _ = classify_readiness(SessionState.UNKNOWN, CLAUDE_SCREEN, "claude")
    assert can is True


def test_is_shell_classification():
    assert is_shell("bash") is True
    assert is_shell("claude") is False
    assert is_shell(None) is False
    assert is_shell("") is False


# --- endpoint behaviour -----------------------------------------------------

class FakeAnalyzer:
    def __init__(self, state, screens):
        self.state = state
        self.screens = list(screens)

    def get_state(self, name, path=None, use_cache=True):
        return self.state

    def get_screen_content(self, name, use_cache=True):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: True)
    monkeypatch.setattr(_srv, "send_prompt", lambda name, text: None)
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    monkeypatch.setattr(_srv, "pane_command", lambda name: "claude")

    def install(state, screens):
        monkeypatch.setattr(_srv, "_state_analyzer", FakeAnalyzer(state, screens))
        return TestClient(app)

    return install


def test_refuses_with_409_and_reports_state(wire):
    client = wire(SessionState.WORKING, [CLAUDE_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "refused"
    assert body["reason"] == "working"
    assert body["state"] == "working"
    assert body["message"]


def test_refusal_happens_before_anything_is_sent(wire, monkeypatch):
    sent = []
    monkeypatch.setattr(_srv, "send_prompt", lambda n, t: sent.append(t))
    client = wire(SessionState.WORKING, [CLAUDE_SCREEN])
    client.post("/api/sessions/claude_demo/prompt", json={"text": "hi"}, headers=AUTH)
    assert sent == []


def test_confirmed_true_when_screen_changes(wire):
    client = wire(SessionState.IDLE, [CLAUDE_SCREEN, CLAUDE_SCREEN + "\nhi"])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["confirmed"] is True


def test_confirmed_false_when_screen_is_unchanged(wire):
    """Reported honestly rather than dressed up as success."""
    client = wire(SessionState.IDLE, [CLAUDE_SCREEN, CLAUDE_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["confirmed"] is False


def test_shell_session_is_refused_end_to_end(wire, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    client = wire(SessionState.IDLE, [SHELL_SCREEN])
    r = client.post("/api/sessions/claude_demo/prompt",
                    json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "shell"
