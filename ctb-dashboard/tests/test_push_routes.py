"""The HTTP surface a phone uses to opt in, and the fan-out that follows.

Pushes follow the same rule the in-page alerts already use -- pinned sessions
only, with a cooldown -- because 71 sessions completing all day is not a
notification anyone wants on a lock screen.
"""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ctb_dashboard import push as push_mod
from ctb_dashboard import server

SECRET = "test-secret"
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CTB_CONTROL_SECRET", SECRET)
    monkeypatch.setattr(server, "_CONTROL_SECRET", SECRET, raising=False)
    monkeypatch.setattr(push_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(push_mod, "_KEY_PATH", tmp_path / "vapid.json")
    monkeypatch.setattr(push_mod, "_SUBS_PATH", tmp_path / "subscriptions.json")
    push_mod._reset_for_tests()
    return TestClient(server.app)


def _auth():
    return {"X-CTB-Secret": SECRET}


# --- opting in --------------------------------------------------------------

def test_the_public_key_is_readable_without_a_token(client):
    """The browser needs it before it can prove anything, and it is public."""
    r = client.get("/api/push/public-key")
    assert r.status_code == 200
    assert r.json()["key"]


def test_subscribing_requires_the_control_token(client):
    r = client.post("/api/push/subscribe", json=SUB)
    assert r.status_code == 403
    assert push_mod.subscriptions() == []


def test_subscribing_stores_the_endpoint(client):
    r = client.post("/api/push/subscribe", json=SUB, headers=_auth())
    assert r.status_code == 200
    assert [s["endpoint"] for s in push_mod.subscriptions()] == [SUB["endpoint"]]


def test_a_subscription_without_an_endpoint_is_refused(client):
    r = client.post("/api/push/subscribe", json={"keys": {}}, headers=_auth())
    assert r.status_code == 422
    assert push_mod.subscriptions() == []


@pytest.mark.parametrize("endpoint", [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://127.0.0.1:8420/api/pinned",           # back into ourselves
    "file:///etc/passwd",
    "ftp://example.com/x",
])
def test_only_https_endpoints_are_accepted(client, endpoint):
    """The stored endpoint is a URL this server will POST to on every
    completion. A real push service is always https; anything else is someone
    aiming our outbound requests somewhere they chose."""
    r = client.post("/api/push/subscribe",
                    json={"endpoint": endpoint, "keys": {}}, headers=_auth())
    assert r.status_code == 422, endpoint
    assert push_mod.subscriptions() == []


def test_unsubscribing_removes_it(client):
    client.post("/api/push/subscribe", json=SUB, headers=_auth())
    r = client.post("/api/push/unsubscribe",
                    json={"endpoint": SUB["endpoint"]}, headers=_auth())
    assert r.status_code == 200
    assert push_mod.subscriptions() == []


# --- who gets pushed --------------------------------------------------------

def _completion(name, when=None):
    return {"name": name, "state": "idle", "completed_at": when or time.time()}


def test_a_pinned_session_completing_is_pushed(client):
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", return_value=1) as notify:
        server._push_completions([_completion("claude_a")])
    notify.assert_called_once()
    assert notify.call_args.args[0] == "claude_a"


def test_nothing_is_pushed_when_nothing_is_pinned(client):
    with patch.object(server, "pinned_session_names", return_value=set()), \
         patch.object(push_mod, "notify") as notify:
        server._push_completions([_completion("claude_b")])
    notify.assert_not_called()


def test_only_the_pinned_session_is_pushed(client):
    """The case that matters: some sessions are pinned, this one is not.

    Testing only against an empty pin set proves nothing -- the code returns
    early on that, so dropping the per-session check still passes.
    """
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", return_value=1) as notify:
        server._push_completions([_completion("claude_a"), _completion("claude_b")])
    assert [c.args[0] for c in notify.call_args_list] == ["claude_a"], (
        "an unpinned session was pushed; with 71 sessions that is the lock screen"
    )


def test_the_same_completion_is_pushed_once(client):
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", return_value=1) as notify:
        entry = _completion("claude_a")
        server._push_completions([entry])
        server._push_completions([entry])       # the next poll sees it again
    assert notify.call_count == 1


def test_a_later_completion_of_the_same_session_is_pushed_again(client):
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", return_value=1) as notify:
        server._push_completions([_completion("claude_a", time.time() - 600)])
        server._push_completions([_completion("claude_a", time.time())])
    assert notify.call_count == 2


def test_a_session_with_no_completion_is_not_pushed(client):
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify") as notify:
        server._push_completions([{"name": "claude_a", "state": "working",
                                   "completed_at": None}])
    notify.assert_not_called()


def test_a_push_failure_does_not_break_the_poll(client):
    """Polling drives the whole UI; a dead push service must not take it down."""
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", side_effect=RuntimeError("boom")):
        server._push_completions([_completion("claude_a")])   # must not raise


# --- the alerts toggle must not depend on push succeeding ---------------------
#
# Reported (2026-08-07): switching alerts on left the button showing OFF. iOS
# exposes window.Notification only inside an installed Home Screen PWA, so in a
# Safari tab the unguarded reference in subscribeToPush threw, and the click
# handler never reached the lines that store and repaint the state. The switch
# records what the user chose; subscribing is a consequence of it, not a
# precondition.

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "src" / "ctb_dashboard" / "templates" / "index.html"


def _toggle_handler() -> str:
    s = INDEX.read_text()
    start = s.index("btnNotif.addEventListener('click'")
    return s[start:s.index("\n    });", start)]


def test_the_toggle_is_recorded_before_any_awaiting():
    handler = _toggle_handler()
    persist = handler.index("localStorage.setItem(NOTIF_KEY")
    assert "await" not in handler[:persist], (
        "an await before persisting lets a failure leave the button lying"
    )
    assert handler.index("updateNotifBtn()") < handler.index("subscribeToPush"), (
        "repaint before subscribing, not after"
    )


def test_subscription_failures_cannot_escape_the_toggle():
    assert "catch" in _toggle_handler()


def test_notification_is_never_touched_unguarded():
    """Every read of it must be behind an existence check."""
    s = INDEX.read_text()
    body = s[s.index("async function subscribeToPush"):]
    body = body[:body.index("async function unsubscribeFromPush")]
    guard = body.index("'Notification' in window")
    assert guard < body.index("Notification.permission"), (
        "Notification.permission is read before checking the API exists"
    )
