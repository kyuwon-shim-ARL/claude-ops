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


def test_close_asks_without_force_first_and_never_opens_a_dialog():
    b = _block()
    assert re.search(r"/delete', \{\s*method: 'POST',\s*body: JSON\.stringify\(\{ force: force, allow_worktree: allowWorktree \}\)", b)
    # The automatic retry for a plain session must not be able to delete a worktree.
    assert "postDelete(name, true, false)" in b
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

_HARNESS_HEAD = """
global.window = { location: {search:'', pathname:'/'}, addEventListener(){}, history:{} };
global.document = { addEventListener(){}, readyState:'complete',
  createElement: () => ({style:{ setProperty(){} }, setAttribute(){}, addEventListener(){}, appendChild(){}}),
  body: {appendChild(){}}, head: {appendChild(){}}, documentElement: {style:{setProperty(){}}} };
global.navigator = {}; global.fetch = () => new Promise(() => {});
"""


def _close_step(status, body, forced):
    harness = _HARNESS_HEAD + f"""
    require({json.dumps(str(CONSOLE_JS))});
    const r = window.ctbConsole._closeStep({{status: {status}, body: {json.dumps(body)}}}, {json.dumps(forced)});
    process.stdout.write(JSON.stringify(r));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


_DIRTY = ["커밋되지 않은 변경사항이 있습니다"]


@pytestmark_node
def test_a_blocked_plain_session_is_closed_anyway():
    # Its files stay on disk; only tmux goes, and restore brings it back.
    blocked = {"status": "blocked", "check": {"is_worktree": False, "reasons": _DIRTY}}
    assert _close_step(409, blocked, False) == "force"


@pytestmark_node
def test_a_blocked_worktree_arms_instead_of_deleting():
    # Its directory and branch would be deleted: the first press only warns.
    blocked = {"status": "blocked", "check": {"is_worktree": True, "reasons": _DIRTY}}
    assert _close_step(409, blocked, False) == "arm"


@pytestmark_node
def test_a_forced_request_that_is_still_blocked_does_not_loop():
    blocked = {"status": "blocked", "check": {"is_worktree": False, "reasons": _DIRTY}}
    assert _close_step(409, blocked, True) == "error"


@pytestmark_node
def test_a_retry_the_server_found_to_be_a_worktree_arms():
    # The first check missed the worktree; the server's did, and refused.
    blocked = {"status": "blocked", "check": {"is_worktree": True, "reasons": _DIRTY}}
    assert _close_step(409, blocked, True) == "arm"


@pytestmark_node
@pytest.mark.parametrize("status,body,expected", [
    (200, {"status": "deleted"}, "deleted"),
    (200, {"status": "error", "error": "x"}, "error"),
    (500, {}, "error"),
])
def test_other_outcomes(status, body, expected):
    assert _close_step(status, body, False) == expected


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
