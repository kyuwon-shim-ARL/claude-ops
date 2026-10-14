"""Inside a quadrant, the user decides the order.

Working sessions sit on top, most recently updated first, as before. Every
other session -- idle, waiting, error, whatever -- keeps the place it holds in
that quadrant's stored pin array, which is the order the user dragged it into.
The console rail walks the same order: Q1, Q2, Q3, Q4, then everything
unpinned the way it always was.

The functions are pure and live inline in index.html, which cannot be
required as a whole (it is inline script with Jinja placeholders), so each one
is cut out of the shipped source by brace matching and run in node.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/templates/index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _fn(html: str, name: str) -> str:
    """One top-level function from the page, by brace matching."""
    start = html.index(f"function {name}(")
    open_at = html.index("{", html.index(")", start))
    depth = 0
    for i in range(open_at, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _source(html: str | None = None) -> str:
    html = html if html is not None else INDEX_HTML.read_text()
    state_order = re.search(r"const _STATE_ORDER = \{[^}]*\};", html).group(0)
    names = ["parseSessionName", "groupQuadrantSessions", "_bySessionState",
             "_quadrantOrder", "_railOrder", "_removeFromQuads", "_moveBefore",
             "_isBeforeCard"]
    return state_order + "\n" + "\n".join(_fn(html, n) for n in names)


def _run(expr: str, html: str | None = None):
    harness = f"""
    {_source(html)}
    process.stdout.write(JSON.stringify({expr}));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _s(name, state="idle", updated=0):
    return {"name": name, "state": state, "updated_at": updated}


def _quad_order(names, sessions, html=None):
    by_name = {s["name"]: s for s in sessions}
    return _run(
        f"_quadrantOrder({json.dumps(names)}, {json.dumps(by_name)}).map(s => s.name)",
        html)


# --- the quadrant's own order ------------------------------------------------

def test_working_sessions_sit_on_top_newest_first():
    sessions = [_s("claude_a", "idle", 900), _s("claude_b", "working", 100),
                _s("claude_c", "working", 500)]
    assert _quad_order(["claude_a", "claude_b", "claude_c"], sessions) == [
        "claude_c", "claude_b", "claude_a"]


def test_everything_else_follows_the_stored_order_not_recency():
    # Newest last in the array: recency must not pull it up.
    sessions = [_s("claude_a", "idle", 100), _s("claude_b", "idle", 200),
                _s("claude_c", "idle", 300)]
    assert _quad_order(["claude_a", "claude_b", "claude_c"], sessions) == [
        "claude_a", "claude_b", "claude_c"]


def test_waiting_and_idle_are_one_group():
    # Waiting used to outrank idle. It no longer does: the user's order wins.
    sessions = [_s("claude_a", "idle", 1), _s("claude_b", "error", 2),
                _s("claude_c", "waiting", 3), _s("claude_d", "context_limit", 4)]
    assert _quad_order(["claude_a", "claude_b", "claude_c", "claude_d"], sessions) == [
        "claude_a", "claude_b", "claude_c", "claude_d"]


def test_names_with_no_live_session_are_skipped():
    sessions = [_s("claude_a"), _s("claude_c")]
    assert _quad_order(["claude_a", "claude_gone", "claude_c"], sessions) == [
        "claude_a", "claude_c"]


def test_an_empty_quadrant_is_empty():
    assert _quad_order([], [_s("claude_a")]) == []


# --- project groups ----------------------------------------------------------

def _grouped(names, sessions, html=None):
    by_name = {s["name"]: s for s in sessions}
    return _run(
        "groupQuadrantSessions(_quadrantOrder(%s, %s)).map(it => it.type === 'group'"
        " ? it.sessions.map(s => s.name) : it.session.name)"
        % (json.dumps(names), json.dumps(by_name)), html)


def test_a_group_takes_its_first_members_place_and_keeps_member_order():
    sessions = [_s("claude_x"), _s("claude_alpha_wt_t"), _s("claude_y"),
                _s("claude_alpha")]
    # The worktree is ranked before its main: the group lands at the
    # worktree's slot and the members keep the user's order (no
    # main-before-worktree, no state sort).
    assert _grouped(["claude_x", "claude_alpha_wt_t", "claude_y", "claude_alpha"],
                    sessions) == [
        "claude_x", ["claude_alpha_wt_t", "claude_alpha"], "claude_y"]


def test_a_working_member_puts_its_group_on_top():
    sessions = [_s("claude_x"), _s("claude_alpha"),
                _s("claude_alpha_wt_t", "working", 50)]
    assert _grouped(["claude_x", "claude_alpha", "claude_alpha_wt_t"], sessions) == [
        ["claude_alpha_wt_t", "claude_alpha"], "claude_x"]


# --- the console rail --------------------------------------------------------

def _rail(sessions, quads, html=None):
    return _run(
        f"_railOrder({json.dumps(sessions)}, {json.dumps(quads)}).map(s => s.name)",
        html)


def test_rail_walks_quadrants_in_order_then_unpinned():
    sessions = [
        _s("claude_u_idle", "idle", 999),
        _s("claude_u_work", "working", 1),
        _s("claude_q4", "working", 999),
        _s("claude_q2_b", "idle", 5),
        _s("claude_q2_a", "idle", 1),
        _s("claude_q1_idle", "idle", 1),
        _s("claude_q1_work", "working", 1),
    ]
    quads = {"Q1": ["claude_q1_idle", "claude_q1_work"],
             "Q2": ["claude_q2_a", "claude_q2_b"], "Q3": [], "Q4": ["claude_q4"]}
    assert _rail(sessions, quads) == [
        "claude_q1_work", "claude_q1_idle",
        "claude_q2_a", "claude_q2_b",
        "claude_q4",
        # Unpinned keep the old rule: state first, then recency.
        "claude_u_work", "claude_u_idle",
    ]


def test_rail_only_holds_the_sessions_it_was_given():
    # The filtered list is passed in: a pinned name that the filter hid
    # must not come back.
    sessions = [_s("claude_a"), _s("claude_c")]
    quads = {"Q1": ["claude_b", "claude_a"], "Q2": [], "Q3": [], "Q4": ["claude_c"]}
    assert _rail(sessions, quads) == ["claude_a", "claude_c"]


# --- the drop intent ----------------------------------------------------------

def _move(quads, name, target, before):
    return _run(f"_moveBefore({json.dumps(quads)}, {json.dumps(name)}, "
                f"{json.dumps(target)}, {json.dumps(before)})")


def test_move_before_reorders_within_a_quadrant():
    q = {"Q1": ["a", "b", "c"], "Q2": [], "Q3": [], "Q4": []}
    assert _move(q, "c", "Q1", "a")["Q1"] == ["c", "a", "b"]


def test_move_before_crosses_quadrants():
    q = {"Q1": ["a", "b"], "Q2": ["x", "y"], "Q3": [], "Q4": []}
    out = _move(q, "a", "Q2", "y")
    assert out["Q1"] == ["b"] and out["Q2"] == ["x", "a", "y"]


def test_move_with_no_anchor_appends():
    q = {"Q1": ["a", "b"], "Q2": ["x"], "Q3": [], "Q4": []}
    assert _move(q, "a", "Q2", None)["Q2"] == ["x", "a"]


def test_move_before_an_anchor_that_is_gone_appends():
    # Another client unpinned the anchor in the meantime.
    q = {"Q1": ["a"], "Q2": ["x"], "Q3": [], "Q4": []}
    assert _move(q, "a", "Q2", "gone")["Q2"] == ["x", "a"]


# --- where a pointer lands relative to a card ---------------------------------

RECT = {"left": 0, "top": 100, "width": 200, "height": 40, "right": 200, "bottom": 140}


@pytest.mark.parametrize("x,y,alone,expected", [
    (150, 50, True, True),     # above the card
    (150, 110, True, True),    # upper half, card alone in its row
    (10, 130, True, False),    # lower half, card alone in its row
    (10, 130, False, True),    # left half, card shares its row
    (150, 110, False, False),  # right half, card shares its row
    (10, 200, False, False),   # below the card
])
def test_is_before_card(x, y, alone, expected):
    assert _run(f"_isBeforeCard({json.dumps(RECT)}, {x}, {y}, {json.dumps(alone)})") is expected


# --- mutation check -----------------------------------------------------------

def test_mutation_without_the_array_index_the_order_is_lost():
    """Swap the array-order tiebreak in _quadrantOrder for recency, the way
    the old sort did, and the stored-order test must fail."""
    html = INDEX_HTML.read_text()
    fn = _fn(html, "_quadrantOrder")
    assert "rest" in fn, "expected the non-working list to be called `rest`"
    mutated_fn = fn.replace(
        "return working.concat(rest);",
        "return working.concat(rest.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0)));")
    assert mutated_fn != fn, "mutation did not apply"
    mutated = html.replace(fn, mutated_fn)
    sessions = [_s("claude_a", "idle", 100), _s("claude_b", "idle", 200),
                _s("claude_c", "idle", 300)]
    assert _quad_order(["claude_a", "claude_b", "claude_c"], sessions, mutated) != [
        "claude_a", "claude_b", "claude_c"]
