"""Mutating endpoints must be fail-closed.

Before this, the dashboard shipped a fail-open check: focus-session only
verified X-CTB-Secret *if* CTB_FOCUS_SECRET happened to be set, and the
delete endpoint had no check at all. In production the secret was never
injected into the service environment, so every control endpoint was
effectively open to anyone who could reach port 8420.

Read endpoints stay open on purpose -- the dashboard is a monitor first, and
gating GETs would break the VSCode webview, whose portMapping proxy only
forwards GET.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app

_SECRET = "control-secret-under-test"

# Every route that changes state, with a minimal valid body.
MUTATING = [
    ("/api/sessions/some-session/delete", {"force": False}),
    ("/api/pinned", {"sessions": []}),
    ("/api/focus-session", {"session": "some-session"}),
    ("/api/sessions/restore", {}),
]


@pytest.fixture(autouse=True)
def _no_real_tmux(monkeypatch, tmp_path):
    """These tests check the gate, not the operation behind it.

    Without this they ran the operation for real: the focus case executed
    `tmux switch-client` against the live server -- creating a session called
    some-session, starting Claude in it, and yanking the terminal out from
    under whoever was working -- and the delete case removed it again. Every
    suite run did it, which is exactly the session that kept appearing and
    disappearing.
    """
    monkeypatch.setattr(_srv, "session_exists", lambda name: False)
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: set())
    monkeypatch.setattr(_srv, "send_prompt", lambda *a, **k: None)
    monkeypatch.setattr(_srv, "send_key", lambda *a, **k: None)
    monkeypatch.setattr(_srv, "send_interrupt", lambda *a, **k: None)
    monkeypatch.setattr(_srv.subprocess, "run", _refuse_subprocess)
    monkeypatch.setattr(_srv.subprocess, "Popen", _refuse_subprocess)
    # /api/pinned does not shell out, so stubbing tmux did not protect it: the
    # gate test posts an empty body, PinnedRequest fills in four empty
    # quadrants, and that was written straight over the real pin file. Every
    # suite run wiped the user's pins.
    monkeypatch.setattr(_srv, "_PINNED_PERSIST_PATH", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(_srv, "_pinned_state", {"Q1": [], "Q2": [], "Q3": [], "Q4": []})


def _refuse_subprocess(*a, **k):
    raise AssertionError(f"a gate test reached the system: {a[:1]}")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    return TestClient(app)


@pytest.fixture
def client_no_secret(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", "")
    return TestClient(app)


@pytest.mark.parametrize("path,body", MUTATING)
def test_mutating_without_token_is_rejected(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 403, f"{path} accepted an unauthenticated write"


@pytest.mark.parametrize("path,body", MUTATING)
def test_mutating_with_wrong_token_is_rejected(client, path, body):
    r = client.post(path, json=body, headers={"X-CTB-Secret": "wrong"})
    assert r.status_code == 403, f"{path} accepted a bad token"


@pytest.mark.parametrize("path,body", MUTATING)
def test_mutating_with_correct_token_passes_the_gate(client, path, body):
    """The gate must not be what rejects the request; anything but 403 is fine."""
    r = client.post(path, json=body, headers={"X-CTB-Secret": _SECRET})
    assert r.status_code != 403, f"{path} rejected a valid token"


@pytest.mark.parametrize("path,body", MUTATING)
def test_mutating_disabled_when_no_secret_configured(client_no_secret, path, body):
    """Fail-closed: an unset secret disables writes rather than allowing them."""
    r = client_no_secret.post(path, json=body, headers={"X-CTB-Secret": "anything"})
    assert r.status_code == 503, f"{path} was reachable with no secret configured"


@pytest.mark.parametrize("path", [
    "/api/health",
    "/api/sessions",
    "/api/pinned",
    "/api/session-ticket-links",
])
def test_read_endpoints_stay_open(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} should not require a token"


def test_read_endpoints_open_even_with_no_secret(client_no_secret):
    """Monitoring must survive a missing secret; only writes are disabled."""
    assert client_no_secret.get("/api/health").status_code == 200
    assert client_no_secret.get("/api/sessions").status_code == 200


def test_legacy_focus_secret_is_still_honoured(monkeypatch):
    """Don't strand a deployment that only set the old variable name."""
    monkeypatch.delenv("CTB_CONTROL_SECRET", raising=False)
    monkeypatch.setenv("CTB_FOCUS_SECRET", "legacy-value")
    assert _srv._resolve_control_secret() == "legacy-value"


def test_new_variable_wins_over_legacy(monkeypatch):
    monkeypatch.setenv("CTB_CONTROL_SECRET", "new-value")
    monkeypatch.setenv("CTB_FOCUS_SECRET", "legacy-value")
    assert _srv._resolve_control_secret() == "new-value"


def test_no_secret_resolves_empty(monkeypatch):
    monkeypatch.delenv("CTB_CONTROL_SECRET", raising=False)
    monkeypatch.delenv("CTB_FOCUS_SECRET", raising=False)
    assert _srv._resolve_control_secret() == ""


def test_token_comparison_is_constant_time():
    """Guard against reintroducing a plain == comparison."""
    import inspect

    src = inspect.getsource(_srv.require_control_token)
    assert "compare_digest" in src
