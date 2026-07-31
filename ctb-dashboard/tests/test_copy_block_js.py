"""Behavioural tests for the copy-block extractor -- running the real JS.

The string-presence tests in test_session_console.py could not have caught what
adversarial testing found: against a live Claude pane the extracted text
carried Claude Code's two-column output indent and tmux's line padding, so
copied Python/YAML would paste with a spurious global indent. The unit fixtures
were clean synthetic strings and looked fine.

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
const input = JSON.parse({payload});
const out = window.ctbConsole._extractCopyBlock(input);
process.stdout.write(JSON.stringify(out));
"""


def extract(text):
    """Call the shipped extractCopyBlock through node."""
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        payload=json.dumps(json.dumps(text)),
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# --- the regression that adversarial testing exposed -------------------------

def test_claude_indent_and_tmux_padding_are_stripped():
    """Captured shape from a live pane: 2-col indent + width padding."""
    screen = (
        "● [[COPY]]\n"
        '  print("Hello, World!")                    \n'
        '  print("Hello, World!")                                        \n'
        "  [[/COPY]]\n"
    )
    assert extract(screen) == 'print("Hello, World!")\nprint("Hello, World!")'


def test_relative_indentation_is_preserved():
    """Dedent must remove the common prefix only -- code structure survives."""
    screen = (
        "  [[COPY]]\n"
        "  def f():        \n"
        "      return 1    \n"
        "  [[/COPY]]\n"
    )
    assert extract(screen) == "def f():\n    return 1"


def test_yaml_block_pastes_cleanly():
    """A spurious global indent is what actually breaks YAML on paste."""
    screen = (
        "  [[COPY]]\n"
        "  root:      \n"
        "    child: 1 \n"
        "  [[/COPY]]\n"
    )
    assert extract(screen) == "root:\n  child: 1"


# --- selection rules ---------------------------------------------------------

def test_latest_complete_block_wins():
    screen = (
        "  [[COPY]]\n  ssh old@host\n  [[/COPY]]\n"
        "  some chatter\n"
        "  [[COPY]]\n  ssh new@host\n  [[/COPY]]\n"
    )
    assert extract(screen) == "ssh new@host"


def test_unclosed_opener_does_not_shadow_an_earlier_complete_block():
    screen = (
        "  [[COPY]]\n  real content\n  [[/COPY]]\n"
        "  [[COPY]]\n  still streaming...\n"
    )
    assert extract(screen) == "real content"


@pytest.mark.parametrize("screen", [
    "",
    "no markers at all",
    "  [[COPY]]\n  only an opener\n",
    "  [[/COPY]]\n  only a closer\n",
    "  [[COPY]]\n     \n  [[/COPY]]\n",  # whitespace-only body
])
def test_no_block_yields_null(screen):
    assert extract(screen) is None


def test_single_long_line_survives_intact():
    """Pairs with capture-pane -J: the line must not come back broken."""
    cmd = "ssh kyuwon@100.85.200.72 -p 22 -L 8420:localhost:8420 -o ServerAliveInterval=30"
    assert extract(f"  [[COPY]]\n  {cmd}   \n  [[/COPY]]\n") == cmd


def test_blank_lines_inside_the_block_are_kept():
    screen = "  [[COPY]]\n  a\n\n  b\n  [[/COPY]]\n"
    assert extract(screen) == "a\n\nb"
