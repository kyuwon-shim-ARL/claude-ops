"""The order of work: one numbered queue, and the quadrants around it.

The queue (`queue` in the pin set) is a list of session names meaning "do
these in this order". Inside a quadrant, working sessions sit on top, newest
first; then the queued ones, by their number; then the rest, newest first. The
console rail walks the queue first -- whatever state its sessions are in --
then the remaining pinned sessions Q1 to Q4, then everything unpinned the way
it always was.

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


NAMES = ["parseSessionName", "groupQuadrantSessions", "_bySessionState",
         "_byRecency", "_queueNumbers", "_quadrantOrder", "_railOrder",
         "_removeFromQuads", "_cloneQuads", "_queueInsert", "_queueRemove",
         "_queueSlotAt"]


def _source(html: str | None = None) -> str:
    html = html if html is not None else INDEX_HTML.read_text()
    state_order = re.search(r"const _STATE_ORDER = \{[^}]*\};", html).group(0)
    return state_order + "\n" + "\n".join(_fn(html, n) for n in NAMES)


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


def _by_name(sessions):
    return {s["name"]: s for s in sessions}


def _quad_order(names, sessions, queue=(), html=None):
    return _run(
        f"_quadrantOrder({json.dumps(names)}, {json.dumps(_by_name(sessions))}, "
        f"_queueNumbers({json.dumps(list(queue))}, {json.dumps(_by_name(sessions))}))"
        ".map(s => s.name)", html)


# --- inside a quadrant ---------------------------------------------------------

def test_working_on_top_newest_first_then_the_rest_newest_first():
    sessions = [_s("claude_a", "idle", 100), _s("claude_b", "working", 100),
                _s("claude_c", "working", 500), _s("claude_d", "waiting", 900)]
    assert _quad_order(["claude_a", "claude_b", "claude_c", "claude_d"], sessions) == [
        "claude_c", "claude_b", "claude_d", "claude_a"]


def test_queued_sessions_follow_the_working_ones_in_queue_order():
    sessions = [_s("claude_a", "idle", 900), _s("claude_b", "idle", 100),
                _s("claude_c", "idle", 500), _s("claude_w", "working", 1)]
    # c is #1, b is #2; a is not queued and is the newest, but still last.
    assert _quad_order(["claude_a", "claude_b", "claude_c", "claude_w"], sessions,
                       queue=["claude_c", "claude_b"]) == [
        "claude_w", "claude_c", "claude_b", "claude_a"]


def test_a_queued_session_that_is_working_stays_with_the_working_ones():
    sessions = [_s("claude_a", "idle", 1), _s("claude_b", "working", 5),
                _s("claude_c", "working", 9)]
    assert _quad_order(["claude_a", "claude_b", "claude_c"], sessions,
                       queue=["claude_b", "claude_a"]) == [
        "claude_c", "claude_b", "claude_a"]


def test_names_with_no_live_session_are_skipped():
    sessions = [_s("claude_a"), _s("claude_c")]
    assert _quad_order(["claude_a", "claude_gone", "claude_c"], sessions) == [
        "claude_a", "claude_c"]


def test_an_empty_quadrant_is_empty():
    assert _quad_order([], [_s("claude_a")]) == []


# --- badge numbers --------------------------------------------------------------

def test_badge_numbers_count_only_sessions_that_exist():
    sessions = [_s("claude_a"), _s("claude_b"), _s("claude_c")]
    assert _run(f"_queueNumbers({json.dumps(['claude_gone', 'claude_b', 'claude_old', 'claude_a'])}, "
                f"{json.dumps(_by_name(sessions))})") == {"claude_b": 1, "claude_a": 2}


def test_a_duplicated_name_keeps_its_first_number():
    sessions = [_s("claude_a"), _s("claude_b")]
    assert _run(f"_queueNumbers({json.dumps(['claude_a', 'claude_b', 'claude_a'])}, "
                f"{json.dumps(_by_name(sessions))})") == {"claude_a": 1, "claude_b": 2}


def test_no_queue_at_all_is_no_numbers():
    # A pin file written before the queue existed has no `queue` key.
    assert _run(f"_queueNumbers(undefined, {json.dumps(_by_name([_s('claude_a')]))})") == {}


# --- project groups ----------------------------------------------------------

def _grouped(names, sessions, queue=()):
    return _run(
        "groupQuadrantSessions(_quadrantOrder(%s, %s, _queueNumbers(%s, %s)))"
        ".map(it => it.type === 'group' ? it.sessions.map(s => s.name) : it.session.name)"
        % (json.dumps(names), json.dumps(_by_name(sessions)), json.dumps(list(queue)),
           json.dumps(_by_name(sessions))))


def test_a_group_sits_at_its_first_members_slot():
    sessions = [_s("claude_x", "idle", 300), _s("claude_alpha_wt_t", "idle", 200),
                _s("claude_y", "idle", 100), _s("claude_alpha", "idle", 50)]
    assert _grouped(["claude_x", "claude_alpha_wt_t", "claude_y", "claude_alpha"],
                    sessions) == [
        "claude_x", ["claude_alpha_wt_t", "claude_alpha"], "claude_y"]


def test_a_queued_member_pulls_its_group_up_with_it():
    sessions = [_s("claude_x", "idle", 900), _s("claude_alpha", "idle", 10),
                _s("claude_alpha_wt_t", "idle", 5)]
    assert _grouped(["claude_x", "claude_alpha", "claude_alpha_wt_t"], sessions,
                    queue=["claude_alpha_wt_t"]) == [
        ["claude_alpha_wt_t", "claude_alpha"], "claude_x"]


# --- the console rail --------------------------------------------------------

def _rail(sessions, quads, html=None):
    return _run(
        f"_railOrder({json.dumps(sessions)}, {json.dumps(quads)}).map(s => s.name)",
        html)


def test_rail_walks_the_queue_then_quadrants_then_unpinned():
    sessions = [
        _s("claude_u_idle", "idle", 999),
        _s("claude_u_work", "working", 1),
        _s("claude_u_queued", "idle", 1),
        _s("claude_q4", "working", 999),
        _s("claude_q2_old", "idle", 1),
        _s("claude_q2_new", "idle", 5),
        _s("claude_q1_idle", "idle", 1),
        _s("claude_q1_work", "working", 1),
        _s("claude_q3_queued_working", "working", 1),
    ]
    quads = {"Q1": ["claude_q1_idle", "claude_q1_work"],
             "Q2": ["claude_q2_old", "claude_q2_new"],
             "Q3": ["claude_q3_queued_working"], "Q4": ["claude_q4"],
             "queue": ["claude_q3_queued_working", "claude_u_queued"]}
    assert _rail(sessions, quads) == [
        # The queue first, whatever state it is in and pinned or not.
        "claude_q3_queued_working", "claude_u_queued",
        # Then each quadrant: working first, then newest first.
        "claude_q1_work", "claude_q1_idle",
        "claude_q2_new", "claude_q2_old",
        "claude_q4",
        # Unpinned keep the old rule: state first, then recency.
        "claude_u_work", "claude_u_idle",
    ]


def test_rail_without_a_queue_key_is_the_quadrant_walk():
    sessions = [_s("claude_a", "idle", 1), _s("claude_b", "idle", 2)]
    quads = {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": []}
    assert _rail(sessions, quads) == ["claude_a", "claude_b"]


def test_rail_only_holds_the_sessions_it_was_given():
    # The filtered list is passed in: a pinned or queued name that the filter
    # hid must not come back.
    sessions = [_s("claude_a"), _s("claude_c")]
    quads = {"Q1": ["claude_b", "claude_a"], "Q2": [], "Q3": [], "Q4": ["claude_c"],
             "queue": ["claude_b", "claude_c"]}
    assert _rail(sessions, quads) == ["claude_c", "claude_a"]


# --- the pin set carries the queue along ---------------------------------------

def test_clone_keeps_the_queue_and_does_not_share_it():
    out = _run("(() => { const q = {Q1: ['a'], Q2: [], Q3: [], Q4: [], queue: ['x', 'y']};"
               " const c = _cloneQuads(q); c.queue.push('z'); return [c.queue, q.queue]; })()")
    assert out == [["x", "y", "z"], ["x", "y"]]


def test_clone_of_a_set_with_no_queue_has_an_empty_one():
    assert _run("_cloneQuads({Q1: [], Q2: [], Q3: [], Q4: []}).queue") == []


def test_unpinning_does_not_take_a_session_out_of_the_queue():
    out = _run("(() => { const q = _cloneQuads({Q1: ['a'], Q2: [], Q3: [], Q4: [], queue: ['a']});"
               " _removeFromQuads(q, 'a'); return q; })()")
    assert out["Q1"] == [] and out["queue"] == ["a"]


# --- queue edits ----------------------------------------------------------------

def _q(queue):
    return {"Q1": [], "Q2": [], "Q3": [], "Q4": [], "queue": queue}


def _insert(queue, name, before):
    return _run(f"_queueInsert({json.dumps(_q(queue))}, {json.dumps(name)}, "
                f"{json.dumps(before)}).queue")


def _remove(queue, name):
    return _run(f"_queueRemove({json.dumps(_q(queue))}, {json.dumps(name)}).queue")


def test_insert_before_a_name():
    assert _insert(["a", "b"], "x", "b") == ["a", "x", "b"]


def test_insert_with_no_anchor_appends():
    assert _insert(["a", "b"], "x", None) == ["a", "b", "x"]


def test_insert_into_a_set_with_no_queue_key():
    assert _run("_queueInsert({Q1: [], Q2: [], Q3: [], Q4: []}, 'x', null).queue") == ["x"]


def test_moving_a_queued_name_does_not_duplicate_it():
    assert _insert(["a", "b", "c"], "c", "a") == ["c", "a", "b"]
    assert _insert(["a", "b", "c"], "a", None) == ["b", "c", "a"]


def test_insert_keeps_entries_for_sessions_that_are_gone():
    # "gone" has no live session and is not drawn; it stays stored, so a
    # session restored with Alt+Shift+Q comes back with its place.
    assert _insert(["a", "gone", "b"], "x", "b") == ["a", "gone", "x", "b"]


# Re-applied by _pinChange to whatever the server holds by the time the write
# goes out -- which another client may have changed in between.

def test_reapplied_after_the_name_was_removed_elsewhere():
    assert _insert(["b"], "a", "b") == ["a", "b"]


def test_reapplied_on_a_set_where_the_name_is_duplicated():
    assert _insert(["a", "b", "a"], "a", "b") == ["a", "b"]


def test_reapplied_past_the_end_when_the_anchor_is_gone():
    assert _insert(["a", "b"], "x", "vanished") == ["a", "b", "x"]


def test_insert_anchored_on_itself_appends_nothing_twice():
    assert _insert(["a", "b"], "a", "a") == ["b", "a"]


def test_remove_takes_every_copy():
    assert _remove(["a", "b", "a"], "a") == ["b"]


def test_remove_of_a_name_not_queued_changes_nothing():
    assert _remove(["a", "b"], "x") == ["a", "b"]


def test_remove_after_it_was_already_removed_elsewhere():
    assert _run("_queueRemove({Q1: [], Q2: [], Q3: [], Q4: []}, 'x').queue") == []


# --- where a pointer lands among the rows --------------------------------------

def _rect(left, top, width=100, height=30):
    return {"left": left, "top": top, "width": width, "height": height,
            "right": left + width, "bottom": top + height}


ONE_COLUMN = [_rect(0, 0), _rect(0, 40), _rect(0, 80)]
WRAPPED = [_rect(0, 0), _rect(110, 0), _rect(0, 40)]


@pytest.mark.parametrize("rects,x,y,expected", [
    (ONE_COLUMN, 50, -5, 0),     # above everything
    (ONE_COLUMN, 50, 10, 0),     # upper half of the first row
    (ONE_COLUMN, 50, 20, 1),     # lower half of the first row
    (ONE_COLUMN, 50, 75, 2),     # in the gap above the third
    (ONE_COLUMN, 50, 200, 3),    # below everything: the end
    (WRAPPED, 20, 15, 0),        # left half of a row-mate
    (WRAPPED, 90, 15, 1),        # right half of the first, so before the second
    (WRAPPED, 190, 15, 2),       # right half of the second: before the next row
    (WRAPPED, 90, 55, 3),        # right half of the last one
    ([], 10, 10, 0),             # an empty queue
])
def test_slot_at(rects, x, y, expected):
    assert _run(f"_queueSlotAt({json.dumps(rects)}, {x}, {y})") == expected


# --- mutation checks ------------------------------------------------------------

def test_mutation_queue_order_is_what_orders_the_queued_sessions():
    """Sort the queued sessions by recency instead of their number and the
    queue-order test must fail."""
    html = INDEX_HTML.read_text()
    fn = _fn(html, "_quadrantOrder")
    mutated_fn = fn.replace("queued[a.name] - queued[b.name]", "(b.updated_at || 0) - (a.updated_at || 0)")
    assert mutated_fn != fn, "mutation did not apply"
    sessions = [_s("claude_a", "idle", 900), _s("claude_b", "idle", 100),
                _s("claude_c", "idle", 500)]
    assert _quad_order(["claude_a", "claude_b", "claude_c"], sessions,
                       queue=["claude_b", "claude_c"], html=html.replace(fn, mutated_fn)) != [
        "claude_b", "claude_c", "claude_a"]


def test_mutation_a_clone_that_forgets_the_queue_is_caught():
    html = INDEX_HTML.read_text()
    fn = _fn(html, "_cloneQuads")
    mutated_fn = re.sub(r",\s*queue:[^}]*", " ", fn)
    assert mutated_fn != fn, "mutation did not apply"
    out = _run("_cloneQuads({Q1: [], Q2: [], Q3: [], Q4: [], queue: ['x']}).queue || null",
               html.replace(fn, mutated_fn))
    assert out != ["x"]


def test_mutation_the_rail_puts_the_queue_first():
    html = INDEX_HTML.read_text()
    fn = _fn(html, "_railOrder")
    mutated_fn = fn.replace("_queueNumbers(", "(() => ({}))(")
    assert mutated_fn != fn, "mutation did not apply"
    sessions = [_s("claude_a", "idle", 1), _s("claude_b", "idle", 2)]
    quads = {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": [], "queue": ["claude_b"]}
    assert _rail(sessions, quads, html.replace(fn, mutated_fn)) != ["claude_b", "claude_a"]
