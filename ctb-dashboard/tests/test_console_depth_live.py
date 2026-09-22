"""The console's reading depth must not ratchet up and stay up.

Scrolling up for history raises the polled window by four hundred lines a
step, to five thousand. That part is wanted. What was not: the depth came
back with the remembered pane, so a session scrolled through once kept
polling and repainting the deep window on every later visit -- and the
remembered pane itself was the whole window, rewritten into localStorage
twice a second, all thirty sessions re-serialised each time.

Driven in a real browser because all of it is storage and DOM behaviour.
"""

import json

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")
    # The pane has to be the full window before a scroll means anything: a
    # one-line pane has nowhere to scroll and the gesture is swallowed.
    page.wait_for_function(
        "() => (window.ctbConsole._state.lines || []).length >= 40")


def depth(page):
    return page.evaluate("() => window.ctbConsole._state.depth")


def stored(page):
    return page.evaluate(
        "() => JSON.parse(localStorage.getItem('ctb_console_tails') || '{}')")


def deepen(page, times=1):
    """Load history, which is what raises the depth.

    Calls the console's own loader rather than synthesising the scroll
    physics: the handler acts on direction, and a poll landing between the
    two synthetic scrolls moves the pane under them, which made the gesture
    flaky in tests without saying anything about the depth. The gesture
    itself is covered by the test above, which is the right place for it.
    """
    for _ in range(times):
        page.evaluate("() => window.ctbConsole._growTail()")
        page.wait_for_function("() => !window.ctbConsole._state.growing")
        page.wait_for_timeout(120)


def test_scrolling_up_still_asks_for_more(board):
    """The ratchet itself is wanted -- this is what must keep working, by the
    gesture a reader actually makes.

    The two scrolls are chained inside the page, the second fired from the
    first one's own event: driven from Python with waits in between, a poll
    landing in the gap puts the pane back at the bottom and the gesture reads
    as no movement, which made this fail about one run in four.
    """
    board.ctb_log_window = True
    open_console(board)
    first = depth(board)
    board.evaluate("""() => new Promise(resolve => {
        const el = document.querySelector('#ctb-console pre');
        const once = () => {
            el.removeEventListener('scroll', once);
            el.addEventListener('scroll', () => resolve(), {once: true});
            el.scrollTop = 0;                    // ...and now upward
        };
        el.addEventListener('scroll', once);
        el.scrollTop = Math.round(el.clientHeight / 2);   // somewhere it has seen
    })""")
    board.wait_for_function(
        "d => window.ctbConsole._state.depth > d", arg=first, timeout=5000)


def test_the_depth_does_not_come_back_with_the_session(board):
    """The bug: one trip through the history made every later visit deep."""
    board.ctb_log_window = True
    open_console(board)
    deepen(board)
    deep = depth(board)
    assert deep > 40

    board.evaluate("name => window.ctbConsole.open(name)", "claude_beta")
    board.wait_for_timeout(200)
    open_console(board, "claude_alpha")
    board.wait_for_timeout(200)
    assert depth(board) < deep, (
        "the deep window came back with the session and would be polled and "
        "repainted from now on")


def test_the_remembered_pane_is_forty_lines_not_the_whole_window(board):
    """Two megabytes of JSON per poll, parsed and rewritten synchronously,
    is what the unbounded version cost."""
    board.ctb_log_window = True
    open_console(board)
    deepen(board, 2)
    board.wait_for_timeout(2400)          # let a poll bank the pane

    entry = stored(board).get("claude_alpha")
    assert entry, "nothing was remembered"
    kept = len(entry["log"].split("\n"))
    assert kept <= 40, f"remembered {kept} lines"
    assert "depth" not in entry, "the depth is still being persisted"


def test_a_store_left_oversized_by_the_old_code_is_normalised(board):
    """The fix has to clean up after the version that caused it.

    Trimming only the session in hand would leave everyone who had used the
    console before this with exactly the store they already had: twenty-nine
    other entries at full size, parsed and re-serialised on every poll, and
    painted untrimmed when recalled. Seeded here the way the old code left
    it, including the `depth` field it used to write.
    """
    board.ctb_log_window = True
    seeded = board.evaluate("""() => {
        const line = 'x'.repeat(120);
        const log = Array(1200).fill(line).join('\\n');
        const all = {};
        for (let i = 0; i < 29; i++)
          all['claude_legacy_' + i] = {log: log, cols: 80, ghost: false,
                                       depth: 5000, at: Date.now() - i};
        localStorage.setItem('ctb_console_tails', JSON.stringify(all));
        return localStorage.getItem('ctb_console_tails').length;
    }""")
    assert seeded > 1_000_000, f"the seeded store was only {seeded} chars"

    open_console(board)
    board.wait_for_timeout(2600)          # one poll writes the store back

    after = board.evaluate(
        "() => (localStorage.getItem('ctb_console_tails') || '').length")
    assert after < 400 * 1024, f"still {after // 1024}KB after a poll"
    entries = stored(board)
    for name, entry in entries.items():
        assert len(entry["log"].split("\n")) <= 40, name
        assert "depth" not in entry, name


def test_a_single_joined_line_cannot_blow_the_store_either(board):
    """Lines are not a size: the pane is captured with `-J`, which joins a
    wrapped line back together, so forty of them can still be enormous."""
    board.evaluate("""() => {
        localStorage.setItem('ctb_console_tails', JSON.stringify({
          'claude_huge': {log: 'y'.repeat(900000), cols: 80, ghost: false, at: Date.now()}
        }));
    }""")
    open_console(board)
    board.wait_for_timeout(2600)
    after = board.evaluate(
        "() => (localStorage.getItem('ctb_console_tails') || '').length")
    assert after < 400 * 1024, f"still {after // 1024}KB"


def test_a_deep_window_is_still_polled_while_the_reader_is_in_it(board):
    """Resetting on switch must not break reading history in the first place:
    while the reader is up there, the deep window is what they are reading."""
    board.ctb_log_window = True
    open_console(board)
    deepen(board)
    deep = depth(board)
    board.wait_for_timeout(2400)
    assert depth(board) == deep, "the depth collapsed under the reader"


def test_the_length_cap_cuts_at_a_line_boundary(board):
    """The cap is in characters (UTF-16 code units) -- what String.length
    counts and what the browser charges localStorage in, which is the unit
    that matters for bounding the store. slice() on that can land inside a
    surrogate pair, and half a first line reads as a rendering fault rather
    than a trim."""
    kept = board.evaluate("""() => {
        const lines = [];
        for (let i = 0; i < 200; i++) lines.push('행 ' + i + ' 🎉 ' + '가'.repeat(200));
        return window.ctbConsole._trimTail(lines.join('\\n'));
    }""")
    # Characters, deliberately: 8192 Hangul syllables are 24576 bytes of
    # UTF-8, and the store is charged in code units, not UTF-8 bytes.
    assert len(kept) <= 8192
    assert "�" not in kept, "a character was cut in half"
    assert kept.split("\n")[0].startswith("행"), "the first line is a fragment"
