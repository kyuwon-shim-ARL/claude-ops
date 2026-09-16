"""Importance follows the server on a board with no stream.

A session's quadrant is shared server state, and two clients disagreeing about
it is a real complaint. Only one thing keeps a streamless board current: the
raw read of /api/pinned at the top of connect(), which runs again on every
reconnect attempt (index.html, `connect`). The SSE path has its own refresh
(`maybeRefreshPinned`, throttled to 10s), but the two paths that feed a board
with no stream -- the 5s fallback poll and the refetch on returning to the page
-- only re-render sessions and never re-read the pin set.

So the property holds, but it rests on one line in a function whose job is
opening a stream, not reading pins. Delete that read and every assertion here
fails, including the first paint. That is what this file is for.

Driven against the shipped page; live_board aborts /api/sessions/stream, so the
board here is on exactly that streamless path.
"""

import pytest  # noqa: F401

from live_board import board, open_board  # noqa: F401  (fixture)


def quadrant_of(page, name):
    """Which quadrant box the board is currently drawing this card in."""
    return page.evaluate(
        """name => {
             const card = document.querySelector(`[data-session-name="${name}"]`);
             if (!card) return null;
             const box = card.closest('[data-quadrant]');
             return box ? box.dataset.quadrant : null;
           }""",
        name,
    )


def move_on_server(page, name, to_quad):
    """Another client re-files the session. Only the server is told."""
    quads = {"Q1": ["claude_alpha", "claude_alpha_wt_topic"],
             "Q2": ["claude_beta"], "Q3": [], "Q4": []}
    for names in quads.values():
        if name in names:
            names.remove(name)
    quads[to_quad].append(name)
    page.ctb_accepted.append(quads)


def test_board_starts_from_the_served_pin_set(board):
    assert quadrant_of(board, "claude_alpha") == "Q1"
    assert quadrant_of(board, "claude_beta") == "Q2"


def test_fallback_poll_picks_up_a_quadrant_change_made_elsewhere(board):
    assert quadrant_of(board, "claude_beta") == "Q2"
    move_on_server(board, "claude_beta", "Q1")
    # maybeRefreshPinned() throttles itself to one read per 10s, and the
    # fallback poll runs every 5s, so the board has to be given both.
    board.wait_for_timeout(16000)
    assert quadrant_of(board, "claude_beta") == "Q1", (
        "the board kept the importance it had at page load while the stream was down"
    )


def test_returning_to_the_page_picks_up_a_quadrant_change(board):
    assert quadrant_of(board, "claude_alpha") == "Q1"
    move_on_server(board, "claude_alpha", "Q4")
    # Away long enough that the throttle is not what answers this.
    board.wait_for_timeout(11000)
    board.evaluate(
        """() => {
             Object.defineProperty(document, 'visibilityState',
               { configurable: true, get: () => 'visible' });
             document.dispatchEvent(new Event('visibilitychange'));
           }"""
    )
    board.wait_for_timeout(1500)
    assert quadrant_of(board, "claude_alpha") == "Q4"
