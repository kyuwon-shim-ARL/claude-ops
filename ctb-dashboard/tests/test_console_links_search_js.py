"""Behavioural tests for the console's tail links and session search.

Both run the real shipped JS through node rather than asserting that some
string appears in the file: what matters here is where a URL ends when a
sentence continues past it, and which session a rough query ranks first --
neither of which a presence check can see.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CONSOLE_JS = (
    Path(__file__).resolve().parents[1]
    / "src" / "ctb_dashboard" / "static" / "js" / "session-control.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
global.window = {{ location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}} }};
global.document = {{
  addEventListener(){{}}, readyState:'complete',
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const args = JSON.parse({payload});
process.stdout.write(JSON.stringify(window.ctbConsole.{fn}(...args)));
"""


def _call(fn, *args):
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        payload=json.dumps(json.dumps(list(args))),
        fn=fn,
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def seg_lines(lines, cols=0):
    """Segments for a whole block, as the tail renders it."""
    return _call("_linkifyLines", lines, cols)


def urls_in(lines, cols=0):
    """Every distinct href the block would produce, in order."""
    out = []
    for line in seg_lines(lines, cols):
        for part in line:
            if part["url"] and (not out or out[-1] != part["url"]):
                out.append(part["url"])
    return out


def links(line):
    """Just the URLs the tail would turn into anchors."""
    return [p["url"] for p in _call("_splitLinks", line) if p["url"]]


def text_of(line):
    """The rendered text must still be the original line, character for char."""
    return "".join(p["text"] for p in _call("_splitLinks", line))


# --- tail links --------------------------------------------------------------

def test_artifact_link_in_a_claude_code_line_is_found():
    line = "  ⧉ https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    assert links(line) == [
        "https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    ]


def test_a_line_without_a_url_is_left_as_one_plain_segment():
    parts = _call("_splitLinks", "  ok, ran 42 tests (no failures)")
    assert parts == [{"text": "  ok, ran 42 tests (no failures)", "url": None}]


def test_two_urls_on_one_line_both_become_links():
    assert links("see http://a.example/x and https://b.example/y now") == [
        "http://a.example/x",
        "https://b.example/y",
    ]


def test_sentence_punctuation_is_not_part_of_the_address():
    assert links("open https://example.com/report.") == ["https://example.com/report"]
    assert links("try https://example.com/a, then b") == ["https://example.com/a"]


def test_a_bracket_the_url_opened_is_kept():
    assert links("https://ex.com/wiki/Foo_(bar) done") == ["https://ex.com/wiki/Foo_(bar)"]


def test_a_bracket_that_wraps_the_url_is_not_swallowed():
    assert links("(https://ex.com/a) done") == ["https://ex.com/a"]


def test_the_rendered_text_reproduces_the_line_exactly():
    for line in [
        "see http://a.example/x and https://b.example/y now",
        "open https://example.com/report.",
        "(https://ex.com/a) done",
        "no url at all",
    ]:
        assert text_of(line) == line


def test_the_glyphs_claude_code_paints_beside_a_link_stay_out_of_it():
    """The blacklist this replaced only excluded box drawing (U+2500-257F).

    Claude Code's own left gutter is ▎ (U+258E), outside that range, so it was
    being glued onto the href of every link it sat next to. • and → likewise.
    """
    assert links("x https://ex.com/a▎ more") == ["https://ex.com/a"]
    assert links("• https://ex.com/b• x") == ["https://ex.com/b"]
    assert links("→ https://ex.com/c→") == ["https://ex.com/c"]


def test_a_scheme_with_no_host_is_not_a_link():
    """'see https://.' used to produce an href of 'https://'."""
    assert links("see https://.") == []
    assert links("bare https:// end") == []


def test_a_url_cut_short_by_a_character_we_cannot_spell_is_not_linked():
    """A Korean path would otherwise link as the site root -- a different page.

    The address does not end where the whitelist stops; dropping the link is
    the honest outcome, and better than one that silently goes elsewhere.
    """
    assert links("한글 https://example.com/가나 뒤") == []
    assert links("https://ex.com/pathでは") == []
    # the one before it, which really did end, still links
    assert links("두 개 https://a.io/x 와 https://b.io/여기") == ["https://a.io/x"]


def test_a_box_drawing_border_does_not_run_into_the_url():
    """tmux panes are full of ─ and │; a link touching one must stop at it.

    No space between the URL and the border: that is the case the character
    class exists for -- whitespace alone would already have ended the match.
    """
    assert links("│https://example.com/x│") == ["https://example.com/x"]


# --- session search ----------------------------------------------------------

SESSIONS = [
    {"name": "claude_alpha", "label": "alpha", "branch": None, "state": "idle"},
    {"name": "claude_claude-ops", "label": "claude-ops", "branch": None, "state": "working"},
    {"name": "claude_beta_wt_fix-login", "label": "beta", "branch": "fix-login", "state": "idle"},
    {"name": "claude_ops-notes", "label": "ops-notes", "branch": None, "state": "idle"},
]


def match(query):
    return [s["name"] for s in _call("_matchSessions", SESSIONS, query)]


def test_an_empty_query_keeps_the_grid_order():
    assert match("") == [s["name"] for s in SESSIONS]


def test_a_prefix_match_outranks_a_mid_label_match():
    """'ops' is a prefix of ops-notes and inside claude-ops; the prefix wins."""
    assert match("ops")[0] == "claude_ops-notes"
    assert "claude_claude-ops" in match("ops")


def test_a_branch_is_searchable():
    assert match("login") == ["claude_beta_wt_fix-login"]


def test_a_rough_guess_still_lands_by_subsequence():
    assert "claude_claude-ops" in match("cops")


def test_a_query_matching_nothing_returns_nothing():
    assert match("zzz") == []


def test_the_shared_claude_prefix_is_not_searchable():
    """Every session is claude_<x>; matching it would match all seventy."""
    assert match("clau") == ["claude_claude-ops"]   # only the one truly named it


def test_a_session_with_no_label_still_matches_without_its_prefix():
    """The fallback must behave like a label, not like a raw tmux name."""
    rows = [{"name": "claude_solo", "label": None, "branch": None, "state": "idle"}]
    assert [s["name"] for s in _call("_matchSessions", rows, "solo")] == ["claude_solo"]


def test_a_project_really_named_claude_ops_keeps_its_name():
    """Only the shared prefix is dropped -- not a label that starts that way."""
    assert match("claude-ops") == ["claude_claude-ops"]


def test_matching_ignores_case():
    assert match("ALPHA") == ["claude_alpha"]


# --- URLs the pane hard-wrapped ----------------------------------------------

# A pane 40 columns wide. capture-pane -J trims trailing padding, so what
# reaches the console is the bare text: a row of exactly 40 columns is the only
# kind that can have been cut at the margin, and a shorter row ended where its
# author ended it. short() marks the rows that are deliberately not full.
COLS = 40


def short(line):
    assert len(line) < COLS, "this row is meant to be shorter than the pane"
    return line


def cont(text):
    """A continuation row as Claude Code writes one: its gutter, then more."""
    return "▎ " + text


def test_a_url_wrapped_across_two_rows_becomes_one_link():
    """The case the feature exists for."""
    url = "https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    head, tail = url[:COLS], url[COLS:]
    assert len(head) == COLS
    assert urls_in([head, cont(tail)], COLS) == [url]


def test_the_joined_link_is_drawn_on_both_rows():
    """Rows stay rows -- selection and copy still count in lines."""
    url = "https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    rows = seg_lines([url[:COLS], cont(url[COLS:])], COLS)
    assert [p["url"] for p in rows[0]] == [url]
    # the gutter is not part of the address and is not painted as a link
    assert rows[1][0] == {"text": "▎ ", "url": None}
    assert rows[1][1]["url"] == url
    # and the text still reproduces each row exactly
    assert "".join(p["text"] for p in rows[0]) == url[:COLS]
    assert "".join(p["text"] for p in rows[1]) == cont(url[COLS:])


def test_a_url_wrapped_across_three_rows_is_joined_whole():
    url = "https://example.com/" + "a" * 70
    middle = cont(url[COLS:COLS + COLS - 2])          # gutter + 38 = 40 columns
    rows = [url[:COLS], middle, cont(url[2 * COLS - 2:])]
    assert len(rows[0]) == COLS and len(middle) == COLS
    assert urls_in(rows, COLS) == [url]


def test_punctuation_on_the_continuation_row_is_still_dropped():
    url = "https://example.com/" + "b" * 30
    head, tail = url[:COLS], url[COLS:]
    assert urls_in([head, cont(tail + ".")], COLS) == [url]


def test_a_continuation_row_that_is_only_punctuation_ends_the_link():
    """Trimming can empty the continuation; what is left is plain text."""
    url = "https://example.com/" + "c" * 20
    assert len(url) == COLS
    rows = seg_lines([url, cont("x.")], COLS)
    assert [p["url"] for p in rows[0]] == [url + "x"]
    assert rows[1][-1] == {"text": ".", "url": None}


def test_the_join_stops_at_the_first_row_that_was_not_full():
    """A short row ends where its author ended it, even mid-chain."""
    head = "https://example.com/" + "e" * 20
    assert len(head) == COLS
    assert urls_in([head, cont("abcd"), cont("efgh")], COLS) == [head + "abcd"]


def test_a_full_row_of_ordinary_text_starts_no_link():
    assert urls_in([short("nothing here at all"), "x" * COLS], COLS) == []


def test_a_log_line_ending_in_a_url_is_not_glued_to_the_next_line():
    """The shape that made the width check necessary.

    Taken from a live monitor pane: line after line ends with a URL and the
    next one starts at column 0 with a timestamp. Nothing here filled the
    pane, so nothing here was wrapped.
    """
    rows = [
        "09:46:45 - httpx - INFO - POST https://api.telegram.org/botX/getUpdates",
        "09:46:55 - httpx - INFO - done",
    ]
    assert urls_in(rows, 159) == ["https://api.telegram.org/botX/getUpdates"]


def test_without_a_pane_width_nothing_is_joined():
    """An older server sends no width; a wrong address is worse than a plain one."""
    url = "https://example.com/" + "d" * 20
    assert len(url) == COLS
    assert urls_in([url, "more-of-it"], 0) == [url]


# --- the continuation gutter, and the width that finds it --------------------

# Both rows below are lifted from live panes; they are the only two places in a
# 26,000-row sample where the rejoin can fire at all, and they disagree about
# whether it should.

def test_claude_codes_own_gutter_continues_a_link():
    """The case the feature exists for, from claude_md_illust.

    Claude Code draws ▎ down the left of its output, so a link it wraps never
    resumes at column 0 -- which is why a column-0-only rule fired zero times.
    """
    head = "  ▎ open https://help.example.com/en/articles/15424964-promotio"
    rows = [head, " ▎ nal-access", "  ▎ done"]
    assert urls_in(rows, len(head)) == [
        "https://help.example.com/en/articles/15424964-promotional-access"
    ]


def test_the_gutter_is_not_part_of_the_address():
    head = "https://example.com/" + "f" * 20
    rows = seg_lines([head, "▎ tail"], COLS)
    assert rows[1][0] == {"text": "▎ ", "url": None}
    assert rows[1][1]["url"] == head + "tail"


def test_leading_spaces_alone_do_not_continue_a_link():
    """The glue case, from claude_land_wt_auction: a curl line that lands on
    the margin, followed by an indented shell job-status line. Allowing bare
    indentation as a continuation doubles the firings and the extra one is
    wrong, so the gutter glyph is required.
    """
    head = 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8899/x.html'
    assert urls_in([head, "  and then a shell message"], len(head)) == []


def test_a_full_width_korean_row_is_recognised_as_full():
    """Width is columns, not UTF-16 units.

    A Korean row is half its own width by string length, which made 998 rows in
    the live sample invisible to the fullness test -- so a link wrapped at the
    end of a Korean line was never rejoined.
    """
    head = "한글" * 10 + "https://example.com/g"   # 40 columns + 21 = 61
    assert len(head) == 41 and _call("_displayWidth", head) == 61
    # 61 is the pane; a length test would have looked for 41 and found nothing
    assert urls_in([head, "▎ tail"], 61) == ["https://example.com/gtail"]
    assert urls_in([head, "▎ tail"], 41) == ["https://example.com/g"]


def test_an_emoji_counts_as_two_columns():
    assert _call("_displayWidth", "🔥") == 2
    assert _call("_displayWidth", "a🔥b") == 4


def test_a_mark_that_occupies_no_column_is_counted_as_none():
    """Over-counting is the dangerous direction.

    A row billed wider than it is can measure as full when it is not, and that
    is what invents a link or drops a good one. Under-counting only loses a
    rejoin, which is why the emoji presentation selector (⚠ vs ⚠️) is left
    erring the safe way.
    """
    assert _call("_displayWidth", "a\u0301") == 1        # decomposed 'á'
    assert _call("_displayWidth", "\u1100\u1161") == 2  # jamo: lead + vowel
    assert _call("_displayWidth", "a\u200bb") == 2       # zero-width space


def test_a_shell_quote_after_a_url_is_not_part_of_it():
    """RFC 3986 allows an apostrophe; a terminal almost never means one.

    Every apostrophe beside a link in 151 URLs captured from live panes was the
    closing quote of a shell argument. trimUrl is what removes it -- they were
    all trailing -- so the character stays in the set.
    """
    assert links("printf '%s' 'http://localhost:8420/'") == ["http://localhost:8420/"]
    assert links("curl 'https://a.io/x' && curl 'https://b.io/y'") == [
        "https://a.io/x", "https://b.io/y"
    ]


def test_a_link_cut_at_the_margin_with_no_continuation_is_not_linked():
    """The half that is present points at a real but different page.

    It happens whenever the rest is not in the capture: the continuation
    scrolled off the top, or the pane has been widened since the line was
    written, so the row is full but nothing follows it.
    """
    head = "https://example.com/" + "h" * 20
    assert len(head) == COLS
    assert urls_in([head], COLS) == []                       # last row
    assert urls_in([head, short("  prose")], COLS) == []      # no continuation
    assert urls_in([head, "unrelated at column 0"], COLS) == []  # not a gutter
    # …and with the continuation there, the whole address links
    assert urls_in([head, "▎ tail"], COLS) == [head + "tail"]


def test_a_url_that_merely_ends_at_the_margin_is_the_price():
    """An address whose last character lands on the last column reads as cut.

    Nothing distinguishes it from a wrap, so it is dropped too. That costs a
    link about once per pane-width of URLs; the alternative costs a wrong one.
    """
    head = "https://example.com/" + "i" * 20
    assert len(head) == COLS
    assert urls_in([head, short("unrelated")], COLS) == []
    # one column shorter and it is an ordinary link again
    assert urls_in([head[:-1], short("unrelated")], COLS) == [head[:-1]]


def test_a_row_that_only_reaches_the_margin_with_punctuation_is_not_cut():
    """From claude_land_wt_auction r31, the one real drop this rule caused.

    The address is complete; the row touches column 80 because of the shell's
    closing ')', which trimUrl removes anyway. Judging fullness on the raw
    match threw the whole link away.
    """
    row = ('      curl -s -o /dev/null -w "%{http_code}" '
           'http://127.0.0.1:8899/index.html)')
    assert urls_in([row, "  and a following line"], len(row)) == [
        "http://127.0.0.1:8899/index.html"
    ]


def test_a_box_border_is_not_a_continuation():
    """│ is a table rule, not a gutter.

    Of 485 rows in a 26k sample beginning with ▎ or │, 465 begin with │ and
    every one is a border; 426 of those sit directly under an exactly-full row,
    which is the whole setup for a false join.
    """
    head = "see https://example.com/report-xxxxxxxxx"
    assert len(head) == COLS
    rows = seg_lines([head, "│ Name    │ Value  │", "x"], COLS)
    assert all(p["url"] is None for p in rows[1])


def test_a_cut_marked_by_an_astral_letter_or_a_combining_mark_is_seen():
    """Both used to emit a truncated href pointing at a real, different page."""
    assert links("https://ex.com/path\U00020000tail") == []   # outside the BMP
    assert links("https://ex.com/a\u0301b") == []             # decomposed 'á'
    assert links("https://ex.com/path가") == []                # the BMP case
