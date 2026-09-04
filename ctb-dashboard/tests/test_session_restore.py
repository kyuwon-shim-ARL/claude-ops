"""Ctrl+Q closes; Ctrl+Shift+Q brings the last closed session back."""

import pytest

from ctb_dashboard import session_restore as sr
from ctb_dashboard.session_create import CreateError


def test_describe_reads_the_worktree_out_of_the_name():
    e = sr.describe("claude_land_wt_auction", path="/p/land/.claude/worktrees/auction")
    assert e["project"] == "land" and e["worktree"] == "auction"
    assert e["path"].endswith("auction") and e["closed_at"]
    assert "worktree" not in sr.describe("claude_ops", path="/p/ops")


def test_record_keeps_newest_last_and_one_per_session(tmp_path):
    p = str(tmp_path / "h.json")
    sr.record(p, {"session": "a", "path": "/a"})
    sr.record(p, {"session": "b", "path": "/b"})
    sr.record(p, {"session": "a", "path": "/a2"})
    assert [r["session"] for r in sr.peek(p)] == ["a", "b"]
    assert sr.peek(p)[0]["path"] == "/a2"


def test_record_is_bounded(tmp_path):
    p = str(tmp_path / "h.json")
    for i in range(30):
        sr.record(p, {"session": f"s{i}", "path": "/x"})
    assert len(sr.peek(p)) == sr.HISTORY_MAX


def test_restore_pops_the_most_recent_and_relaunches_in_place(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    d = tmp_path / "proj"
    d.mkdir()
    launched = []
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: launched.append((s, str(cwd))))
    sr.record(p, {"session": "claude_old", "path": str(d)})
    sr.record(p, {"session": "claude_new", "path": str(d)})
    out = sr.restore_last(p, live=set)
    assert out["session"] == "claude_new" and out["status"] == "created"
    assert launched == [("claude_new", str(d))]
    assert [r["session"] for r in sr.peek(p)] == ["claude_old"]


def test_restore_skips_live_sessions_and_gone_directories(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    d = tmp_path / "proj"
    d.mkdir()
    launched = []
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: launched.append(s))
    sr.record(p, {"session": "claude_ok", "path": str(d)})
    sr.record(p, {"session": "claude_gone", "path": str(tmp_path / "missing")})
    sr.record(p, {"session": "claude_alive", "path": str(d)})
    out = sr.restore_last(p, live=lambda: {"claude_alive"})
    assert out["session"] == "claude_ok" and launched == ["claude_ok"]
    assert sr.peek(p) == []


def test_restore_of_a_worktree_goes_through_create(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    calls = []
    monkeypatch.setattr(sr, "create_session", lambda **k: calls.append(k) or {"status": "created", "path": "/wt"})
    sr.record(p, sr.describe("claude_land_wt_auction", path="/gone"))
    out = sr.restore_last(p, live=set)
    assert calls == [{"project": "land", "worktree": "auction"}]
    assert out["status"] == "created" and out["path"] == "/wt"


def test_restore_with_nothing_left_returns_none(tmp_path):
    assert sr.restore_last(str(tmp_path / "h.json"), live=set) is None


def test_a_failed_relaunch_is_dropped_from_history_and_raised(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")

    def boom(**k):
        raise CreateError("no_project", "gone")
    monkeypatch.setattr(sr, "create_session", boom)
    sr.record(p, sr.describe("claude_x_wt_y", path="/x"))
    with pytest.raises(CreateError):
        sr.restore_last(p, live=set)
    assert sr.peek(p) == []
