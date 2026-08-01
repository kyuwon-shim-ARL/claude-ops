"""Behavioural tests for tap-range copy cleanup -- running the real shipped JS.

String-presence tests cannot catch what adversarial testing found earlier:
against a live Claude pane the copied text carried Claude Code's two-column
output indent and tmux's line padding, so pasted Python/YAML arrived with a
spurious global indent. The unit fixtures were clean synthetic strings and
looked fine.

So these drive the actual function through node, with realistic terminal text.
Skipped (not silently passed) when node is unavailable.
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
global.window = {{ location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}} }};
global.document = {{
  addEventListener(){{}}, readyState:'complete',
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const lines = JSON.parse({payload});
process.stdout.write(JSON.stringify(window.ctbConsole._cleanLines(lines)));
"""


def clean(lines):
    """Call the shipped cleanLines through node."""
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        payload=json.dumps(json.dumps(lines)),
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# --- the regression adversarial testing exposed ------------------------------

def test_claude_indent_and_tmux_padding_are_stripped():
    """Captured shape from a live pane: 2-col indent + width padding."""
    selected = [
        '  print("Hello, World!")                    ',
        '  print("Hello, World!")                                        ',
    ]
    assert clean(selected) == 'print("Hello, World!")\nprint("Hello, World!")'


def test_relative_indentation_is_preserved():
    """Dedent removes the common prefix only -- code structure survives."""
    assert clean(["  def f():        ", "      return 1    "]) == "def f():\n    return 1"


def test_yaml_block_pastes_cleanly():
    """A spurious global indent is what actually breaks YAML on paste."""
    assert clean(["  root:      ", "    child: 1 "]) == "root:\n  child: 1"


def test_single_long_line_survives_intact():
    """Pairs with capture-pane -J: the line must not come back broken."""
    cmd = "ssh kyuwon@100.85.200.72 -p 22 -L 8420:localhost:8420 -o ServerAliveInterval=30"
    assert clean(["  " + cmd + "   "]) == cmd


# --- selection edges ---------------------------------------------------------

def test_leading_and_trailing_blank_lines_are_trimmed():
    """Tapping a little wide should not add empty lines to the clipboard."""
    assert clean(["   ", "  content  ", "", "   "]) == "content"


def test_blank_lines_inside_the_range_are_kept():
    assert clean(["  a", "", "  b"]) == "a\n\nb"


def test_blank_only_selection_yields_empty_string():
    assert clean(["   ", "", "  "]) == ""
    assert clean([]) == ""


def test_single_line_selection():
    """The common case: tap one line, tap it again, copy."""
    assert clean(["  git status   "]) == "git status"


def test_unindented_content_is_untouched():
    assert clean(["no indent here", "  relative"]) == "no indent here\n  relative"
