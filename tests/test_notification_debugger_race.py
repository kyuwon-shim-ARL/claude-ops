"""One debugger, ninety monitor threads.

get_debugger() hands the same instance to every per-session monitor thread.
Each of them mutates the debugger's dicts and then serialises all of them to
disk, and a thread adding a session while another was part-way through
json.dump raised "dictionary changed size during iteration" -- 126 times in
the production log since the 2nd of September.

Each one was a lost debug write, and silent by construction: the only record
of the notification debugger failing is the log it exists to replace.

What these tests pin is the copy: the old code handed the live dict to
json.dump, which walks it in Python and formats it with indent=2 -- a window
wide enough to lose that race 126 times. Restore that and the first test
fails. The lock around the copy closes what is left, the dict comprehension's
own iteration, and that window is narrow enough that no test here reliably
hits it -- it is kept because it is correct and free, not because a failing
test demanded it.
"""

import json
import os
import threading

import pytest

from claude_ctb.utils.notification_debugger import NotificationDebugger
from claude_ctb.utils.session_state import SessionState


@pytest.fixture
def debugger(tmp_path, monkeypatch):
    d = NotificationDebugger(debug_dir=str(tmp_path))
    # The screen capture shells out to tmux for a session that does not exist;
    # what is under test is the bookkeeping around it.
    monkeypatch.setattr(d, "_capture_screen_context", lambda name: {})
    # Save on every call: the races below are races between writers, so the
    # throttle would hide exactly what they are looking for. The throttle has
    # its own tests further down.
    d.save_interval = 0
    return d


def hammer(debugger, sessions, rounds, errors):
    for i in range(rounds):
        for name in sessions:
            try:
                debugger.log_state_change(
                    name, SessionState.IDLE, SessionState.WORKING, "test")
            except Exception as e:      # noqa: BLE001 -- that is the point
                errors.append(e)


def test_concurrent_state_changes_do_not_break_the_save(debugger, caplog):
    """Every thread brings a session the others have never seen, which is the
    shape that changes the dict's size while it is being written out -- and
    the shape the monitor makes, since it runs one thread per session."""
    errors = []
    threads = [
        threading.Thread(target=hammer, args=(
            debugger, ["claude_thread_%d_%d" % (t, k) for k in range(4)], 8, errors))
        for t in range(8)
    ]
    with caplog.at_level("ERROR"):
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert errors == [], errors
    failures = [r.message for r in caplog.records
                if "Failed to save debug session" in r.getMessage()]
    assert failures == [], failures


def test_the_file_left_behind_is_valid_json(debugger):
    """Written through a temporary file and renamed, so a reader never sees
    half a document and two savers cannot interleave into one file."""
    errors = []
    threads = [
        threading.Thread(target=hammer, args=(
            debugger, ["claude_s_%d" % t], 12, errors)) for t in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(debugger.session_file) as f:
        data = json.load(f)          # raises if a write was interleaved
    assert len(data["state_history"]) == 6
    assert not list(debugger.debug_dir.glob("*.tmp")), "a temporary file was left behind"


def test_every_entry_survives(debugger):
    """The lock must not be a cure that loses data: twelve rounds from each of
    six threads is seventy-two entries, all of them under the history cap."""
    errors = []
    threads = [
        threading.Thread(target=hammer, args=(
            debugger, ["claude_keep_%d" % t], 12, errors)) for t in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    for name, history in debugger.state_history.items():
        assert len(history) == 12, (name, len(history))


# --- what the writer costs, and what it leaves behind ------------------------

def test_the_file_is_not_rewritten_on_every_state_change(debugger, monkeypatch):
    """The whole document went out on every transition -- three hundred
    kilobytes today, growing toward megabytes as the history fills, from
    ninety threads. Nothing is lost by waiting: the data stays in memory and
    the next save writes all of it."""
    debugger.save_interval = 60
    debugger.flush()                       # a baseline file exists
    with open(debugger.session_file) as f:
        assert json.load(f)["state_history"] == {}

    for i in range(20):
        debugger.log_state_change(
            "claude_x", SessionState.IDLE, SessionState.WORKING, "r")

    # Content, not mtime: two writes a millisecond apart can share a
    # timestamp, and what is being asserted is that the document on disk did
    # not follow every transition.
    with open(debugger.session_file) as f:
        assert json.load(f)["state_history"] == {}, "the file followed every change"
    # ...and nothing was dropped on the floor while it waited.
    assert len(debugger.state_history["claude_x"]) == 20


def test_a_flush_writes_everything_that_was_held(debugger):
    debugger.save_interval = 60
    for i in range(5):
        debugger.log_state_change(
            "claude_y", SessionState.IDLE, SessionState.WORKING, "r")
    debugger.flush()
    with open(debugger.session_file) as f:
        assert len(json.load(f)["state_history"]["claude_y"]) == 5


def test_the_interval_lets_a_later_change_through(debugger):
    debugger.save_interval = 0
    debugger.log_state_change("claude_z", SessionState.IDLE, SessionState.WORKING, "r")
    with open(debugger.session_file) as f:
        assert len(json.load(f)["state_history"]["claude_z"]) == 1
    debugger.log_state_change("claude_z", SessionState.WORKING, SessionState.IDLE, "r")
    with open(debugger.session_file) as f:
        assert len(json.load(f)["state_history"]["claude_z"]) == 2, \
            "the second change never reached the file"


def test_old_session_files_are_pruned_at_startup(tmp_path):
    """One file per process start, and nothing ever removed one: fifty-eight
    of them, twenty-seven megabytes, going back to September."""
    from claude_ctb.utils.notification_debugger import NotificationDebugger
    for i in range(40):
        f = tmp_path / ("debug_session_2026090%d_00000%d.json" % (i % 9, i % 9))
        f.write_text("{}")
        os.utime(f, (1000 + i, 1000 + i))
    (tmp_path / "debug_session_dead.0.tmp").write_text("half a document")

    d = NotificationDebugger(debug_dir=str(tmp_path))
    left = list(tmp_path.glob("debug_session_*.json"))
    # Its own new file is one of them.
    assert len(left) <= d.KEEP_SESSIONS + 1, len(left)
    assert not list(tmp_path.glob("*.tmp")), "an abandoned temporary file survived"


def test_pruning_keeps_the_newest(tmp_path):
    from claude_ctb.utils.notification_debugger import NotificationDebugger
    keep = tmp_path / "debug_session_20260923_120000.json"
    drop = tmp_path / "debug_session_20260901_120000.json"
    for f, t in ((keep, 9999), (drop, 1000)):
        f.write_text("{}")
        os.utime(f, (t, t))
    for i in range(30):
        x = tmp_path / ("debug_session_pad_%02d.json" % i)
        x.write_text("{}")
        os.utime(x, (2000 + i, 2000 + i))

    NotificationDebugger(debug_dir=str(tmp_path))
    assert keep.exists(), "the newest file was pruned"
    assert not drop.exists(), "the oldest file survived"
