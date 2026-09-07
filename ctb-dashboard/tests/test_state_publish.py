"""The stream wakes the moment a poll lands, instead of checking every 3s.

The poller and the SSE generator used to run on two independent 3s timers,
so a change could sit in the cache for up to a full extra interval before any
browser heard of it. Now a poll *publishes*: it bumps a revision and wakes
every waiting stream at once. A stream that was busy sending when several
polls landed sees the newest snapshot the moment it comes back, without
waiting for yet another poll. Streams also send a heartbeat snapshot every
30s even when the hash is unchanged, which bounds how stale the unhashed
fields (tmux activity) can get on a quiet board.
"""

import asyncio
import inspect

import pytest

import ctb_dashboard.server as _srv


def _snap(h, **extra):
    return {"version": 1, "updated_at": 0, "sessions": [], "_hash": h, **extra}


async def _next(gen, timeout=1.0):
    return await asyncio.wait_for(gen.__anext__(), timeout)


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(_srv, "_cached_state", _snap(""))
    monkeypatch.setattr(_srv, "_state_rev", 0)
    monkeypatch.setattr(_srv, "_state_changed", None)


def test_publish_stamps_when_and_how_long():
    async def run():
        await _srv._publish_state(_snap("a"), poll_ms=417)
        return _srv._cached_state

    snap = asyncio.run(run())
    assert snap["poll_ms"] == 417
    assert snap["published_at"] > 0
    assert _srv._state_rev == 1


def test_two_waiting_streams_both_wake_on_one_publish():
    async def run():
        g1 = _srv._session_event_generator()
        g2 = _srv._session_event_generator()
        t1 = asyncio.create_task(_next(g1))
        t2 = asyncio.create_task(_next(g2))
        await asyncio.sleep(0.05)
        assert not t1.done() and not t2.done()
        await _srv._publish_state(_snap("a"), poll_ms=1)
        e1, e2 = await asyncio.gather(t1, t2)
        return e1, e2

    e1, e2 = asyncio.run(run())
    assert e1["event"] == "sessions" and e2["event"] == "sessions"
    assert '"_hash": "a"' in e1["data"] and '"_hash": "a"' in e2["data"]


def test_first_event_is_immediate_when_state_already_exists():
    async def run():
        await _srv._publish_state(_snap("a"), poll_ms=1)
        gen = _srv._session_event_generator()
        return await _next(gen, timeout=0.2)

    assert '"_hash": "a"' in asyncio.run(run())["data"]


def test_unchanged_hash_does_not_emit():
    async def run():
        await _srv._publish_state(_snap("a"), poll_ms=1)
        gen = _srv._session_event_generator()
        await _next(gen)
        await _srv._publish_state(_snap("a"), poll_ms=1)   # same content, new poll
        with pytest.raises(asyncio.TimeoutError):
            await _next(gen, timeout=0.2)

    asyncio.run(run())


def test_stream_busy_during_several_publishes_gets_newest_at_once():
    """Codex's interleaving case: the consumer is away at `yield` while three
    polls land. On return it must deliver the newest snapshot immediately,
    not wait for a fourth poll."""
    async def run():
        await _srv._publish_state(_snap("a"), poll_ms=1)
        gen = _srv._session_event_generator()
        await _next(gen)                         # now parked at yield
        for h in ("b", "c", "d"):
            await _srv._publish_state(_snap(h), poll_ms=1)
        ev = await _next(gen, timeout=0.2)
        return ev

    assert '"_hash": "d"' in asyncio.run(run())["data"]


def test_heartbeat_resends_after_interval_without_change():
    clock = {"t": 1000.0}

    async def run():
        await _srv._publish_state(_snap("a"), poll_ms=1)
        gen = _srv._session_event_generator(clock=lambda: clock["t"], heartbeat=30.0)
        await _next(gen)
        clock["t"] += 31.0                       # nothing published, clock moved on
        ev = await _next(gen, timeout=0.5)
        return ev

    assert '"_hash": "a"' in asyncio.run(run())["data"]


def test_cancelled_stream_leaves_others_working():
    async def run():
        g1 = _srv._session_event_generator()
        g2 = _srv._session_event_generator()
        t1 = asyncio.create_task(_next(g1))
        t2 = asyncio.create_task(_next(g2))
        await asyncio.sleep(0.05)
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
        await _srv._publish_state(_snap("a"), poll_ms=1)
        return await t2

    assert '"_hash": "a"' in asyncio.run(run())["data"]


def test_hash_covers_every_field_the_cards_paint():
    """progress, last_reply, pending_count and working_since are painted on
    the card but used to be left out of the hash, so those updates sat
    invisible until something else changed."""
    base = dict(name="claude_x", state="working", completed_at=None, context_percent=10,
                last_prompt="p", work_context="w", recap="r", progress=[1, 3],
                last_reply="", pending_count=2, working_since=5.0, last_activity=100.0)
    h0 = _srv._content_hash([dict(base)])
    for field, value in [("progress", [2, 3]), ("last_reply", "done"),
                         ("pending_count", 0), ("working_since", 9.0)]:
        assert _srv._content_hash([{**base, field: value}]) != h0, field
    # tmux activity ticks every poll; it must not turn every poll into a push
    assert _srv._content_hash([{**base, "last_activity": 200.0}]) == h0


def test_session_path_lookup_is_bounded():
    import ctb_dashboard.sessions as sess
    src = inspect.getsource(sess.get_session_path)
    assert "timeout=" in src
