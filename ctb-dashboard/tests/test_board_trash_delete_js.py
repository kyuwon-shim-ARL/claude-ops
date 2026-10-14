"""The board's trash button now closes a session the way the console's
Ctrl+Q does: no modal for a plain session (automatic retry) or a safe
worktree, one confirmation for an unsafe worktree.

The decision of what to do next after a delete POST is a pure function,
_boardDeleteDecision, exposed on window.ctbBoardDeleteDecision the way
session-control.js exposes _closeStep. Extracts the real shipped source
from index.html (not requirable as a whole -- it is inline script with
Jinja placeholders) and runs it in node.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/templates/index.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _decision_source() -> str:
    html = INDEX_HTML.read_text()
    start = html.index("function _boardDeleteDecision")
    end = html.index("window.ctbBoardDeleteDecision = _boardDeleteDecision;") + len(
        "window.ctbBoardDeleteDecision = _boardDeleteDecision;"
    )
    return html[start:end]


def _decide(status, body, forced):
    src = _decision_source()
    harness = f"""
    global.window = {{}};
    {src}
    process.stdout.write(JSON.stringify(window.ctbBoardDeleteDecision({status}, {json.dumps(body)}, {json.dumps(forced)})));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_a_successful_delete_is_done():
    assert _decide(200, {"status": "deleted"}, False) == "done"


def test_a_blocked_plain_session_retries():
    blocked = {"status": "blocked", "check": {"is_worktree": False, "reasons": ["dirty"]}}
    assert _decide(409, blocked, False) == "retry-plain"


def test_a_blocked_worktree_asks_for_confirmation():
    blocked = {"status": "blocked", "check": {"is_worktree": True, "reasons": ["dirty"]}}
    assert _decide(409, blocked, False) == "confirm-worktree"


def test_a_retry_the_server_now_says_is_a_worktree_still_confirms():
    # The first check missed the worktree; the server's did, and refused --
    # must not fall through to treating the forced retry as a plain error.
    blocked = {"status": "blocked", "check": {"is_worktree": True, "reasons": ["dirty"]}}
    assert _decide(409, blocked, True) == "confirm-worktree"


def test_a_forced_retry_that_is_still_blocked_does_not_loop():
    blocked = {"status": "blocked", "check": {"is_worktree": False, "reasons": ["dirty"]}}
    assert _decide(409, blocked, True) == "error"


@pytest.mark.parametrize("status,body", [
    (200, {"status": "error", "error": "x"}),
    (500, {}),
])
def test_other_outcomes_are_errors(status, body):
    assert _decide(status, body, False) == "error"


# --- mutation check: a decision that ignored is_worktree would be wrong ----

def test_mutation_without_the_worktree_check_would_misroute_a_plain_retry():
    """If the is_worktree branch were deleted, a blocked worktree on the
    first attempt would fall into retry-plain instead of confirm-worktree --
    this must be false against the real shipped function."""
    blocked = {"status": "blocked", "check": {"is_worktree": True, "reasons": ["dirty"]}}
    assert _decide(409, blocked, False) != "retry-plain"
