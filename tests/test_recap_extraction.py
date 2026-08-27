"""The recap Claude Code prints is the best summary the dashboard can show.

These cases come from real panes (see `tmux capture-pane` on claude_SBDD_landscape
and claude_CAMDA): the recap sits between the past-tense completion line and the
prompt, wraps onto indented continuation lines, and always carries a trailing
"(disable recaps in /config)" that must not reach the card.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ctb-dashboard" / "src"))

from ctb_dashboard.state_detector import SessionStateAnalyzer  # noqa: E402


@pytest.fixture
def analyzer():
    return SessionStateAnalyzer()


SINGLE = """\
✻ Sautéed for 54s
※ recap: Writing a consulting-grade AI×AMR report; audited citation coverage. (disable recaps in /config)
❯
"""

WRAPPED = """\
✻ Crunched for 9m 16s
※ recap: You're exploring whether GTA-5's latent map can aid scaffold hopping; I concluded MolFormer embeddings already do this better. Next: decide if I
  draft a ScaffoldHopReward component or a backlog ticket. (disable recaps in /config)
❯
"""


def test_single_line_recap_drops_the_config_hint(analyzer):
    assert analyzer.extract_recap(SINGLE) == (
        "Writing a consulting-grade AI×AMR report; audited citation coverage."
    )


def test_wrapped_recap_is_joined_into_one_line(analyzer):
    out = analyzer.extract_recap(WRAPPED)
    assert out.startswith("You're exploring whether GTA-5's latent map")
    assert out.endswith("draft a ScaffoldHopReward component or a backlog ticket.")
    assert "\n" not in out
    assert "disable recaps" not in out


def test_the_latest_recap_wins(analyzer):
    screen = SINGLE + "\n" + WRAPPED
    assert analyzer.extract_recap(screen).startswith("You're exploring")


def test_continuation_stops_at_the_prompt(analyzer):
    screen = (
        "※ recap: first part\n"
        "  second part. (disable recaps in /config)\n"
        "❯ 이건 사용자 프롬프트다\n"
    )
    assert analyzer.extract_recap(screen) == "first part second part."


def test_no_recap_on_screen(analyzer):
    assert analyzer.extract_recap("✻ Cooked for 6s\n❯\n") is None
    assert analyzer.extract_recap("") is None
    assert analyzer.extract_recap(None) is None


def test_recap_is_capped(analyzer):
    screen = "※ recap: " + "가" * 500 + " (disable recaps in /config)\n"
    assert len(analyzer.extract_recap(screen)) == 300
