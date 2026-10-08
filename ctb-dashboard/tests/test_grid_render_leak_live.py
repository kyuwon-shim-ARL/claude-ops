"""The board must not grow with every render.

render() cleared the grid with `grid.children`, which holds elements only, so
the whitespace text between the cards of each rebuild stayed behind. A board
left open gained ~930 nodes a minute (measured on the live page: #grid went
164 -> 1644 child nodes in two minutes, 1602 of them text). Seeding a fresh
page with a day's worth took it from 49 to 505 ms of CPU a second, most of it
style recalculation: the "it gets slow if I leave it open" that was reported.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (board fixture)


def grid_nodes(page):
    return page.evaluate("() => document.getElementById('grid').childNodes.length")


def test_rendering_again_and_again_leaves_the_grid_the_same_size(board):
    page = board
    page.ctb_set_state("claude_alpha", "idle")
    settled = grid_nodes(page)
    for i in range(10):
        page.ctb_set_state("claude_alpha", "working" if i % 2 else "idle")
    page.ctb_set_state("claude_alpha", "idle")
    assert grid_nodes(page) == settled


def test_the_empty_state_survives_the_clearing(board):
    page = board
    for i in range(3):
        page.ctb_set_state("claude_alpha", "working" if i % 2 else "idle")
    assert page.evaluate("() => !!document.querySelector('#grid > #empty-state')")
