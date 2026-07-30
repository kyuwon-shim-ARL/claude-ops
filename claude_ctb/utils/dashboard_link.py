"""Deep links from a Telegram notification straight into the dashboard console.

This is what removes the round trip. Notifications arrive in Telegram, but the
controls live in the dashboard, so seeing "작업 완료" used to mean switching apps
and finding the session by hand. A link that opens the console for *that* session
collapses those steps into one tap.

The base URL is configuration, not a constant: hard-coding a tailnet address in
the bot would break the moment the address changes, and would leak a host
address into the repo. With nothing configured the caller omits the line rather
than emitting a link that goes nowhere.
"""

import os
import re
from urllib.parse import quote

# Same charset the dashboard enforces on every session-scoped route
# (server.py _SESSION_NAME_RE). Kept in sync deliberately: a name this rejects
# would be rejected by the API too, so the link would be dead on arrival.
_SESSION_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-:.]{1,64}$')


def dashboard_base_url() -> str:
    """Configured dashboard origin, e.g. http://100.85.200.72:8420 (no trailing /)."""
    return os.environ.get("CTB_DASHBOARD_URL", "").rstrip("/")


def build_session_deeplink(session_name: str) -> str | None:
    """URL that opens the dashboard with this session's console already open.

    Returns None when there is nothing safe to link to -- no configured base URL,
    or a session name the dashboard would reject anyway.
    """
    base = dashboard_base_url()
    if not base:
        return None
    if not session_name or not _SESSION_NAME_RE.match(session_name):
        return None
    return f"{base}/?session={quote(session_name, safe='')}"


def deeplink_line(session_name: str) -> str:
    """A ready-to-append notification line, or '' when no link is available.

    Returning '' keeps the caller free of conditionals and guarantees that a
    missing configuration degrades to the old message rather than a broken link.
    """
    url = build_session_deeplink(session_name)
    return f"\n📱 **바로 열기**: {url}" if url else ""
