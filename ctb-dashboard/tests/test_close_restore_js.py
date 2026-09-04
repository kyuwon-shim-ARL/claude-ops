"""Ctrl+Q closes the open session like the trash; Ctrl+Shift+Q restores."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CONSOLE_JS = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/js/session-control.js"


def _block():
    js = CONSOLE_JS.read_text()
    return js[js.index("  /* Ctrl/Cmd+Q closes the open session"):js.index("  /* Ctrl/Cmd+Tab bounces")]


def test_close_uses_the_trashs_delete_without_force():
    b = _block()
    assert re.search(r"/delete', \{\s*method: 'POST', body: JSON\.stringify\(\{ force: false \}\)", b)
    assert "force: true" not in b


def test_a_blocked_close_only_reports_and_points_at_the_trash():
    b = _block()
    assert "r.status === 409" in b and "reasons" in b and "🗑" in b
    assert "confirm(" not in b and "alert(" not in b  # no dialog either way


def test_a_closed_session_hands_the_console_to_its_neighbour_or_closes_it():
    b = _block()
    assert "if (next) show(next.name, true); else hide();" in b


def test_restore_opens_what_came_back_and_says_when_nothing_is_left():
    b = _block()
    assert "'/api/sessions/restore'" in b
    assert "show(r.body.session, true)" in b
    assert "r.status === 404" in b


def test_chords_q_and_shift_q_with_alt_fallback():
    b = _block()
    assert "e.code !== 'KeyQ'" in b and "accelHeld(e)" in b
    assert "if (e.shiftKey) restoreSession(); else closeSession();" in b
    assert "if (!e.shiftKey && !state.session) return;" in b


pytestmark_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


@pytestmark_node
@pytest.mark.parametrize("order,name,expected", [
    (["a", "b", "c"], "b", "c"),   # the one below, like a browser tab
    (["a", "b", "c"], "c", "b"),   # last: the one above
    (["a"], "a", None),            # alone: nothing, the console closes
    (["a", "b"], "zz", None),      # not on the rail
])
def test_neighbour_choice(order, name, expected):
    harness = f"""
    global.window = {{ location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}} }};
    global.document = {{ addEventListener(){{}}, readyState:'complete',
      createElement: () => ({{style:{{ setProperty(){{}} }}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
      body: {{appendChild(){{}}}}, head: {{appendChild(){{}}}}, documentElement: {{style:{{setProperty(){{}}}}}} }};
    global.navigator = {{}}; global.fetch = () => new Promise(() => {{}});
    require({json.dumps(str(CONSOLE_JS))});
    const list = {json.dumps([{"name": n} for n in order])};
    const r = window.ctbConsole._neighbourAfterClose(list, {json.dumps(name)});
    process.stdout.write(JSON.stringify(r ? r.name : null));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == expected
