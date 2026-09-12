"""Getting back to live, finding a way to the end, and searching the output.

Three things a reader on a phone kept losing: a pane frozen by a half-made
selection with no obvious way out, a console reopened hundreds of lines up,
and no way to find anything in what is on screen. Driven against the shipped
page in a real browser, because all three are DOM behaviour.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"
PILL = "#ctb-console button[aria-label='맨 아래로 가기']"
PREV = "#ctb-console button[aria-label='이전 요청으로 가기']"
FIND = "#con-find"
FIND_INPUT = "#con-find-input"


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def frozen(page):
    """The amber "갱신 정지됨" badge — the console's own word for paused."""
    return page.evaluate(
        "() => [...document.querySelectorAll('#ctb-console div')]"
        "  .some(e => e.textContent.includes('갱신 정지됨')"
        "          && e.style.display !== 'none' && e.style.position === 'absolute')")


def scroll_up(page, to=0):
    page.eval_on_selector("#ctb-console pre", "(el, to) => { el.scrollTop = to; }", to)
    page.wait_for_timeout(120)


def logs(page):
    """How many times the pane has been asked for. One recovery, one ask."""
    return len([u for u in page.ctb_requests if u.endswith("/log")])


def at_bottom(page):
    return page.eval_on_selector(
        "#ctb-console pre",
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 8")


# --- tap to hold, tap to let go ---------------------------------------------

def test_a_tap_holds_the_pane_and_a_second_tap_lets_go(board):
    """The whole reason copying was hard: the lines moved. Standing still is
    the feature; the drag that copies is the platform's own."""
    open_console(board)
    assert not frozen(board)
    board.click("#ctb-console pre")
    assert frozen(board)
    board.click("#ctb-console pre")
    assert not frozen(board)


def test_a_held_pane_stops_asking_for_the_log(board):
    open_console(board)
    board.click("#ctb-console pre")
    board.wait_for_timeout(300)
    before = logs(board)
    board.wait_for_timeout(2600)                     # POLL_MS is 2000
    assert logs(board) == before


# --- Enter gets you back to work -------------------------------------------

def test_enter_thaws_a_frozen_pane_and_returns_the_caret(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")      # holds the pane
    assert frozen(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_function("() => !document.querySelector('#ctb-console pre')"
                            ".style.boxShadow.includes('245,158,11')")
    assert not frozen(board)
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_enter_brings_the_view_back_to_the_bottom(board):
    open_console(board)
    scroll_up(board)
    assert not at_bottom(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_function(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        return el.scrollHeight - el.scrollTop - el.clientHeight < 8; }")


def test_enter_in_the_prompt_box_still_sends_a_bare_newline(board):
    """The one Enter that must not be stolen.

    An empty Enter sent to tmux is how a Claude Code prompt gets confirmed.
    Holding the pane says nothing about whether the session is waiting for
    that key.
    """
    open_console(board)
    board.click("#ctb-console pre")                  # hold it, to be sure
    assert frozen(board)
    board.click("#ctb-console textarea")
    board.keyboard.press("Enter")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Enter"]
    # A hold is for reading; sending is the end of reading, so it lets go --
    # otherwise the key's own effect on the pane would be hidden.
    assert not frozen(board)


def test_enter_on_a_button_is_the_press_not_a_recovery(board):
    open_console(board)
    scroll_up(board)
    board.focus("#ctb-console button[aria-label='콘솔 닫기']")
    board.keyboard.press("Enter")
    board.wait_for_selector(CONSOLE, state="hidden")


# --- the jump-to-end pill ---------------------------------------------------

def test_the_pill_is_hidden_at_the_bottom(board):
    open_console(board)
    assert board.eval_on_selector_all(PILL, "els => els.length") == 1
    assert board.is_hidden(PILL)


def test_the_pill_appears_far_from_the_end_and_takes_you_there(board):
    open_console(board)
    scroll_up(board)
    board.wait_for_selector(PILL, state="visible")
    board.click(PILL)
    board.wait_for_function(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        return el.scrollHeight - el.scrollTop - el.clientHeight < 8; }")
    board.wait_for_selector(PILL, state="hidden")


def test_the_pill_waits_for_two_full_pages_of_scrolling(board):
    """One screen up is a single Claude Code status block -- the branch line,
    the HUD, the permission hint -- and the bottom is a flick away. Two is
    where the end is genuinely gone."""
    open_console(board)

    def show_at(fraction):
        """Scroll so the end is `fraction` of a pane height away."""
        return board.eval_on_selector(
            "#ctb-console pre",
            "(el, f) => { el.scrollTop = el.scrollHeight - el.clientHeight"
            "                          - el.clientHeight * f;"
            "             return el.scrollHeight - el.clientHeight"
            "                    - el.scrollTop >= el.clientHeight * f - 2; }",
            fraction)

    assert show_at(0.7), "the pane is too short to scroll this test"
    # The pill answers a scroll event, not the assignment: at 120ms this read
    # "hidden" even under the rules this replaces, which is a pass for the
    # wrong reason.
    board.wait_for_timeout(400)
    assert board.is_hidden(PILL)

    assert show_at(1.5), "one page up is still not far enough"
    board.wait_for_timeout(400)
    assert board.is_hidden(PILL)

    assert show_at(2.5)
    board.wait_for_selector(PILL, state="visible")


# --- back to the previous request -------------------------------------------

TURNS = "\n".join(
    "❯ 요청 A" if i == 10 else
    "❯ 요청 B" if i == 70 else
    ("line %03d output" % i)
    for i in range(120)
)


def with_turns(board):
    """Repaint the pane from a log that has two submitted requests in it."""
    board.ctb_log = TURNS
    board.ctb_log_hash = "h-turns"
    open_console(board, "claude_beta")
    board.wait_for_selector("#ctb-console [data-line]")


def where(board, line):
    """A line's position, in pixels from the top edge of the pane. Negative
    means scrolled off above it."""
    return board.evaluate(
        "line => { const el = document.querySelector('#ctb-console pre');"
        "          const n = el.querySelector(`[data-line='${line}']`);"
        "          return n.getBoundingClientRect().top"
        "                 - el.getBoundingClientRect().top; }", line)


def covered_by_pill(board, line):
    """Is the row hidden behind the pill that was just pressed?"""
    return board.evaluate(
        "line => { const el = document.querySelector('#ctb-console pre');"
        "          const n = el.querySelector(`[data-line='${line}']`);"
        "          const p = document.querySelector("
        "            \"#ctb-console button[aria-label='이전 요청으로 가기']\");"
        "          const a = n.getBoundingClientRect(), b = p.getBoundingClientRect();"
        "          return a.top < b.bottom && a.bottom > b.top; }", line)


def test_no_earlier_request_means_no_pill(board):
    """The default pane is output only. A button for a trip with no
    destination is worse than no button."""
    open_console(board)
    scroll_up(board)
    board.wait_for_timeout(400)
    assert board.is_hidden(PREV)


def test_the_prev_pill_walks_back_one_request_at_a_time(board):
    with_turns(board)
    board.wait_for_selector(PREV, state="visible")

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 70) < 80, "the later request comes to the top"
    assert not covered_by_pill(board, 70), (
        "the one line the press was for, hidden by the press")

    # Pressing it again goes further back, not nowhere: the request it just
    # landed on is no longer above the view.
    board.wait_for_selector(PREV, state="visible")
    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 10) < 80
    assert where(board, 70) > board.eval_on_selector(
        "#ctb-console pre", "el => el.clientHeight * 0.5"), (
        "the request just left behind should now be well down the pane")


def test_the_prev_pill_offers_the_next_page_of_history(board):
    """The window holds the last N lines, so the oldest turn in it is rarely
    the oldest turn there is. A button that vanishes at the window edge strands
    the reader one press short of what they were walking towards."""
    with_turns(board)
    scroll_up(board)                                  # to the very top
    board.wait_for_timeout(400)
    assert board.is_visible(PREV), "more history may exist, so keep offering"

    before = logs(board)
    board.click(PREV)
    board.wait_for_timeout(500)
    assert logs(board) > before, "the press has to actually ask for more"


def test_the_walk_survives_the_page_of_history_it_asked_for(board):
    """The press at the window edge prepends 400 lines. For the instant between
    the rows landing in the DOM and the scroll position being restored, every
    landing measures as hundreds of rows below the view -- and a walk judged in
    that instant was deleted as "the reader moved on". It is judged only when
    the reader presses, and counted from the newest turn, which a prepend
    cannot move."""
    # Two of the turns are two lines apart, so a walk that survived the page
    # and a walk that fell back to geometry give different answers.
    board.ctb_log = "\n".join(
        ("❯ 요청 %d" % i) if i in (168, 170, 190) else ("line %03d output" % i)
        for i in range(200))
    board.ctb_log_hash = "h-prepend"
    board.ctb_log_window = True                   # 40 lines: 160..199
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")

    # Lands the turn at 170 -- and lands it near the top of a shallow window,
    # which is itself the request for more history: 160 older lines arrive
    # underneath the walk, renumbering every row.
    board.click(PREV)
    board.wait_for_function("() => window.ctbConsole._state.lines.length >= 200",
                            timeout=4000)
    board.wait_for_timeout(300)

    # The walk still stands on the same turn, so this goes to the one before it
    # rather than starting over from what happens to be on screen.
    board.click(PREV)
    board.wait_for_timeout(300)
    # A tight band. Standing still with 168 merely visible two rows up reads
    # as ~17px; a real landing puts it at the PROMPT_HEAD offset.
    assert 30 < where(board, 168) < 80, "the turn before the one we stood on"


def test_the_prev_pill_goes_away_once_the_history_runs_out(board):
    """`exhausted` is the console's word for "the pane has no more history".
    Past that point the button has nowhere left to go."""
    with_turns(board)
    scroll_up(board)
    board.evaluate("() => { window.ctbConsole._state.exhausted = true; }")
    board.eval_on_selector("#ctb-console pre", "el => { el.scrollTop = 1; }")
    board.wait_for_timeout(400)
    assert board.is_hidden(PREV)


def test_running_out_of_history_hides_the_pill_with_no_other_repaint(board):
    """A zero-gain answer sets `exhausted` and repaints nothing: same lines,
    same scroll position. The pill had been decided while deepening still
    looked possible, so without a refresh right there it sat enabled with
    nowhere left to go until some unrelated event happened to redraw it."""
    board.ctb_log = "\n".join(
        "❯ 요청" if i == 118 else ("line %03d output" % i) for i in range(120))
    board.ctb_log_hash = "h-exhaust"
    board.ctb_log_window = True
    open_console(board, "claude_beta")
    # Already deeper than the pane has to give: the next ask brings nothing.
    board.evaluate("() => { window.ctbConsole._state.depth = 200; }")
    scroll_up(board)
    board.wait_for_timeout(300)
    assert board.is_visible(PREV)

    # The first press brings back what history there is...
    board.click(PREV)
    board.wait_for_function("() => window.ctbConsole._state.lines.length >= 120",
                            timeout=4000)
    # ...and the second gets nothing, which is how the pane says it is done.
    board.click(PREV)
    board.wait_for_function("() => window.ctbConsole._state.exhausted === true",
                            timeout=4000)
    assert board.is_hidden(PREV)


def test_scrolling_up_still_loads_older_lines(board):
    """The freeze rename put a `var held` in this callback, which hoists over
    the held() predicate called a few lines above it: every automatic grow died
    with "held is not a function" before it could render a thing. `exhausted`
    is the flag only the end of that callback sets."""
    errors = []
    board.on("pageerror", lambda e: errors.append(str(e)))
    open_console(board)
    board.eval_on_selector("#ctb-console pre",
                           "el => { el.scrollTop = el.scrollHeight; }")
    board.wait_for_timeout(300)
    # Two marks, not one: the grow only fires on the way UP, and the handler
    # compares against the last scroll it saw.
    board.eval_on_selector("#ctb-console pre", "el => { el.scrollTop = 0; }")
    board.wait_for_function("() => window.ctbConsole._state.exhausted === true",
                            timeout=6000)
    assert errors == []


def test_neighbouring_requests_are_not_skipped(board):
    """Three turns two lines apart. Geometry alone walked 104 -> 100: landing
    104 below the top edge left 102 *inside* the view, where "above the view"
    could not see it. The walk remembers where it stands instead."""
    # Mid-pane, so the scroll range never runs out and every landing is exact.
    board.ctb_log = "\n".join(
        ("❯ 요청 %d" % i) if i in (40, 42, 44) else ("line %03d output" % i)
        for i in range(200))
    board.ctb_log_hash = "h-close"
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 44) < 80

    board.click(PREV)
    board.wait_for_timeout(200)
    # A tight band: if the press had skipped to 40, then 40 would be at ~56
    # and 42 a row and a half below it, outside this.
    assert 20 < where(board, 42) < 80, "42 is the turn before 44, not 40"


def test_output_drifting_the_landing_upward_does_not_re_offer_it(board):
    """A live pane repaints every two seconds, and with a fixed-size capture
    the landed request creeps back above the top edge. Judged by geometry it
    became a candidate again, so the next press returned to the SAME request,
    forever. The walk is remembered by the request's text, which survives the
    window sliding under it."""
    with_turns(board)
    board.wait_for_selector(PREV, state="visible")
    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 70) < 80

    # What the poll does to a scrolled reader: the same content, a little
    # further up. Enough to push the landing off the top edge.
    board.eval_on_selector("#ctb-console pre", "el => { el.scrollTop += 100; }")
    board.wait_for_timeout(200)
    assert where(board, 70) < 0, "the landing is above the view now"

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 10) < 80, "the press must go further back, not home"


def test_a_request_too_long_for_the_pane_is_still_reachable(board):
    """capture-pane -J rejoins a wrapped request into one long line, and
    pre-wrap draws it as many rows. Judged by its LAST row, a request whose
    opening words were already off-screen counted as "still in view" and could
    not be jumped to -- the pill skipped past it to an older turn."""
    board.ctb_log = "\n".join(
        ("❯ " + "아주 긴 요청입니다 " * 40) if i == 60 else ("line %03d output" % i)
        for i in range(120))
    board.ctb_log_hash = "h-wrap"
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")

    # Park the view so the request straddles the top edge: its first rows are
    # gone, its last rows are still on screen.
    straddles = board.evaluate(
        "() => { const el = document.querySelector('#ctb-console pre');"
        "        const n = el.querySelector(\"[data-line='60']\");"
        "        const t = el.getBoundingClientRect().top;"
        "        const r = n.getBoundingClientRect();"
        "        if (r.height < 40) return false;"
        "        el.scrollTop += r.top - t + r.height / 2;"
        "        const a = n.getBoundingClientRect();"
        "        return a.top < t && a.bottom > t; }")
    assert straddles, "the fixture must produce a request taller than one row"
    board.wait_for_timeout(200)

    board.wait_for_selector(PREV, state="visible")
    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 60) < 80, "the whole request comes back into view"


def test_the_same_request_twice_does_not_confuse_the_walk(board):
    """Sending the same words twice makes two identical lines. Remembered by
    text and resolved to "the nearest occurrence", the walk was handed back the
    turn it had just left. It counts turns from the newest instead."""
    board.ctb_log = "\n".join(
        "❯ 같은 요청" if i in (40, 60) else ("line %03d output" % i)
        for i in range(200))
    board.ctb_log_hash = "h-dupe"
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 60) < 80

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 40) < 80, "the older twin, not the one just left"


def test_the_window_sliding_does_not_send_the_walk_backwards(board):
    """Live output pushes lines out of the top of the window, so every index
    moves. Identified by text and "the nearest index", the walk resolved to the
    WRONG twin after a slide and handed back the request just visited. Counted
    from the newest, a slide cannot touch it."""
    def log(shift):
        rows = ["line %03d output" % i for i in range(200)]
        for i in (20, 40, 60):
            rows[i] = "❯ 오래된 요청" if i == 20 else "❯ 같은 요청"
        return "\n".join(rows[shift:] + ["new output"] * shift)

    board.ctb_log = log(0)
    board.ctb_log_hash = "h-slide-0"
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")
    board.click(PREV)                                 # the newer twin, line 60
    board.wait_for_timeout(150)
    board.click(PREV)                                 # the older twin, line 40
    board.wait_for_timeout(200)
    assert 0 < where(board, 40) < 80

    # Twelve lines of new output: 20 -> 8, 40 -> 28, 60 -> 48.
    board.ctb_log = log(12)
    board.ctb_log_hash = "h-slide-12"
    board.evaluate("() => { window.ctbConsole._state.skipped = 3; }")
    board.wait_for_function(
        "() => window.ctbConsole._state.lines[8].indexOf('오래된') > 0",
        timeout=6000)

    board.click(PREV)
    board.wait_for_timeout(200)
    assert 0 < where(board, 8) < 80, "the turn before the older twin"
    assert not (0 < where(board, 28) < 80), "not the twin we had just left"


def test_a_hold_hides_a_pill_it_could_not_act_on(board):
    """At the window edge the pill offers the next page of history, and a held
    pane cannot be grown. A button that answers a press with nothing -- no
    movement, no fetch, no word -- is worse than an absent one."""
    with_turns(board)
    scroll_up(board)                                  # to the oldest turn
    board.wait_for_timeout(400)
    assert board.is_visible(PREV)

    board.evaluate("""() => { const el = document.querySelector('#ctb-console pre');
      el.querySelector("[data-line='2']").dispatchEvent(
        new MouseEvent('click', {bubbles: true})); }""")
    assert frozen(board), "the tap has to have taken hold for this to mean anything"
    board.wait_for_timeout(200)
    assert board.is_hidden(PREV)


def test_going_back_to_live_cancels_a_landing_still_in_flight(board):
    """The press at the window edge fetches before it lands. Enter in the
    meantime says "back to work" -- and the landing, arriving after it, dragged
    the reader off the live end again and unpinned the pane behind them."""
    # The window starts 40 lines deep, so the turn at 190 is inside it and the
    # one at 150 is not: pressing has to fetch to reach it.
    board.ctb_log = "\n".join(
        ("❯ 요청 %d" % i) if i in (150, 190) else ("line %03d output" % i)
        for i in range(200))
    board.ctb_log_hash = "h-flight"
    board.ctb_log_window = True                       # a window that can grow
    open_console(board, "claude_beta")
    board.wait_for_selector(PREV, state="visible")
    scroll_up(board)                                  # to the oldest loaded turn
    board.wait_for_timeout(400)

    board.ctb_hold_log = True                         # the next fetch waits
    board.click(PREV)
    board.wait_for_function("() => window.ctbConsole._state.growing === true",
                            timeout=4000)

    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")                     # resumeLive, mid-flight
    board.wait_for_timeout(200)
    assert at_bottom(board)

    board.ctb_release_log()                           # the answer lands now
    board.wait_for_timeout(600)
    assert at_bottom(board), "the landing must not have pulled us back up"
    assert board.evaluate("() => window.ctbConsole._state.walk") is None
    assert board.evaluate("() => window.ctbConsole._state.pinned") is True


def test_the_find_bar_owns_the_top_while_it_is_open(board):
    """Both draw at the top of the pane and the bar is full width: leaving the
    pill under it makes a button nobody can press."""
    with_turns(board)
    board.wait_for_selector(PREV, state="visible")
    board.keyboard.press("Control+Shift+F")
    board.wait_for_selector(FIND, state="visible")
    assert board.is_hidden(PREV)
    board.keyboard.press("Escape")
    board.wait_for_selector(PREV, state="visible")


def test_the_pill_thaws_a_frozen_pane_too(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")
    scroll_up(board)
    board.wait_for_selector(PILL, state="visible")
    board.click(PILL)
    assert not frozen(board)


# --- find in the output -----------------------------------------------------

def open_find(board):
    board.keyboard.press("Control+Shift+f")
    board.wait_for_selector(FIND, state="visible")


def count(board):
    return board.eval_on_selector(FIND + " [aria-live]", "e => e.textContent")


def test_the_chord_opens_the_find_bar_and_freezes_the_pane(board):
    open_console(board)
    open_find(board)
    assert frozen(board)
    assert board.evaluate("document.activeElement.id") == "con-find-input"


def test_the_session_palette_keeps_plain_ctrl_f(board):
    open_console(board)
    board.keyboard.press("Control+f")
    board.wait_for_selector("#con-find", state="hidden")
    assert board.evaluate(
        "() => [...document.querySelectorAll('[role=option],[data-search-session]')]"
        ".length > 0")


def test_typing_highlights_every_match_and_counts_them(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 3
    assert count(board) == "1/3"


def test_enter_steps_through_the_matches_and_shift_enter_goes_back(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.keyboard.press("Enter")
    assert count(board) == "2/3"
    board.keyboard.press("Enter")
    assert count(board) == "3/3"
    board.keyboard.press("Enter")          # wraps
    assert count(board) == "1/3"
    board.keyboard.press("Shift+Enter")
    assert count(board) == "3/3"


def test_the_current_match_is_scrolled_into_view(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")          # first hit is on line 7, far up
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    assert board.evaluate(
        "() => { const m = document.querySelector('#ctb-console mark[data-find-hit]');"
        "        const p = document.querySelector('#ctb-console pre');"
        "        const a = m.getBoundingClientRect(), b = p.getBoundingClientRect();"
        "        return a.top >= b.top - 2 && a.bottom <= b.bottom + 2; }")


def test_a_word_that_is_not_there_says_so(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("zzzzz")
    assert count(board) == "없음"
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0


def test_matches_survive_a_link_in_the_line(board):
    """A match that crosses a linkified URL must still highlight.

    Range.surroundContents refuses a range that only half-contains an
    element, and the naive version silently dropped those hits.
    """
    open_console(board)
    board.evaluate(
        "() => window.ctbConsole._renderTail('see http://x.test/a now')")
    # "a now" starts inside the <a> and ends outside it.
    assert board.eval_on_selector_all("#ctb-console [data-line='0'] a",
                                      "els => els.length") == 1
    open_find(board)
    board.keyboard.type("a now")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 1
    assert board.eval_on_selector("#ctb-console [data-line='0']",
                                  "e => e.textContent") == "see http://x.test/a now"


def test_escape_closes_find_and_leaves_the_console_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Escape")
    board.wait_for_selector(FIND, state="hidden")
    assert board.is_visible(CONSOLE)
    assert not frozen(board)
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_closing_find_leaves_no_highlights_behind(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.wait_for_selector("#ctb-console mark[data-find-hit]")
    board.keyboard.press("Escape")
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0
    assert board.eval_on_selector("#ctb-console [data-line='7']",
                                  "e => e.textContent") == "line 007 needle here"


def test_terminal_keys_stand_down_while_the_find_bar_is_open(board):
    """Ctrl+U over the console is a kill-line for tmux. Not while searching.

    Guarded twice on purpose: the bar swallows its own keys, and keysTaken()
    stands the console's shortcuts down for anything that starts elsewhere in
    the sheet while the bar is up.
    """
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.keyboard.press("Control+u")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Control+u")
    board.wait_for_timeout(300)
    assert not any("/key" in u for u in board.ctb_requests)


def test_enter_recovery_stands_down_while_the_find_bar_is_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Enter")
    assert board.is_visible(FIND)


def test_switching_session_closes_the_find_bar(board):
    open_console(board)
    open_find(board)
    board.evaluate("() => window.ctbConsole.open('claude_beta')")
    board.wait_for_selector(FIND, state="hidden")
    assert not frozen(board)


# --- Shift+Escape sends Escape to the session -------------------------------

def test_shift_escape_sends_escape_to_the_session(board):
    open_console(board)
    board.keyboard.press("Shift+Escape")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]
    assert board.is_visible(CONSOLE)


def test_holding_shift_escape_sends_one_escape(board):
    """Every repeat would be another interrupt aimed at a live session."""
    open_console(board)
    board.keyboard.down("Shift")
    board.keyboard.down("Escape")
    for _ in range(5):
        board.evaluate(
            "() => document.dispatchEvent(new KeyboardEvent('keydown',"
            "  {key:'Escape', shiftKey:true, repeat:true, bubbles:true}))")
    board.keyboard.up("Escape")
    board.keyboard.up("Shift")
    board.wait_for_timeout(400)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]


def test_plain_escape_still_closes_the_console(board):
    open_console(board)
    board.keyboard.press("Escape")
    board.wait_for_selector(CONSOLE, state="hidden")


# --- what recovery costs and what it restores -------------------------------

def test_recovery_asks_for_the_pane_exactly_once(board):
    """Not zero (the console sits on a stale pane), not twice."""
    open_console(board)
    board.evaluate("() => window.ctbConsole._state.timer && clearInterval(0)")
    before = logs(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_timeout(500)
    assert logs(board) - before == 1


def test_recovery_from_a_frozen_pane_asks_exactly_once(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")      # freezes; stops the poll
    board.wait_for_timeout(300)
    before = logs(board)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    board.wait_for_timeout(500)
    assert logs(board) - before == 1


def test_recovery_restarts_the_poll_that_the_freeze_stopped(board):
    open_console(board)
    board.click("#ctb-console [data-line='3']")
    board.wait_for_timeout(300)
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    before = logs(board)
    board.wait_for_timeout(2600)                     # POLL_MS is 2000
    assert logs(board) > before


def test_recovery_does_not_leave_history_loading_stuck(board):
    """The queued repaint it drops is what used to clear `growing`."""
    open_console(board)
    board.evaluate("() => { window.ctbConsole._state.growing = true; }")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.press("Enter")
    assert board.evaluate("() => window.ctbConsole._state.growing") is False


def test_holding_enter_does_not_send_the_draft(board):
    """The press that recovered the console lands in the prompt box.

    Held down, the repeats arrive there -- and the box may be holding a draft
    written hours ago. The physical press has to end before the box counts as
    typed into.
    """
    open_console(board)
    board.fill("#ctb-console textarea", "rm -rf something")
    board.evaluate("document.activeElement.blur()")
    board.keyboard.down("Enter")
    for _ in range(4):
        board.evaluate(
            "() => document.querySelector('#ctb-console textarea')"
            "  .dispatchEvent(new KeyboardEvent('keydown',"
            "    {key:'Enter', repeat:true, bubbles:true}))")
    board.keyboard.up("Enter")
    board.wait_for_timeout(300)
    assert board.input_value("#ctb-console textarea") == "rm -rf something"
    assert not any("prompt" in u for u in board.ctb_requests)
    # And the press after the release is a normal send again.
    board.click("#ctb-console textarea")
    board.keyboard.press("Enter")
    board.wait_for_timeout(300)
    assert any("prompt" in u for u in board.ctb_requests)


def test_find_leaves_the_palette_chord_alone(board):
    """Ctrl+F from inside the find box still opens the session palette."""
    open_console(board)
    open_find(board)
    board.keyboard.press("Control+f")
    assert board.evaluate(
        "() => [...document.querySelectorAll('[data-search-session]')].length > 0")


def test_a_dead_session_closes_the_find_bar(board):
    open_console(board)
    open_find(board)
    board.keyboard.type("needle")
    board.evaluate("() => window.ctbConsole._sessionGone()")
    assert board.is_hidden(FIND)
    assert board.eval_on_selector_all("#ctb-console mark[data-find-hit]",
                                      "els => els.length") == 0


# --- one-shot key send ------------------------------------------------------

def arm(board):
    board.keyboard.press("Control+Period")
    board.wait_for_function(
        "() => window.ctbConsole._sendArmed()")


def status(board):
    return board.eval_on_selector("#ctb-console [role=status]", "e => e.textContent")


def test_arming_says_so_on_the_status_line(board):
    """An armed console that looks idle is a trap: the next key leaves."""
    open_console(board)
    arm(board)
    assert "다음 한 키를 세션으로" in status(board)


def test_the_armed_key_goes_to_the_session_not_into_the_prompt_box(board):
    """The caret is in the box; Enter there normally sends the draft."""
    open_console(board)
    board.fill("#ctb-console textarea", "draft that must not be sent")
    arm(board)
    board.keyboard.press("Enter")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Enter"]
    assert board.input_value("#ctb-console textarea") == "draft that must not be sent"
    assert not any("prompt" in u for u in board.ctb_requests)


def test_a_digit_is_sent_instead_of_switching_session(board):
    open_console(board)
    arm(board)
    board.keyboard.press("3")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["3"]
    assert board.evaluate("() => window.ctbConsole._state.session") == "claude_alpha"


def test_dom_key_names_are_translated_for_the_server(board):
    """The allowlist speaks tmux: Up, not ArrowUp; BSpace, not Backspace."""
    open_console(board)
    arm(board)
    board.keyboard.press("ArrowUp")
    board.wait_for_timeout(200)
    arm(board)
    board.keyboard.press("Backspace")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Up", "BSpace"]


def test_escape_is_sent_rather_than_closing_the_console(board):
    open_console(board)
    arm(board)
    board.keyboard.press("Escape")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Escape"]
    assert board.is_visible(CONSOLE)


def test_tab_is_sent_rather_than_moving_the_focus(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("Tab")
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["Tab"]
    assert board.evaluate("document.activeElement.tagName") == "TEXTAREA"


def test_it_disarms_after_exactly_one_key(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("y")
    board.wait_for_timeout(200)
    board.keyboard.press("y")              # a letter again, this time typed
    board.wait_for_timeout(300)
    assert [k["key"] for k in board.ctb_keys] == ["y"]
    assert board.input_value("#ctb-console textarea") == "y"


def test_the_chord_again_changes_your_mind(board):
    open_console(board)
    arm(board)
    board.keyboard.press("Control+Period")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False
    board.keyboard.press("Escape")         # and Escape is the console's again
    board.wait_for_selector(CONSOLE, state="hidden")
    assert board.ctb_keys == []


def test_a_key_that_cannot_be_sent_cancels_and_says_so(board):
    open_console(board)
    board.click("#ctb-console textarea")
    arm(board)
    board.keyboard.press("q")
    board.wait_for_timeout(300)
    assert board.ctb_keys == []
    assert "보낼 수 없는 키" in status(board)
    assert board.input_value("#ctb-console textarea") == ""


def test_a_chord_stands_the_mode_down_and_passes_through(board):
    """Changing your mind by reaching for another shortcut."""
    open_console(board)
    arm(board)
    board.keyboard.press("Control+Shift+f")
    board.wait_for_selector(FIND, state="visible")
    assert board.ctb_keys == []
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False


def test_it_does_not_arm_while_the_find_bar_is_open(board):
    open_console(board)
    open_find(board)
    board.keyboard.press("Control+Period")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False


def test_switching_session_disarms(board):
    open_console(board)
    arm(board)
    board.evaluate("() => window.ctbConsole.open('claude_beta')")
    assert board.evaluate("() => window.ctbConsole._sendArmed()") is False
