"""A pinned session's importance (its quadrant) shows on the console rail.

The grid tints a pinned card by quadrant, but the switcher strip above the
terminal painted every chip the same, so which open session was the urgent one
could not be read at a glance. The dashboard publishes the quadrant per
session and the strip paints each chip with that quadrant's hue. Runs the
shipped JS in node with a minimal DOM.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src/ctb_dashboard"
CONSOLE_JS = SRC / "static/js/session-control.js"
INDEX_HTML = SRC / "templates/index.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
function El(tag) {{
  this.tag = tag; this.style = {{ setProperty(){{}} }}; this.attrs = {{}}; this.children = [];
  this.textContent = ''; this.className = ''; this.dataset = {{}};
  this.clientWidth = 300; this.offsetLeft = 0; this.offsetWidth = 50; this.scrollLeft = 0;
}}
El.prototype.setAttribute = function (k, v) {{ this.attrs[k] = String(v); }};
El.prototype.appendChild = function (c) {{ this.children.push(c); return c; }};
El.prototype.addEventListener = function () {{}};
El.prototype.removeEventListener = function () {{}};
El.prototype.getAttribute = function (k) {{ return this.attrs[k]; }};
El.prototype.querySelector = function () {{ return null; }};
El.prototype.querySelectorAll = function () {{ return []; }};
El.prototype.closest = function () {{ return null; }};
El.prototype.focus = function () {{}};
El.prototype.contains = function () {{ return false; }};
El.prototype.getBoundingClientRect = function () {{ return {{top:0,left:0,width:0,height:0}}; }};
global.window = {{ location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
  matchMedia: () => ({{matches:false, addEventListener(){{}}}}), innerHeight: 800 }};
global.document = {{
  addEventListener(){{}}, removeEventListener(){{}}, readyState:'complete',
  createElement: (t) => new El(t), getElementById: () => null,
  head: new El('head'), body: new El('body'), documentElement: new El('html'),
}};
global.navigator = {{}};
global.fetch = () => new Promise(() => {{}});
require({path});
const c = window.ctbConsole;
{body}
"""


def _run(body):
    script = _HARNESS.format(path=json.dumps(str(CONSOLE_JS)), body=body)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _chips(quad_of):
    body = f"""
      window.ctbSessionOrder = [
        {{name:'claude_a', label:'a', branch:null, state:'idle'}},
        {{name:'claude_b', label:'b', branch:null, state:'idle'}},
        {{name:'claude_c', label:'c', branch:null, state:'idle'}},
      ];
      window.ctbPinned = Object.keys({json.dumps(quad_of)});
      window.ctbQuadOf = {json.dumps(quad_of)};
      c._el().strip = new El('div');
      c._renderStrip();
      process.stdout.write(JSON.stringify(c._el().strip.children.map(ch => ch.attrs['data-quad'] || null)));
    """
    return _run(body)


def test_chip_carries_its_sessions_quadrant():
    assert _chips({"claude_a": "Q1", "claude_c": "Q3"}) == ["Q1", None, "Q3"]


def test_an_unpinned_rail_has_no_quadrant_marks():
    assert _chips({}) == [None, None, None]


def test_every_quadrant_has_a_rail_colour_rule():
    js = CONSOLE_JS.read_text()
    for q in ("Q1", "Q2", "Q3", "Q4"):
        assert re.search(rf'\.con-chip\[data-quad="{q}"\]', js), q


def test_rail_hues_match_the_grid_quadrant_palette():
    """Same importance, same colour: the chip ring uses the grid's Q hues."""
    html = INDEX_HTML.read_text()
    js = CONSOLE_JS.read_text()
    grid = re.search(r"function getQuadConfig\(\)(.*?)\n    }\n", html, re.S).group(1)
    for q in ("Q1", "Q2", "Q3", "Q4"):
        hue = re.search(rf"{q}: \{{ tint: 'rgba\((\d+,\d+,\d+)", grid).group(1)
        assert hue in js, f"{q} hue {hue} missing from the rail css"


def test_dashboard_publishes_the_quadrant_map():
    html = INDEX_HTML.read_text()
    assert "window.ctbQuadOf" in html
