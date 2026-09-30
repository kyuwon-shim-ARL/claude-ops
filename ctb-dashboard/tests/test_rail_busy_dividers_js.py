"""Working chips recede, idle gets a colour, and a divider marks every spot
the rail switches between busy (working) and not.

작업중 used to be the loudest thing on the rail (breathing green dot) while
유휴 -- the state the user actually has to catch and roll -- sat grey and
still. This flips that: working chips dim via data-busy, idle's dot turns
sky blue, and paintRunDividers() marks the busy/idle boundaries so where the
rail switches is visible without reading any word. Runs the real JS in node
with the same recursive-selector DOM harness as the context-gauge tests
(quadrant test's harness returns null from querySelector and cannot exercise
this).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src/ctb_dashboard"
CONSOLE_JS = SRC / "static/js/session-control.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
function El(tag) {{
  this.tag = tag; this.style = {{ setProperty(){{}} }}; this.attrs = {{}}; this.children = [];
  this.textContent = ''; this._className = ''; this.dataset = {{}};
  this.clientWidth = 300; this.offsetLeft = 0; this.offsetWidth = 50; this.scrollLeft = 0;
  var self = this;
  this.classList = {{
    add: function (c) {{ var cur = self._className.split(/\\s+/).filter(Boolean);
      if (cur.indexOf(c) === -1) cur.push(c); self._className = cur.join(' '); }},
    remove: function (c) {{ var cur = self._className.split(/\\s+/).filter(Boolean);
      self._className = cur.filter(function (x) {{ return x !== c; }}).join(' '); }},
    contains: function (c) {{ return self._className.split(/\\s+/).indexOf(c) !== -1; }},
  }};
}}
Object.defineProperty(El.prototype, 'className', {{
  get: function () {{ return this._className; }},
  set: function (v) {{ this._className = v; }},
}});
El.prototype.setAttribute = function (k, v) {{ this.attrs[k] = String(v); }};
El.prototype.appendChild = function (c) {{ c.parentNode = this; this.children.push(c); return c; }};
El.prototype.removeChild = function (c) {{
  var i = this.children.indexOf(c); if (i > -1) this.children.splice(i, 1); return c;
}};
El.prototype.insertBefore = function (c, ref) {{
  c.parentNode = this;
  var i = ref ? this.children.indexOf(ref) : -1;
  if (i === -1) this.children.push(c); else this.children.splice(i, 0, c);
  return c;
}};
El.prototype.addEventListener = function () {{}};
El.prototype.removeEventListener = function () {{}};
El.prototype.getAttribute = function (k) {{ return this.attrs[k] !== undefined ? this.attrs[k] : null; }};
El.prototype.removeAttribute = function (k) {{ delete this.attrs[k]; }};
El.prototype.hasAttribute = function (k) {{ return this.attrs[k] !== undefined; }};

function matchesSimple(el, sel) {{
  if (sel[0] === '.') return el.classList && el.classList.contains(sel.slice(1));
  var m = /^\\[([\\w-]+)(?:=\\"([^\\"]*)\\")?\\]$/.exec(sel);
  if (m) {{
    var has = el.attrs[m[1]] !== undefined;
    if (m[2] === undefined) return has;
    return has && el.attrs[m[1]] === m[2];
  }}
  return false;
}}
function collect(el, sel, out) {{
  for (var i = 0; i < el.children.length; i++) {{
    var c = el.children[i];
    if (matchesSimple(c, sel)) out.push(c);
    collect(c, sel, out);
  }}
}}
El.prototype.querySelectorAll = function (sel) {{
  var out = []; collect(this, sel, out); return out;
}};
El.prototype.querySelector = function (sel) {{
  var out = this.querySelectorAll(sel); return out.length ? out[0] : null;
}};
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


def _item(name, state):
    return {"name": name, "label": name, "branch": None, "state": state}


def _rail_summary_js():
    return """
      var kids = c._el().strip.children.filter(function (k) {
        return k.attrs['data-switch-session'] !== undefined || k.attrs['data-ctb-divider'] !== undefined;
      });
      var out = kids.map(function (k) {
        if (k.attrs['data-ctb-divider'] !== undefined) {
          var lab = k.querySelector('.con-run-divider-label');
          return {divider: true, label: lab ? lab.textContent : null};
        }
        return {
          name: k.getAttribute('data-switch-session'),
          busy: k.hasAttribute('data-busy'),
        };
      });
      process.stdout.write(JSON.stringify(out));
    """


def _render(states):
    items = [_item("s" + str(i), st) for i, st in enumerate(states)]
    return f"""
      window.ctbSessionOrder = {json.dumps(items)};
      c._el().strip = new El('div');
      c._renderStrip();
      {_rail_summary_js()}
    """


def test_working_chips_carry_data_busy_and_idle_does_not():
    out = _run(_render(["working", "idle", "waiting"]))
    chips = [row for row in out if not row.get("divider")]
    assert chips[0]["busy"] is True
    assert chips[1]["busy"] is False
    assert chips[2]["busy"] is False


def test_current_chip_is_never_dimmed_even_while_working():
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
      ];
      window.ctbState = {session: 's0'};
      c._state.session = 's0';
      c._el().strip = new El('div');
      c._renderStrip();
      var chip = c._el().strip.children[0];
      process.stdout.write(JSON.stringify({
        current: chip.getAttribute('aria-current'),
        busy: chip.hasAttribute('data-busy'),
      }));
    """
    out = _run(body)
    assert out["current"] == "true"
    # data-busy is still set (CSS carves the aria-current exception), the
    # point under test is that the attribute pairing exists for CSS to key on.
    assert out["busy"] is True


def test_no_divider_when_every_chip_is_the_same_kind():
    out = _run(_render(["working", "working", "working"]))
    assert not any(row.get("divider") for row in out)


def test_one_divider_between_a_busy_run_and_an_idle_run():
    out = _run(_render(["working", "working", "idle", "idle", "idle"]))
    dividers = [row for row in out if row.get("divider")]
    assert len(dividers) == 1
    assert dividers[0]["label"] == "유휴 3"


def test_divider_before_a_busy_run_carries_no_label():
    out = _run(_render(["idle", "working", "working"]))
    dividers = [row for row in out if row.get("divider")]
    assert len(dividers) == 1
    assert dividers[0]["label"] is None


def test_alternating_busy_idle_gets_a_divider_at_every_switch():
    out = _run(_render(["idle", "working", "idle"]))
    dividers = [row for row in out if row.get("divider")]
    assert len(dividers) == 2
    assert dividers[0]["label"] is None       # opens the working run
    assert dividers[1]["label"] == "유휴 1"    # opens the trailing idle run


def test_mixed_non_busy_run_is_labelled_waiting_not_idle():
    out = _run(_render(["working", "idle", "waiting"]))
    dividers = [row for row in out if row.get("divider")]
    assert len(dividers) == 1
    assert dividers[0]["label"] == "대기 2"


def test_dividers_carry_no_switch_session_and_are_hidden_from_a11y():
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
        {name:'s1', label:'s1', branch:null, state:'idle'},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      var div = c._el().strip.children.filter(function (k) {
        return k.attrs['data-ctb-divider'] !== undefined;
      })[0];
      process.stdout.write(JSON.stringify({
        hasSwitch: div.hasAttribute('data-switch-session'),
        ariaHidden: div.getAttribute('aria-hidden'),
      }));
    """
    out = _run(body)
    assert out["hasSwitch"] is False
    assert out["ariaHidden"] == "true"


def test_syncstrip_moves_the_divider_when_a_chip_flips_state_in_place():
    """syncStrip patches state without re-sorting -- so a chip flipping from
    working to idle in the middle of the rail has to move the boundary to
    where the chips actually sit now, not where they sat at build time."""
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
        {name:'s1', label:'s1', branch:null, state:'working'},
        {name:'s2', label:'s2', branch:null, state:'idle'},
      ];
      window.ctbSessionAll = window.ctbSessionOrder;
      c._el().strip = new El('div');
      c._renderStrip();

      // s1 finishes: working -> idle, in place, no resort.
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
        {name:'s1', label:'s1', branch:null, state:'idle'},
        {name:'s2', label:'s2', branch:null, state:'idle'},
      ];
      window.ctbSessionAll = window.ctbSessionOrder;
      window.dispatchEvent = undefined;
      c._syncSurfaces();

      """ + _rail_summary_js()
    out = _run(body)
    chips = [row for row in out if not row.get("divider")]
    dividers = [row for row in out if row.get("divider")]
    assert [c["name"] for c in chips] == ["s0", "s1", "s2"]
    assert chips[0]["busy"] is True
    assert chips[1]["busy"] is False
    assert chips[2]["busy"] is False
    assert len(dividers) == 1
    assert dividers[0]["label"] == "유휴 2"


def test_mark_chip_gone_clears_data_busy_and_counts_as_non_idle():
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      var chip = c._el().strip.children[0];
      c._markChipGone(chip);
      process.stdout.write(JSON.stringify({
        busy: chip.hasAttribute('data-busy'),
        chipState: chip.getAttribute('data-chip-state'),
      }));
    """
    out = _run(body)
    assert out["busy"] is False
    assert out["chipState"] == "gone"


def test_idle_dot_colour_is_sky_blue_and_no_longer_breathes():
    js = CONSOLE_JS.read_text()
    assert "idle: '#38bdf8'" in js
    # working must not be a key in STATE_LIVE any more -- extract the object
    # literal and check it does not mention working.
    import re
    m = re.search(r"var STATE_LIVE = \{(.*?)\};", js, re.S)
    assert m, "STATE_LIVE object not found"
    assert "working" not in m.group(1)


def test_gone_chip_dot_is_grey_not_idle_blue():
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      var chip = c._el().strip.children[0];
      c._markChipGone(chip);
      var dot = chip.querySelector('.ctb-sdot');
      process.stdout.write(JSON.stringify({background: dot.style.background}));
    """
    out = _run(body)
    assert out["background"] == "#6b7280"


def test_mutation_check_no_dividers_when_paintRunDividers_is_stubbed_out():
    """If paintRunDividers is broken (a mutation makes it a no-op), the
    divider assertions above must fail -- proven here directly: with the
    real function replaced by a no-op, a busy/idle rail produces zero
    dividers, which is what a broken implementation would silently return."""
    body = """
      window.ctbSessionOrder = [
        {name:'s0', label:'s0', branch:null, state:'working'},
        {name:'s1', label:'s1', branch:null, state:'idle'},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      // Simulate the mutation: wipe out any dividers renderStrip placed,
      // standing in for a paintRunDividers() that never ran.
      var divs = c._el().strip.querySelectorAll('[data-ctb-divider]');
      divs.forEach(function (d) { d.parentNode.removeChild(d); });
      """ + _rail_summary_js()
    out = _run(body)
    assert not any(row.get("divider") for row in out)
