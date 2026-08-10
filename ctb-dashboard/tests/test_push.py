"""Web Push: the only way a completion reaches a phone whose screen is off.

The dashboard's existing alerts are fired by the open page, so a backgrounded
iOS PWA gets nothing. These cover the parts that decide whether a push is
actually deliverable: a stable key pair, a subscription store that survives a
restart and drops dead endpoints, and a fan-out that does not spam.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ctb_dashboard import push as push_mod


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(push_mod, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(push_mod, "_KEY_PATH", tmp_path / "vapid.json")
    monkeypatch.setattr(push_mod, "_SUBS_PATH", tmp_path / "subscriptions.json")
    # A usable contact, as a real deployment must configure: notify() refuses to
    # send without one rather than let Apple reject it as BadJwtToken.
    monkeypatch.setattr(push_mod, "_SUBJECT", "mailto:ops@example.org")
    push_mod._reset_for_tests()
    return tmp_path


SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}
SUB2 = {"endpoint": "https://push.example/def", "keys": {"p256dh": "x", "auth": "y"}}


# --- keys -------------------------------------------------------------------

def test_keys_are_generated_once_and_reused(store):
    """A new key pair would silently invalidate every existing subscription."""
    first = push_mod.public_key()
    assert first
    push_mod._reset_for_tests()          # as a restart would
    assert push_mod.public_key() == first


def test_private_key_is_not_world_readable(store):
    push_mod.public_key()
    assert oct((store / "vapid.json").stat().st_mode)[-3:] == "600"


def test_public_key_is_url_safe_base64(store):
    """The browser passes it to applicationServerKey verbatim."""
    key = push_mod.public_key()
    assert "+" not in key and "/" not in key and "=" not in key


# --- subscriptions ----------------------------------------------------------

def test_subscription_survives_a_restart(store):
    push_mod.add_subscription(SUB)
    push_mod._reset_for_tests()
    assert [s["endpoint"] for s in push_mod.subscriptions()] == [SUB["endpoint"]]


def test_the_same_endpoint_is_not_stored_twice(store):
    push_mod.add_subscription(SUB)
    push_mod.add_subscription(dict(SUB))
    assert len(push_mod.subscriptions()) == 1


def test_a_subscription_can_be_removed(store):
    push_mod.add_subscription(SUB)
    push_mod.remove_subscription(SUB["endpoint"])
    assert push_mod.subscriptions() == []


def test_a_subscription_without_an_endpoint_is_rejected(store):
    with pytest.raises(ValueError):
        push_mod.add_subscription({"keys": {}})


# --- sending ----------------------------------------------------------------

def test_send_reaches_every_subscriber(store):
    push_mod.add_subscription(SUB)
    push_mod.add_subscription(SUB2)
    with patch.object(push_mod, "webpush") as wp:
        sent = push_mod.notify("claude_demo", "done")
    assert sent == 2
    assert wp.call_count == 2


def test_a_gone_subscription_is_dropped(store):
    """410/404 is the push service saying the phone unsubscribed. Keeping it
    means retrying a dead endpoint on every completion, forever."""
    push_mod.add_subscription(SUB)
    push_mod.add_subscription(SUB2)

    def fail_first(subscription_info, data, vapid_private_key, vapid_claims, **kw):
        if subscription_info["endpoint"] == SUB["endpoint"]:
            raise push_mod.WebPushException("gone", response=MagicMock(status_code=410))

    with patch.object(push_mod, "webpush", side_effect=fail_first):
        push_mod.notify("claude_demo", "done")

    assert [s["endpoint"] for s in push_mod.subscriptions()] == [SUB2["endpoint"]]


def test_a_transient_failure_keeps_the_subscription(store):
    push_mod.add_subscription(SUB)
    with patch.object(push_mod, "webpush",
                      side_effect=push_mod.WebPushException(
                          "boom", response=MagicMock(status_code=500))):
        assert push_mod.notify("claude_demo", "done") == 0
    assert len(push_mod.subscriptions()) == 1, "a 500 is the push service's problem, not ours"


def test_the_payload_carries_what_the_worker_needs(store):
    push_mod.add_subscription(SUB)
    with patch.object(push_mod, "webpush") as wp:
        push_mod.notify("claude_demo", "작업 완료")
    payload = json.loads(wp.call_args.kwargs["data"])
    assert payload["session"] == "claude_demo"
    assert payload["body"] == "작업 완료"
    assert payload["url"].endswith("?session=claude_demo"), "tapping it must open that console"


def test_sending_with_no_subscribers_is_not_an_error(store):
    with patch.object(push_mod, "webpush") as wp:
        assert push_mod.notify("claude_demo", "done") == 0
    wp.assert_not_called()


# --- the contact address is not optional -------------------------------------
#
# Apple rejects every push whose VAPID `sub` is not a routable contact, with a
# flat 403 BadJwtToken. The default was mailto:admin@localhost, which is never
# routable, so an unset CTB_PUSH_SUBJECT produced a push system that subscribed
# fine, reported no error to the phone, and delivered nothing. That is the exact
# silent failure this whole feature kept running into.

def test_an_unroutable_subject_is_rejected_at_startup():
    assert not push_mod._subject_is_usable("mailto:admin@localhost")
    assert not push_mod._subject_is_usable("")
    assert not push_mod._subject_is_usable("kyuwon@example.com")   # no scheme


@pytest.mark.parametrize("subject", [
    "mailto:someone@example.org",
    "https://example.org/contact",
])
def test_a_routable_subject_is_accepted(subject):
    assert push_mod._subject_is_usable(subject)


def test_sending_without_a_usable_subject_does_not_pretend_to_work(store, monkeypatch):
    """Better a logged refusal than a push Apple silently throws away."""
    monkeypatch.setattr(push_mod, "_SUBJECT", "mailto:admin@localhost")
    push_mod.add_subscription(SUB)
    with patch.object(push_mod, "webpush") as wp:
        assert push_mod.notify("claude_demo", "done") == 0
    wp.assert_not_called()
