"""Tests for session_delete git-safety logic.

Uses real git repositories in temp dirs (git logic is the whole point, so
mocking git would test nothing). tmux and session-path lookup are patched.
"""

import os
import re
import subprocess
import time
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


@pytest.fixture(autouse=True)
def _no_other_sessions(monkeypatch):
    """The shared-worktree guard asks tmux who else is live; nobody, unless a
    test says otherwise (conftest refuses tmux outright)."""
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: {})


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


def _unmerged_worktree(repo):
    """A worktree with an unmerged commit, an untracked file and an ignored
    one -- everything a `worktree remove --force` used to take with it."""
    (repo / ".gitignore").write_text("*.log\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore logs")
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    (wt / "h.txt").write_text("wt work")
    _git(wt, "add", ".")
    _git(wt, "commit", "-m", "wt commit")
    (wt / "scratch.txt").write_text("untracked")
    (wt / "run.log").write_text("ignored")
    return wt


def _branch_exists(repo, branch):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                           f"refs/heads/{branch}"], capture_output=True).returncode == 0


def test_force_delete_moves_an_unmerged_worktree_to_the_trash(repo, monkeypatch):
    wt = _unmerged_worktree(repo)
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "deleted"
    assert out["removed_worktree"] is False
    assert out["branch_deleted"] is False
    assert not wt.exists()

    trash = Path(out["trashed_to"])
    assert trash.parent == repo / ".claude" / "trash"
    assert re.fullmatch(r"wt-\d{8}T\d{6}", trash.name)
    assert (trash / "h.txt").read_text() == "wt work"
    assert (trash / "scratch.txt").read_text() == "untracked"
    assert (trash / "run.log").read_text() == "ignored"
    assert _branch_exists(repo, "feature")
    # Still a worktree git knows, on its branch -- what restore moves back.
    head = subprocess.run(["git", "-C", str(trash), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == "feature"
    # And the trash itself never shows up in the main repo's status.
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    assert ".claude" not in status, status


def test_a_failed_move_to_the_trash_fails_closed(repo, monkeypatch):
    """A locked worktree (or one with submodules) cannot be moved. That must
    end in an error with the directory where it was -- never a fallback to
    `worktree remove`."""
    wt = _unmerged_worktree(repo)
    _git(repo, "worktree", "lock", str(wt))
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "error"
    assert "locked" in out["error"]
    assert "trashed_to" not in out
    assert (wt / "scratch.txt").read_text() == "untracked"
    assert (wt / "run.log").exists()
    assert _branch_exists(repo, "feature")


def test_a_worktree_shared_with_another_live_session_is_left_in_place(repo, monkeypatch):
    """`claude_<p>_wt_<w>` and its `_sh` shell work in the same directory;
    closing one must not pull the worktree out from under the other."""
    wt = _unmerged_worktree(repo)
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "get_sessions_activity",
                        lambda: {"claude_x_wt_feature": 1, "claude_x_wt_feature_sh": 1})
    killed = []
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: killed.append(name) or True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "deleted"
    assert out["kept_worktree_shared_with"] == "claude_x_wt_feature_sh"
    assert out["removed_worktree"] is False and "trashed_to" not in out
    assert killed == ["claude_x_wt_feature"]
    assert (wt / "scratch.txt").exists()
    assert _branch_exists(repo, "feature")


def test_a_session_elsewhere_does_not_count_as_sharing(repo, monkeypatch):
    wt = _unmerged_worktree(repo)
    paths = {"claude_x_wt_feature": str(wt), "claude_x": str(repo)}
    monkeypatch.setattr(session_delete, "get_session_path", lambda name: paths[name])
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: dict.fromkeys(paths, 1))
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert "kept_worktree_shared_with" not in out
    assert Path(out["trashed_to"]).is_dir()


def test_an_unforced_close_of_a_dirty_shared_worktree_is_blocked_first(repo, monkeypatch):
    """Ctrl+Q's automatic retry forces with allow_worktree=False. On a dirty
    worktree that force does not apply, so the answer must be "blocked" (the
    first press arms) -- not a kill of a busy Claude because its `_sh` sibling
    happens to be open."""
    wt = _unmerged_worktree(repo)
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "get_sessions_activity",
                        lambda: {"claude_x_wt_feature": 1, "claude_x_wt_feature_sh": 1})
    killed = []
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: killed.append(name) or True)
    for force, allow in ((False, True), (True, False)):
        out = session_delete.delete_session("claude_x_wt_feature", force=force, allow_worktree=allow)
        assert out["status"] == "blocked"
    assert killed == []


def test_a_safe_shared_worktree_close_kills_only_this_session(repo, monkeypatch):
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "get_sessions_activity",
                        lambda: {"claude_x_wt_feature": 1, "claude_x_wt_feature_sh": 1})
    killed = []
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: killed.append(name) or True)
    out = session_delete.delete_session("claude_x_wt_feature", force=False)
    assert out["kept_worktree_shared_with"] == "claude_x_wt_feature_sh"
    assert killed == ["claude_x_wt_feature"] and wt.is_dir() and _branch_exists(repo, "feature")


def test_a_sibling_directory_with_a_common_prefix_is_not_sharing(repo, monkeypatch):
    wt = _unmerged_worktree(repo)
    wtx = repo.parent / "wtx"
    wtx.mkdir()
    paths = {"claude_x_wt_feature": str(wt), "claude_other": str(wtx)}
    monkeypatch.setattr(session_delete, "get_session_path", lambda name: paths[name])
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: dict.fromkeys(paths, 1))
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert "kept_worktree_shared_with" not in out
    assert Path(out["trashed_to"]).is_dir()


def test_sharing_is_judged_from_the_worktree_top_not_the_pane(repo, monkeypatch):
    """A Claude pane cd'd into wt/src and a shell at wt/ are in the same
    worktree: the guard's root is git's top level, not the pane's cwd."""
    wt = _unmerged_worktree(repo)
    (wt / "src").mkdir()
    paths = {"claude_x_wt_feature": str(wt / "src"), "claude_x_wt_feature_sh": str(wt)}
    monkeypatch.setattr(session_delete, "get_session_path", lambda name: paths[name])
    monkeypatch.setattr(session_delete, "get_sessions_activity", lambda: dict.fromkeys(paths, 1))
    killed = []
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: killed.append(name) or True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["kept_worktree_shared_with"] == "claude_x_wt_feature_sh"
    assert killed == ["claude_x_wt_feature"] and wt.is_dir()


def test_a_pane_in_a_subdirectory_trashes_the_whole_worktree(repo, monkeypatch):
    wt = _unmerged_worktree(repo)
    (wt / "src").mkdir()
    _patch_path(monkeypatch, wt / "src")
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "deleted", out.get("error")
    assert not wt.exists()
    assert Path(out["trashed_from"]) == wt
    assert re.fullmatch(r"wt-\d{8}T\d{6}", Path(out["trashed_to"]).name)
    assert (Path(out["trashed_to"]) / "scratch.txt").exists()


def test_gc_leaves_symlinks_in_the_trash_alone(repo, tmp_path, monkeypatch):
    """Only directories `worktree move` put there are GC's to purge; a
    symlink in the trash points at something that is not."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("not ours")
    trash = repo / ".claude" / "trash"
    trash.mkdir(parents=True)
    link = trash / "link-20000101T000000"
    link.symlink_to(target)
    calls = []
    real = session_delete._run_git
    monkeypatch.setattr(session_delete, "_run_git",
                        lambda cwd, args, timeout=5: calls.append(args) or real(cwd, args, timeout))
    session_delete.gc_trash(str(repo))
    assert link.is_symlink() and (target / "keep.txt").exists()
    assert calls == []


def _trash_entry(repo, name, stamp):
    """A worktree parked in the trash under `<name>-<stamp>`, on branch `<name>`."""
    trash = repo / ".claude" / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / f"{name}-{stamp}"
    _git(repo, "worktree", "add", "-b", name, str(dest))
    (dest / "work.txt").write_text(name)
    return dest


def test_gc_purges_only_expired_trash_and_their_branches(repo, monkeypatch):
    old = _trash_entry(repo, "old", "20000101T000000")
    fresh = _trash_entry(repo, "fresh", time.strftime("%Y%m%dT%H%M%S"))
    session_delete.gc_trash(str(repo))
    assert not old.exists() and not _branch_exists(repo, "old")
    assert (fresh / "work.txt").exists() and _branch_exists(repo, "fresh")


def test_gc_retention_comes_from_ctb_trash_days(repo, monkeypatch):
    two_days_ago = time.strftime("%Y%m%dT%H%M%S", time.localtime(time.time() - 2 * 86400))
    entry = _trash_entry(repo, "mid", two_days_ago)
    monkeypatch.setenv("CTB_TRASH_DAYS", "3")
    session_delete.gc_trash(str(repo))
    assert entry.exists()
    monkeypatch.setenv("CTB_TRASH_DAYS", "1")
    session_delete.gc_trash(str(repo))
    assert not entry.exists()


def test_gc_falls_back_to_mtime_without_a_stamp(repo):
    entry = _trash_entry(repo, "nostamp", "x")
    week_ago = time.time() - 30 * 86400
    os.utime(entry, (week_ago, week_ago))
    session_delete.gc_trash(str(repo))
    assert not entry.exists()


def test_a_worktree_delete_collects_expired_trash(repo, monkeypatch):
    old = _trash_entry(repo, "old", "20000101T000000")
    wt = _unmerged_worktree(repo)
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert Path(out["trashed_to"]).is_dir()
    assert not old.exists()


def test_a_failing_gc_does_not_fail_the_delete(repo, monkeypatch):
    old = _trash_entry(repo, "old", "20000101T000000")
    _git(repo, "worktree", "lock", str(old))
    wt = _unmerged_worktree(repo)
    _patch_path(monkeypatch, wt)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True)
    assert out["status"] == "deleted"
    assert old.exists()


def test_a_force_that_excludes_worktrees_leaves_an_unsafe_worktree_alone(repo, monkeypatch):
    """Ctrl+Q forces a plain session on the strength of a first check that
    said "not a worktree". If the server's own check now says it is one, that
    force must not reach `worktree remove --force` and `branch -D`."""
    wt = repo.parent / "wt"
    _git(repo, "worktree", "add", "-b", "feature", str(wt))
    (wt / "h.txt").write_text("wt work")
    _git(wt, "add", ".")
    _git(wt, "commit", "-m", "wt commit")
    _patch_path(monkeypatch, wt)
    killed = []
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: killed.append(name) or True)
    out = session_delete.delete_session("claude_x_wt_feature", force=True, allow_worktree=False)
    assert out["status"] == "blocked"
    assert killed == []
    assert Path(wt).exists()


def test_a_force_that_excludes_worktrees_still_closes_a_plain_session(repo, monkeypatch):
    (repo / "f.txt").write_text("dirty")
    _patch_path(monkeypatch, repo)
    monkeypatch.setattr(session_delete, "_kill_tmux", lambda name: True)
    out = session_delete.delete_session("claude_x", force=True, allow_worktree=False)
    assert out["status"] == "deleted"
    assert (repo / "f.txt").read_text() == "dirty"


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
# renderForceConfirm is now only ever shown for an unsafe worktree: a plain
# session's trash-button click retries automatically (force + allow_worktree
# false), with no dialog, the same way the console's Ctrl+Q does -- its
# delete only kills tmux and leaves every file on disk. The one remaining
# modal said "저장되지 않은 변경사항이 영구히 사라집니다" for a worktree force,
# which is untrue: a force now parks it in the trash, not destroys it.


_INDEX = (Path(__file__).resolve().parents[1]
          / "src" / "ctb_dashboard" / "templates" / "index.html")


def _force_confirm() -> str:
    s = _INDEX.read_text()
    fn = s[s.index("function renderForceConfirm"):]
    return fn[:fn.index("\n    }")]


def test_a_worktree_is_told_it_goes_to_the_trash_not_away():
    """The force no longer destroys a worktree: it parks it, files, commits
    and branch included, for CTB_TRASH_DAYS. Saying "영구히 사라집니다" would
    talk people out of a recoverable action -- the same lie, the other way."""
    body = _force_confirm()
    assert "휴지통" in body and "7일" in body and "Shift+Q" in body
    assert "영구" not in body


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


def _repo_with_commit(root, name):
    import subprocess as sp
    repo = root / name
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("x")
    sp.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    sp.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def test_a_worktree_warns_that_untracked_files_go_with_it(tmp_path, monkeypatch):
    """`git worktree remove` deletes the directory, untracked files included."""
    import subprocess as sp
    from ctb_dashboard import session_delete as sd

    main = _repo_with_commit(tmp_path, "main")
    wt = tmp_path / "wt"
    sp.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "feature", str(wt)],
           check=True)
    (wt / "scratch.txt").write_text("not tracked")

    monkeypatch.setattr(sd, "get_session_path", lambda name: str(wt))
    check = sd.check_delete_safety("claude_probe")

    assert check["is_worktree"] is True
    assert check["has_untracked"] is True
    assert any("추적하지 않는" in r for r in check["reasons"]), check["reasons"]
    # A force no longer deletes them on the spot; the reason must say what does happen.
    reason = next(r for r in check["reasons"] if "추적하지 않는" in r)
    assert "휴지통" in reason and "7일" in reason


def test_a_regular_session_is_not_blocked_by_untracked_files(tmp_path, monkeypatch):
    """Nothing on disk is removed, so they are not a reason to refuse."""
    from ctb_dashboard import session_delete as sd

    repo = _repo_with_commit(tmp_path, "plain")
    (repo / "scratch.txt").write_text("not tracked")

    monkeypatch.setattr(sd, "get_session_path", lambda name: str(repo))
    check = sd.check_delete_safety("claude_probe")

    assert check["has_untracked"] is True
    assert not any("추적하지 않는" in r for r in check["reasons"]), check["reasons"]
    assert not any("커밋되지 않은" in r for r in check["reasons"]), check["reasons"]
