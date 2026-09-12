"""The shipped dashboard page, driven in a real browser.

The board's filtering and the console's controls are DOM behaviour: what is
worth asserting is what a browser does with the shipped HTML and JS, and a
fake DOM would only prove the stub. Everything the page asks for is answered
from here -- canned sessions and pins, the real static JS off disk, nothing
off the machine.
"""

import contextlib
import json
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

sync_api = pytest.importorskip("playwright.sync_api")

SRC = Path(__file__).resolve().parents[1] / "src" / "ctb_dashboard"
NOW = 1_800_000_000


def _page_html():
    env = Environment(loader=FileSystemLoader(str(SRC / "templates")))
    return env.get_template("index.html").render(
        csp_nonce="test", dashboard_url="", asset_v="test"
    )


def _session(name, *, state="idle", age=60, context=""):
    return {
        "name": name,
        "state": state,
        "updated_at": NOW - age,
        "last_activity": NOW - age,
        "work_context": context,
    }


SESSIONS = [
    _session("claude_alpha", state="working"),
    # A repo with a worktree beside it: the grid groups these two under one
    # header, and the header carries a count the filter has to keep honest.
    _session("claude_alpha_wt_topic", state="idle"),
    _session("claude_beta", state="waiting"),
    _session("claude_gamma", state="idle"),
    _session("claude_delta", state="idle", context="alpha mentioned here"),
]
# A pane worth scrolling and searching: 120 lines, with "needle" on three of
# them so a find has more than one place to go.
LOG = "\n".join(
    ("line %03d needle here" % i) if i in (7, 61, 118) else ("line %03d ordinary output" % i)
    for i in range(120)
)

QUADS = {"Q1": ["claude_alpha", "claude_alpha_wt_topic"],
         "Q2": ["claude_beta"], "Q3": [], "Q4": []}


@contextlib.contextmanager
def open_board(theme=None):
    """The real dashboard page, fed canned sessions, in a real browser.

    `theme` picks one of the console's three palettes ('dark', 'light',
    'parchment'); the default follows the headless browser, which is light.
    """
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # no browser installed on this host
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page()
        # Every write the page makes, in order -- the pin endpoint is the only
        # one under test here, and asserting on what it was sent is the only
        # way to know a control actually did something.
        posted = []
        accepted = []
        page.ctb_posted = posted
        page.ctb_accepted = accepted
        page.ctb_keys = []
        page.ctb_log = LOG
        page.ctb_log_hash = "h1"
        # See the /log route below: off by default, so no existing expectation
        # about the canned pane changes.
        page.ctb_log_window = False
        page.ctb_hold_log = False
        page.ctb_held = []

        def release_log(index=0):
            """Answer a request the route was told to hold."""
            route_obj, body = page.ctb_held.pop(index)
            route_obj.fulfill(status=200, content_type="application/json",
                              body=json.dumps(body))

        page.ctb_release_log = release_log
        # A control token the page already has: without one the first write
        # opens a window.prompt(), which a headless browser dismisses.
        page.add_init_script("localStorage.setItem('ctb.controlToken', 'test-token')")
        if theme:
            page.add_init_script(
                "localStorage.setItem('ctb_theme', %s)" % json.dumps(theme))
        # Tailwind is blocked with the rest of the network, and the page hides
        # its empty state with Tailwind's `.hidden`. Without the rule, every
        # visibility assertion below would pass on a visible element.
        # Two stylesheet edits, both so a colour read is the colour that ends
        # up on screen:
        #   .hidden -- Tailwind is blocked with the rest of the network, and
        #     the page hides its empty state with it, so without the rule
        #     every visibility assertion would pass on a visible element;
        #   transitions off -- the controls fade between backgrounds, and
        #     getComputedStyle during a fade reports the interpolated value.
        #     Read immediately after opening the console, that is still the
        #     colour it started from, which quietly made a colour assertion
        #     pass no matter what the rule said.
        page.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => {"
            "  const s = document.createElement('style');"
            "  s.textContent = '.hidden{display:none!important}'"
            "    + '*,*::before,*::after{transition:none!important;"
            "       animation:none!important}';"
            "  document.head.appendChild(s); })"
        )

        # Every path the page fetched, in order. Used to assert that something
        # did NOT refetch.
        requests = []
        page.ctb_requests = requests

        def route(r):
            url = r.request.url
            requests.append(url.split("http://ctb.test", 1)[-1].split("?")[0])
            path = url.split("http://ctb.test", 1)[-1].split("?")[0]
            if path.startswith("/api/pinned"):
                if r.request.method == "POST":
                    body = json.loads(r.request.post_data or "{}")
                    posted.append(body)
                    if getattr(page, "ctb_refuse_writes", False):
                        # What the server sends when the control token is
                        # missing or wrong. A refused write changes nothing:
                        # `posted` records the attempt, `accepted` is state.
                        return r.fulfill(status=403, content_type="application/json",
                                         body='{"detail":"forbidden"}')
                    accepted.append(body)
                    # The real server answers with the set it now holds.
                    return r.fulfill(status=200, content_type="application/json",
                                     body=json.dumps(body))
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps(accepted[-1] if accepted else QUADS))
            if path.startswith("/api/sessions/stream"):
                return r.abort()
            if path.startswith("/api/sessions/") and path.endswith("/key"):
                # What key the console actually asked tmux for. "a request was
                # made" is not the assertion worth making about a key.
                page.ctb_keys.append(json.loads(r.request.post_data or "{}"))
                return r.fulfill(status=200, content_type="application/json",
                                 body='{"ok":true}')
            if path.startswith("/api/sessions/") and path.endswith("/log"):
                # A real pane: long enough to scroll, with a word that appears
                # more than once so a find has somewhere to step to.
                body = {"log": page.ctb_log, "hash": page.ctb_log_hash,
                        "cols": 80, "ghost": False}
                if "since=" + page.ctb_log_hash in url:
                    body = {"unchanged": True}
                # Opt-in, because most tests want the whole canned pane at any
                # depth. A test about LOADING history needs the other thing: a
                # window that really only holds the last N lines, so asking for
                # more brings something back.
                elif page.ctb_log_window:
                    asked = 0
                    for part in url.split("?", 1)[-1].split("&"):
                        if part.startswith("lines="):
                            asked = int(part[6:] or 0)
                    if asked:
                        rows = page.ctb_log.split("\n")
                        body["log"] = "\n".join(rows[-asked:])
                        body["hash"] = "%s-%d" % (page.ctb_log_hash,
                                                  min(asked, len(rows)))
                # Held until the test releases it: the only way to assert on
                # what happens while a fetch is still in flight.
                if page.ctb_hold_log:
                    page.ctb_held.append((r, body))
                    return
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps(body))
            if path.startswith("/api/sessions/create"):
                # What the server answers when tmux really did start one.
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"session": "claude_fresh",
                                                  "status": "created"}))
            if path.startswith("/api/projects"):
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({
                                     "root": "/home/someone/projects",
                                     "projects": [
                                         {"name": "atlas", "is_git": True,
                                          "session_exists": False},
                                         {"name": "borealis", "is_git": False,
                                          "session_exists": False},
                                     ]}))
            if path.startswith("/api/sessions"):
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"sessions": SESSIONS,
                                                  "updated_at": NOW}))
            if path.startswith("/static/"):
                f = SRC / path.lstrip("/")
                if not f.exists():
                    return r.fulfill(status=404, body="")
                # Bytes, not text: the parchment theme pulls a jpg, and
                # decoding it as UTF-8 threw inside the route handler, which
                # playwright reports as a pile of unrelated fulfill errors.
                ctype = {
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".jpg": "image/jpeg",
                    ".png": "image/png",
                }.get(f.suffix, "text/plain")
                return r.fulfill(status=200, content_type=ctype, body=f.read_bytes())
            if path in ("/", ""):
                return r.fulfill(status=200, content_type="text/html",
                                 body=_page_html())
            if path == "/__deny_writes":
                return r.fulfill(status=200, body="")
            return r.fulfill(status=200, content_type="application/json", body="{}")

        # Nothing leaves the machine: the CDN fonts and Tailwind are not what
        # is under test, and a suite that needs the network is a flaky suite.
        # Registered first so the page's own routes, added below, win.
        page.route("**", lambda r: r.abort())
        page.route("http://ctb.test/**", route)
        page.goto("http://ctb.test/")
        page.wait_for_selector('[data-session-name="claude_alpha"]')
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture
def board():
    with open_board() as page:
        yield page


