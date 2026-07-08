"""Tests for session_delete git-safety logic.

Uses real git repositories in temp dirs (git logic is the whole point, so
mocking git would test nothing). tmux and session-path lookup are patched.
"""

import subprocess
from pathlib import Path

import pytest

from ctb_dashboard import session_delete


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A repo with a bare 'origin' remote and one pushed commit on main."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-b", "main", str(work)],
                   check=True, capture_output=True)
    _git(work, "config", "user.email", "t@t.com")
    _git(work, "config", "user.name", "t")
    _git(work, "remote", "add", "origin", str(origin))
    (work / "f.txt").write_text("hello")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    # establish origin/HEAD -> origin/main
    _git(work, "remote", "set-head", "origin", "main")
    return work


def _patch_path(monkeypatch, path):
    monkeypatch.setattr(session_delete, "get_session_path", lambda name: str(path))


def test_clean_pushed_repo_is_safe(repo, monkeypatch):
    _patch_path(monkeypatch, repo)
    r = session_delete.check_delete_safety("claude_x")
    assert r["is_git"] is True
    assert r["is_worktree"] is False
    assert r["safe"] is True
    assert r["reasons"] == []


def test_uncommitted_changes_block(repo, monkeypatch):
    (repo / "f.txt").write_text("dirty")
    _patch_path(monkeypatch, repo)
    r = session_delete.check_delete_safety("claude_x")
    assert r["has_uncommitted"] is True
    assert r["safe"] is False
    assert any("커밋" in x for x in r["reasons"])


def test_unpushed_commits_block(repo, monkeypatch):
    (repo / "g.txt").write_text("new")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second")
    _patch_path(monkeypatch, repo)
    r = session_delete.check_delete_safety("claude_x")
    assert r["unpushed_count"] == 1
    assert r["safe"] is False
    assert any("푸시" in x for x in r["reasons"])


def test_no_upstream_block(tmp_path, monkeypatch):
    work = tmp_path / "solo"
    subprocess.run(["git", "init", "-b", "main", str(work)],
                   check=True, capture_output=True)
    _git(work, "config", "user.email", "t@t.com")
    _git(work, "config", "user.name", "t")
    (work / "f.txt").write_text("hi")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    _patch_path(monkeypatch, work)
    r = session_delete.check_delete_safety("claude_x")
    assert r["has_upstream"] is False
    assert r["safe"] is False


def test_non_git_is_safe(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    _patch_path(monkeypatch, plain)
    r = session_delete.check_delete_safety("claude_x")
    assert r["is_git"] is False
    assert r["safe"] is True


def test_merged_worktree_is_safe(repo, monkeypatch):
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    # feature == main (no new commits) -> merged (ancestor of origin/main)
    _patch_path(monkeypatch, wt)
    r = session_delete.check_delete_safety("claude_x_wt_feature")
    assert r["is_worktree"] is True
    assert r["is_merged"] is True
    assert r["safe"] is True


def test_unmerged_worktree_blocks(repo, monkeypatch):
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    (wt / "h.txt").write_text("wt work")
    _git(wt, "add", ".")
    _git(wt, "commit", "-m", "wt commit")
    _patch_path(monkeypatch, wt)
    r = session_delete.check_delete_safety("claude_x_wt_feature")
    assert r["is_worktree"] is True
    assert r["is_merged"] is False
    assert r["safe"] is False
    assert any("병합" in x for x in r["reasons"])


def test_delete_blocked_without_force(repo, monkeypatch):
    (repo / "f.txt").write_text("dirty")
    _patch_path(monkeypatch, repo)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x", force=False)
    assert out["status"] == "blocked"


def test_force_delete_removes_unmerged_worktree(repo, monkeypatch):
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    (wt / "h.txt").write_text("wt work")
    _git(wt, "add", ".")
    _git(wt, "commit", "-m", "wt commit")
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "deleted"
    assert out["removed_worktree"] is True
    assert not Path(wt).exists()


def test_safe_delete_removes_merged_worktree(repo, monkeypatch):
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=False)
    assert out["status"] == "deleted"
    assert out["removed_worktree"] is True
    assert out["branch_deleted"] is True
    assert not Path(wt).exists()
