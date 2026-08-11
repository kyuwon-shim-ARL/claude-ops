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


# --- the force dialog must describe what is actually destroyed ---------------
#
# Deleting a regular session kills tmux and leaves every file on disk; only a
# worktree session has its directory removed. The force confirmation said
# "저장되지 않은 변경사항이 영구히 사라집니다" for both, which is untrue for the
# regular case and talks people out of a harmless action.

from pathlib import Path

_INDEX = (Path(__file__).resolve().parents[1]
          / "src" / "ctb_dashboard" / "templates" / "index.html")


def _force_confirm() -> str:
    s = _INDEX.read_text()
    fn = s[s.index("function renderForceConfirm"):]
    return fn[:fn.index("\n    }")]


def test_the_force_warning_depends_on_the_session_type():
    assert "is_worktree" in _force_confirm(), (
        "one warning for both cases means one of them is a lie"
    )


def test_a_regular_session_is_told_its_files_survive():
    body = _force_confirm()
    assert "파일" in body and "유지" in body


# --- untracked files are not uncommitted changes -----------------------------
#
# `git status --porcelain` lists untracked files too, so a repo where every
# change is committed but a stray directory exists — .verify/ here — was
# reported as "커밋되지 않은 변경사항이 있습니다". The user had committed
# everything and was told otherwise.
#
# The distinction matters differently per session type: deleting a regular
# session removes nothing from disk, while `git worktree remove` does take
# untracked files with it.

def test_untracked_files_alone_are_not_uncommitted(tmp_path):
    import subprocess as sp
    repo = tmp_path / "r"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("x")
    sp.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    sp.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    (repo / "stray").mkdir()
    (repo / "stray" / "note").write_text("untracked")

    from ctb_dashboard.session_delete import _has_uncommitted, _has_untracked
    assert _has_uncommitted(str(repo)) is False, "everything is committed"
    assert _has_untracked(str(repo)) is True


def test_a_tracked_edit_is_uncommitted(tmp_path):
    import subprocess as sp
    repo = tmp_path / "r2"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("x")
    sp.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    sp.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    (repo / "a.txt").write_text("changed")

    from ctb_dashboard.session_delete import _has_uncommitted
    assert _has_uncommitted(str(repo)) is True
