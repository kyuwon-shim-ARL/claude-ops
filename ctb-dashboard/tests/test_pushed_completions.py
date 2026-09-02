"""Remembering which completions were already pushed, across a restart.

The record used to live only in memory, so every restart -- a deploy, a crash,
a config change -- emptied it, and the next poll pushed again for work that had
finished hours earlier. A morning of restarts arrived on the phone as a burst
of duplicates.
"""

import json
import os

import pytest

import ctb_dashboard.server as _srv


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(_srv, "_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(_srv, "_PUSHED_PATH", str(tmp_path / "pushed-completions.json"))
    _srv._pushed_completions.clear()
    yield tmp_path
    _srv._pushed_completions.clear()


def _push(monkeypatch, sessions, pinned=("claude_demo",)):
    sent = []
    monkeypatch.setattr(_srv, "pinned_session_names", lambda: set(pinned))
    monkeypatch.setattr(_srv.push, "notify",
                        lambda name, body, title=None: sent.append(name) or 1)
    _srv._push_completions(sessions)
    return sent


ENTRY = {"name": "claude_demo", "completed_at": 1000.0}


def test_a_completion_is_pushed_once(state, monkeypatch):
    assert _push(monkeypatch, [ENTRY]) == ["claude_demo"]
    assert _push(monkeypatch, [ENTRY]) == []


def test_the_record_survives_a_restart(state, monkeypatch):
    _push(monkeypatch, [ENTRY])
    # A restart: in-memory state gone, the file is all there is.
    _srv._pushed_completions.clear()
    _srv._pushed_completions.update(_srv._load_pushed_completions())
    assert _push(monkeypatch, [ENTRY]) == [], "pushed again for work already reported"


def test_the_next_completion_of_the_same_session_still_pushes(state, monkeypatch):
    _push(monkeypatch, [ENTRY])
    later = {"name": "claude_demo", "completed_at": 2000.0}
    assert _push(monkeypatch, [later]) == ["claude_demo"]


def test_the_file_is_read_when_the_module_starts(tmp_path):
    """The restart test above simulates the load; this pins that it is wired.

    Run in a fresh interpreter, because a module-level initialiser cannot be
    re-run inside this one -- and that initialiser is the whole mechanism.
    """
    import json as _json
    import subprocess
    import sys

    (tmp_path / "pushed-completions.json").write_text(_json.dumps({"claude_x": 42.0}))
    out = subprocess.run(
        [sys.executable, "-c",
         "import ctb_dashboard.server as s; print(s._pushed_completions['claude_x'])"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "CTB_STATE_DIR": str(tmp_path)},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "42.0"


def test_an_unreadable_record_is_not_fatal(state):
    (state / "pushed-completions.json").write_text("{ this is not json")
    assert _srv._load_pushed_completions() == {}


def test_a_record_of_the_wrong_shape_is_discarded(state):
    (state / "pushed-completions.json").write_text(json.dumps({"a": "not-a-time", "b": 5}))
    assert _srv._load_pushed_completions() == {"b": 5}


def test_an_unpinned_session_is_never_pushed(state, monkeypatch):
    """The gate the console's 🔕 badge exists to explain."""
    assert _push(monkeypatch, [ENTRY], pinned=("claude_other",)) == []
