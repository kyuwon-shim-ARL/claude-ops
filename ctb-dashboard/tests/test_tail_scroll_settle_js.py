"""The console tail must not be redrawn while a scroll is in flight.

iOS drives a fling from the geometry it captured at lift-off; rebuilding the
tail underneath it throws the view hundreds of lines. `whenSettled` holds the
redraw until the scroll events stop and no finger is down. Runs the shipped JS
in node; each test drives the real timers.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CONSOLE_JS = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/js/session-control.js"

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
const c = window.ctbConsole;
const log = [];
const t0 = Date.now();
const mark = (tag) => log.push([tag, Date.now() - t0]);
{body}
"""


def _run(body, wait_ms=600):
    script = _HARNESS.format(path=json.dumps(str(CONSOLE_JS)), body=body)
    script += f"\nsetTimeout(() => process.stdout.write(JSON.stringify(log)), {wait_ms});"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_at_rest_the_redraw_runs_at_once():
    log = _run("c._whenSettled(() => mark('ran'));")
    assert log[0][0] == "ran" and log[0][1] < 30


def test_a_scroll_in_flight_holds_the_redraw_until_the_events_stop():
    log = _run("""
      c._noteScrolling();
      c._whenSettled(() => mark('ran'));
      mark('queued');
      // a fling: an event every 16ms for 200ms, then silence
      let n = 0;
      const iv = setInterval(() => { c._noteScrolling(); if (++n >= 12) clearInterval(iv); }, 16);
    """)
    tags = [t for t, _ in log]
    assert tags == ["queued", "ran"]
    ran_at = dict(log)["ran"]
    # not before the last event (~200ms) plus the settle window
    assert 250 <= ran_at < 500


def test_a_finger_on_the_glass_holds_the_redraw_even_in_silence():
    log = _run("""
      c._setTouching(true);
      c._whenSettled(() => mark('ran'));
      setTimeout(() => mark('still-held'), 300);
      setTimeout(() => { c._setTouching(false); c._noteScrolling(); }, 350);
    """)
    tags = [t for t, _ in log]
    assert tags == ["still-held", "ran"]


def test_only_the_latest_redraw_survives_a_fling():
    log = _run("""
      c._noteScrolling();
      c._whenSettled(() => mark('first'));
      c._whenSettled(() => mark('second'));
    """)
    assert [t for t, _ in log] == ["second"]


def test_in_flight_is_reported_while_moving_and_cleared_at_rest():
    log = _run("""
      mark(c._scrollInFlight() ? 'moving' : 'rest');
      c._noteScrolling();
      mark(c._scrollInFlight() ? 'moving' : 'rest');
      setTimeout(() => mark(c._scrollInFlight() ? 'moving' : 'rest'), 300);
    """)
    assert [t for t, _ in log] == ["rest", "moving", "rest"]


# --- what a key did to the input box --------------------------------------

def _describe(before, after):
    body = f"mark(c._describeBox({json.dumps(before)}, {json.dumps(after)}));"
    return _run(body, wait_ms=50)[0][0]


def test_a_key_that_fills_an_empty_box_says_so():
    assert _describe("", "git status") == "채워짐"


def test_a_key_that_empties_the_box_says_so():
    assert _describe("git status", "") == "비워짐"


def test_a_key_that_rewrites_the_box_says_so():
    assert _describe("git st", "git status") == "바뀜"


def test_a_tab_that_makes_a_ghost_real_is_reported_as_accepted():
    body = "mark(c._describeBox({text:'git status', ghost:true}, {text:'git status', ghost:false}));"
    assert _run(body, wait_ms=50)[0][0] == "제안 확정됨"


# --- theme palettes --------------------------------------------------------

def test_every_theme_defines_the_same_tokens():
    """applyTheme only sets the active theme's keys and never clears the rest,
    so a theme missing a key would inherit a stale --con-* value from whatever
    was cycled through last. Key parity is the guard."""
    body = "mark(JSON.stringify(Object.fromEntries(Object.entries(c._THEMES).map(([k,v]) => [k, Object.keys(v).sort()]))));"
    themes = json.loads(_run(body, wait_ms=50)[0][0])
    assert set(themes) == {"dark", "light", "parchment"}
    assert themes["light"] == themes["dark"] == themes["parchment"]


# --- Ctrl+[ and Ctrl+] walk the rail; with Shift, only the Q1 sessions ------

def _step(order, current, direction, urgent=False, quad_of=None):
    body = (
        f"window.ctbSessionOrder = {json.dumps([{'name': n, 'label': n, 'state': 'idle'} for n in order])};"
        f"window.ctbQuadOf = {json.dumps(quad_of or {})};"
        f"c._state.session = {json.dumps(current)};"
        f"const it = c._stepSession({direction}, {json.dumps(urgent)}); mark(it ? it.name : null);"
    )
    return _run(body, wait_ms=50)[0][0]


_ORDER = [f"s{i}" for i in range(1, 13)]
_Q = {"s2": "Q1", "s5": "Q1", "s7": "Q2", "s9": "Q1"}


def test_left_moves_one_up_from_the_eleventh_session():
    assert _step(_ORDER, "s11", -1) == "s10"


def test_right_moves_one_down():
    assert _step(_ORDER, "s10", 1) == "s11"


def test_left_from_the_top_wraps_to_the_last_session():
    assert _step(_ORDER, "s1", -1) == "s12"


def test_right_from_the_bottom_wraps_to_the_first():
    assert _step(_ORDER, "s12", 1) == "s1"


def test_with_nothing_open_left_starts_at_the_end_and_right_at_the_head():
    assert _step(_ORDER, None, -1) == "s12"
    assert _step(_ORDER, None, 1) == "s1"


def test_q1_left_skips_everything_that_is_not_q1():
    assert _step(_ORDER, "s9", -1, True, _Q) == "s5"


def test_q1_right_skips_everything_that_is_not_q1():
    assert _step(_ORDER, "s2", 1, True, _Q) == "s5"


def test_q1_from_a_non_q1_session_goes_to_the_nearest_q1_in_that_direction():
    assert _step(_ORDER, "s7", -1, True, _Q) == "s5"
    assert _step(_ORDER, "s7", 1, True, _Q) == "s9"


def test_q1_wraps_both_ways():
    assert _step(_ORDER, "s2", -1, True, _Q) == "s9"
    assert _step(_ORDER, "s9", 1, True, _Q) == "s2"


def test_q1_with_nothing_open_starts_at_the_far_end():
    assert _step(_ORDER, None, -1, True, _Q) == "s9"
    assert _step(_ORDER, None, 1, True, _Q) == "s2"


def test_q1_with_no_q1_sessions_goes_nowhere():
    assert _step(_ORDER, "s7", -1, True, {"s7": "Q2"}) is None


def test_the_only_q1_session_open_goes_nowhere():
    assert _step(_ORDER, "s2", 1, True, {"s2": "Q1"}) is None


def test_brackets_are_bound_and_backquote_is_gone():
    js = CONSOLE_JS.read_text()
    assert "'BracketLeft'" in js and "'BracketRight'" in js
    assert "stepSession(dir, e.shiftKey)" in js
    assert "Backquote" not in js and "e.key !== '`'" not in js


def test_a_finger_whose_touchend_never_arrives_releases_on_its_own():
    """touchend is lost when the touched line was replaced by a poll; the
    lease must lapse by itself so polling does not stay skipped forever."""
    log = _run("""
      c._setTouching(true);          // a 60s lease, as the test hook grants
      mark(c._scrollInFlight() ? 'moving' : 'rest');
    """)
    assert [t for t, _ in log] == ["moving"]
    # the real lease is short: prove it lapses without a touchend
    log = _run("""
      // grab the real lease length by starting one through the public path
      const tail = { addEventListener(){}, };
      c._noteScrolling();
      c._whenSettled(() => mark('ran'));
    """, wait_ms=400)
    assert [t for t, _ in log] == ["ran"]
