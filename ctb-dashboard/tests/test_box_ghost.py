"""Ghost vs typed text in Claude Code's input box, read from the escape-coded capture."""

from ctb_dashboard.server import box_draft, box_is_ghost

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


# --- box_draft: the same capture, read for the text as well ------------------
#
# The unsent-draft push needs both halves at once -- what is in the box, and
# whether anyone typed it -- because nagging someone about a suggestion they
# never wrote is worse than staying quiet.


def test_draft_returns_typed_text_and_not_ghost():
    assert box_draft(["output", "❯ 소음 점수 다시 정리해줘"]) == ("소음 점수 다시 정리해줘", False)


def test_draft_flags_a_suggestion():
    assert box_draft([f"❯ {ESC}[2m제안된 프롬프트{ESC}[0m"]) == ("제안된 프롬프트", True)


def test_draft_of_an_empty_box_is_none():
    assert box_draft(["❯   ", "tail"]) is None


def test_draft_with_no_box_at_all_is_none():
    assert box_draft(["just output", "  more output"]) is None


def test_draft_ignores_trailing_padding():
    assert box_draft(["❯ 짧은 글" + " " * 30]) == ("짧은 글", False)
