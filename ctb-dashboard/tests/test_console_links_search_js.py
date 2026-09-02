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


def test_matching_ignores_case():
    assert match("ALPHA") == ["claude_alpha"]
