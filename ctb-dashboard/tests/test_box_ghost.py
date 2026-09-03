"""Ghost vs typed text in Claude Code's input box, read from the escape-coded capture."""

from ctb_dashboard.server import box_is_ghost

ESC = "\x1b"


def test_dim_text_after_the_prompt_is_a_ghost():
    raw = [f"{ESC}[39m❯  {ESC}[2m응 돌려봐{ESC}[0m"]
    assert box_is_ghost(raw) is True


def test_plain_text_after_the_prompt_is_typed():
    raw = [f"{ESC}[39m❯  응 돌려봐{ESC}[0m"]
    assert box_is_ghost(raw) is False


def test_dim_elsewhere_on_the_screen_does_not_count():
    raw = [f"{ESC}[2m  ? for shortcuts{ESC}[0m", "❯ git status"]
    assert box_is_ghost(raw) is False


def test_an_empty_box_is_neither():
    assert box_is_ghost(["❯ ", f"{ESC}[2mhint{ESC}[0m"]) is None


def test_the_last_box_wins():
    raw = ["❯ old typed", f"❯ {ESC}[2mnew ghost{ESC}[0m"]
    assert box_is_ghost(raw) is True


def test_combined_sgr_with_dim_counts():
    raw = [f"❯ {ESC}[2;90msuggest{ESC}[0m"]
    assert box_is_ghost(raw) is True
