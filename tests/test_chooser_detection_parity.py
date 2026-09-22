"""The two detectors must see a chooser the same way.

There are two copies of the state detector -- the canonical one the Telegram
monitor imports, and the dashboard's. They are meant to agree (that is what
test_session_state_parity.py is for), and a fix applied to one of them is a
system where the board says 입력대기 and the phone says nothing, or the other
way round. This pins the chooser footer specifically, which is the part that
was just added to both.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ctb-dashboard" / "src"))

from claude_ctb.utils.session_state import SessionStateAnalyzer as Canonical  # noqa: E402
from ctb_dashboard.state_detector import SessionStateAnalyzer as Dashboard  # noqa: E402

LINES = [
    "Enter to confirm · Esc to cancel",
    "Enter to select · ↑/↓ to navigate · Esc to cancel",
    "Enter to review · d to discard · Esc to close",
    "⏵⏵ bypass permissions on (shift+tab to cycle) · ← 8 agents",
    "⏵⏵ bypass permissions on · 1 shell · ← 8 agents",
    "… +24 lines (ctrl+o to expand)",
    "esc to interrupt · ctrl+t to hide",
    "Esc to close",
    "│ Enter to confirm · Esc to cancel │ Enter │ Esc는 종료 취소 │",
    "↑/↓ 이동 · x 완료 · d 그만둠",
    "",
]


@pytest.mark.parametrize("line", LINES)
def test_both_detectors_agree_on_what_a_chooser_footer_is(line):
    assert Canonical._is_key_hint_footer(line) == Dashboard._is_key_hint_footer(line), line


def test_the_canonical_detector_sees_the_folder_trust_prompt():
    """The monitor is what sends the Telegram notification. Ten sessions were
    parked on this screen and it had nothing to say about any of them."""
    content = "\n".join([
        "> /init",
        "",
        "  ❯ No, exit",
        "    Yes, I trust this folder",
        " Enter to confirm · Esc to cancel",
    ])
    assert Canonical()._detect_input_waiting(content)
