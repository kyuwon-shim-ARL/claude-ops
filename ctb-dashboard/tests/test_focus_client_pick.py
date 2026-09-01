"""Which tmux client /api/focus-session moves -- and which it must leave alone.

The endpoint used to switch every attached client to the requested session, so
one tap on a card in the browser dragged all of a VSCode window's terminals
onto the same session at once. A terminal keeps the tab name it was created
with, so the tab labelled 'omc-research-skills' then showed 'ops'.
"""

from ctb_dashboard.server import _ALREADY_THERE, _pick_client

ROWS = "\n".join([
    "/dev/pts/60\tclaude_omc-research-skills\t1788300000",
    "/dev/pts/65\tclaude_PIU-v2\t1788300500",
    "/dev/pts/92\tclaude_cross-talk\t1788300100",
])


def test_client_already_on_the_session_means_nothing_to_switch():
    assert _pick_client(ROWS, "claude_PIU-v2") is _ALREADY_THERE


def test_otherwise_the_single_most_recently_used_client():
    # Not a list, and not the first row: the freshest client_activity wins, so
    # a terminal that reconnected under a new name is still the one that moves.
    picked = _pick_client(ROWS, "claude_ops")
    assert picked == "/dev/pts/65"
    assert isinstance(picked, str)


def test_no_clients_at_all():
    assert _pick_client("", "claude_ops") is None


def test_malformed_rows_are_skipped_not_fatal():
    assert _pick_client("/dev/pts/9\tclaude_a\nbad\n\t\t\n", "claude_b") == "/dev/pts/9"


def test_missing_or_unparsable_activity_still_yields_a_client():
    assert _pick_client("/dev/pts/9\tclaude_a\n/dev/pts/8\tclaude_b\tnope", "claude_c") \
        in {"/dev/pts/9", "/dev/pts/8"}
