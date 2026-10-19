"""The console header folds its tools when they would cut the session name.

An iPhone 12 (390px) gave a long name about 30px -- "u…" -- because seven
tools sat beside it. When the name would be cut, everything but session
search and close folds behind ⋯; a tap lays the tools out on their own row
under the name, and a second tap folds them again. A wide screen, where the
name fits, shows every tool in its usual place and no ⋯ at all.

Layout is the whole question here, so it is asked of a real browser.
"""

import pytest  # noqa: F401

import live_board
from live_board import _session, open_board

LONG = "claude_uni-mol-QSAR-feature-store"
LONG2 = "claude_another-very-long-session-name"
MORE = "#ctb-console .con-head-more"


@pytest.fixture(autouse=True)
def _long_name(monkeypatch):
    monkeypatch.setattr(live_board, "SESSIONS", live_board.SESSIONS + [_session(LONG), _session(LONG2)])


def head(page):
    return page.evaluate("""(() => {
      const e = window.ctbConsole._el();
      const vis = n => getComputedStyle(n).display !== 'none' && n.getBoundingClientRect().width > 0;
      const t = e.title.getBoundingClientRect();
      const findBtn = document.querySelector('#ctb-console [aria-label="\\uc138\\uc158 \\uac80\\uc0c9 \\uc5f4\\uae30"]');
      const closeBtn = document.querySelector('#ctb-console [aria-label="\\ucf58\\uc194 \\ub2eb\\uae30"]');
      const copy = document.querySelector('#ctb-console [aria-label="\\ud654\\uba74 \\ub0b4\\uc6a9 \\ubcf5\\uc0ac"]');
      return {
        titleW: e.title.clientWidth, titleFull: e.title.scrollWidth, titleTop: t.top,
        more: vis(e.headMore), find: vis(findBtn), close: vis(closeBtn), copy: vis(copy),
        copyTop: copy.getBoundingClientRect().top,
        expanded: e.headMore.getAttribute('aria-expanded'),
      };
    })()""")


def open_console(page, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.evaluate("n => window.ctbConsole.open(n)", LONG)
    page.wait_for_selector("#ctb-console", state="visible")
    page.wait_for_timeout(300)


def test_phone_folds_tools_and_keeps_search_and_close():
    with open_board() as page:
        open_console(page, 390)
        h = head(page)
        assert h["more"] and h["find"] and h["close"]
        assert not h["copy"]
        # Most of the name now shows; before this it was ~30px.
        assert h["titleW"] > 150


def test_tap_lays_tools_out_under_the_name_and_tap_again_folds():
    with open_board() as page:
        open_console(page, 390)
        folded = head(page)
        page.click(MORE)
        h = head(page)
        assert h["copy"] and h["expanded"] == "true"
        assert h["copyTop"] > h["titleTop"] + 20       # its own row, below
        assert h["titleW"] >= folded["titleW"] - 1     # the name gave nothing up
        # A re-measure (here a resize, which runs fitHead) while the name is
        # still cut leaves the row open: only the reader folds it.
        page.set_viewport_size({"width": 380, "height": 844})
        page.wait_for_timeout(200)
        assert head(page)["copy"]
        page.click(MORE)
        h = head(page)
        assert not h["copy"] and h["more"] and h["expanded"] == "false"


def test_wide_screen_shows_every_tool_and_no_fold_key():
    with open_board() as page:
        open_console(page, 1200)
        h = head(page)
        assert not h["more"]
        assert h["copy"] and h["find"] and h["close"]
        assert h["titleW"] >= h["titleFull"]


def test_switching_session_folds_the_row_again():
    with open_board() as page:
        open_console(page, 390)
        page.click(MORE)
        assert head(page)["copy"]
        page.evaluate("n => window.ctbConsole.open(n)", LONG2)
        page.wait_for_timeout(300)
        h = head(page)
        assert not h["copy"] and h["more"] and h["expanded"] == "false"


def test_widening_while_open_drops_the_fold_and_narrowing_folds_again():
    with open_board() as page:
        open_console(page, 390)
        page.click(MORE)
        page.set_viewport_size({"width": 1200, "height": 844})
        page.wait_for_timeout(300)
        h = head(page)
        assert not h["more"] and h["copy"]
        assert h["copyTop"] < h["titleTop"] + 20       # back in line with the name
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        h = head(page)
        assert h["more"] and not h["copy"]
