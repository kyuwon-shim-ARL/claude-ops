"""Context-window usage on a rail chip: number slot + colour, aria-label
carries it, syncSurfaces patches the same node in place, markChipGone resets
it to unknown. Runs the real JS in node with a harness whose
querySelector/querySelectorAll actually resolve class and [data-attr]
selectors recursively (the quadrant test's harness returns null and cannot
exercise patching)."""

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


def _run(body, js_path=None):
    script = _HARNESS.format(path=json.dumps(str(js_path or CONSOLE_JS)), body=body)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _render(items):
    return f"""
      window.ctbSessionOrder = {json.dumps(items)};
      c._el().strip = new El('div');
      c._renderStrip();
      var chips = c._el().strip.children;
      var out = chips.map(function (chip) {{
        var slot = chip.querySelector('.ctb-sctx');
        return {{
          name: chip.getAttribute('data-switch-session'),
          text: slot ? slot.textContent : null,
          color: slot ? slot.style.color : null,
          weight: slot ? slot.style.fontWeight : null,
          ariaLabel: chip.getAttribute('aria-label'),
        }};
      }});
      process.stdout.write(JSON.stringify(out));
    """


def _item(name, ctx):
    return {"name": name, "label": name, "branch": None, "state": "idle", "context_percent": ctx}


def test_chip_shows_percentage_and_warn_color_at_72(js_path=None):
    out = _run(_render([_item("claude_a", 72)]), js_path)
    assert out[0]["text"] == "72%"
    assert out[0]["color"] == "var(--con-warn)"
    assert "컨텍스트 72%" in out[0]["ariaLabel"]


def test_err_color_and_bold_at_85():
    out = _run(_render([_item("claude_a", 85)]))
    assert out[0]["text"] == "85%"
    assert out[0]["color"] == "var(--con-err)"
    assert out[0]["weight"] == "700"


def test_muted_color_below_60():
    out = _run(_render([_item("claude_a", 30)]))
    assert out[0]["text"] == "30%"
    assert out[0]["color"] == "var(--con-muted)"
    assert out[0]["weight"] == ""


def test_null_shows_em_dash():
    out = _run(_render([_item("claude_a", None)]))
    assert out[0]["text"] == "—"
    assert "컨텍스트" not in out[0]["ariaLabel"]


def test_sync_surfaces_updates_same_chip_node():
    body = """
      window.ctbSessionOrder = [
        {name:'claude_a', label:'a', branch:null, state:'idle', context_percent: 20},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      var chip0 = c._el().strip.children[0];

      window.ctbSessionOrder = [
        {name:'claude_a', label:'a', branch:null, state:'idle', context_percent: 91},
      ];
      window.ctbSessionAll = window.ctbSessionOrder;
      window.dispatchEvent = undefined;
      c._syncSurfaces();
      var chip1 = c._el().strip.children[0];
      var slot = chip1.querySelector('.ctb-sctx');
      process.stdout.write(JSON.stringify({
        sameNode: chip0 === chip1,
        text: slot.textContent,
        color: slot.style.color,
      }));
    """
    out = _run(body)
    assert out["sameNode"] is True
    assert out["text"] == "91%"
    assert out["color"] == "var(--con-err)"


def test_mark_chip_gone_resets_slot_to_em_dash():
    body = """
      window.ctbSessionOrder = [
        {name:'claude_a', label:'a', branch:null, state:'idle', context_percent: 75},
      ];
      c._el().strip = new El('div');
      c._renderStrip();
      var chip = c._el().strip.children[0];
      c._markChipGone(chip);
      var slot = chip.querySelector('.ctb-sctx');
      process.stdout.write(JSON.stringify({
        text: slot.textContent,
        ariaLabel: chip.getAttribute('aria-label'),
        title: chip.title,
      }));
    """
    out = _run(body)
    assert out["text"] == "—"
    assert "컨텍스트" not in out["ariaLabel"]
    assert "컨텍스트" not in out["title"]
    assert "claude_a" in out["title"]


def test_source_level_fields_present():
    js = CONSOLE_JS.read_text()
    html = INDEX_HTML.read_text()
    assert "context_percent" in js
    assert "context_percent" in html
    fetch_order_src = re.search(r"function fetchOrder\(\)(.*?)\n  }\n", js, re.S).group(1)
    assert "context_percent" in fetch_order_src
    to_order_item_src = re.search(r"function _toOrderItem\(s\)(.*?)\n    }\n", html, re.S).group(1)
    assert "context_percent" in to_order_item_src


def test_mutation_disables_paint_ctx_slot_and_assertion_fails(tmp_path):
    """Prove the 72% assertion is load-bearing: with paintCtxSlot's body
    replaced by a no-op, the chip never gets its text/colour set and the
    happy-path assertion must fail."""
    js = CONSOLE_JS.read_text()
    mutated = re.sub(
        r"function paintCtxSlot\(slot, pct\) \{.*?\n  \}",
        "function paintCtxSlot(slot, pct) { /* mutated: no-op */ }",
        js, count=1, flags=re.S,
    )
    assert mutated != js, "mutation did not match paintCtxSlot -- test would be vacuous"
    mutated_path = tmp_path / "session-control.mutated.js"
    mutated_path.write_text(mutated)

    with pytest.raises(AssertionError):
        test_chip_shows_percentage_and_warn_color_at_72(js_path=mutated_path)
