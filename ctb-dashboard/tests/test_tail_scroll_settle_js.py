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
