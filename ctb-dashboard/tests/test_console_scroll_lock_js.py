"""The keyboard page chord's gating, and what the page lock puts back.

pageTail's arithmetic is covered in test_page_tail_js; the bugs that bite
live in the gating around it -- whether a chord meant for the console also
reaches the grid behind it, and whether closing the console hands the page
back exactly as it was. Both run the shipped JS with a recording stub DOM.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "ctb_dashboard" / "static"
CONSOLE_JS = STATIC / "js" / "session-control.js"
INDEX_HTML = (
    Path(__file__).resolve().parents[1]
    / "src" / "ctb_dashboard" / "templates" / "index.html"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

# A DOM thin enough to load the console but faithful about the two things
# under test: which keydown listeners exist, and what body.style holds.
_HARNESS = """
const handlers = [];
const bodyStyle = {{ setProperty(){{}}, removeProperty(){{}} }};
global.scrolled = null;
function elem() {{
  return {{
    style: {{ setProperty(){{}}, removeProperty(){{}} }},
    classList: {{add(){{}}, remove(){{}}}},
    setAttribute(){{}}, removeAttribute(){{}}, getAttribute(){{ return null; }},
    addEventListener(){{}}, appendChild(){{}}, removeChild(){{}},
    querySelector(){{ return null; }}, querySelectorAll(){{ return []; }},
    focus(){{}}, contains(){{ return false; }},
  }};
}}
global.window = {{
  location: {{search:'', pathname:'/'}}, history: {{}},
  addEventListener(){{}},
  pageXOffset: {sx}, pageYOffset: {sy},
  scrollTo: (x, y) => {{ global.scrolled = [x, y]; }},
  getComputedStyle: (el) => ({{ lineHeight: el._lh || '18px', fontSize: '12px' }}),
  matchMedia: () => ({{ matches: false, addEventListener(){{}} }}),
}};
global.document = {{
  addEventListener: (type, fn) => {{ if (type === 'keydown') handlers.push(fn); }},
  readyState: 'complete',
  documentElement: {{ scrollLeft: 0, scrollTop: 0,
    style: {{ setProperty(){{}}, removeProperty(){{}} }} }},
  createElement: elem, getElementById: () => null,
  body: {{ style: bodyStyle, appendChild(){{}}, removeChild(){{}},
           setAttribute(){{}}, removeAttribute(){{}}, getAttribute(){{ return null; }} }},
  activeElement: null,
}};
global.navigator = {{ userAgent: 'iPhone' }};
global.fetch = () => Promise.resolve({{ ok: true, json: () => Promise.resolve({{}}) }});
require({console_js});
const c = window.ctbConsole;
{body}
"""


def _run(body, *, sx=0, sy=0):
    script = _HARNESS.format(
        console_js=json.dumps(str(CONSOLE_JS)), body=body, sx=sx, sy=sy
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


_KEY = """
const els = c._els();
els.tail = {{ _lh: '18px', clientHeight: 360, scrollHeight: 3600, scrollTop: {top} }};
c._state.session = {session};
let prevented = false;
const ev = {{
  key: {key}, shiftKey: {shift}, metaKey: {meta}, ctrlKey: false, altKey: false,
  isComposing: {composing}, keyCode: {keycode},
  preventDefault: () => {{ prevented = true; }},
}};
handlers.forEach((h) => {{ try {{ h(ev); }} catch (e) {{}} }});
process.stdout.write(JSON.stringify({{prevented, top: els.tail.scrollTop}}));
"""


def press(key, *, shift=True, meta=True, session='"claude_x"', top=1800,
          composing=False, keycode=0):
    return _run(_KEY.format(
        key=json.dumps(key), shift=json.dumps(shift), meta=json.dumps(meta),
        session=session, top=top, composing=json.dumps(composing),
        keycode=keycode,
    ))


def test_the_chord_pages_up_and_swallows_the_key():
    r = press("ArrowUp")
    assert r["top"] == 1800 - 19 * 18
    assert r["prevented"] is True, "the textarea must not see the arrow"


def test_the_chord_pages_down():
    assert press("ArrowDown")["top"] == 1800 + 19 * 18


def test_a_bare_arrow_is_left_alone():
    """Without the accelerator the caret keeps the key."""
    r = press("ArrowUp", meta=False)
    assert r == {"prevented": False, "top": 1800}


def test_the_accelerator_without_shift_is_left_alone():
    """Cmd+Arrow is 'jump to end' in a textarea; only Shift is ours."""
    assert press("ArrowUp", shift=False)["top"] == 1800


def test_nothing_happens_with_no_session_open():
    assert press("ArrowUp", session="null") == {"prevented": False, "top": 1800}


def test_a_key_mid_composition_is_ignored():
    """Hangul composition reports keyCode 229; preventDefault there can strand
    the composition buffer."""
    assert press("ArrowUp", composing=True, keycode=229) == {
        "prevented": False, "top": 1800,
    }


_LOCK = """
const body = document.body;
body.style.background = '#111';        // the board's own inline theme
body.style.color = '#eee';
c._lockPage();
const locked = {position: body.style.position, overflow: body.style.overflow,
                top: body.style.top, left: body.style.left};
body.style.background = '#fff';        // something writes while locked
c._unlockPage();
process.stdout.write(JSON.stringify({
  locked,
  after: {position: body.style.position, overflow: body.style.overflow,
          top: body.style.top, background: body.style.background,
          color: body.style.color},
  scrolled: global.scrolled,
}));
"""


def test_lock_parks_the_page_and_gives_it_back():
    r = _run(_LOCK, sx=0, sy=740)
    assert r["locked"]["position"] == "fixed"
    assert r["locked"]["overflow"] == "hidden"
    assert r["locked"]["top"] == "-740px"
    # Handed back unset, not to some snapshot of the attribute.
    assert r["after"]["position"] == ""
    assert r["after"]["overflow"] == ""
    assert r["after"]["top"] == ""
    assert r["scrolled"] == [0, 740]


def test_unlock_keeps_what_was_written_while_locked():
    """A snapshot-restore of the whole style attribute would revert this."""
    r = _run(_LOCK, sy=740)
    assert r["after"]["background"] == "#fff"
    assert r["after"]["color"] == "#eee"


def test_the_horizontal_offset_comes_back_too():
    r = _run(_LOCK, sx=120, sy=740)
    assert r["locked"]["left"] == "-120px"
    assert r["scrolled"] == [120, 740]


def test_locking_twice_keeps_the_first_offset():
    """Switching session calls show() again without hide()."""
    r = _run("""
      c._lockPage();
      window.pageYOffset = 9999;
      c._lockPage();
      c._unlockPage();
      process.stdout.write(JSON.stringify({scrolled: global.scrolled}));
    """, sy=300)
    assert r["scrolled"] == [0, 300]


def test_unlocking_without_locking_does_nothing():
    r = _run("""
      c._unlockPage();
      process.stdout.write(JSON.stringify({scrolled: global.scrolled,
                                           position: document.body.style.position}));
    """)
    assert r["scrolled"] is None
    assert r.get("position", "") == "", "body must be left untouched"


def test_the_grid_stands_down_while_the_console_is_open():
    """The card-arrow handler in index.html moved focus behind the sheet."""
    html = INDEX_HTML.read_text()
    start = html.index("grid.addEventListener('keydown'")
    guard = html[start:start + 700]
    assert "ctbConsole.isOpen()" in guard, (
        "arrows over the grid must be ignored while the console covers it"
    )
