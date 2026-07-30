"""Deep links are the piece that actually removes the app round trip.

A wrong link here is worse than no link: it sends the user somewhere broken at
exactly the moment they are trying to act on a notification. So the builder is
strict about what it will emit, and silent when it cannot emit anything useful.
"""

import pytest

from claude_ctb.utils.dashboard_link import (
    build_session_deeplink,
    dashboard_base_url,
    deeplink_line,
)

BASE = "http://100.85.200.72:8420"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("CTB_DASHBOARD_URL", BASE)


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.delenv("CTB_DASHBOARD_URL", raising=False)


def test_link_opens_the_console_for_the_session(configured):
    assert build_session_deeplink("claude_MSK2025") == BASE + "/?session=claude_MSK2025"


def test_trailing_slash_in_config_does_not_double_up(monkeypatch):
    monkeypatch.setenv("CTB_DASHBOARD_URL", BASE + "/")
    assert build_session_deeplink("claude_x") == BASE + "/?session=claude_x"
    assert dashboard_base_url() == BASE


def test_no_link_without_configuration(unconfigured):
    """Better no line than a link to nowhere."""
    assert build_session_deeplink("claude_x") is None
    assert deeplink_line("claude_x") == ""


@pytest.mark.parametrize("name", [
    "",
    "bad name",          # space
    "bad/name",          # path separator
    "bad?name",          # would corrupt the query string
    "bad#frag",
    "a" * 65,            # over the 64-char limit
    "세션",               # non-ASCII
])
def test_names_the_dashboard_would_reject_produce_no_link(configured, name):
    assert build_session_deeplink(name) is None
    assert deeplink_line(name) == ""


@pytest.mark.parametrize("name", [
    "claude_MSK2025",
    "claude-ops",
    "a.b:c_d-e",
    "1698",
    "a" * 64,
])
def test_valid_names_are_accepted(configured, name):
    """Assert the round trip, not the literal spelling.

    quote() percent-encodes characters like ':' -- that is correct URL
    encoding, and the browser's URLSearchParams decodes it back, so what
    matters is that the value survives the trip.
    """
    from urllib.parse import parse_qs, urlparse

    link = build_session_deeplink(name)
    assert link is not None
    assert parse_qs(urlparse(link).query)["session"] == [name]


def test_line_is_appendable_and_starts_on_its_own_row(configured):
    line = deeplink_line("claude_x")
    assert line.startswith("\n")
    assert BASE in line


def test_line_is_empty_string_not_none_so_f_strings_stay_clean(configured):
    """The notifier interpolates this directly; None would render as 'None'."""
    assert isinstance(deeplink_line("bad name"), str)
    assert isinstance(deeplink_line("claude_x"), str)


def test_notifier_templates_include_the_deeplink():
    """Guard the wiring, not just the helper."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "claude_ctb" / "telegram" / "notifier.py").read_text()
    assert "from ..utils.dashboard_link import deeplink_line" in src
    # Both the context-rich and the fallback completion messages.
    assert src.count("{deeplink_line(session_name)}") == 2


def test_dashboard_js_validates_the_session_param():
    """The client must not open a console for a name the API would reject."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "ctb-dashboard" / "src"
          / "ctb_dashboard" / "static" / "js" / "session-control.js").read_text()
    assert "SESSION_NAME_RE" in js
    assert "URLSearchParams" in js
    assert "SESSION_NAME_RE.test(name)" in js
    # The regex must match the server's charset.
    assert "/^[a-zA-Z0-9_\\-:.]{1,64}$/" in js
    # And the param should not survive a reload.
    assert "replaceState" in js
