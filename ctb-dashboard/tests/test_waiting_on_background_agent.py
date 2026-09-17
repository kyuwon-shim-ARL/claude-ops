# -*- coding: utf-8 -*-
"""The dashboard's copy of the detector answers the same as the canonical one.

The bug: a session waiting on a background agent read as IDLE, on the board
and in the monitor alike. The whole story, and the rest of the cases, live in
the canonical suite at tests/test_waiting_on_background_agent.py -- this file
exists because ctb_dashboard.state_detector is a SEPARATE COPY of the
detector, and a fix that lands in only one of them is how the two surfaces end
up disagreeing about what a session is doing.

The two screens are duplicated rather than imported: the suites run in
different environments and neither can import the other's tests. They must be
kept in step by hand, which is the cost of the copy.
"""

import pytest

from ctb_dashboard.state_detector import SessionStateAnalyzer

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

PLAIN = f"""● 이제 마무리까지 계속 갑니다.

✻ Waiting for 2 background agents to finish

{SEP}
❯ 
{SEP}
"""

PASTED = f"""❯ Here is the transcript:
  ✻ Waiting for 1 background agent to finish
● That was an old transcript.
{SEP}
❯ 
{SEP}
  [OMC#5.1.0L] | Model: Opus 5
"""


@pytest.fixture
def analyzer():
    return SessionStateAnalyzer()


def test_waiting_on_an_agent_is_working(analyzer):
    assert analyzer._detect_working_state(LIVE) is True


def test_it_does_not_need_the_omc_status_bar(analyzer):
    assert analyzer._detect_working_state(PLAIN) is True


def test_a_pasted_transcript_does_not_make_an_idle_session_work(analyzer):
    assert analyzer._detect_working_state(PASTED) is False


def test_the_waiting_line_is_not_a_completion():
    import re
    past = re.compile(
        rf'[{SessionStateAnalyzer._TOOL_GLYPHS}] \w+ for {SessionStateAnalyzer._DURATION_RE}')
    assert not past.search("✻ Waiting for 1 background agent to finish")
    assert past.search("✻ Crunched for 59s")

# The cross-detector agreement check lives in the canonical suite
# (tests/test_waiting_on_background_agent.py): only that environment can
# import both copies, because this one cannot load the canonical module.
