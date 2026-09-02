"""Web Push, so a completion reaches a phone whose screen is off.

The dashboard's other alerts are fired by the open page, which means a
backgrounded iOS PWA never sees them. A push is delivered by Apple to the
service worker instead, so the app does not have to be running.

Two pieces of state live on disk, both under ``~/.claude-ops``:

* the VAPID key pair -- regenerating it would silently invalidate every
  subscription already stored on a phone, so it is written once and reused.
* the subscriptions themselves -- one per browser that opted in. They are not
  secrets in the credential sense, but the private key next to them is, so the
  directory is created 0700 and the key file 0600.

The keys are generated on first use rather than configured, unlike
CTB_CONTROL_SECRET: nothing about them ever needs a human, and a missing
notification is a worse failure than one more file.
"""

import base64
import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

_STATE_DIR = Path.home() / ".claude-ops"
_KEY_PATH = _STATE_DIR / "vapid.json"
_SUBS_PATH = _STATE_DIR / "subscriptions.json"

# Apple requires a contactable subject on the VAPID claim, and enforces it: a
# sub that is not routable comes back as a flat 403 BadJwtToken. The old default
# of mailto:admin@localhost satisfied nothing and failed exactly that way --
# subscriptions registered, the phone showed no error, and not one push
# arrived. So an unusable subject is refused here rather than at Apple.
_SUBJECT = os.environ.get("CTB_PUSH_SUBJECT", "")


def _subject_is_usable(subject: str) -> bool:
    """A VAPID sub must be a mailto: or https: URI someone could answer."""
    if not subject:
        return False
    if subject.startswith("mailto:"):
        address = subject[len("mailto:"):]
        host = address.rpartition("@")[2]
        return "@" in address and "." in host and not host.endswith(".localhost")
    if subject.startswith("https://"):
        return len(subject) > len("https://")
    return False
# Where a tapped notification should land. Without an absolute origin the
# service worker cannot focus the right client.
_BASE_URL = os.environ.get("CTB_DASHBOARD_URL", "").rstrip("/")

_lock = threading.Lock()
_keys: Optional[Dict[str, str]] = None
_subs: Optional[List[dict]] = None


def _reset_for_tests() -> None:
    """Drop the in-memory caches so a test can simulate a restart."""
    global _keys, _subs
    with _lock:
        _keys = None
        _subs = None
        _failures.clear()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _ensure_dir() -> None:
    _STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def _load_keys() -> Dict[str, str]:
    global _keys
    if _keys is not None:
        return _keys
    _ensure_dir()
    try:
        _keys = json.loads(_KEY_PATH.read_text())
        return _keys
    except Exception:
        pass

    # VAPID is an ECDSA P-256 key pair; generate it directly rather than pull
    # in another wrapper for one call.
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key()
    _keys = {
        # pywebpush wants the private key as DER, base64url, no padding.
        "private": _b64(priv.private_numbers().private_value.to_bytes(32, "big")),
        "public": _b64(pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )),
    }
    tmp = _KEY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_keys))
    os.chmod(tmp, 0o600)
    os.replace(tmp, _KEY_PATH)
    logger.info("Generated a VAPID key pair at %s", _KEY_PATH)
    return _keys


def public_key() -> str:
    """The applicationServerKey the browser subscribes with."""
    with _lock:
        return _load_keys()["public"]


def _private_key() -> str:
    with _lock:
        return _load_keys()["private"]


def _load_subs() -> List[dict]:
    global _subs
    if _subs is not None:
        return _subs
    try:
        _subs = json.loads(_SUBS_PATH.read_text())
        if not isinstance(_subs, list):
            _subs = []
    except Exception:
        _subs = []
    return _subs


def _save_subs() -> None:
    _ensure_dir()
    tmp = _SUBS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_subs or []))
    os.chmod(tmp, 0o600)
    os.replace(tmp, _SUBS_PATH)


def subscriptions() -> List[dict]:
    with _lock:
        return list(_load_subs())


def add_subscription(sub: dict) -> None:
    """Store one browser's subscription. Re-subscribing is not an error."""
    endpoint = (sub or {}).get("endpoint")
    if not endpoint:
        raise ValueError("subscription has no endpoint")
    with _lock:
        subs = _load_subs()
        for existing in subs:
            if existing.get("endpoint") == endpoint:
                existing.update(sub)
                break
        else:
            subs.append(sub)
        _save_subs()


def remove_subscription(endpoint: str) -> None:
    global _subs
    with _lock:
        subs = _load_subs()
        _subs = [s for s in subs if s.get("endpoint") != endpoint]
        _save_subs()


def notify(session: str, body: str, title: str = "Claude 작업 완료") -> int:
    """Push one completion to every subscribed browser.

    Returns how many were delivered. Endpoints the push service reports as gone
    are dropped: keeping them means retrying a dead phone forever.
    """
    global _subs
    with _lock:
        subs = list(_load_subs())
    if not subs:
        return 0
    if not _subject_is_usable(_SUBJECT):
        logger.error(
            "CTB_PUSH_SUBJECT is %r, which Apple will refuse (BadJwtToken). "
            "Set it to a mailto: or https: contact you control; no push sent.",
            _SUBJECT,
        )
        return 0

    url = f"{_BASE_URL}/?session={session}" if _BASE_URL else f"/?session={session}"
    payload = json.dumps({
        "title": title,
        "body": body,
        "session": session,
        "url": url,
    }, ensure_ascii=False)

    private = _private_key()
    delivered, dead = 0, []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": _SUBJECT},
                # Sending happens inside the poll cycle, so a push service
                # having a bad day delays every session's data by this much
                # per subscriber. Keep it well under the poll interval.
                timeout=5,
            )
            delivered += 1
            _failures.pop(sub.get("endpoint") or "", None)
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                dead.append(sub.get("endpoint"))
                logger.info("Dropping a push subscription the service says is gone")
            else:
                _note_failure(sub, dead, status, e)
        except Exception as e:  # network, DNS, anything else transient
            _note_failure(sub, dead, None, e)

    if dead:
        with _lock:
            _subs = [s for s in _load_subs() if s.get("endpoint") not in dead]
            _save_subs()
    return delivered


# 404 and 410 are the push services saying "this one is gone", and those are
# dropped on the spot. Everything else -- a 400 from Apple for a token it no
# longer likes, a name that stops resolving -- looks identical to a service
# having a bad minute, so it cannot be trusted once. But it must not be
# forgiven forever either: a subscription that fails every single time is dead
# in every way that matters, and retrying it delays every other subscriber
# inside the poll cycle. So: consecutive failures, counted per endpoint, and
# dropped at five. A single success clears the count.
#
# In memory on purpose. A restart forgets, and a genuinely dead endpoint simply
# earns its five again within the hour; a subscription is not worth a schema
# change and a migration to remember a grudge across restarts.
_MAX_CONSECUTIVE_FAILURES = 5
_failures: dict = {}


def _note_failure(sub: dict, dead: list, status, err) -> None:
    endpoint = sub.get("endpoint") or ""
    n = _failures.get(endpoint, 0) + 1
    _failures[endpoint] = n
    if n >= _MAX_CONSECUTIVE_FAILURES:
        dead.append(endpoint)
        _failures.pop(endpoint, None)
        logger.info("Dropping a push subscription after %d consecutive failures: %s",
                    n, _host_of(endpoint))
    else:
        logger.warning("Push failed (%s, %d in a row) for %s: %s",
                       status, n, _host_of(endpoint), err)


def _host_of(endpoint: str) -> str:
    """The push service, for a log line that says which subscriber failed.

    Never the whole endpoint: the path is the credential that lets anyone send
    to that device.
    """
    try:
        return urlparse(endpoint).hostname or "?"
    except ValueError:
        return "?"
