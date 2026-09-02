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

# A pane 40 columns wide. capture-pane -J trims the padding, so a row that is
# exactly 40 characters is the only kind that can have been cut at the margin;
# pad() here is a no-op kept for readability of the short rows.
COLS = 40


def pad(line):
    return line


def test_a_url_wrapped_across_two_rows_becomes_one_link():
    """The case that made most artifact links unfollowable on a phone."""
    url = "https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    head, tail = url[:COLS], url[COLS:]
    assert len(head) == COLS
    assert urls_in([head, pad(tail)], COLS) == [url]


def test_the_joined_link_is_drawn_on_both_rows():
    """Rows stay rows -- selection and copy still count in lines."""
    url = "https://claude.ai/code/artifact/67b095b6-2541-42dc-a5f0-98c25c251f3a"
    rows = seg_lines([url[:COLS], pad(url[COLS:])], COLS)
    assert [p["url"] for p in rows[0]] == [url]
    assert rows[1][0]["url"] == url
    # and the text still reproduces each row exactly
    assert "".join(p["text"] for p in rows[0]) == url[:COLS]
    assert "".join(p["text"] for p in rows[1]) == pad(url[COLS:])


def test_a_url_wrapped_across_three_rows_is_joined_whole():
    url = "https://example.com/" + "a" * 70
    rows = [url[:COLS], url[COLS:2 * COLS], pad(url[2 * COLS:])]
    assert len(rows[0]) == len(rows[1]) == COLS
    assert urls_in(rows, COLS) == [url]


def test_an_indented_next_line_is_not_glued_on():
    """Claude Code indents its output; only the terminal writes at column 0."""
    head = "x" * (COLS - 20) + "https://example.com/"
    assert len(head) == COLS
    assert urls_in([head, pad("  and then some prose")], COLS) == ["https://example.com/"]


def test_a_url_that_stops_short_of_the_margin_takes_no_continuation():
    """Padding proves the row was not full, so there is nothing to rejoin."""
    assert urls_in([pad("see https://example.com/x"), pad("next line here")], COLS) == [
        "https://example.com/x"
    ]


def test_punctuation_on_the_continuation_row_is_still_dropped():
    url = "https://example.com/" + "b" * 30
    head, tail = url[:COLS], url[COLS:]
    assert urls_in([head, pad(tail + ".")], COLS) == [url]


def test_a_continuation_row_of_pure_punctuation_is_not_part_of_the_link():
    """Trimming may empty the whole second row; it is then plain text."""
    url = "https://example.com/" + "c" * 20
    assert len(url) == COLS
    rows = seg_lines([url, pad(".")], COLS)
    assert [p["url"] for p in rows[0]] == [url]
    assert all(p["url"] is None for p in rows[1])


def test_a_full_row_of_ordinary_text_starts_no_link():
    assert urls_in([pad("nothing here at all"), "x" * COLS], COLS) == []


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


def test_the_join_stops_at_the_first_row_that_was_not_full():
    """A short row ends where its author ended it, even mid-chain."""
    head = "https://example.com/" + "e" * 20
    assert len(head) == COLS
    # 'abcd' is all URL characters but only 4 columns wide -- not a wrap.
    assert urls_in([head, "abcd", "efgh"], COLS) == [head + "abcd"]


def test_without_a_pane_width_nothing_is_joined():
    """An older server sends no width; a wrong address is worse than a plain one."""
    url = "https://example.com/" + "d" * 20
    assert len(url) == COLS
    assert urls_in([url, "more-of-it"], 0) == [url]
