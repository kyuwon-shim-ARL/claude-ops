"""Tests for creating a session from the dashboard.

Real git repositories in temp dirs (the worktree logic is the point, so a
mocked git would test nothing); tmux is never touched -- conftest refuses it
outright, and the launch is patched.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ctb_dashboard import server, session_create
from ctb_dashboard.session_create import CreateError

# Captured before the autouse fixture stubs it out, so the tmux argv contract
# tests below exercise the real function.
REAL_LAUNCH = session_create.launch_session


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A projects root with one git project and one plain directory."""
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("CTB_PROJECTS_ROOT", str(root))

    repo = root / "alpha"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("hi")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    (root / "beta").mkdir()  # not a git repo
    (root / ".hidden").mkdir()
    (root / "loose.txt").write_text("x")
    return root


@pytest.fixture(autouse=True)
def _no_live_tmux(monkeypatch):
    """Record launches instead of starting them; conftest already bans tmux."""
    launched = []
    monkeypatch.setattr(session_create, "launch_session",
                        lambda s, p: launched.append((s, str(p))))
    monkeypatch.setattr(session_create, "schedule_remote_control", lambda s: None)
    monkeypatch.setattr(session_create, "_live_sessions", lambda: set())
    return launched


@pytest.fixture
def launched(_no_live_tmux):
    return _no_live_tmux


# --- listing ---------------------------------------------------------------


def test_lists_only_project_directories(root):
    out = session_create.list_projects()
    names = [p["name"] for p in out["projects"]]
    assert set(names) == {"alpha", "beta"}  # no dotfile, no loose file; order is by mtime
    assert out["root"] == str(root)


def test_reports_git_and_session_status(root, monkeypatch):
    monkeypatch.setattr(session_create, "_live_sessions", lambda: {"claude_alpha"})
    by_name = {p["name"]: p for p in session_create.list_projects()["projects"]}
    assert by_name["alpha"]["is_git"] is True
    assert by_name["alpha"]["session_exists"] is True
    assert by_name["beta"]["is_git"] is False
    assert by_name["beta"]["session_exists"] is False


def test_missing_root_is_empty_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CTB_PROJECTS_ROOT", str(tmp_path / "nope"))
    assert session_create.list_projects()["projects"] == []


def test_worktrees_listed_with_branch(root):
    session_create.create_session(project="alpha", worktree="feat")
    out = session_create.list_worktrees("alpha")
    assert out["is_git"] is True
    assert [w["name"] for w in out["worktrees"]] == ["feat"]
    assert out["worktrees"][0]["branch"] == "worktree-feat"
    assert out["worktrees"][0]["session"] == "claude_alpha_wt_feat"


def test_worktrees_of_non_git_project_is_empty(root):
    out = session_create.list_worktrees("beta")
    assert out["is_git"] is False
    assert out["worktrees"] == []


def test_worktrees_of_unknown_project_raises(root):
    with pytest.raises(CreateError) as e:
        session_create.list_worktrees("nosuch")
    assert e.value.code == "no_project"


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("name", ["../escape", "a/b", "", ".hidden", "x" * 65, "a b"])
def test_rejects_bad_project_names(root, name):
    with pytest.raises(CreateError) as e:
        session_create.create_session(project=name)
    assert e.value.code in ("invalid_project", "bad_request")


@pytest.mark.parametrize("name", ["../x", "a/b", "a b", "-lead", "x" * 65])
def test_rejects_bad_worktree_names(root, name):
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="alpha", worktree=name)
    assert e.value.code in ("invalid_worktree", "bad_request")


def test_requires_exactly_one_of_project_or_new_project(root):
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="alpha", new_project="gamma")
    assert e.value.code == "bad_request"
    with pytest.raises(CreateError) as e:
        session_create.create_session()
    assert e.value.code == "bad_request"


def test_symlinked_project_escaping_root_is_refused(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="link")
    assert e.value.code == "invalid_project"


# --- creation --------------------------------------------------------------


def test_existing_project_session(root, launched):
    r = session_create.create_session(project="alpha")
    assert r["status"] == "created"
    assert r["session"] == "claude_alpha"
    assert r["path"] == str(root / "alpha")
    assert r["project_created"] is False
    assert launched == [("claude_alpha", str(root / "alpha"))]


def test_unknown_project_is_refused(root, launched):
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="nosuch")
    assert e.value.code == "no_project"
    assert launched == []


def test_existing_session_is_reported_not_relaunched(root, launched, monkeypatch):
    monkeypatch.setattr(session_create, "_live_sessions", lambda: {"claude_alpha"})
    r = session_create.create_session(project="alpha")
    assert r["status"] == "exists"
    assert launched == []


def test_new_project_creates_git_repo_with_commit(root, launched):
    r = session_create.create_session(new_project="gamma")
    gamma = root / "gamma"
    assert r["status"] == "created"
    assert r["project_created"] is True
    assert (gamma / ".git").exists()
    assert (gamma / ".gitignore").exists()
    log = subprocess.run(["git", "-C", str(gamma), "log", "--oneline"],
                         capture_output=True, text=True)
    assert log.returncode == 0 and log.stdout.strip()
    assert launched == [("claude_gamma", str(gamma))]


def test_new_project_without_git(root):
    session_create.create_session(new_project="delta", git_init=False)
    assert (root / "delta").is_dir()
    assert not (root / "delta" / ".git").exists()


def test_new_project_that_exists_is_refused(root, launched):
    with pytest.raises(CreateError) as e:
        session_create.create_session(new_project="alpha")
    assert e.value.code == "project_exists"
    assert launched == []


def test_worktree_created_on_convention_path_and_branch(root, launched):
    r = session_create.create_session(project="alpha", worktree="feat")
    wt = root / "alpha" / ".claude" / "worktrees" / "feat"
    assert r["session"] == "claude_alpha_wt_feat"
    assert r["worktree_created"] is True
    assert r["path"] == str(wt)
    assert wt.is_dir()
    branch = subprocess.run(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    assert branch == "worktree-feat"
    assert launched == [("claude_alpha_wt_feat", str(wt))]


def test_existing_worktree_is_reused_not_recreated(root, launched):
    session_create.create_session(project="alpha", worktree="feat")
    launched.clear()
    r = session_create.create_session(project="alpha", worktree="feat")
    assert r["worktree_created"] is False
    assert r["status"] == "created"
    assert len(launched) == 1


def test_worktree_reuses_orphaned_branch(root, launched):
    """A worktree removed but whose branch survives must still be openable."""
    session_create.create_session(project="alpha", worktree="feat")
    wt = root / "alpha" / ".claude" / "worktrees" / "feat"
    subprocess.run(["git", "-C", str(root / "alpha"), "worktree", "remove", str(wt)],
                   check=True, capture_output=True)
    assert not wt.exists()
    r = session_create.create_session(project="alpha", worktree="feat")
    assert r["worktree_created"] is True
    assert wt.is_dir()


def test_worktree_on_non_git_project_is_refused(root, launched):
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="beta", worktree="feat")
    assert e.value.code == "not_git"
    assert launched == []
    assert not (root / "beta" / ".claude").exists()


def test_launch_failure_surfaces(root, monkeypatch):
    def boom(session, path):
        raise CreateError("tmux_failed", "no server running")
    monkeypatch.setattr(session_create, "launch_session", boom)
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="alpha")
    assert e.value.code == "tmux_failed"


# --- tmux argv contract ----------------------------------------------------


def test_launch_argv_matches_cs_convention(root, monkeypatch):
    """The launch must be detached, in the right dir, under a login shell."""
    calls = []

    def fake_run(argv, timeout=None):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(session_create, "_run", fake_run)
    monkeypatch.setattr(session_create, "_claude_history_exists", lambda p: False)
    REAL_LAUNCH("claude_alpha_wt_feat", Path("/tmp/x"))

    new_session = calls[0]
    assert new_session[:4] == ["tmux", "new-session", "-d", "-s"]
    assert new_session[4] == "claude_alpha_wt_feat"
    assert "-c" in new_session and new_session[new_session.index("-c") + 1] == "/tmp/x"
    assert new_session[new_session.index("-n") + 1] == "alpha_wt_feat"
    cmd = new_session[-1]
    assert cmd.startswith("bash --login -c ")
    assert "--dangerously-skip-permissions" in cmd
    assert "--continue" not in cmd
    assert "exec bash --login" in cmd
    assert calls[1][:3] == ["tmux", "set-window-option", "-t"]
    assert calls[1][-2:] == ["remain-on-exit", "on"]


def test_launch_resumes_when_history_exists(root, monkeypatch):
    calls = []
    monkeypatch.setattr(session_create, "_run",
                        lambda argv, timeout=None: (calls.append(argv),
                                                    subprocess.CompletedProcess(argv, 0, "", ""))[1])
    monkeypatch.setattr(session_create, "_claude_history_exists", lambda p: True)
    REAL_LAUNCH("claude_alpha", Path("/tmp/x"))
    assert "--continue" in calls[0][-1]


def test_launch_failure_raises_create_error(root, monkeypatch):
    monkeypatch.setattr(
        session_create, "_run",
        lambda argv, timeout=None: subprocess.CompletedProcess(argv, 1, "", "duplicate session"))
    with pytest.raises(CreateError) as e:
        REAL_LAUNCH("claude_alpha", Path("/tmp/x"))
    assert e.value.code == "tmux_failed"
    assert "duplicate session" in e.value.message


# --- HTTP ------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_CONTROL_SECRET", "s3cret")
    return TestClient(server.app)


AUTH = {"X-CTB-Secret": "s3cret"}


def test_projects_endpoint(client, root):
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert {p["name"] for p in r.json()["projects"]} == {"alpha", "beta"}


def test_worktrees_endpoint_404s_for_unknown_project(client, root):
    assert client.get("/api/projects/nosuch/worktrees").status_code == 404


def test_worktrees_endpoint_422s_for_bad_name(client, root):
    assert client.get("/api/projects/a%20b/worktrees").status_code == 422


def test_create_requires_control_token(client, root, launched):
    r = client.post("/api/sessions/create", json={"project": "alpha"})
    assert r.status_code == 403
    assert launched == []


def test_create_endpoint_happy_path(client, root, launched):
    r = client.post("/api/sessions/create", json={"project": "alpha"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["session"] == "claude_alpha"
    assert len(launched) == 1


def test_create_endpoint_status_codes(client, root, launched):
    assert client.post("/api/sessions/create", json={"project": "nosuch"},
                       headers=AUTH).status_code == 404
    assert client.post("/api/sessions/create", json={"new_project": "alpha"},
                       headers=AUTH).status_code == 409
    assert client.post("/api/sessions/create", json={"project": "../x"},
                       headers=AUTH).status_code == 422
    assert client.post("/api/sessions/create", json={}, headers=AUTH).status_code == 400
    assert client.post("/api/sessions/create", json={"project": "beta", "worktree": "f"},
                       headers=AUTH).status_code == 409
    assert launched == []


def test_create_is_audited(client, root, launched, tmp_path):
    from ctb_dashboard import control_audit
    client.post("/api/sessions/create", json={"project": "alpha"}, headers=AUTH)
    entries = Path(control_audit.AUDIT_PATH).read_text().strip().splitlines()
    assert any('"create"' in e and "claude_alpha" in e for e in entries)


# --- reported failures that used to be silent -------------------------------


def test_duplicate_session_race_reports_exists_not_an_error(root, launched, monkeypatch):
    """Two taps race past the exists-check; tmux settles it, and the loser's
    session does exist -- which is what was asked for, not a 502."""
    live = set()

    def dup(session, path):
        live.add(session)  # the other request won while we were checking
        raise CreateError("tmux_failed", "duplicate session: claude_alpha")

    monkeypatch.setattr(session_create, "launch_session", dup)
    monkeypatch.setattr(session_create, "_live_sessions", lambda: set(live))
    r = session_create.create_session(project="alpha")
    assert r["status"] == "exists"


def test_other_tmux_failures_still_raise(root, monkeypatch):
    def dead(session, path):
        raise CreateError("tmux_failed", "no server running on /tmp/tmux-1000/default")

    monkeypatch.setattr(session_create, "launch_session", dead)
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="alpha")
    assert e.value.code == "tmux_failed"


def test_project_reads_are_rate_limited(client, root):
    """Unauthenticated and git-spawning: they need a budget of their own."""
    from ctb_dashboard import server as srv

    srv._project_read_limiter.reset()
    monkey = srv._project_read_limiter
    monkey.max_events = 3
    try:
        codes = [client.get("/api/projects").status_code for _ in range(5)]
        assert 429 in codes
    finally:
        monkey.max_events = 120
        monkey.reset()


def test_read_flood_does_not_starve_control_writes(client, root, launched):
    """A read flood must not spend the budget that stopping a session needs."""
    from ctb_dashboard import server as srv

    srv._project_read_limiter.reset()
    srv._project_read_limiter.max_events = 2
    try:
        for _ in range(6):
            client.get("/api/projects")
        r = client.post("/api/sessions/create", json={"project": "alpha"}, headers=AUTH)
        assert r.status_code == 200, r.text
    finally:
        srv._project_read_limiter.max_events = 120
        srv._project_read_limiter.reset()


def test_failed_git_init_leaves_no_directory_behind(root, launched, monkeypatch):
    """Otherwise every retry answers '이미 있습니다' about a project that never
    got made -- a lie that never clears itself."""
    monkeypatch.setattr(
        session_create, "_run",
        lambda argv, timeout=None: subprocess.CompletedProcess(argv, 1, "", "disk full"))
    with pytest.raises(CreateError) as e:
        session_create.create_session(new_project="gamma")
    assert e.value.code == "git_init_failed"
    assert not (root / "gamma").exists()
    assert launched == []


def test_failed_initial_commit_fails_the_create(root, launched, monkeypatch):
    """A repo with no commit does not fail `git worktree add -b` -- it silently
    produces an orphan branch. So the commit failure has to stop things here."""
    real_git = session_create._git

    def no_commit(cwd, *args, **kw):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess([], 1, "", "no user.email")
        return real_git(cwd, *args, **kw)

    monkeypatch.setattr(session_create, "_git", no_commit)
    with pytest.raises(CreateError) as e:
        session_create.create_session(new_project="gamma")
    assert e.value.code == "git_init_failed"
    assert "user.name" in e.value.message or "user.email" in e.value.message
    assert not (root / "gamma").exists()
    assert launched == []


def test_a_retry_after_a_failed_create_succeeds(root, launched, monkeypatch):
    """The point of the rollback: the same name works on the next attempt."""
    calls = {"n": 0}
    real_run = session_create._run

    def flaky(argv, timeout=None):
        if calls["n"] == 0 and argv[:2] == ["git", "init"]:
            calls["n"] += 1
            return subprocess.CompletedProcess(argv, 1, "", "transient")
        return real_run(argv, timeout=timeout)

    monkeypatch.setattr(session_create, "_run", flaky)
    with pytest.raises(CreateError):
        session_create.create_session(new_project="gamma")
    r = session_create.create_session(new_project="gamma")
    assert r["status"] == "created"
    assert (root / "gamma" / ".git").exists()


def test_project_dir_survives_a_failure_that_predates_it(root, launched, monkeypatch):
    """Rollback must only ever remove what this call created."""
    with pytest.raises(CreateError):
        session_create.create_session(new_project="alpha")  # already exists
    assert (root / "alpha" / "f.txt").exists()


def test_worktree_error_reports_the_attempt_that_decided_it(root, monkeypatch):
    """The fallback's message, not the first attempt's 'branch already exists'."""
    def both_fail(cwd, *args, **kw):
        if args[:2] == ("worktree", "add"):
            if "-b" in args:
                return subprocess.CompletedProcess([], 1, "", "branch already exists")
            return subprocess.CompletedProcess([], 1, "", "already used by worktree")
        return subprocess.CompletedProcess([], 0, "true", "")

    monkeypatch.setattr(session_create, "_git", both_fail)
    monkeypatch.setattr(session_create, "_is_git_repo", lambda p: True)
    with pytest.raises(CreateError) as e:
        session_create.create_session(project="alpha", worktree="feat")
    assert "already used by worktree" in e.value.message


def test_leading_underscore_worktree_is_allowed_like_cs(root, launched):
    r = session_create.create_session(project="alpha", worktree="_scratch")
    assert r["session"] == "claude_alpha_wt__scratch"


def test_created_session_names_survive_the_dashboard_session_filter():
    """A session the dashboard cannot see is a session that was never created."""
    from ctb_dashboard import sessions as sessions_mod

    raw = "claude_alpha\nclaude_alpha_wt_feat\nclaude-multi-monitor\n"
    kept = [s for s in raw.split("\n") if s.strip()]
    kept = [s for s in kept if s not in (
        "claude-multi-monitor", "claude-monitor", "claude-telegram-bridge")]
    assert kept == ["claude_alpha", "claude_alpha_wt_feat"]
    # And the filter the module actually applies is the one modelled above.
    src = Path(sessions_mod.__file__).read_text()
    assert "grep '^claude'" in src
    assert "'claude-multi-monitor', 'claude-monitor', 'claude-telegram-bridge'," in src
