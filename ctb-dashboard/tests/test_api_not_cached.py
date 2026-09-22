"""Live state must not be served out of a browser's cache.

None of the /api responses carried a Cache-Control, an ETag or an Expires. A
response with no freshness information at all is heuristically cacheable: the
browser invents a lifetime and serves the old body without asking. The server
already guards /static against exactly this, one directory over.

On a phone it showed up as a session's importance reading wrong, and as a
change to it lasting a few seconds and then reverting -- the board re-reads
/api/pinned every ten seconds and adopts what it gets, so a cached body undid
the write that had just succeeded.
"""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard.server import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(_srv, "_PINNED_PERSIST_PATH", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(_srv, "_TICKET_LINKS_PATH", str(tmp_path / "tickets.json"))
    return TestClient(app)


READ_ENDPOINTS = [
    "/api/pinned",
    "/api/sessions",
    "/api/projects",
    "/api/sessions/closed",
    "/api/session-ticket-links",
]


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_api_reads_are_never_cacheable(client, path):
    r = client.get(path)
    assert r.status_code < 500, r.text
    assert r.headers.get("cache-control") == "no-store", (
        f"{path} sends {r.headers.get('cache-control')!r}; with no freshness "
        f"information a browser may serve this body again on its own")


def test_the_page_itself_is_still_no_store(client):
    assert client.get("/").headers.get("cache-control") == "no-store"


def test_static_still_revalidates_rather_than_no_store(client):
    """Static files are revalidated, not refetched: an unchanged file should
    cost a 304, not a full body on every load."""
    r = client.get("/static/js/control-token.js")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache"


def test_pinned_read_after_write_is_the_written_value(client, monkeypatch):
    """The end of the loop the phone was stuck in: write, then read back."""
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", "s")
    quads = {"Q1": ["claude_one"], "Q2": [], "Q3": [], "Q4": []}
    w = client.post("/api/pinned", json=quads, headers={"X-CTB-Secret": "s"})
    assert w.status_code == 200
    assert client.get("/api/pinned").json()["Q1"] == ["claude_one"]
