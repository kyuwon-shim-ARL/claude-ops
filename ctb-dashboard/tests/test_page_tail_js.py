"""How far one keyboard page moves the tail, on panes of different sizes.

The device is the variable this has to survive: an iPhone shows a dozen lines
where a desktop shows fifty, so the step is measured from the pane rather
than picked. These drive the shipped pageTail() against a fake element whose
geometry is set per case -- what is asserted is the arithmetic that decides
where the reader lands.
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
global.window = {{
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
  getComputedStyle: (el) => ({{ lineHeight: el._lh, fontSize: '12px' }}),
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete',
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const c = window.ctbConsole;
const g = {spec};
c._els().tail = {{
  _lh: g.lineHeight,
  clientHeight: g.clientHeight,
  scrollHeight: g.scrollHeight,
  scrollTop: g.scrollTop,
}};
const moved = c._pageTail(g.dir);
process.stdout.write(JSON.stringify({{moved: moved, top: c._els().tail.scrollTop}}));
"""


def page(dir, *, line_height="18px", client=360, content=3600, top=0):
    spec = json.dumps({
        "lineHeight": line_height, "clientHeight": client,
        "scrollHeight": content, "scrollTop": top, "dir": dir,
    })
    script = _HARNESS.format(path=json.dumps(str(CONSOLE_JS)), spec=spec)
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_page_is_the_screen_less_one_line_of_overlap():
    """360px / 18px = 20 lines visible, so a page is 19 of them."""
    assert page(1, client=360, line_height="18px", top=0) == {
        "moved": True, "top": 19 * 18,
    }


def test_a_small_phone_pane_moves_less_than_a_desktop_one():
    """The whole point of measuring: same content, different device."""
    phone = page(1, client=234, line_height="19.5px", top=0)["top"]
    desk = page(1, client=760, line_height="18px", top=0)["top"]
    assert phone < desk
    # 234/19.5 = 12 lines visible -> 11 lines of travel
    assert phone == 11 * 19.5


def test_up_and_down_are_symmetric():
    down = page(1, top=0)["top"]
    back = page(-1, top=down)["top"]
    assert back == 0


def test_it_stops_at_the_bottom_instead_of_overshooting():
    r = page(1, client=360, content=3600, top=3240)
    assert r == {"moved": False, "top": 3240}   # 3600-360 is the floor


def test_it_stops_at_the_top():
    assert page(-1, top=0) == {"moved": False, "top": 0}


def test_a_partial_page_still_lands_exactly_at_the_end():
    r = page(1, client=360, content=3600, top=3100)
    assert r["moved"] is True
    assert r["top"] == 3240


def test_a_pane_too_short_for_two_lines_still_moves_one():
    """floor(20/18) = 1 visible; the overlap rule would leave zero travel."""
    assert page(1, client=20, line_height="18px", top=0)["top"] == 18


def test_an_unresolvable_line_height_falls_back_to_the_font():
    """getComputedStyle can answer 'normal'; 12px * 1.5 is the fallback."""
    r = page(1, client=360, line_height="normal", top=0)
    assert r["top"] == 19 * 18   # floor(360/18)=20 visible, 19 of travel


def test_nothing_to_scroll_does_not_move():
    assert page(1, client=360, content=360, top=0) == {"moved": False, "top": 0}
