"""What state each session is in, said in words, on both console surfaces.

The rail at the top of the console showed state as a 7px coloured dot and
nothing else, and it was painted when the console opened and then left alone:
it repaints on a switch, on the number-hint hold, on a quadrant write and when
a session ends, but it did not listen for new session data. A session could
finish and its dot would still read as working for as long as the console
stayed up. So the surface meant to tell you what was going on was the one that
had stopped asking.

Three things are asserted here, in order of what they cost the user:
  1. state is legible without decoding a colour -- a word on every chip and
     every palette row, plus `data-live` for the ones that breathe;
  2. new data reaches both surfaces, and reaches them IN PLACE: no reorder, no
     rebuild, no scroll jump, because a rail that rearranges under the hand is
     worse than one that is slightly stale;
  3. the palette's selection survives all of it -- it is tracked by session
     name, so Enter opens the row that was highlighted.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

PALETTE = "[role='dialog'][aria-label='세션 검색']"
CHIP = "#ctb-console [data-switch-session]"


def open_console(page, name="claude_alpha"):
    page.evaluate("n => window.ctbConsole.open(n)", name)
    page.wait_for_selector("#ctb-console", state="visible")


def open_palette(page):
    page.keyboard.press("Control+f")
    page.wait_for_selector(PALETTE, state="visible")


def chip_text(page, name):
    return page.inner_text(f'{CHIP}[data-switch-session="{name}"]')


def row_text(page, name):
    return page.inner_text(f'[data-search-session="{name}"]')


# --- 1. the word, not just the colour ---------------------------------------

def test_the_rail_says_the_state_in_words(board):
    open_console(board)
    assert "작업중" in chip_text(board, "claude_alpha")      # state=working
    assert "입력대기" in chip_text(board, "claude_beta")      # state=waiting
    assert "유휴" in chip_text(board, "claude_gamma")         # state=idle


def test_idle_and_waiting_are_not_the_same_word(board):
    """They were both "대기", which are opposite things to do next."""
    open_console(board)
    assert "입력대기" in chip_text(board, "claude_beta")
    assert "입력대기" not in chip_text(board, "claude_gamma")


def test_the_palette_says_the_state_too(board):
    open_console(board)
    open_palette(board)
    assert "작업중" in row_text(board, "claude_alpha")
    assert "유휴" in row_text(board, "claude_gamma")


def test_live_states_are_marked_for_motion_and_settled_ones_are_not(board):
    """`data-live` is the hook the breathing animation hangs off."""
    open_console(board)
    live = board.eval_on_selector_all(
        CHIP + " .ctb-sdot",
        "d => d.map(x => x.hasAttribute('data-live'))")
    names = board.eval_on_selector_all(
        CHIP, "c => c.map(x => x.dataset.switchSession)")
    by_name = dict(zip(names, live))
    assert by_name["claude_alpha"] is True      # working
    assert by_name["claude_beta"] is True       # waiting on you
    assert by_name["claude_gamma"] is False     # idle sits still


def test_the_dot_is_decoration_to_a_screen_reader(board):
    open_console(board)
    assert board.eval_on_selector_all(
        CHIP + " .ctb-sdot",
        "d => d.every(x => x.getAttribute('aria-hidden') === 'true')")


def test_the_accessible_name_carries_branch_and_state(board):
    """The visible text is clipped to an ellipsis and the dot is hidden, so
    the label is the only place the whole answer exists."""
    open_console(board)
    label = board.get_attribute(
        f'{CHIP}[data-switch-session="claude_alpha_wt_topic"]', "aria-label")
    assert "topic" in label and "유휴" in label


# --- 2. new data reaches the surfaces, in place ------------------------------

def test_the_rail_follows_a_state_change(board):
    open_console(board)
    assert "작업중" in chip_text(board, "claude_alpha")
    board.ctb_set_state("claude_alpha", "idle")
    assert "유휴" in chip_text(board, "claude_alpha")


def test_the_rail_updates_without_rebuilding_or_reordering(board):
    """A chip that is replaced is a chip that moves out from under the hand.

    A property set on a live node cannot survive replacement, so it answers
    the only question that matters: is this the same chip?
    """
    open_console(board)
    before = board.eval_on_selector_all(
        CHIP, "c => c.map(x => x.dataset.switchSession)")
    board.eval_on_selector(f'{CHIP}[data-switch-session="claude_alpha"]',
                           "c => { c.__probe = 'kept'; }")
    board.ctb_set_state("claude_alpha", "idle")
    assert board.eval_on_selector(
        f'{CHIP}[data-switch-session="claude_alpha"]', "c => c.__probe") == "kept"
    after = board.eval_on_selector_all(
        CHIP, "c => c.map(x => x.dataset.switchSession)")
    assert after == before, "the rail re-sorted under the user"


def test_the_open_session_keeps_its_chip_when_it_ends(board):
    """Losing it is how you end up unable to switch away from a dead pane.

    Ending it for real: the session leaves the list and its pane starts
    answering 404, which is what makes the console declare it gone.
    """
    open_console(board, "claude_gamma")
    board.ctb_drop_session("claude_gamma")
    board.wait_for_timeout(400)
    chip = f'{CHIP}[data-switch-session="claude_gamma"]'
    assert board.is_visible(chip)
    # And it does not go on claiming the state it had when it died. Which
    # signal arrived first -- the board dropping it, or its own pane
    # answering 404 -- must not change this.
    assert "종료됨" in board.inner_text(chip)
    assert "종료됨" in board.get_attribute(chip, "aria-label")


def test_the_state_lane_holds_the_longest_word(board):
    """A word that outgrows its lane resizes the chip and slides the ones
    after it -- under a finger already on its way down."""
    open_console(board)
    widest = board.eval_on_selector(f'{CHIP} .ctb-slabel', """el => {
        const probe = el.cloneNode(true);
        probe.style.minWidth = '0';
        probe.style.position = 'absolute';
        document.body.appendChild(probe);
        let w = 0;
        for (const word of ['작업중', '입력대기', '응답없음', '오류',
                            '한도', '유휴', '상태미상', '종료됨']) {
          probe.textContent = word;
          w = Math.max(w, probe.getBoundingClientRect().width);
        }
        probe.remove();
        return w; }""")
    reserved = board.eval_on_selector(
        f'{CHIP} .ctb-slabel', "el => el.getBoundingClientRect().width")
    assert widest <= reserved, f"{widest}px word in a {reserved}px lane"


def test_a_filtered_away_session_is_not_called_dead(board):
    """The rail is built from the board's VISIBLE order, which the age filter
    shortens. Search reaches past that filter and opens what it finds, so a
    live session arrives on the rail missing from that list routinely --
    absence from it is not evidence of death.
    """
    board.click('#filter-age [data-age="1h"]')      # hides gamma (3 days old)
    board.wait_for_timeout(80)
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.keyboard.type("gamma")
    board.wait_for_timeout(80)
    board.keyboard.press("Enter")
    board.wait_for_function(
        "() => window.ctbConsole._state.session === 'claude_gamma'")
    chip = f'{CHIP}[data-switch-session="claude_gamma"]'
    assert board.is_visible(chip)
    assert "종료됨" not in board.inner_text(chip)
    assert "유휴" in board.inner_text(chip)


def test_the_open_session_keeps_its_chip_when_the_filter_hides_everything(board):
    """The rail going dark takes the only marker of where the user is.

    Search reaches past the age filter, so "the filter hid every session on
    the board" and "there is a session open on this screen" happen together.
    """
    # Filter first, then open: the rail is BUILT at that moment, and building
    # it from an empty list is the case under test. (Patching an existing rail
    # keeps the chip for other reasons, which would hide this.)
    board.click('#filter-age [data-age="30d"]')
    board.wait_for_timeout(80)
    board.click('#filter-age button:first-child')   # "오래된" — older than a month
    board.wait_for_timeout(150)                      # nothing qualifies
    assert board.eval_on_selector_all("#grid [data-session-name]",
                                      """c => c.filter(x => {
                                           for (let e = x; e; e = e.parentElement)
                                             if (e.style && e.style.display === 'none')
                                               return false;
                                           return true; }).length""") == 0
    open_console(board, "claude_gamma")
    chip = f'{CHIP}[data-switch-session="claude_gamma"]'
    assert board.is_visible(chip)
    assert "유휴" in board.inner_text(chip)
    assert "종료됨" not in board.inner_text(chip)


def test_a_newcomer_does_not_replace_the_rows_you_are_looking_at(board):
    """A session arriving must not throw away the row under a finger, nor
    scroll the list back to the keyboard selection -- least of all one that
    does not match what is typed.
    """
    open_console(board, "claude_alpha")
    open_palette(board)
    board.keyboard.type("a")            # matches several, not the newcomer
    board.wait_for_timeout(80)
    board.eval_on_selector("[data-search-session]", "r => { r.__probe = 'kept'; }")
    board.ctb_sessions = board.ctb_sessions + [
        {"name": "claude_zzz", "state": "working",
         "updated_at": 0, "last_activity": 0, "work_context": ""}]
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(200)
    assert board.eval_on_selector(
        "[data-search-session]", "r => r.__probe") == "kept"
    # ...and it is not shown either, because it does not match the query.
    assert not board.is_visible('[data-search-session="claude_zzz"]')


def test_escape_reaches_the_launcher_when_the_card_is_gone_from_view(board):
    """focus() on a card the age filter has hidden is a no-op that reports
    nothing, and Escape used to stop there -- leaving the caret nowhere."""
    card = '[data-session-name="claude_gamma"]'
    board.eval_on_selector(card, "c => c.focus()")
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    # It ages out while the palette is up. Dispatched rather than clicked:
    # the palette is modal, which is the whole reason the user cannot see
    # this happening behind it.
    board.eval_on_selector('#filter-age [data-age="1h"]', "b => b.click()")
    board.wait_for_timeout(80)
    board.keyboard.press("Escape")
    board.wait_for_selector(PALETTE, state="hidden")
    assert board.evaluate(
        "() => document.activeElement && document.activeElement.id") \
        == "btn-find-session"


def test_the_palette_follows_a_state_change_while_it_is_open(board):
    open_console(board)
    open_palette(board)
    assert "작업중" in row_text(board, "claude_alpha")
    board.ctb_set_state("claude_alpha", "stuck_after_agent")
    assert "응답없음" in row_text(board, "claude_alpha")


def test_a_session_that_ends_is_marked_not_removed(board):
    """The row you are pointing at must not vanish as you reach for it."""
    open_console(board)
    open_palette(board)
    board.ctb_drop_session("claude_gamma")
    row = f'[data-search-session="claude_gamma"]'
    assert board.is_visible(row)
    assert "종료됨" in board.inner_text(row)


def test_picking_a_session_that_ended_says_so_instead_of_opening_it(board):
    open_console(board, "claude_alpha")
    open_palette(board)
    board.ctb_drop_session("claude_gamma")
    board.click('[data-search-session="claude_gamma"]')
    board.wait_for_timeout(100)
    assert board.evaluate("window.ctbConsole._state.session") == "claude_alpha"
    assert board.is_visible(PALETTE)
    # It has to SAY so -- a palette that just ignores the click is a broken
    # palette as far as the person clicking it is concerned.
    assert "종료" in board.inner_text(f"{PALETTE} [role='status']")
    # ...and the keyboard has to still work afterwards. A click lands on a
    # row, which is not focusable, so without handing focus back the arrows,
    # the typing and Escape were all dead.
    assert board.evaluate(
        f"""() => document.activeElement
              === document.querySelector("{PALETTE} input")""")
    board.keyboard.press("ArrowDown")
    assert board.evaluate(
        "() => !!document.querySelector('[aria-selected=\"true\"]')")


def test_the_refusal_speaks_on_a_board_with_no_console(board):
    """The palette used to borrow the console's status line, which does not
    exist until a console has been built."""
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    board.ctb_drop_session("claude_gamma")
    board.click('[data-search-session="claude_gamma"]')
    board.wait_for_timeout(100)
    assert "종료" in board.inner_text(f"{PALETTE} [role='status']")
    assert not board.is_visible("#ctb-console")


def test_the_dots_have_a_size_on_first_use_from_the_board(board):
    """Opened before any console existed, the palette's dots were empty spans.

    The styles that give them their size and their breathing live in the
    console's stylesheet, which only a console used to install.
    """
    board.keyboard.press("f")
    board.wait_for_selector(PALETTE, state="visible")
    # Computed style, not a bounding box: the dot breathes with a transform,
    # and a rect sampled mid-breath is up to 9.45px of a 7px dot.
    box = board.eval_on_selector(
        f"{PALETTE} .ctb-sdot",
        "d => { const c = getComputedStyle(d); return [c.width, c.height]; }")
    assert box == ["7px", "7px"]


def test_typing_does_not_bring_back_a_stale_state(board):
    """Rows are rebuilt from the frozen list when the query changes, and the
    list remembers the state each session had when the palette opened."""
    open_console(board, "claude_alpha")
    open_palette(board)
    board.ctb_set_state("claude_gamma", "stuck_after_agent")
    assert "응답없음" in row_text(board, "claude_gamma")
    board.keyboard.type("gam")
    board.wait_for_timeout(80)
    assert "응답없음" in row_text(board, "claude_gamma")
    assert "유휴" not in row_text(board, "claude_gamma")


def test_typing_does_not_resurrect_an_ended_session(board):
    open_console(board, "claude_alpha")
    open_palette(board)
    board.ctb_drop_session("claude_gamma")
    board.keyboard.type("gam")
    board.wait_for_timeout(80)
    assert "종료됨" in row_text(board, "claude_gamma")


def test_a_session_started_while_the_palette_is_open_is_findable(board):
    """Membership is reconciled; only the ORDER is frozen.

    A palette opened while the board was still loading used to say "no
    sessions" for as long as it stayed open, whatever arrived afterwards.
    """
    open_console(board, "claude_alpha")
    open_palette(board)
    # The query is typed FIRST, so the palette is sitting on "no matches"
    # when the session arrives. Typing afterwards would have hidden the bug:
    # a keystroke is what used to be needed to see anything new at all.
    board.keyboard.type("newcomer")
    board.wait_for_timeout(80)
    assert "일치하는 세션 없음" in board.inner_text(PALETTE)
    board.ctb_sessions = board.ctb_sessions + [
        {"name": "claude_newcomer", "state": "working",
         "updated_at": 0, "last_activity": 0, "work_context": ""}]
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(200)
    assert board.is_visible('[data-search-session="claude_newcomer"]')


def test_a_rail_emptied_by_the_last_session_can_come_back(board):
    """Hidden because empty must not mean hidden forever.

    The console is closed first, so nothing is holding a chip open: with a
    session still on screen its own chip keeps the rail up, and the revive
    path is never the thing under test.
    """
    open_console(board, "claude_alpha")
    board.evaluate("() => window.ctbConsole.close()")
    board.ctb_sessions = []
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(150)
    assert board.eval_on_selector_all(CHIP, "c => c.length") == 0
    board.ctb_sessions = [{"name": "claude_later", "state": "working",
                           "updated_at": 0, "last_activity": 0,
                           "work_context": ""}]
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(200)
    board.evaluate("() => window.ctbConsole.open('claude_later')")
    board.wait_for_timeout(150)
    assert board.is_visible(f'{CHIP}[data-switch-session="claude_later"]')


def test_a_new_session_does_not_rebuild_the_rail(board):
    """It goes on the end. A rebuild between a finger going down and coming
    up throws away the chip that was being pressed."""
    open_console(board, "claude_alpha")
    board.eval_on_selector(f'{CHIP}[data-switch-session="claude_alpha"]',
                           "c => { c.__probe = 'kept'; }")
    board.ctb_sessions = board.ctb_sessions + [
        {"name": "claude_newcomer", "state": "working",
         "updated_at": 0, "last_activity": 0, "work_context": ""}]
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(200)
    assert board.is_visible(f'{CHIP}[data-switch-session="claude_newcomer"]')
    assert board.eval_on_selector(
        f'{CHIP}[data-switch-session="claude_alpha"]', "c => c.__probe") == "kept"


def _contrast(page, selector):
    """Contrast of the text in `selector` against what is actually behind it.

    Blends in sRGB channels (not in luminance, which is not linear in the
    thing being blended) and walks up for the first non-transparent
    background, so a selected row is measured against the selection, not
    against the sheet it is drawn on.
    """
    return page.eval_on_selector(selector, """el => {
        const rgb = (c) => (c.match(/[\\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
        const alpha = (c) => {
          const p = (c.match(/[\\d.]+/g) || []);
          return p.length > 3 ? Number(p[3]) : 1;
        };
        const lum = ([r, g, b]) => {
          const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92
                                      : Math.pow((v + 0.055) / 1.055, 2.4); };
          return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        };
        let bg = [255, 255, 255];
        for (let n = el; n; n = n.parentElement) {
          const c = getComputedStyle(n).backgroundColor;
          if (c && alpha(c) > 0) { bg = rgb(c); break; }
        }
        const cs = getComputedStyle(el);
        let a = Number(cs.opacity || 1);
        for (let n = el.parentElement; n; n = n.parentElement) {
          a *= Number(getComputedStyle(n).opacity || 1);
        }
        const fg = rgb(cs.color).map((v, i) => v * a + bg[i] * (1 - a));
        const hi = Math.max(lum(fg), lum(bg)), lo = Math.min(lum(fg), lum(bg));
        return (hi + 0.05) / (lo + 0.05);
      }""")


@pytest.mark.parametrize("theme", ["light", "dark", "parchment"])
@pytest.mark.parametrize("session,word", [("claude_alpha", "작업중"),
                                          ("claude_gamma", "유휴")])
def test_state_words_are_readable_in_every_theme(theme, session, word):
    """A word nobody can read is decoration with a font.

    Both weights matter: the settled one was the placeholder grey, which
    measures 3.8:1 on the light sheet and 2.1:1 on a selected row.
    """
    from live_board import open_board
    with open_board(theme=theme) as page:
        page.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
        page.wait_for_selector("#ctb-console", state="visible")
        chip = f'{CHIP}[data-switch-session="{session}"] .ctb-slabel'
        assert word in page.inner_text(chip)
        ratio = _contrast(page, chip)
        assert ratio >= 4.5, f"{theme} rail {word}: {ratio:.2f}:1"

        # And on a palette row, including the selected one, whose background
        # is the selection colour rather than the sheet.
        page.keyboard.press("Control+f")
        page.wait_for_selector(PALETTE, state="visible")
        row = f'[data-search-session="{session}"] .ctb-slabel'
        ratio = _contrast(page, row)
        assert ratio >= 4.5, f"{theme} palette {word}: {ratio:.2f}:1"
        sel = "[aria-selected='true'] .ctb-slabel"
        ratio = _contrast(page, sel)
        assert ratio >= 4.5, f"{theme} selected row: {ratio:.2f}:1"


def test_the_palette_can_still_find_a_session_by_what_it_is_working_on(board):
    """The board's search box matched work_context and the last prompt.

    That box is gone. A search that can only match the name cannot find "the
    one where I was fixing the parser" the way the old one could, so the
    palette carries the same haystack.
    """
    open_console(board, "claude_alpha")
    open_palette(board)
    # claude_delta's work_context is "alpha mentioned here" (see live_board).
    board.keyboard.type("mentioned")
    board.wait_for_timeout(80)
    assert board.is_visible('[data-search-session="claude_delta"]')


def test_a_name_match_still_outranks_a_context_match(board):
    open_console(board, "claude_beta")
    open_palette(board)
    board.keyboard.type("alpha")
    board.wait_for_timeout(80)
    first = board.eval_on_selector_all(
        "[data-search-session]", "r => r.map(x => x.dataset.searchSession)")[0]
    assert first == "claude_alpha"


def test_the_state_word_is_readable_against_its_background(board):
    """The word exists so state does not have to be decoded from a colour.

    Painted in the dot's colour it measured about 1.5:1 on the light theme --
    unreadable at 10px, which would have made the word decoration too.
    """
    open_console(board)
    ratio = board.eval_on_selector(
        f'{CHIP}[data-switch-session="claude_alpha"] .ctb-slabel',
        """el => {
             const lum = (c) => {
               const [r, g, b] = c.match(/\\d+(\\.\\d+)?/g).slice(0, 3).map(Number)
                 .map(v => { v /= 255; return v <= 0.03928 ? v / 12.92
                                       : Math.pow((v + 0.055) / 1.055, 2.4); });
               return 0.2126 * r + 0.7152 * g + 0.0722 * b;
             };
             let bg = 'rgba(0, 0, 0, 0)';
             for (let n = el; n; n = n.parentElement) {
               const c = getComputedStyle(n).backgroundColor;
               if (c && !c.startsWith('rgba(0, 0, 0, 0')) { bg = c; break; }
             }
             const cs = getComputedStyle(el);
             const a = parseFloat(cs.opacity || '1');
             const fg = lum(cs.color), b2 = lum(bg);
             // Flatten the label's own opacity against what is behind it.
             const eff = fg * a + b2 * (1 - a);
             const hi = Math.max(eff, b2), lo = Math.min(eff, b2);
             return (hi + 0.05) / (lo + 0.05);
           }""")
    assert ratio >= 4.5, f"state word contrast is {ratio:.2f}:1"


# --- 3. the selection survives -----------------------------------------------

def test_arrowing_does_not_rebuild_the_list(board):
    open_console(board)
    open_palette(board)
    board.eval_on_selector("[data-search-session]", "r => { r.__probe = 'kept'; }")
    board.keyboard.press("ArrowDown")
    board.keyboard.press("ArrowUp")
    assert board.eval_on_selector("[data-search-session]", "r => r.__probe") == "kept"


def test_enter_opens_the_row_that_was_highlighted(board):
    """The list is frozen when the palette opens and the selection is a name.

    It used to be a row index into a list rebuilt from a catalogue that sorts
    by state -- so a session changing state between the arrow key and Enter
    handed you a different session.
    """
    open_console(board, "claude_alpha")
    open_palette(board)
    # Down to the first UNPINNED row: the pinned block sorts ahead and does
    # not move, so a selection inside it would survive a re-sort by accident
    # and prove nothing.
    for _ in range(3):
        board.keyboard.press("ArrowDown")
    picked = board.evaluate(
        "() => document.querySelector('[aria-selected=\"true\"]')"
        ".dataset.searchSession")
    # A session changing state re-sorts the catalogue (pin, then state, then
    # recency), and the arrows are what used to re-read it.
    board.ctb_set_state("claude_gamma", "working")
    board.keyboard.press("ArrowDown")
    board.keyboard.press("ArrowUp")
    assert board.evaluate(
        "() => document.querySelector('[aria-selected=\"true\"]')"
        ".dataset.searchSession") == picked, "the highlight moved on its own"
    board.keyboard.press("Enter")
    board.wait_for_timeout(120)
    assert board.evaluate("window.ctbConsole._state.session") == picked


def test_the_highlight_is_announced(board):
    open_console(board)
    open_palette(board)
    board.keyboard.press("ArrowDown")
    active = board.get_attribute(f"{PALETTE} input", "aria-activedescendant")
    assert active
    assert board.get_attribute("#" + active, "aria-selected") == "true"


def test_enter_mid_hangul_belongs_to_the_ime(board):
    """Confirming a syllable is not choosing a session."""
    open_console(board, "claude_alpha")
    open_palette(board)
    board.evaluate(
        f"""() => document.querySelector("{PALETTE} input").dispatchEvent(
              new KeyboardEvent('keydown',
                {{key:'Enter', isComposing:true, bubbles:true}}))""")
    board.wait_for_timeout(100)
    assert board.is_visible(PALETTE)
    assert board.evaluate("window.ctbConsole._state.session") == "claude_alpha"


# --- the ghost list ----------------------------------------------------------

def test_an_empty_board_beats_the_consoles_own_fallback_snapshot(board):
    """The console keeps a snapshot it fetched for itself, for the case where
    the board has not published anything yet (a deep link, the VSCode webview
    before its first poll). Published-and-empty has to beat that snapshot, or
    the last session ending leaves the rail rebuilding the dead ones from it.

    `_state.order` is set here the way fetchOrder() sets it -- reaching for
    the internal is the point: it is the fallback under test.
    """
    open_console(board, "claude_alpha")
    board.evaluate("""() => { window.ctbConsole._state.order = [
        {name:'claude_ghost', label:'ghost', branch:null, state:'working'}]; }""")
    board.evaluate("() => window.ctbConsole.close()")
    board.ctb_sessions = []
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(200)
    assert board.eval_on_selector_all(CHIP, "c => c.length") == 0
    board.evaluate("() => window.ctbConsole.openPalette()")
    board.wait_for_selector(PALETTE, state="visible")
    assert "일치하는 세션 없음" in board.inner_text(PALETTE)


def test_an_empty_board_leaves_no_ghosts_in_the_palette(board):
    """An empty array is an answer, not a missing one.

    It used to fall back to the last published order, so with every session
    gone the palette still listed them -- and Enter opened a console onto a
    pane that will never answer.
    """
    open_console(board)
    board.ctb_sessions = []
    board.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    board.wait_for_timeout(150)
    board.evaluate("() => window.ctbConsole.openPalette()")
    board.wait_for_selector(PALETTE, state="visible")
    assert "일치하는 세션 없음" in board.inner_text(PALETTE)
