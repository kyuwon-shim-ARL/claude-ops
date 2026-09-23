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
