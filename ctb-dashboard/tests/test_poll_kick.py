"""A kick after sending input wakes the poller immediately, instead of it
sitting out the rest of POLL_INTERVAL.

Before this, a send landed in tmux and then waited for the poller's own
timer -- up to POLL_INTERVAL (2s) -- before the board reflected it. Now the
send-side invalidates the stale screen cache and kicks the poller, which
runs at a short floor cadence for a few seconds afterward (FAST_WINDOW) so a
burst of keystrokes doesn't all wait for one slow interval, but also doesn't
make the poller spin.
"""

import asyncio
import time

import pytest

import ctb_dashboard.server as _srv
from ctb_dashboard.state_detector import SessionStateAnalyzer


@pytest.fixture(autouse=True)
def _fresh_kick_state(monkeypatch):
    monkeypatch.setattr(_srv, "_poll_kick", None)
    monkeypatch.setattr(_srv, "_fast_until", 0.0)
    monkeypatch.setattr(_srv, "_hold_clear_pending", set())


# --- _next_poll_delay: pure function ---------------------------------------

def test_next_poll_delay_normal_is_poll_interval():
    assert _srv._next_poll_delay(now=100.0, last_start=99.0, fast_until=0.0) == _srv.POLL_INTERVAL


def test_next_poll_delay_fast_floors_from_last_start():
    # last poll started at 100.0, floor is 1.0s after that
    assert _srv._next_poll_delay(now=100.2, last_start=100.0, fast_until=103.0) == pytest.approx(0.8)


def test_next_poll_delay_fast_floor_already_elapsed_is_zero():
    assert _srv._next_poll_delay(now=101.5, last_start=100.0, fast_until=103.0) == 0.0


def test_next_poll_delay_expired_fast_window_falls_back_to_poll_interval():
    # fast_until already in the past -> normal cadence
    assert _srv._next_poll_delay(now=200.0, last_start=199.0, fast_until=150.0) == _srv.POLL_INTERVAL


# --- _kick_poller: sets fast window + wakes event --------------------------

def test_kick_poller_sets_fast_until_and_wakes_event():
    async def run():
        before = _srv._kick_event()
        assert not before.is_set()
        _srv._kick_poller()
        return before.is_set(), _srv._fast_until

    is_set, fast_until = asyncio.run(run())
    assert is_set
    assert fast_until > 0


def test_kick_poller_extends_but_never_shortens_fast_until():
    async def run():
        _srv._kick_poller()
        first = _srv._fast_until
        _srv._fast_until = first + 100.0  # pretend a later kick already pushed it out
        _srv._kick_poller()
        return first, _srv._fast_until

    first, second = asyncio.run(run())
    assert second == pytest.approx(first + 100.0)


# --- _poll_sessions: drains _hold_clear_pending before probing ------------

def test_poll_sessions_drains_hold_clear_pending(monkeypatch):
    monkeypatch.setattr(_srv, "_working_hold", {"claude_x": 123.0, "claude_y": 456.0})
    monkeypatch.setattr(_srv, "_hold_clear_pending", {"claude_x"})
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: [])
    monkeypatch.setattr(_srv, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(_srv, "load_context_by_tmux_session", lambda: {})

    _srv._poll_sessions()

    assert "claude_x" not in _srv._working_hold
    assert _srv._working_hold.get("claude_y") == 456.0
    assert _srv._hold_clear_pending == set()


def test_poll_sessions_pending_clear_added_mid_probe_is_not_lost(monkeypatch):
    """A clear added *while this very poll is already running* -- after its
    drain has finished and moved on to probing -- must not be lost; it has
    to survive to be consumed by the *next* poll instead of silently
    vanishing. get_all_claude_sessions() is the first thing _poll_sessions
    calls after the drain, so adding from inside it stands in for a request
    handler's _kick_poller()/_hold_clear_pending.add() landing mid-probe."""
    monkeypatch.setattr(_srv, "_working_hold", {"claude_x": 1.0})
    monkeypatch.setattr(_srv, "_hold_clear_pending", set())

    added = {"done": False}

    def _sessions_then_add_mid_probe():
        if not added["done"]:
            _srv._hold_clear_pending.add("claude_x")  # arrives after this poll's drain
            added["done"] = True
        return []

    monkeypatch.setattr(_srv, "get_all_claude_sessions", _sessions_then_add_mid_probe)
    monkeypatch.setattr(_srv, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(_srv, "load_context_by_tmux_session", lambda: {})

    _srv._poll_sessions()  # this poll's drain ran before the add -- hold survives
    assert _srv._working_hold.get("claude_x") == 1.0
    assert _srv._hold_clear_pending == {"claude_x"}  # not lost

    _srv._poll_sessions()  # next poll's drain consumes it
    assert "claude_x" not in _srv._working_hold
    assert _srv._hold_clear_pending == set()


# --- SessionStateAnalyzer.invalidate ---------------------------------------

def test_invalidate_clears_both_caches():
    analyzer = SessionStateAnalyzer()
    analyzer._screen_cache["claude_x"] = ("stale screen", object())
    analyzer._state_cache["claude_x"] = ("stale state", object())
    analyzer._screen_cache["claude_y"] = ("other", object())

    analyzer.invalidate("claude_x")

    assert "claude_x" not in analyzer._screen_cache
    assert "claude_x" not in analyzer._state_cache
    assert "claude_y" in analyzer._screen_cache  # untouched


def test_invalidate_is_safe_when_nothing_cached():
    analyzer = SessionStateAnalyzer()
    analyzer.invalidate("claude_never_seen")  # must not raise


def test_invalidate_mid_capture_is_not_undone_by_its_stale_write(monkeypatch):
    """A capture already running when invalidate() lands can still finish
    afterward -- it must not write its now-stale result back into the
    cache, which would silently resurrect what invalidate() just cleared."""
    import ctb_dashboard.state_detector as _sd

    analyzer = SessionStateAnalyzer()
    name = "claude_x"

    class _FakeResult:
        returncode = 0
        stdout = "stale, captured before the send"
        stderr = ""

    def fake_run(*a, **kw):
        # invalidate() lands here -- logically after this capture started,
        # but before it writes its result back.
        analyzer.invalidate(name)
        return _FakeResult()

    monkeypatch.setattr(_sd.subprocess, "run", fake_run)
    content = analyzer.get_screen_content(name, use_cache=False)

    assert content == "stale, captured before the send"  # caller still gets its read
    assert name not in analyzer._screen_cache  # but it must not be cached


def test_invalidate_mid_get_state_is_not_undone_by_its_stale_write(monkeypatch):
    analyzer = SessionStateAnalyzer()
    name = "claude_x"

    def fake_get_screen_content(nm, use_cache=True):
        analyzer.invalidate(name)
        return "no state markers here"

    monkeypatch.setattr(analyzer, "get_screen_content", fake_get_screen_content)
    analyzer.get_state(name, use_cache=True)

    assert name not in analyzer._state_cache


def test_capture_started_after_invalidate_still_caches_normally(monkeypatch):
    """The guard must not block ordinary writes forever -- only a write
    whose capture started before the invalidate. A normal capture that
    starts afterward must land in the cache as usual."""
    import ctb_dashboard.state_detector as _sd

    analyzer = SessionStateAnalyzer()
    name = "claude_x"
    analyzer.invalidate(name)

    class _FakeResult:
        returncode = 0
        stdout = "fresh content"
        stderr = ""

    monkeypatch.setattr(_sd.subprocess, "run", lambda *a, **kw: _FakeResult())
    content = analyzer.get_screen_content(name, use_cache=False)

    assert content == "fresh content"
    assert analyzer._screen_cache[name][0] == "fresh content"


# --- _background_poller loop behavior --------------------------------------

def test_background_poller_kick_runs_next_poll_before_poll_interval(monkeypatch):
    """A kick during the normal wait wakes the poller well inside
    POLL_INTERVAL, not after the full interval elapses."""
    calls = []

    def fake_poll():
        calls.append(0)
        return {"version": 1, "updated_at": 0, "sessions": [], "_hash": "h"}

    monkeypatch.setattr(_srv, "_poll_sessions", fake_poll)
    monkeypatch.setattr(_srv, "POLL_INTERVAL", 2)
    monkeypatch.setattr(_srv, "FAST_FLOOR", 0.05)
    monkeypatch.setattr(_srv, "_cached_state", {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""})
    monkeypatch.setattr(_srv, "_state_rev", 0)
    monkeypatch.setattr(_srv, "_state_changed", None)

    async def run():
        task = asyncio.create_task(_srv._background_poller())
        await asyncio.sleep(0.05)  # first poll lands
        assert len(calls) == 1
        _srv._kick_poller()
        await asyncio.sleep(0.3)  # far less than POLL_INTERVAL=2
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return len(calls)

    n = asyncio.run(run())
    assert n >= 2, "kick should have woken a second poll well before POLL_INTERVAL elapsed"


def test_background_poller_without_kick_waits_full_poll_interval(monkeypatch):
    calls = []

    def fake_poll():
        calls.append(0)
        return {"version": 1, "updated_at": 0, "sessions": [], "_hash": "h"}

    monkeypatch.setattr(_srv, "_poll_sessions", fake_poll)
    monkeypatch.setattr(_srv, "POLL_INTERVAL", 0.3)
    monkeypatch.setattr(_srv, "_cached_state", {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""})
    monkeypatch.setattr(_srv, "_state_rev", 0)
    monkeypatch.setattr(_srv, "_state_changed", None)

    async def run():
        task = asyncio.create_task(_srv._background_poller())
        await asyncio.sleep(0.05)
        assert len(calls) == 1
        await asyncio.sleep(0.1)  # well before the 0.3s interval
        n_early = len(calls)
        await asyncio.sleep(0.35)  # now past it
        n_late = len(calls)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return n_early, n_late

    n_early, n_late = asyncio.run(run())
    assert n_early == 1
    assert n_late >= 2


def _reset_background_poller_state(monkeypatch):
    monkeypatch.setattr(_srv, "_cached_state", {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""})
    monkeypatch.setattr(_srv, "_state_rev", 0)
    monkeypatch.setattr(_srv, "_state_changed", None)


def test_kicked_poll_gaps_respect_floor_and_dont_spin(monkeypatch):
    """Catches two opposite mutations at once: dropping the floor sleep
    (spin -- near-zero gaps, far too many polls) and dropping the floor
    itself (gaps smaller than FAST_FLOOR)."""
    starts = []

    def fake_poll():
        starts.append(time.monotonic())
        return {"version": 1, "updated_at": 0, "sessions": [], "_hash": "h"}

    monkeypatch.setattr(_srv, "_poll_sessions", fake_poll)
    monkeypatch.setattr(_srv, "POLL_INTERVAL", 5.0)  # effectively "never" for this window
    monkeypatch.setattr(_srv, "FAST_WINDOW", 0.5)
    monkeypatch.setattr(_srv, "FAST_FLOOR", 0.05)
    _reset_background_poller_state(monkeypatch)

    async def run():
        task = asyncio.create_task(_srv._background_poller())
        await asyncio.sleep(0.01)
        _srv._kick_poller()
        await asyncio.sleep(0.45)  # stay inside the 0.5s fast window
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    assert len(starts) >= 3, "expected several floor-cadence polls, got too few"
    eps = 0.02
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    for g in gaps:
        assert g >= _srv.FAST_FLOOR - eps, f"gap {g} smaller than the floor: {gaps}"
    # Spin guard: at FAST_FLOOR=0.05s over a 0.45s window, there is no way
    # to have legitimately produced many more than ~0.45/0.05 polls.
    max_possible = int(0.45 / (_srv.FAST_FLOOR - eps)) + 3
    assert len(starts) <= max_possible, f"too many polls, looks like a spin: {starts}"


def test_second_kick_after_fast_window_expired_also_wakes_a_poll_early(monkeypatch):
    """If the kick event is never cleared, every wait after the first kick
    returns instantly regardless of whether a new kick landed, so the loop
    falls back to a plain (non-interruptible) sleep -- a second kick arriving
    after the first fast window has expired would then be silently ignored
    until the full POLL_INTERVAL elapses. Catches a missing kick_event.clear()."""
    starts = []

    def fake_poll():
        starts.append(time.monotonic())
        return {"version": 1, "updated_at": 0, "sessions": [], "_hash": "h"}

    monkeypatch.setattr(_srv, "_poll_sessions", fake_poll)
    monkeypatch.setattr(_srv, "POLL_INTERVAL", 1.0)
    monkeypatch.setattr(_srv, "FAST_WINDOW", 0.1)
    monkeypatch.setattr(_srv, "FAST_FLOOR", 0.05)
    _reset_background_poller_state(monkeypatch)

    async def run():
        task = asyncio.create_task(_srv._background_poller())
        await asyncio.sleep(0.01)
        _srv._kick_poller()               # kick #1
        await asyncio.sleep(0.3)          # let the 0.1s fast window fully expire
        n_before_second_kick = len(starts)
        _srv._kick_poller()               # kick #2, well inside the next POLL_INTERVAL wait
        await asyncio.sleep(0.3)          # much less than POLL_INTERVAL=1.0
        n_after_second_kick = len(starts)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return n_before_second_kick, n_after_second_kick

    n_before, n_after = asyncio.run(run())
    assert n_after > n_before, (
        "a second kick after the fast window expired must still wake an "
        "early poll, well before POLL_INTERVAL elapses"
    )
