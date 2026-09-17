# -*- coding: utf-8 -*-
"""A session waiting on a background agent is working, and says so.

The turn has handed off: the main loop is not generating, so nothing on
screen says 'esc to interrupt'. What Claude Code shows instead is

    ✻ Waiting for 1 background agent to finish

and the detector read that as the opposite. Two separate faults did it, and
both are pinned here:

  1. `✻ Waiting for 1 …` has the shape of a completion line -- glyph, word,
     "for", number, exactly like `✻ Crunched for 59s` -- and three of the four
     places that tested for one did not require the duration's unit. The
     strongest evidence that the session was still working was being read as
     proof that it had stopped.
  2. Nothing recognised the line for what it is.

The cost was not a wrong badge. The monitor treats WORKING → anything-else as
a finished turn and sends "작업 완료", so a session that had just handed work
to an agent announced that it was done -- with the agent still running, in the
observed case for over an hour.

The screens here are the real thing: `tmux capture-pane` of a session in that
state, trimmed to the tail that matters.
"""

import pytest

from claude_ctb.utils.session_state import SessionStateAnalyzer

SEP = "─" * 60

LIVE = f"""● 이제 마무리까지 계속 갑니다.

✻ Waiting for 1 background agent to finish

{SEP}
❯ ㅇㅇ 계속 진행해줘
{SEP}
  [OMC#5.1.0L] | Model: Opus 5 | 5h:[###-----]39%(0h15m)
  session:2448m | ctx:[#####-----]47% | 🔧154 🤖7
  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← 9 agents

  ● main
  ◯ oh-my-claudecode:executor  Checking tutor.py preview port     1h 0m 4s · ↓ 273.7k tokens
"""

# The same session without OMC's status bar: plain Claude Code. The token
# counter on the agent row is what the structural matchers were catching, and
# it is not there for everyone.
PLAIN = f"""● 이제 마무리까지 계속 갑니다.

✻ Waiting for 2 background agents to finish

{SEP}
❯ 
{SEP}
"""


@pytest.fixture
def analyzer():
    return SessionStateAnalyzer()


def test_waiting_on_an_agent_is_working(analyzer):
    assert analyzer._detect_working_state(LIVE) is True


def test_it_does_not_need_the_omc_status_bar(analyzer):
    """Plain Claude Code has no token counter to fall back on."""
    assert analyzer._detect_working_state(PLAIN) is True


def test_the_waiting_line_is_not_a_completion(analyzer):
    """`✻ Waiting for 1` has the shape of `✻ Crunched for 59s`.

    Read as a completion it does worse than miss the working state: it
    actively vetoes the other working signals.
    """
    import re
    past = re.compile(
        rf'[{SessionStateAnalyzer._TOOL_GLYPHS}] \w+ for {SessionStateAnalyzer._DURATION_RE}')
    assert not past.search("✻ Waiting for 1 background agent to finish")
    # ...while the lines it exists for still match.
    for done in ("✻ Crunched for 59s", "✻ Cogitated for 5m 8s",
                 "✻ Worked for 57s", "● Baked for 2m"):
        assert past.search(done), done


# --- the words alone are not evidence -----------------------------------------

def test_a_pasted_transcript_does_not_make_an_idle_session_work(analyzer):
    """The counterexample: `● ` is also an assistant-output prefix.

    Somebody pastes a transcript that contains the waiting line, and the
    assistant answers below it. An earlier design allowed `● ` rows between
    the line and the box and called this live.
    """
    pasted = f"""❯ Here is the transcript:
  ✻ Waiting for 1 background agent to finish
● That was an old transcript.
{SEP}
❯ 
{SEP}
  [OMC#5.1.0L] | Model: Opus 5
"""
    assert analyzer._detect_working_state(pasted) is False


def test_an_old_copy_from_an_earlier_turn_does_not_count(analyzer):
    """It is written into the transcript every time it happens -- one real
    capture held five copies in 275 lines."""
    stale = f"""✻ Waiting for 1 background agent to finish

● 에이전트가 끝났고, 결과는 이렇습니다.
✻ Crunched for 59s

{SEP}
❯ 
{SEP}
"""
    assert analyzer._detect_working_state(stale) is False


def test_waiting_for_zero_agents_is_not_waiting(analyzer):
    none_left = f"""✻ Waiting for 0 background agents to finish

{SEP}
❯ 
{SEP}
"""
    assert analyzer._detect_working_state(none_left) is False


def test_no_input_box_means_no_answer(analyzer):
    """A capture taken mid-redraw can be missing the bottom of the screen.

    With no box there is no anchor, and no anchor has to mean "this rule says
    nothing" rather than "believe the words".
    """
    torn = "✻ Waiting for 1 background agent to finish\n"
    assert analyzer._waiting_on_background_agent(torn.split("\n")) is False


def test_a_wrapped_line_still_counts(analyzer):
    """A narrow pane breaks it over two rows."""
    wrapped = f"""✻ Waiting for 1 background agent
to finish

{SEP}
❯ 
{SEP}
"""
    assert analyzer._detect_working_state(wrapped) is True

# The dashboard ships its own copy of this detector; the same two screens are
# asserted against it in ctb-dashboard/tests/test_waiting_on_background_agent.py.
# A session that is working on one surface and idle on the other is worse than
# either answer alone.


# --- the anchor has to be the real input box ---------------------------------

def test_a_quoted_prompt_inside_a_draft_is_not_the_input_box(analyzer):
    """The worst failure this rule can have: a finished session reading as
    working, which silences its completion notification.

    Somebody pastes a transcript into the box and does not send it yet. The
    draft holds a `❯` of its own, and a reverse scan for "the last ❯" lands
    inside the box instead of on it -- with the waiting line, also pasted,
    sitting right above it.
    """
    drafted = f"""✻ Worked for 57s · done 3:58 PM
{SEP}
❯ Here is a transcript:
  ✻ Waiting for 1 background agent to finish
  ❯ old request
{SEP}
"""
    assert analyzer._detect_working_state(drafted) is False


def test_a_wrapped_completion_still_ends_the_turn(analyzer):
    """Requiring the duration's unit must not be defeated by a line break.

    A narrow pane splits `✻ Worked for 57s · done 3:58 PM` mid-number, so no
    single row carries `57s`; with a stale `agents:1` still on the bar, the
    session read as working after it had finished.
    """
    wrapped_done = """✻ Worked for 57
s · done 3:58 PM
❯ 
  [OMC#4.13.2] | agents:1
"""
    assert analyzer._detect_working_state(wrapped_done) is False


def test_the_waiting_line_wrapped_mid_word_still_counts(analyzer):
    """tmux breaks at the pane edge, not at a space."""
    mid_word = f"""✻ Waiting for 1 background age
nt to finish
{SEP}
❯ 
{SEP}
"""
    assert analyzer._detect_working_state(mid_word) is True


def test_the_waiting_line_wrapped_over_three_rows_still_counts(analyzer):
    narrow = f"""✻ Waiting for 1 backgro
und agent to fin
ish
{SEP}
❯ 
{SEP}
"""
    assert analyzer._detect_working_state(narrow) is True


# --- both copies of the detector, one answer ---------------------------------

def _dashboard_analyzer():
    """The dashboard ships a SEPARATE COPY of this detector.

    It cannot import the canonical module in its own environment (the
    canonical one pulls in the telegram client), which is why the check lives
    here: this environment can load both. A cross-detector test that always
    skips is not a guarantee, it is a comment.
    """
    import sys
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "ctb-dashboard" / "src"
    if not (src / "ctb_dashboard" / "state_detector.py").is_file():
        pytest.skip("dashboard package not present in this checkout")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from ctb_dashboard.state_detector import SessionStateAnalyzer as Dash
    return Dash()


@pytest.mark.parametrize("name", ["LIVE", "PLAIN", "DRAFTED", "MID_WORD"])
def test_the_dashboard_copy_answers_the_same(analyzer, name):
    """A session that is working on one surface and idle on the other is
    worse than either answer on its own."""
    screens = {
        "LIVE": LIVE,
        "PLAIN": PLAIN,
        "DRAFTED": f"""✻ Worked for 57s · done 3:58 PM
{SEP}
❯ Here is a transcript:
  ✻ Waiting for 1 background agent to finish
  ❯ old request
{SEP}
""",
        "MID_WORD": f"""✻ Waiting for 1 background age
nt to finish
{SEP}
❯ 
{SEP}
""",
    }
    screen = screens[name]
    assert (_dashboard_analyzer()._detect_working_state(screen)
            == analyzer._detect_working_state(screen))


# --- the monitor must not call a working agent a stall ------------------------

def test_a_long_agent_run_is_exempt_from_stall_alerts(monkeypatch):
    """The fix makes a waiting session WORKING, and WORKING for long enough
    is what the stall path is looking for.

    Without the exemption a one-hour agent run starts producing stall alerts
    at the twenty-minute mark: the wrong "완료" notification would have been
    traded for a wrong "멈춤" one, which is not a fix. The exemption already
    existed for OMC's `agents:N`, a format the current HUD no longer prints.
    """
    from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor

    captured = {}

    class _Result:
        returncode = 0
        stdout = LIVE

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(
        "claude_ctb.monitoring.multi_monitor.subprocess.run", fake_run)
    mon = MultiSessionMonitor.__new__(MultiSessionMonitor)   # no config needed
    assert mon._has_active_subagents("claude_gh") is True
    assert "capture-pane" in captured["cmd"]


def test_a_settled_session_is_not_exempt(monkeypatch):
    """The exemption must not swallow a genuine stall."""
    from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor

    class _Result:
        returncode = 0
        stdout = f"""✻ Worked for 57s · done 3:58 PM
{SEP}
❯ 
{SEP}
"""

    monkeypatch.setattr(
        "claude_ctb.monitoring.multi_monitor.subprocess.run",
        lambda *a, **k: _Result())
    mon = MultiSessionMonitor.__new__(MultiSessionMonitor)
    assert mon._has_active_subagents("claude_gh") is False
