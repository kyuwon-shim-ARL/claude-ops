"""What "가져오기" pulls back, and what it refuses to.

The button copies the last request into the console's own box so it can be
edited after an Escape. Getting the wrong line is worse than getting none:
resending a menu entry or the frame of the input box would put words in the
user's mouth. These run the shipped JS, so the discriminator being tested is
the one that ships.
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
process.stdout.write(JSON.stringify(window.ctbConsole._findLastSubmitted({payload})));
"""

RULE = "─" * 40


def recall(lines):
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)), payload=json.dumps(lines)
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_takes_the_last_submitted_prompt():
    assert recall([
        "❯ 첫 요청",
        "  Claude가 답한 내용",
        "",
        "❯ 두 번째 요청",
        "",
        "  작업 중…",
    ]) == "두 번째 요청"


def test_joins_a_wrapped_prompt():
    assert recall([
        "❯ 사무실이니까 소음 점수를 더 높게",
        "  중요하게 생각해서 다시 정리해줘",
        "",
    ]) == "사무실이니까 소음 점수를 더 높게 중요하게 생각해서 다시 정리해줘"


def test_ignores_the_input_box():
    """The box sits under a rule; that is the whole difference on screen."""
    assert recall([
        "❯ 진짜로 보낸 요청",
        "",
        RULE,
        "❯ 아직 안 보낸 초안",
        RULE,
    ]) == "진짜로 보낸 요청"


def test_ignores_an_indented_menu_choice():
    """A trust prompt draws "❯ No, exit" inside a frame, never at column 0."""
    assert recall([
        "❯ 진짜로 보낸 요청",
        "",
        "  Do you trust the files in this folder?",
        "  ❯ 1. Yes, proceed",
        "    2. No, exit",
    ]) == "진짜로 보낸 요청"


def test_nothing_to_recall():
    assert recall(["그냥 출력", "", "  더 많은 출력"]) == ""


def test_empty_prompt_line_is_skipped():
    assert recall(["❯ 실제 요청", "", "❯", ""]) == "실제 요청"
