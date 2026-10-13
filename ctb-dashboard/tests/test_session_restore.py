"""Ctrl+Q closes; Ctrl+Shift+Q brings the last closed session back."""

import subprocess
from pathlib import Path

import pytest

from ctb_dashboard import session_delete
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


def test_a_failed_relaunch_stays_in_history_and_is_raised(tmp_path, monkeypatch):
    """A restore that fails must not cost the entry: the next Shift+Q, once
    whatever was in the way is gone, should still find it."""
    p = str(tmp_path / "h.json")

    def boom(**k):
        raise CreateError("no_project", "gone")
    monkeypatch.setattr(sr, "create_session", boom)
    sr.record(p, sr.describe("claude_old", path="/o"))
    sr.record(p, sr.describe("claude_x_wt_y", path="/x"))
    with pytest.raises(CreateError):
        sr.restore_last(p, live=set)
    assert [r["session"] for r in sr.peek(p)] == ["claude_x_wt_y", "claude_old"]


# --- shell sessions come back as shells -------------------------------------


def test_describe_marks_a_shell_session_and_strips_its_suffix(monkeypatch):
    monkeypatch.setattr(sr, "is_shell_session", lambda name: True)
    e = sr.describe("claude_land_wt_auction_sh", path="/p/land/.claude/worktrees/auction")
    assert e["shell"] is True and e["worktree"] == "auction" and e["project"] == "land"


def test_a_plain_shell_session_is_restored_without_claude(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    d = tmp_path / "proj"
    d.mkdir()
    shells, claudes = [], []
    monkeypatch.setattr(sr, "launch_shell_session", lambda s, cwd: shells.append((s, str(cwd))))
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: claudes.append(s))
    sr.record(p, {"session": "claude_proj_sh", "path": str(d), "shell": True})
    out = sr.restore_last(p, live=set)
    assert out["status"] == "created"
    assert shells == [("claude_proj_sh", str(d))] and claudes == []


def test_a_worktree_shell_session_is_recreated_as_a_shell(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    calls = []
    monkeypatch.setattr(sr, "create_session", lambda **k: calls.append(k) or {"status": "created", "path": "/wt"})
    monkeypatch.setattr(sr, "is_shell_session", lambda name: True)
    sr.record(p, sr.describe("claude_land_wt_auction_sh", path="/gone"))
    sr.restore_last(p, live=set)
    assert calls == [{"project": "land", "worktree": "auction", "shell": True}]


# --- restore from the trash (real git) --------------------------------------


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def trashed(tmp_path, monkeypatch):
    """A worktree session force-deleted into the trash, its history entry
    recorded the way server._delete_and_remember records it."""
    repo = tmp_path / "land"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    wt = repo / ".claude" / "worktrees" / "auction"
    _git(repo, "worktree", "add", "-q", "-b", "worktree-auction", str(wt))
    (wt / "draft.txt").write_text("unsaved idea")

    session = "claude_land_wt_auction"
    monkeypatch.setattr(session_delete, "get_session_path", lambda name: str(wt))
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    entry = sr.describe(session, path=str(wt))
    out = session_delete.delete_session(session, force=True)
    assert out["status"] == "deleted" and not wt.exists()
    entry["trashed_to"] = out["trashed_to"]
    h = str(tmp_path / "h.json")
    sr.record(h, entry)

    launched = []
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: launched.append((s, str(cwd))))
    monkeypatch.setattr(sr, "create_session",
                        lambda **k: pytest.fail("a trashed worktree must be moved back, not recreated"))
    return {"history": h, "wt": wt, "trash": Path(out["trashed_to"]), "launched": launched,
            "session": session}


def test_restore_moves_the_worktree_back_and_resumes_in_its_own_path(trashed):
    out = sr.restore_last(trashed["history"], live=set)
    wt = trashed["wt"]
    assert out["status"] == "created" and out["path"] == str(wt)
    assert (wt / "draft.txt").read_text() == "unsaved idea"
    assert not trashed["trash"].exists()
    # The original path is what Claude's transcript is keyed by, so --continue
    # finds the conversation there.
    assert trashed["launched"] == [(trashed["session"], str(wt))]
    assert sr.peek(trashed["history"]) == []


def test_restore_refuses_when_the_original_path_is_taken_and_keeps_the_entry(trashed):
    trashed["wt"].mkdir(parents=True)
    with pytest.raises(CreateError) as e:
        sr.restore_last(trashed["history"], live=set)
    assert "휴지통" in e.value.message
    assert trashed["trash"].is_dir() and (trashed["trash"] / "draft.txt").exists()
    assert trashed["launched"] == []
    assert [r["session"] for r in sr.peek(trashed["history"])] == [trashed["session"]]


def test_restore_falls_back_to_create_when_the_trash_is_gone(tmp_path, monkeypatch):
    p = str(tmp_path / "h.json")
    calls = []
    monkeypatch.setattr(sr, "create_session", lambda **k: calls.append(k) or {"status": "created", "path": "/wt"})
    entry = sr.describe("claude_land_wt_auction", path="/gone")
    entry["trashed_to"] = str(tmp_path / "expired")
    sr.record(p, entry)
    out = sr.restore_last(p, live=set)
    assert calls == [{"project": "land", "worktree": "auction"}]
    assert out["path"] == "/wt"


def test_a_plain_named_session_that_trashed_a_worktree_comes_back(tmp_path, monkeypatch):
    """`claude_land` cd'd into a worktree and force-deleted: the worktree was
    trashed, but the name carries no `_wt_`, so the entry has no `worktree`.
    Restore must still move it back rather than find the path gone and drop it."""
    repo = tmp_path / "land"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    wt = repo / ".claude" / "worktrees" / "auction"
    _git(repo, "worktree", "add", "-q", "-b", "worktree-auction", str(wt))
    (wt / "src").mkdir()
    (wt / "src" / "draft.txt").write_text("unsaved idea")

    monkeypatch.setattr(session_delete, "get_session_path", lambda name: str(wt / "src"))
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    entry = sr.describe("claude_land", path=str(wt / "src"))
    assert "worktree" not in entry
    out = session_delete.delete_session("claude_land", force=True)
    assert out["status"] == "deleted", out.get("error")
    entry["trashed_to"] = out["trashed_to"]
    entry["trashed_from"] = out["trashed_from"]
    h = str(tmp_path / "h.json")
    sr.record(h, entry)

    launched = []
    monkeypatch.setattr(sr, "launch_session", lambda s, cwd: launched.append((s, str(cwd))))
    res = sr.restore_last(h, live=set)
    assert res["status"] == "created"
    assert (wt / "src" / "draft.txt").read_text() == "unsaved idea"
    assert launched == [("claude_land", str(wt / "src"))]
    assert sr.peek(h) == []
