"""
Notification contract: the user is contacted only when their input is genuinely
needed, or when work has actually finished.

Evidence that motivated these tests (logs/multi_monitor.log, 2026-09-13..15):
54% of notifications (37/68) were originated by screen-text scraping
(`task_completion_detector`) with no state transition behind them — e.g. seven idle
sessions firing "Test Execution Finished" within 16 minutes because their panes still
displayed old pytest output.

These tests assert the boolean decision of should_send_completion_notification, not the
presence of any string.
"""

import time
from unittest.mock import patch

from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
from claude_ctb.utils.session_state import SessionState


class TestNotificationNoise:
    def setup_method(self):
        self.monitor = MultiSessionMonitor()
        self.session = "test_session"
        self.monitor.notification_sent[self.session] = False
        self.monitor.last_notification_time[self.session] = 0
        # Screen has been still for a long time: satisfies the stability guard.
        self.monitor.last_screen_change_time[self.session] = time.time() - 600

    def _decide(self, previous, current, screen):
        self.monitor.last_state[self.session] = previous
        with patch.object(self.monitor, "get_session_state", return_value=current), \
             patch.object(self.monitor.state_analyzer, "get_current_screen_only",
                          return_value=screen):
            should_notify, _ = self.monitor.should_send_completion_notification(self.session)
        return should_notify

    # --- unwanted: no state transition, screen text only -------------------

    def test_idle_session_showing_stale_traceback_does_not_notify(self):
        """An idle session whose pane still shows an old traceback is not news."""
        screen = "  File \"x.py\", line 3\nTraceback (most recent call last):\nValueError\n"
        assert self._decide(SessionState.IDLE, SessionState.IDLE, screen) is False

    def test_idle_session_showing_stale_test_summary_does_not_notify(self):
        """The dominant observed false positive: leftover pytest output on an idle pane."""
        screen = "All tests passed\n42 passed in 3.10s\n"
        assert self._decide(SessionState.IDLE, SessionState.IDLE, screen) is False

    def test_working_session_does_not_notify_mid_turn_on_error_text(self):
        """Still working: the user's intervention is not needed yet."""
        screen = "Error: could not resolve host\nretrying...\n"
        assert self._decide(SessionState.WORKING, SessionState.WORKING, screen) is False

    # --- wanted -----------------------------------------------------------

    def test_work_actually_finished_notifies(self):
        screen = "Done. Anything else?\n"
        assert self._decide(SessionState.WORKING, SessionState.IDLE, screen) is True

    def test_finished_work_still_notifies_when_screen_has_test_output(self):
        """Demoting the detector must not silence a genuine completion."""
        screen = "All tests passed\n42 passed in 3.10s\n"
        assert self._decide(SessionState.WORKING, SessionState.IDLE, screen) is True

    def test_waiting_for_input_notifies(self):
        screen = "Do you want to make this edit?\n"
        assert self._decide(SessionState.IDLE, SessionState.WAITING_INPUT, screen) is True


class TestNotificationSequences:
    """Temporal cases. A single call cannot expose these; each drives several polls."""

    def setup_method(self):
        self.monitor = MultiSessionMonitor()
        self.session = "seq_session"
        self.monitor.notification_sent[self.session] = False
        self.monitor.last_notification_time[self.session] = 0

    def _poll(self, state, screen, screen_settled_for):
        """One monitor poll. screen_settled_for = seconds since the pane last changed."""
        self.monitor.last_screen_change_time[self.session] = time.time() - screen_settled_for
        with patch.object(self.monitor, "get_session_state", return_value=state), \
             patch.object(self.monitor.state_analyzer, "get_current_screen_only",
                          return_value=screen):
            should_notify, _ = self.monitor.should_send_completion_notification(self.session)
        return should_notify

    def test_completion_suppressed_for_instability_is_delivered_once_later(self):
        """
        The transition is consumed on the poll that sees it. If the stability guard
        suppresses that poll and nothing retains the completion, it is lost forever.
        """
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        # Work ends, but the pane is still repainting: suppressed, not discarded.
        assert self._poll(SessionState.IDLE, "done\n", 0) is False
        # Pane has settled: the held completion is delivered.
        assert self._poll(SessionState.IDLE, "done\n", 60) is True
        # And only once.
        assert self._poll(SessionState.IDLE, "done\n", 60) is False

    def test_resumed_work_does_not_notify_while_still_working(self):
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False   # held
        assert self._poll(SessionState.WORKING, "working again...", 0) is False
        # Still working: a settled pane is not a completion.
        assert self._poll(SessionState.WORKING, "working again...", 60) is False

    def test_heuristic_fallback_fires_only_with_observed_work(self):
        """
        The heuristic branches, isolated from the transition branch. Every poll here is
        IDLE -> IDLE, so previous_state is never WORKING and branch 1 cannot be what fires.
        """
        screen = "All tests passed\n42 passed in 3.10s\n"
        # No work ever observed: stale output is not news.
        assert self._poll(SessionState.IDLE, screen, 60) is False
        # Work is observed, then the session settles back to idle *without* the poll that
        # sees the ending being a WORKING -> terminal transition.
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, screen, 60) is True      # transition branch
        # Episode reported. The same stale screen must not fire again without new work,
        # even with the latch and cooldown cleared — this is the heuristic branches alone.
        self.monitor.notification_sent[self.session] = False
        self.monitor.last_notification_time[self.session] = 0
        assert self._poll(SessionState.IDLE, screen, 60) is False
        assert self._poll(SessionState.IDLE, screen, 60) is False

    def test_held_completion_does_not_shadow_a_request_for_input(self):
        """
        A held completion must not swallow the one notification the user cares most about.
        The pane keeps repainting (a spinner, a timer), so stability never arrives.
        """
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False          # hold created
        assert self._poll(SessionState.WAITING_INPUT, "Approve? 1. Yes", 0) is True

    def test_hold_is_dropped_when_work_resumes_and_ends_via_scheduled(self):
        """
        Regression: with the hold left uncancelled, the final poll released a completion
        belonging to the *earlier*, superseded work episode. previous_state is SCHEDULED at
        that point, so the transition branch does not cover it.
        """
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False          # hold created
        assert self._poll(SessionState.WORKING, "working again...", 0) is False
        assert self._poll(SessionState.SCHEDULED, "scheduled...", 0) is False
        assert self._poll(SessionState.IDLE, "plain output\n", 60) is False

    def test_session_reset_discards_work_evidence_and_holds(self):
        """A recreated/reconnected session must not inherit the previous incarnation's state."""
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False          # hold created
        # What the reconnect and startup paths do to a session's tracking:
        self.monitor._pending_completion.pop(self.session, None)
        self.monitor._work_seen.pop(self.session, None)
        self.monitor.notification_sent[self.session] = False
        self.monitor.last_state[self.session] = SessionState.UNKNOWN
        assert self._poll(SessionState.IDLE, "plain output\n", 60) is False

    def test_hold_is_not_released_during_automatic_overload_retry(self):
        """
        API 529 backoff: the monitor is retrying by itself. Nothing finished and nothing is
        being asked of the user, so a held completion must not be released here.
        """
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False          # hold created
        assert self._poll(SessionState.OVERLOADED, "API Error: 529 overloaded", 0) is False
        assert self._poll(SessionState.OVERLOADED, "API Error: 529 overloaded", 60) is False
        # Once it really settles into a terminal state, the hold is delivered.
        assert self._poll(SessionState.IDLE, "done\n", 60) is True

    def test_hold_is_not_released_on_unknown_state(self):
        """UNKNOWN means the detector could not tell; a guess is not a completion."""
        assert self._poll(SessionState.WORKING, "working...", 0) is False
        assert self._poll(SessionState.IDLE, "done\n", 0) is False          # hold created
        assert self._poll(SessionState.UNKNOWN, "", 60) is False

    def test_stale_error_screen_does_not_refire_across_cooldown_rearm(self):
        """
        The observed signature: claude_generative-antibiotic-pa sent "Error Detected" three
        times in thirteen minutes — 8-minute gaps, i.e. once per cooldown re-arm — with the
        same unresolved screen. The re-arm itself is not the defect; what made it visible was
        a branch that could fire from screen text alone. With that branch gone, re-arming as
        often as you like produces nothing until real work happens and ends.
        """
        screen = "Traceback (most recent call last):\nValueError: boom\n"
        for _ in range(3):
            # Simulate the cooldown window reopening and the dedup latch re-arming.
            self.monitor.notification_sent[self.session] = False
            self.monitor.last_notification_time[self.session] = 0
            assert self._poll(SessionState.IDLE, screen, 600) is False


class TestCompletionInsideCooldownIsHeldNotLost:
    """
    GitHub #25, mechanism A: a completion that happens within NOTIFICATION_COOLDOWN
    (180s) of the previous notification used to be lost forever, even if the session
    then stayed idle for hours. previous_state is consumed (set to current_state) at
    the top of should_send_completion_notification, so once the notification_sent /
    cooldown guards returned early without recording a hold, the next poll could never
    see a WORKING -> terminal transition for that episode again.

    These tests drive a real wall-clock timeline via patched time.time(), mirroring
    the actual poll cadence rather than only the screen-stability deltas used above.
    """

    def setup_method(self):
        self.monitor = MultiSessionMonitor()
        self.session = "cooldown_session"
        self.monitor.notification_sent[self.session] = False
        self.monitor.last_notification_time[self.session] = 0
        self.monitor.last_state[self.session] = SessionState.UNKNOWN
        self.t0 = 1_000_000.0

    def _poll_at(self, offset, state, screen, settle=600):
        """One poll at wall-clock self.t0 + offset. settle = seconds the pane has
        been stable for (independent of the wall clock used for cooldown math)."""
        now = self.t0 + offset
        self.monitor.last_screen_change_time[self.session] = now - settle
        with patch("claude_ctb.monitoring.multi_monitor.time.time", return_value=now), \
             patch.object(self.monitor, "get_session_state", return_value=state), \
             patch.object(self.monitor.state_analyzer, "get_current_screen_only",
                          return_value=screen), \
             patch.object(self.monitor.state_analyzer, "detect_quiet_completion",
                          return_value=False), \
             patch.object(self.monitor.state_analyzer, "has_completion_indicators",
                          return_value=False):
            should_notify, _ = self.monitor.should_send_completion_notification(self.session)
        return should_notify

    def test_completion_inside_cooldown_is_delivered_once_after_cooldown_if_still_idle(self):
        """W(t0) -> I(t30)=True -> W(t80) -> I(t140)=False (inside cooldown, held) ->
        I(t215, screen stable)=True (cooldown elapsed, hold released) -> I(t230)=False."""
        assert self._poll_at(0, SessionState.WORKING, "working...") is False
        assert self._poll_at(30, SessionState.IDLE, "done\n") is True
        assert self._poll_at(80, SessionState.WORKING, "working again...") is False
        assert self._poll_at(140, SessionState.IDLE, "done\n") is False
        assert self.session in self.monitor._pending_completion
        assert self._poll_at(215, SessionState.IDLE, "done\n") is True
        assert self._poll_at(230, SessionState.IDLE, "done\n") is False

    def test_hold_is_not_released_if_session_goes_back_to_working_before_cooldown_ends(self):
        """Regression guard: if WORKING resumes before the cooldown elapses, the
        stale hold must not fire later out of nowhere — only the NEXT real
        completion should notify."""
        assert self._poll_at(0, SessionState.WORKING, "working...") is False
        assert self._poll_at(30, SessionState.IDLE, "done\n") is True
        assert self._poll_at(80, SessionState.WORKING, "working again...") is False
        assert self._poll_at(140, SessionState.IDLE, "done\n") is False
        # Session goes back to WORKING before the cooldown (t30+180=t210) ends.
        assert self._poll_at(150, SessionState.WORKING, "working yet again...") is False
        # The stale hold must not fire while WORKING, nor right after.
        assert self._poll_at(215, SessionState.WORKING, "working yet again...") is False
        assert self._poll_at(230, SessionState.WORKING, "still working...") is False
        # Only the next real completion notifies.
        assert self._poll_at(260, SessionState.IDLE, "done\n") is True

    def test_micro_gap_guard_still_holds(self):
        """Mechanism B is out of scope: a brief, unstable IDLE followed by a
        return to WORKING within seconds must still not notify."""
        assert self._poll_at(0, SessionState.WORKING, "working...") is False
        assert self._poll_at(3, SessionState.IDLE, "done\n", settle=0) is False
        assert self._poll_at(6, SessionState.WORKING, "working...", settle=0) is False


class TestContextLimitRestartLoop:
    """
    GitHub #25 follow-up (adversarial review MAJOR finding): _auto_restart_session
    force-sets last_state=WORKING and notification_sent=True right after restarting a
    session on CONTEXT_LIMIT (multi_monitor.py ~L778-781). If the next poll still shows
    CONTEXT_LIMIT (e.g. a stale screen after a /exit that did not take), branch 0 is
    blocked by the 60s restart_cooldown, but the always-re-arm fix for #25 mechanism A
    let this fake WORKING->CONTEXT_LIMIT read as `is_completion_transition`, so a hold
    got recorded; once the cooldown re-arm fallback cleared notification_sent, branch 3
    (which did not exclude CONTEXT_LIMIT) released that hold, should_notify=True, and
    send_completion_notification (seeing last_state==CONTEXT_LIMIT) called
    send_context_limit_notification -> auto-restart again, looping roughly every
    notification_cooldown seconds.
    """

    def setup_method(self):
        self.monitor = MultiSessionMonitor()
        self.session = "ctx_limit_session"
        self.t0 = 1_000_000.0

    def _poll_at(self, offset, state, screen="Context limit reached", settle=600):
        now = self.t0 + offset
        self.monitor.last_screen_change_time[self.session] = now - settle
        with patch("claude_ctb.monitoring.multi_monitor.time.time", return_value=now), \
             patch.object(self.monitor, "get_session_state", return_value=state), \
             patch.object(self.monitor.state_analyzer, "get_current_screen_only",
                          return_value=screen), \
             patch.object(self.monitor.state_analyzer, "detect_quiet_completion",
                          return_value=False), \
             patch.object(self.monitor.state_analyzer, "has_completion_indicators",
                          return_value=False):
            should_notify, _ = self.monitor.should_send_completion_notification(self.session)
        return should_notify

    def _simulate_auto_restart(self, restart_offset):
        """What _auto_restart_session does to monitor state after restarting."""
        self.monitor.last_state[self.session] = SessionState.WORKING
        self.monitor.notification_sent[self.session] = True
        self.monitor._context_limit_restart_time[self.session] = self.t0 + restart_offset

    def test_residual_context_limit_after_restart_does_not_loop(self):
        """Screen still shows CONTEXT_LIMIT after the restart (stale /exit): no
        notification, and no second restart, across several minutes of polling."""
        # First real detection and restart.
        assert self._poll_at(0, SessionState.WORKING, "working...") is False
        assert self._poll_at(10, SessionState.CONTEXT_LIMIT) is True
        self._simulate_auto_restart(restart_offset=20)
        # Screen is still CONTEXT_LIMIT (restart's /exit didn't take). Poll for 400s.
        fired = [
            offset for offset in range(23, 400, 3)
            if self._poll_at(offset, SessionState.CONTEXT_LIMIT)
        ]
        assert fired == [], f"context-limit loop fired at offsets {fired}"
        # last_state is CONTEXT_LIMIT throughout -> branch 0 cannot see a fresh
        # transition into CONTEXT_LIMIT, so a second restart cannot be triggered.
        assert self.monitor.last_state[self.session] == SessionState.CONTEXT_LIMIT

    def test_auto_restart_then_idle_does_not_fire_deferred_work_completed(self):
        """After a successful restart (handoff never actually starts new work and
        the session settles into IDLE), no stale 'Work completed (deferred -> idle)'
        notification should fire — that hold belongs to the already-handled
        context-limit episode, not a new completion."""
        assert self._poll_at(0, SessionState.WORKING, "working...") is False
        assert self._poll_at(10, SessionState.CONTEXT_LIMIT) is True
        self._simulate_auto_restart(restart_offset=20)
        fired = [
            offset for offset in range(23, 400, 3)
            if self._poll_at(offset, SessionState.IDLE, screen="done\n")
        ]
        assert fired == [], f"deferred 'Work completed' fired at offsets {fired}"

