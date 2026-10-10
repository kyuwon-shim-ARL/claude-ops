"""HTTP contract for shell=True on the prompt endpoint.

Shell mode skips the Claude readiness gate entirely (there is no Claude UI to
read state from) and instead refuses only when Claude itself is in the pane --
the one case where raw text would reach Claude instead of bash.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app

_SECRET = "shell-prompt-secret"
AUTH = {"X-CTB-Secret": _SECRET}


@pytest.fixture
def sent(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo_sh")
    monkeypatch.setattr(_srv, "_SEND_CONFIRM_DELAY", 0)
    calls = []
    monkeypatch.setattr(_srv, "send_shell_line",
                        lambda name, text: calls.append((name, text)))
    # Screen content before/after -- just needs to be non-None and to differ
    # once, so 'confirmed' comes back true without asserting on it elsewhere.
    screens = {"n": 0}

    class _Analyzer:
        def get_screen_content(self, name, use_cache=True):
            screens["n"] += 1
            return f"$ {screens['n']}"

    monkeypatch.setattr(_srv, "_state_analyzer", _Analyzer())
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def test_shell_text_is_sent_when_bash_is_foreground(client, sent, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "echo hi", "shell": True}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "sent"
    assert sent == [("claude_demo_sh", "echo hi")]


@pytest.mark.parametrize("cmd", ["sudo", "su", "ssh", "passwd", "gpg", "mysql",
                                 "psql", "sqlite3", "python", "python3",
                                 "bash", "zsh"])
def test_every_allow_listed_command_is_allowed(client, sent, monkeypatch, cmd):
    monkeypatch.setattr(_srv, "pane_command", lambda name: cmd)
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "secret", "shell": True}, headers=AUTH)
    assert r.status_code == 200, (cmd, r.json())
    assert sent == [("claude_demo_sh", "secret")]


@pytest.mark.parametrize("cmd", ["vim", "less", "tmux", "node", "ruby"])
def test_a_command_off_the_allow_list_is_refused_by_name(client, sent, monkeypatch, cmd):
    """Switched from a deny-list to an allow-list on purpose: naming risk
    tools (vim, tmux, ...) guards against the wrong thing and lets anything
    unanticipated straight through. Anything not explicitly allowed is
    refused, and the refusal names the command."""
    monkeypatch.setattr(_srv, "pane_command", lambda name: cmd)
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "secret", "shell": True}, headers=AUTH)
    assert r.status_code == 409
    body = r.json()
    assert body["reason"] == "command_not_allowed"
    assert cmd in body["message"]
    assert sent == []


def test_claude_as_foreground_command_is_refused(client, sent, monkeypatch):
    """'claude' is simply not on the allow-list -- refused as that, by
    name, before pane_has_claude is even consulted."""
    monkeypatch.setattr(_srv, "pane_command", lambda name: "claude")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: True)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "echo hi", "shell": True}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "command_not_allowed"
    assert sent == []


def test_claude_running_under_a_bash_group_leader_is_refused(client, sent, monkeypatch):
    """pane_command can report 'bash' while claude is the real occupant --
    the same group-leader quirk session_readiness guards against."""
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: True)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "echo hi", "shell": True}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "claude_running"
    assert sent == []


def test_unknown_pane_command_is_refused(client, sent, monkeypatch):
    """pane_command() returning None is 'tmux could not answer', not 'safe
    to assume bash' -- refuse rather than guess."""
    monkeypatch.setattr(_srv, "pane_command", lambda name: None)
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "echo hi", "shell": True}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "unknown_pane"
    assert sent == []


def test_multiline_text_is_rejected(client, sent, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "line one\nline two", "shell": True}, headers=AUTH)
    assert r.status_code == 422
    assert sent == []


def test_trailing_newline_is_accepted_and_stripped(client, sent, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "echo hi\r\n", "shell": True}, headers=AUTH)
    assert r.status_code == 200
    assert sent == [("claude_demo_sh", "echo hi")]


@pytest.mark.parametrize("text", ["echo\x00hi", "echo\x1bhi", "echo\x7fhi", "echo\thi"])
def test_control_characters_are_rejected(client, sent, monkeypatch, text):
    """send-keys -l types raw bytes -- a control character (other than the
    trailing line ending, already stripped) has no business in a line that
    is typed rather than pasted. \\t (tab) is a control character too."""
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": text, "shell": True}, headers=AUTH)
    assert r.status_code == 422
    assert sent == []


def test_empty_text_is_422(client, sent, monkeypatch):
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    r = client.post("/api/sessions/claude_demo_sh/prompt",
                    json={"text": "", "shell": True}, headers=AUTH)
    assert r.status_code == 422
    assert sent == []


def test_non_shell_path_still_refuses_at_a_real_shell(client, sent, monkeypatch):
    """shell=False (the default / every existing caller) keeps today's
    behaviour unchanged -- a bare shell pane refuses a plain prompt."""
    from ctb_dashboard.state_detector import SessionState

    class _ShellAnalyzer:
        def get_state(self, name, path=None, use_cache=True):
            return SessionState.IDLE

        def get_screen_content(self, name, use_cache=True):
            return "$ "

    monkeypatch.setattr(_srv, "_state_analyzer", _ShellAnalyzer())
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    monkeypatch.setattr(_srv, "session_exists", lambda name: True)
    r = client.post("/api/sessions/claude_real/prompt",
                    json={"text": "정리해줘"}, headers=AUTH)
    assert r.status_code == 409
    assert r.json()["reason"] == "shell"
