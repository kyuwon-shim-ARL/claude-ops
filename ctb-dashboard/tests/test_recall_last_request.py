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


# --- the turn boundaries the jump-back pill walks ---------------------------

def submitted(lines):
    script = _HARNESS.replace("_findLastSubmitted", "_submittedLines").format(
        path=json.dumps(str(CONSOLE_JS)), payload=json.dumps(lines)
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_every_submitted_prompt_in_order():
    assert submitted([
        "❯ 첫 요청",
        "  답",
        "",
        "❯ 두 번째 요청",
        "  답",
    ]) == [0, 3]


def test_the_pill_and_recall_agree_on_what_a_turn_is():
    """One test, two readers. A boundary the pill jumps to that recall would
    not take back is a boundary that means two different things."""
    lines = [
        "❯ 진짜로 보낸 요청",
        "",
        "  Do you trust the files in this folder?",
        "  ❯ 1. Yes, proceed",
        "",
        RULE,
        "❯ 아직 안 보낸 초안",
        RULE,
    ]
    assert submitted(lines) == [0]
    assert recall(lines) == "진짜로 보낸 요청"


def test_no_turns_at_all():
    assert submitted(["그냥 출력", "", "  더 많은 출력"]) == []


# --- answered AskUserQuestion blocks are also turn boundaries --------------

def test_answered_question_header_counts_as_a_turn_linux_bullet():
    assert submitted([
        "❯ 첫 요청",
        "",
        "● User answered Claude's questions:",
        "  ⎿  · 협업 형태를 어떻게 잡을까요? → GitHub 원격 (권장)",
    ]) == [0, 2]


def test_answered_question_header_counts_as_a_turn_macos_bullet():
    assert submitted([
        "⏺ User answered Claude's questions:",
        "  ⎿  · 질문 → 답",
    ]) == [0]


def test_mixed_typed_and_answered_turns_stay_in_order():
    assert submitted([
        "❯ 첫 요청",
        "  답",
        "",
        "● User answered Claude's questions:",
        "  ⎿  · 질문 → 답",
        "",
        "❯ 두 번째 요청",
    ]) == [0, 3, 6]


def test_answered_header_must_be_at_column_zero():
    """Indented into Claude's own prose, this is not a turn boundary."""
    assert submitted([
        "❯ 요청",
        "  User answered Claude's questions:",
    ]) == [0]


def test_bullet_used_for_something_else_is_not_a_turn():
    """The same bullet introduces ordinary tool-call lines; only the full
    header phrase makes it a turn boundary."""
    assert submitted([
        "● Bash(echo hi)",
        "  ⎿  hi",
    ]) == []


def test_recall_still_ignores_answered_question_blocks():
    """findLastSubmitted stays typed-prompts only: pasting an answer header
    into the input box would be useless."""
    assert recall([
        "❯ 실제 요청",
        "",
        "● User answered Claude's questions:",
        "  ⎿  · 질문 → 답",
    ]) == "실제 요청"
