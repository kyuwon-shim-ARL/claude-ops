# -*- coding: utf-8 -*-
"""Claude Code 2.1.258+ moved the agent-status line below the input box.

The bug: instead of printing "Waiting for N background agents to finish"
above the ❯ prompt (see test_waiting_on_background_agent.py), the client now
prints a roster BELOW the prompt and HUD -- one row per agent, ending in an
elapsed time + token count for a running agent, or the word "idle" for a
finished one. The existing detector only looked above the input box, so a
running subagent handoff read as IDLE.
"""

import pytest

from ctb_dashboard.state_detector import SessionStateAnalyzer

SEP = "─" * 40


def _screen(roster_line, extra_rows=""):
    return f"""{SEP}
❯
{SEP}
  branch:main | !4 ?6 ⇡16
  [OMC#5.1.0L] | Model: Fable 5.1 | 5h:[#-------]16%(1h52m) ... | ctx:[##--------]20% | 🔧28 🤖1 ⚡1
  ⏵⏵ bypass permissions on · 1 shell · ← 9 agents
  ● main
  {roster_line}
{extra_rows}"""


RUNNING = _screen(
    "◯ ctx-gauge-impl  Implement the plan at /home/kyuwon/projects/claude...                                   5m 14s · ↓ 175.1k tokens"
)

WRAPPED_RUNNING = _screen(
    "◯ ctx-gauge-impl  Implement the plan at /home/kyuwon/projects/claude...                                   3m 50s ·",
    extra_rows="  ↓ 175.1k tokens\n",
)

THREE_ROW_WRAP = _screen(
    "◯ ctx-gauge-impl  Implement the plan at",
    extra_rows="  5m 14s ·\n  ↓ 175.1k tokens\n",
)

# The elapsed+token tail must be the terminal status of the row: trailing
# text after the metrics (a wrapped description, not a real running row)
# must not match.
TRAILING_TEXT_AFTER_METRICS = _screen(
    "◯ reviewer  Explain 42s · ↓ 1.2M tokens format  idle"
)

HOURS_MINUTES_RUNNING = _screen(
    "◯ ctx-gauge-impl  Implement the plan                                                                        1h 2m · ↓ 1.2M tokens"
)

SECONDS_ONLY_RUNNING = _screen(
    "◯ ctx-gauge-impl  Implement the plan                                                                        42s · ↓ 387 tokens"
)

# A running-looking row PASTED INSIDE the draft (between the ❯ row and the
# rule that closes the input box) must not count -- only the real roster
# below the closing rule is live.
PASTED_INSIDE_DRAFT = f"""{SEP}
❯ here's the roster I saw earlier:
  ◯ worker  task   5m 14s · ↓ 175.1k tokens
{SEP}
  branch:main | !4 ?6 ⇡16
  ● main
  ◯ ctx-gauge-impl  Implement the plan                                        idle
"""

LONG_ROSTER_RUNNING_FIRST = _screen(
    "◯ ctx-gauge-impl  Implement the plan at /home/kyuwon/projects/claude...                                   5m 14s · ↓ 175.1k tokens",
    extra_rows="\n".join(
        f"  ◯ worker-{i}  task   idle" for i in range(22)
    ) + "\n",
)

FINISHED = _screen(
    "◯ ctx-gauge-impl  Implement the plan at /home/kyuwon/projects/claude...                                   idle"
)

ROSTER_HEADER_ONLY = f"""{SEP}
❯
{SEP}
  branch:main | !4 ?6 ⇡16
  [OMC#5.1.0L] | Model: Fable 5.1 | ctx:[##--------]20% | 🔧28 🤖1 ⚡1
  ⏵⏵ bypass permissions on · 1 shell · ← 9 agents
  ● main
"""

FOOTER_ONLY = f"""{SEP}
❯
{SEP}
  ⏵⏵ bypass permissions on · 1 shell · ← 9 agents
"""

PASTED_ABOVE_PROMPT = f"""◯ ctx-gauge-impl  Implement the plan ...                                   5m 14s · ↓ 175.1k tokens
{SEP}
❯
{SEP}
  ⏵⏵ bypass permissions on · 1 shell · ← 9 agents
"""


@pytest.fixture
def analyzer():
    return SessionStateAnalyzer()


def test_running_agent_row_is_working(analyzer):
    assert analyzer._detect_working_state(RUNNING) is True


def test_wrapped_running_agent_row_is_working(analyzer):
    assert analyzer._detect_working_state(WRAPPED_RUNNING) is True


def test_finished_agent_row_is_not_working(analyzer):
    assert analyzer._agent_roster_running(FINISHED.split('\n')) is False


def test_roster_header_with_only_main_is_not_working(analyzer):
    assert analyzer._agent_roster_running(ROSTER_HEADER_ONLY.split('\n')) is False


def test_cumulative_agent_footer_alone_is_not_working(analyzer):
    assert analyzer._agent_roster_running(FOOTER_ONLY.split('\n')) is False


def test_a_running_row_pasted_above_the_prompt_does_not_count(analyzer):
    assert analyzer._agent_roster_running(PASTED_ABOVE_PROMPT.split('\n')) is False


def test_three_row_wrap_is_working(analyzer):
    assert analyzer._detect_working_state(THREE_ROW_WRAP) is True


def test_trailing_text_after_metrics_does_not_count(analyzer):
    assert analyzer._agent_roster_running(TRAILING_TEXT_AFTER_METRICS.split('\n')) is False


def test_hours_and_minutes_elapsed_is_working(analyzer):
    assert analyzer._detect_working_state(HOURS_MINUTES_RUNNING) is True


def test_seconds_only_elapsed_is_working(analyzer):
    assert analyzer._detect_working_state(SECONDS_ONLY_RUNNING) is True


def test_a_running_row_pasted_inside_the_draft_does_not_count(analyzer):
    # Scoped to our function directly: a pre-existing, unrelated structural
    # pattern (`[↓↑] [\d.,]+k? tokens`) also scans the whole filtered screen
    # and independently flags this fixture as WORKING regardless of
    # input-box position -- that is a separate bug outside this function's
    # scope, tracked separately rather than fixed here.
    assert analyzer._agent_roster_running(PASTED_INSIDE_DRAFT.split('\n')) is False


def test_running_row_beyond_the_25_line_window_is_still_found(analyzer):
    assert analyzer._detect_working_state(LONG_ROSTER_RUNNING_FIRST) is True
