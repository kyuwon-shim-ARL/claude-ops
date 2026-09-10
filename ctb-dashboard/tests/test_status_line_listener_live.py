"""One Ctrl+U is one kill-line, however much the status line has said.

The Ctrl+U handler was registered inside setStatus(): every status message
added another copy of it, so a single press fired once per message the
console had ever shown, and each of those calls setStatus again. It ran the
control rate limiter dry -- 16,358 key requests in 89 seconds in the audit
log, 40,342 in one day -- and while the limiter was empty nothing else could
be sent to any session either, which is what "too many control requests"
in the console meant.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)


def key_posts(page):
    return [p for p in page.ctb_requests if p.endswith("/key")]


def open_console(page, name="claude_alpha"):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector("#ctb-console", state="visible")


def test_one_press_is_one_key_however_talkative_the_console_was(board):
    open_console(board)
    board.evaluate("""() => {
        for (let i = 0; i < 40; i++) window.ctbConsole._setStatus('말 ' + i);
    }""")
    before = len(key_posts(board))
    board.evaluate("() => document.getElementById('ctb-console').click()")
    board.keyboard.press("Control+u")
    # Long enough for the storm to show: with the listener stacked, one press
    # sent 40 -- one per status message above -- and a short wait would have
    # failed on an empty list instead, for the wrong reason.
    board.wait_for_timeout(1200)
    assert len(key_posts(board)) - before == 1


def test_holding_the_key_does_not_spray_the_session(board):
    """The OS repeats a held key ~30 times a second; tmux gets one."""
    open_console(board)
    before = len(key_posts(board))
    board.evaluate("""() => {
        for (let i = 0; i < 20; i++) {
          document.dispatchEvent(new KeyboardEvent('keydown',
            {key: 'u', ctrlKey: true, repeat: i > 0, bubbles: true}));
        }
    }""")
    board.wait_for_timeout(600)
    assert len(key_posts(board)) - before == 1
