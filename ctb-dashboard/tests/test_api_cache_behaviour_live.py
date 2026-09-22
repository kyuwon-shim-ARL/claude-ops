"""What a browser actually does with a response that says nothing about cache.

The /api responses carried no Cache-Control, no ETag and no Expires. The RFC
says such a response MAY be reused on the browser's own judgement; this shows
that Chromium does, which is the whole of the bug: the board re-reads
/api/pinned every ten seconds and adopts what it gets, so a cached body undid
the write that had just succeeded and the session's importance sprang back.

Two fixes, both exercised here against a real server and a real browser:
the header the server now sends, and the cache mode the page now asks for --
which is what rescues a phone that already has the old body stored from
before the header existed.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def counting_server():
    """Answers every GET with a number one higher than the last.

    Two identical answers therefore mean the second never reached it.
    `Last-Modified` far in the past is what makes a browser's heuristic
    freshness lifetime long: the usual rule is a tenth of the age.
    """
    hits = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path
            hits[path] = hits.get(path, 0) + 1
            body = ('{"n": %d}' % hits[path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
            if "nostoreheader" in path:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()


@pytest.fixture
def page(counting_server):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page()
        pg.goto("http://127.0.0.1:%d/blank" % counting_server)
        pg.port = counting_server
        try:
            yield pg
        finally:
            browser.close()


def read_twice(page, path, opts="undefined"):
    return page.evaluate(
        """async ([port, path, opts]) => {
            const url = `http://127.0.0.1:${port}${path}`;
            const one = await (await fetch(url, opts || undefined)).json();
            const two = await (await fetch(url, opts || undefined)).json();
            return [one.n, two.n];
        }""",
        [page.port, path, None if opts == "undefined" else opts])


def test_a_response_with_no_cache_headers_is_reused(page):
    """The bug itself. Without this the rest of this file has no reason to
    exist, and the diagnosis would rest on reading the specification."""
    first, second = read_twice(page, "/api/bare")
    assert first == second, (
        "the browser went back to the server; if it no longer reuses such a "
        "response the header below is belt with no braces, but do not remove it")


def test_the_no_store_header_stops_it(page):
    """What the server now sends for everything under /api/."""
    first, second = read_twice(page, "/api/nostoreheader")
    assert second == first + 1, "a no-store response was still served from cache"


def test_asking_for_no_store_stops_it_even_without_the_header(page):
    """What the page now asks for. This is the half that helps a phone which
    already has the old body stored from before the header existed -- the
    header cannot reach into a cache entry that is already there."""
    first, second = read_twice(page, "/api/bare2", opts={"cache": "no-store"})
    assert second == first + 1, "cache:'no-store' was still served from cache"
