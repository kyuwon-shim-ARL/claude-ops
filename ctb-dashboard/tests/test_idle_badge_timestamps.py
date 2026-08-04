"""Idle-age timestamps must survive a dashboard restart.

Field report (2026-08-05): every card's idle badge read ~0 right after a
`systemctl --user restart ctb-dashboard`, so the badge was showing time since
restart rather than time since the session went idle. Measured on the live
service: 69 of 71 sessions carried an identical `updated_at`, exactly the
restart moment, and none survived it.

The persistence itself was never broken -- `_load_timestamps()` reads the file
back correctly. The first poll then threw it away: `prev_state` is read from
`_cached_state`, which is in-memory only, so on a fresh process it is None for
every session, `None != "idle"` counted as a state change, and every timestamp
was rewritten to now.
"""

import time
from unittest.mock import patch

import pytest

from ctb_dashboard import server


@pytest.fixture
def clean_state():
    """Isolate the module-level poll state, restoring whatever was there."""
    saved = (server._prev_session_timestamps, server._cached_state,
             server._last_known_prompt)
    server._prev_session_timestamps = {}
    server._cached_state = {"version": 1, "updated_at": 0, "sessions": [], "_hash": ""}
    server._last_known_prompt = {}
    yield
    (server._prev_session_timestamps, server._cached_state,
     server._last_known_prompt) = saved


def _probe(name, state="idle"):
    """A _probe_session return tuple: (name, state, path, ctx, prompt,
    work_context, pending, working_since, progress, last_reply)."""
    return (name, state, "/tmp/x", 10, "", "", None, None, None, "")


def _poll(sessions, activity, probes, tmpdir=None):
    with patch.object(server, "get_all_claude_sessions", return_value=sessions), \
         patch.object(server, "get_sessions_activity", return_value=activity), \
         patch.object(server, "_probe_session", side_effect=lambda n: probes[n]), \
         patch.object(server, "_TS_PERSIST_PATH", str(tmpdir / "ts.json") if tmpdir else "/dev/null"):
        return server._poll_sessions()


def _entry(result, name):
    return next(s for s in result["sessions"] if s["name"] == name)


def test_restart_keeps_the_persisted_idle_age(clean_state, tmp_path):
    """A fresh process with persisted timestamps must not reset them.

    This is the reported bug: the badge restarted from zero on every deploy.
    """
    name = "claude_demo"
    went_idle = time.time() - 3600  # idle for an hour before the restart
    server._prev_session_timestamps = {name: went_idle}
    # _cached_state is empty exactly as it is on a fresh process.

    result = _poll([name], {name: went_idle}, {name: _probe(name, "idle")}, tmp_path)

    assert _entry(result, name)["updated_at"] == pytest.approx(went_idle, abs=1), (
        "the restart wiped the persisted idle age"
    )


def test_a_real_state_change_still_moves_the_timestamp(clean_state, tmp_path):
    """Keeping persisted values must not freeze genuine transitions."""
    name = "claude_demo"
    started = time.time() - 3600
    server._prev_session_timestamps = {name: started}
    server._cached_state = {"sessions": [{"name": name, "state": "working"}]}

    result = _poll([name], {name: time.time()}, {name: _probe(name, "idle")}, tmp_path)

    assert _entry(result, name)["updated_at"] == pytest.approx(time.time(), abs=5), (
        "working -> idle must restamp"
    )


def test_unchanged_state_does_not_restamp(clean_state, tmp_path):
    name = "claude_demo"
    started = time.time() - 3600
    server._prev_session_timestamps = {name: started}
    server._cached_state = {"sessions": [{"name": name, "state": "idle"}]}

    result = _poll([name], {name: started}, {name: _probe(name, "idle")}, tmp_path)

    assert _entry(result, name)["updated_at"] == pytest.approx(started, abs=1)


def test_first_sight_of_a_session_uses_its_pane_activity(clean_state, tmp_path):
    """A session with no persisted entry predates us; tmux knows better than now.

    Sessions that existed before the dashboard ever ran would otherwise all
    claim to have changed state at startup.
    """
    name = "claude_new"
    last_active = time.time() - 1800
    result = _poll([name], {name: last_active}, {name: _probe(name, "idle")}, tmp_path)

    assert _entry(result, name)["updated_at"] == pytest.approx(last_active, abs=1), (
        "should fall back to tmux session_activity, not the poll time"
    )


def test_first_sight_without_activity_data_falls_back_to_now(clean_state, tmp_path):
    """No tmux activity for the session — `now` is all that is left."""
    name = "claude_new"
    result = _poll([name], {}, {name: _probe(name, "idle")}, tmp_path)

    assert _entry(result, name)["updated_at"] == pytest.approx(time.time(), abs=5)


def test_timestamps_are_written_for_the_next_process(clean_state, tmp_path):
    name = "claude_demo"
    went_idle = time.time() - 3600
    server._prev_session_timestamps = {name: went_idle}

    _poll([name], {name: went_idle}, {name: _probe(name, "idle")}, tmp_path)

    import json
    saved = json.loads((tmp_path / "ts.json").read_text())
    assert saved[name] == pytest.approx(went_idle, abs=1)
