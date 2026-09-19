"""Byte-based transport limit on /api/sessions/{name}/prompt.

Replaces the deleted destructive-command pattern screening. That screening
used a 10000-CHARACTER cap and reported any over-long text as "matches a
destructive-command pattern" -- so a 12KB JSON payload of ordinary prose was
rejected with a message about destructive commands. This is the direct
regression test for that bug, plus coverage that the new limit is
byte-based (Korean is 3 bytes/char, so a char-based cap is wrong in both
directions).

The old pattern list also matched prose, not commands (`\\bsudo\\s+` blocks
"sudo 없이 uv 설치하는 방법 알려줘"). Those strings must now get past the
size gate.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
import ctb_dashboard.session_input as _session_input
from ctb_dashboard.server import app, _MAX_PROMPT_BYTES

_SECRET = "prompt-size-secret"
AUTH = {"X-CTB-Secret": _SECRET}


@pytest.fixture
def prompt(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    # Everything below the size gate reaches tmux; stub it out so accept-path
    # cases don't touch a live session. What classify_readiness decides
    # afterward is not this test's concern -- only that the size gate let it
    # through.
    monkeypatch.setattr(_srv, "send_prompt", lambda *a, **k: None)
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    monkeypatch.setattr(
        _srv._state_analyzer, "get_state", lambda *a, **k: _srv.SessionState.UNKNOWN
    )
    monkeypatch.setattr(
        _srv._state_analyzer, "get_screen_content", lambda *a, **k: ""
    )
    audited = []
    monkeypatch.setattr(
        _srv,
        "_audit",
        lambda endpoint, name, client, ok, reason=None: audited.append(reason),
    )
    return audited


@pytest.fixture
def client():
    return TestClient(app)


def _post(client, text):
    return client.post(
        "/api/sessions/claude_demo/prompt", json={"text": text}, headers=AUTH
    )


def test_12kb_payload_is_accepted_by_size_gate(client, prompt):
    """Direct regression test: a 12KB prose blob is not a destructive command."""
    r = _post(client, "가" * 4000)  # 4000 chars * 3 bytes = 12KB
    assert r.status_code != 413
    assert "too_long" not in prompt


@pytest.mark.parametrize(
    "text",
    [
        "sudo 없이 uv 설치하는 방법 알려줘",
        "chown 설정이 /data 에서 꼬였는데 확인해줘",
    ],
)
def test_prose_that_matched_old_patterns_is_accepted(client, prompt, text):
    r = _post(client, text)
    assert r.status_code != 413
    assert "too_long" not in prompt


def test_oversize_utf8_text_is_rejected(client, prompt):
    text = "a" * (_MAX_PROMPT_BYTES + 1)
    r = _post(client, text)
    assert r.status_code == 413
    assert prompt[-1] == "too_long"


def test_korean_text_under_char_limit_but_over_byte_limit_is_rejected(client, prompt):
    """Character count is well below 64*1024, but byte count is not.

    Fails against a character-based limit, since len(text) here is far below
    _MAX_PROMPT_BYTES even though the UTF-8 encoding is not.
    """
    char_count = _MAX_PROMPT_BYTES // 2 + 100  # 3 bytes/char -> well over the byte cap
    text = "가" * char_count
    assert char_count < _MAX_PROMPT_BYTES
    assert len(text.encode("utf-8")) > _MAX_PROMPT_BYTES

    r = _post(client, text)
    assert r.status_code == 413
    assert prompt[-1] == "too_long"


def test_text_at_exact_byte_limit_is_accepted(client, prompt):
    text = "a" * _MAX_PROMPT_BYTES
    assert len(text.encode("utf-8")) == _MAX_PROMPT_BYTES

    r = _post(client, text)
    assert r.status_code != 413
    assert "too_long" not in prompt


class _FakeTmuxRun:
    """Records argv and reports success, without touching real tmux."""

    def __call__(self, argv, **kwargs):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()


@pytest.fixture
def real_send(monkeypatch):
    """Exercise the real send_prompt (and its own _validate), not a stub.

    The other fixture in this file replaces `_srv.send_prompt` with a no-op,
    which means it can never catch a second, independent length limit living
    inside session_input.send_prompt itself -- exactly the bug that slipped
    through: server.py's 413 gate was raised to 64 KiB, but
    session_input.MAX_PROMPT_LENGTH (character-based, 4000) still bound
    first and rejected with a 422 carrying a "chars, over the ... limit"
    detail. This fixture instead stubs tmux at the subprocess boundary so
    the real send_prompt runs end to end.
    """
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: name == "claude_demo")
    monkeypatch.setattr(_session_input, "subprocess", type("S", (), {
        "run": _FakeTmuxRun(),
        "TimeoutExpired": Exception,
    }))
    monkeypatch.setattr(_srv, "pane_command", lambda name: "bash")
    monkeypatch.setattr(_srv, "pane_has_claude", lambda name: False)
    monkeypatch.setattr(
        _srv._state_analyzer, "get_state", lambda *a, **k: _srv.SessionState.UNKNOWN
    )
    monkeypatch.setattr(
        _srv._state_analyzer, "get_screen_content", lambda *a, **k: ""
    )
    audited = []
    monkeypatch.setattr(
        _srv,
        "_audit",
        lambda endpoint, name, client, ok, reason=None: audited.append(reason),
    )
    return audited


def test_reported_bug_12900_byte_json_payload_is_not_blocked(client, real_send):
    """The actual reported bug: a ~12,900-byte prompt sent as JSON, through
    the real send_prompt path (both length checks live).

    Must not come back 422 with a length-related detail (the inner
    character-based cap that was still 4000), and must not come back 413
    (it's under the 64 KiB transport limit).
    """
    text = "가" * 4300  # 4300 chars * 3 bytes/char = 12,900 bytes
    assert len(text.encode("utf-8")) == 12900

    r = _post(client, text)

    assert r.status_code != 413
    assert "too_long" not in real_send
    if r.status_code == 422:
        detail = str(r.json().get("detail", ""))
        assert "chars, over the" not in detail
        assert "limit" not in detail
