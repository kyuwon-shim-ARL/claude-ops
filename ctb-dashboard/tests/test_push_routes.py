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


def test_the_switch_distinguishes_armed_from_page_only():
    """ON meaning both "push armed" and "only while this page is open" is what
    made a silent phone look correctly configured."""
    s = INDEX.read_text()
    body = s[s.index("function updateNotifBtn"):]
    body = body[:body.index("\n    }")]
    assert "pushSubscribed" in body, "the label must depend on whether push is armed"
    assert "화면만" in body


def test_every_reason_push_cannot_arm_is_named():
    s = INDEX.read_text()
    body = s[s.index("function pushBlockReason"):]
    body = body[:body.index("\n    }")]
    for check in ("isSecureContext", "serviceWorker", "'Notification' in window",
                  "PushManager", "denied"):
        assert check in body, f"{check} has no explanation"


def test_subscription_attempts_are_audited(client):
    """A phone that never manages to subscribe must not look like one that
    never tried."""
    with patch.object(server, "_audit") as audit:
        client.post("/api/push/subscribe", json=SUB, headers=_auth())
    assert any(c.args[0] == "push_subscribe" and c.args[3] is True
               for c in audit.call_args_list)


def test_a_refused_subscription_is_audited_too(client):
    with patch.object(server, "_audit") as audit:
        client.post("/api/push/subscribe",
                    json={"endpoint": "http://x/y"}, headers=_auth())
    assert any(c.args[0] == "push_subscribe" and c.args[3] is False
               for c in audit.call_args_list)


def test_each_cause_has_a_label_visible_without_tapping():
    """"ON (화면만)" alone still left both sides guessing which of four causes
    it was; the switch has to name the one it hit."""
    s = INDEX.read_text()
    body = s[s.index("function pushBlockReason"):]
    body = body[:body.index("\n    }\n")]
    for short in ("HTTPS 필요", "홈화면 필요", "권한 거부", "미지원"):
        assert short in body, f"no short label for {short}"
    btn = s[s.index("function updateNotifBtn"):]
    btn = btn[:btn.index("\n    }")]
    assert "blocked.short" in btn, "the label must reach the button"


def test_a_pending_permission_is_not_left_unexplained():
    """'default' blocks a subscription exactly as 'denied' does. Naming only
    'denied' sent an unanswered prompt to the meaningless "(화면만)"."""
    s = INDEX.read_text()
    body = s[s.index("function pushBlockReason"):]
    body = body[:body.index("\n    }\n")]
    assert "권한 필요" in body
    assert "!== 'granted'" in body


def test_a_registration_failure_reports_what_it_said():
    """This runs on a phone; a console warning is invisible there."""
    s = INDEX.read_text()
    assert "pushLastError" in s
    sub = s[s.index("async function subscribeToPush"):]
    sub = sub[:sub.index("\n    }")]
    assert "pushLastError =" in sub, "the failure must be recorded, not only logged"
    reason = s[s.index("function pushBlockReason"):]
    reason = reason[:reason.index("\n    }\n")]
    assert "pushLastError" in reason, "and surfaced where the user can read it"


def test_a_stalled_registration_is_not_read_as_a_failure():
    """A pending promise looks identical to a silent failure from outside; the
    phone showed "(화면만)" for both."""
    s = INDEX.read_text()
    btn = s[s.index("function updateNotifBtn"):]
    btn = btn[:btn.index("\n    }")]
    assert "pushBusy" in btn and "등록 중" in btn


def test_every_registration_step_has_a_deadline_and_a_name():
    """Without one, a step that never settles leaves the switch stuck forever
    with nothing to report."""
    s = INDEX.read_text()
    sub = s[s.index("async function subscribeToPush"):]
    sub = sub[:sub.index("\n    }")]
    assert "Promise.race" in sub, "a step that never settles must still time out"
    for stage in ("서비스워커 준비", "기존 구독 조회", "푸시 구독 생성", "서버 등록"):
        assert stage in sub, f"{stage} is unnamed, so a stall there cannot be reported"
    assert "finally" in sub, "the in-flight flag must clear on every path"


# --- the phone reports why registration failed --------------------------------
#
# Four rounds of asking the user to read a label back. The browser already knows
# which step timed out; it should say so where it can be read directly.

def test_a_registration_failure_can_be_reported(client):
    with patch.object(server, "_audit") as audit:
        r = client.post("/api/push/report",
                        json={"stage": "서비스워커 준비", "error": "응답 없음"},
                        headers=_auth())
    assert r.status_code == 200
    assert any(c.args[0] == "push_report" for c in audit.call_args_list)


def test_reporting_requires_the_control_token(client):
    assert client.post("/api/push/report", json={"stage": "x"}).status_code == 403


def test_the_client_reports_what_it_caught():
    s = INDEX.read_text()
    helper = s[s.index("function reportPushFailure"):]
    helper = helper[:helper.index("\n    }")]
    assert "/api/push/report" in helper, "the failure must be sent, not only shown"
    sub = s[s.index("async function subscribeToPush"):]
    sub = sub[:sub.index("\n    }\n")]
    assert "reportPushFailure" in sub


def test_a_rejected_subscribe_is_reported_too():
    """VSCode showed ON (등록 실패) and the server received no report at all:
    the report was only sent from the catch, so a non-ok response set the error
    and told nobody."""
    s = INDEX.read_text()
    sub = s[s.index("async function subscribeToPush"):]
    sub = sub[:sub.index("\n    }")]
    ok_branch = sub[sub.index("if (!res.ok)"):sub.index("} catch")]
    assert "reportPushFailure" in ok_branch, "a refused subscribe must be reported"


def test_a_403_says_it_is_the_token():
    """'서버 응답 403' names a number; the reader needs the cause."""
    s = INDEX.read_text()
    sub = s[s.index("async function subscribeToPush"):]
    sub = sub[:sub.index("\n    }")]
    assert "403" in sub and "토큰" in sub


# --- what finished, not just that something did -------------------------------
#
# "wte 세션이 작업을 마쳤습니다" told you which session and nothing else, which
# with fifteen pinned sessions is barely a signal. Everything needed is already
# computed for the card: the prompt, the reply, progress, pending work.

def _body(**over):
    entry = {"name": "claude_wte", "state": "idle", "completed_at": 1.0,
             "last_prompt": "", "last_reply": "", "work_context": "",
             "progress": None, "pending_count": None, "context_percent": None}
    entry.update(over)
    return server._completion_body(entry)


def test_the_reply_is_what_it_leads_with():
    body = _body(last_reply="전부 완료했습니다. gates PASS, JSON 무결성 OK.")
    assert "gates PASS" in body


def test_the_prompt_says_which_job_this_was():
    body = _body(last_prompt="테스트 다 돌리고 배포해줘", last_reply="배포 완료")
    assert "테스트 다 돌리고 배포해줘" in body
    assert body.index("테스트 다 돌리고") < body.index("배포 완료"), "ask first, outcome second"


def test_a_tool_call_is_not_an_outcome():
    """last_reply is sometimes the tail of a tool invocation, which says nothing
    about what was accomplished."""
    body = _body(last_prompt="로그 확인해줘", last_reply="Bash(cd /tmp/x && tail -n 50 out.log)")
    assert "Bash(" not in body
    assert "로그 확인해줘" in body


def test_progress_and_pending_work_are_carried():
    body = _body(last_reply="1단계 끝", progress=[2, 5], pending_count=3)
    assert "2/5" in body
    assert "3" in body


def test_context_is_mentioned_only_when_it_is_nearly_full():
    assert "ctx" not in _body(last_reply="끝", context_percent=40).lower()
    assert "88" in _body(last_reply="끝", context_percent=88)


def test_a_session_with_nothing_to_say_still_gets_a_body():
    assert _body().strip()


def test_the_body_stays_short_enough_for_a_lock_screen():
    body = _body(last_prompt="가" * 400, last_reply="나" * 400)
    assert len(body) < 320, "a lock screen shows a few lines, not an essay"


def test_the_completion_push_uses_it():
    with patch.object(server, "pinned_session_names", return_value={"claude_a"}), \
         patch.object(push_mod, "notify", return_value=1) as notify:
        server._push_completions([{"name": "claude_a", "state": "idle",
                                   "completed_at": 1.0, "last_reply": "빌드 성공"}])
    assert "빌드 성공" in notify.call_args.args[1]


def test_the_vscode_webview_says_why_it_cannot_arm_push():
    """Its port proxy forwards only GET, so subscribe and even the failure
    report never leave the webview — the audit log has no write from it at all.
    'ON (등록 실패)' was the result, which explains nothing and suggests a fault
    that could be fixed. The page can detect this context exactly:
    acquireVsCodeApi exists only inside a webview."""
    s = INDEX.read_text()
    body = s[s.index("function pushBlockReason"):]
    body = body[:body.index("\n    }\n")]
    # Detected by the API's presence rather than the _vscodeApi const, which is
    # declared further down the file than this runs.
    assert "acquireVsCodeApi" in body
    assert "VSCode" in body
