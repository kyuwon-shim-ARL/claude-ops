"""Creating a bash-only session from the dashboard.

Same create_session entry point, a `shell=True` flag. The point is a tmux
session with no Claude in it and no history file -- this is the path meant
for typing passwords and API keys -- marked with the `@ctb_shell` tmux
option so the rest of the system (readiness gate, poller, Telegram bridge)
can tell it apart from a real Claude session.
"""

import subprocess

import pytest

from ctb_dashboard import session_create
from ctb_dashboard.session_create import CreateError, create_session


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("CTB_PROJECTS_ROOT", str(root))
    repo = root / "alpha"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    return root


@pytest.fixture
def tmux(monkeypatch):
    """Record tmux argv instead of starting anything, and pretend nothing
    is live unless a test says otherwise."""
    calls = []

    def fake_run(argv, timeout=None):
        calls.append(argv)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(session_create, "_run", fake_run)
    monkeypatch.setattr(session_create, "_live_sessions", lambda: set())
    return calls


def test_shell_session_name_has_sh_suffix(root, tmux):
    result = create_session(project="alpha", shell=True)
    assert result["session"] == "claude_alpha_sh"


def test_shell_launch_uses_a_history_less_login_shell_with_no_claude(root, tmux):
    create_session(project="alpha", shell=True)
    # Create-and-mark is one tmux invocation (see launch_shell_session): a
    # ';' argv element chains `set-option` onto the same `new-session` call
    # so there is no window where the session exists but is not yet marked.
    launches = [c for c in tmux if "new-session" in c]
    assert len(launches) == 1
    argv = launches[0]
    assert "new-session" in argv and ";" in argv and "set-option" in argv
    command = argv[argv.index("new-session"):argv.index(";")][-1]
    assert "HISTFILE=/dev/null" in command
    assert "bash --login" in command
    assert "claude" not in command


def test_shell_launch_sets_the_ctb_shell_marker_in_the_same_call(root, tmux):
    create_session(project="alpha", shell=True)
    # `=NAME:` (target-pane form), not `=NAME`: verified live on tmux 3.6a --
    # an option command's `-t` takes a target-pane, and the bare `=NAME`
    # exact-match form that works for a session target does not apply here.
    launches = [c for c in tmux if "new-session" in c]
    assert launches[0][-5:] == ["set-option", "-t", "=claude_alpha_sh:", "@ctb_shell", "1"]


def test_shell_launch_does_not_set_remain_on_exit(root, tmux):
    create_session(project="alpha", shell=True)
    assert not any(c[:2] == ["tmux", "set-window-option"] for c in tmux)


def test_marker_failure_kills_the_session_and_raises(root, tmux, monkeypatch):
    """If the chained set-option fails, tmux still created the session (the
    chain is not transactional) -- left alone that is an unmarked pane a
    later 'exists' create could hand back as if it were a shell session."""
    killed = []

    def fake_run(argv, timeout=None):
        tmux.append(argv)

        class R:
            returncode = 1 if "new-session" in argv else 0
            stdout = ""
            stderr = "no such session"
        if argv[:2] == ["tmux", "kill-session"]:
            killed.append(argv)
        return R()

    monkeypatch.setattr(session_create, "_run", fake_run)
    with pytest.raises(CreateError) as exc:
        create_session(project="alpha", shell=True)
    assert exc.value.code == "tmux_failed"
    assert killed == [["tmux", "kill-session", "-t", "claude_alpha_sh"]]


def test_non_shell_create_is_unaffected(root, tmux):
    result = create_session(project="alpha")
    assert result["session"] == "claude_alpha"
    new_session_calls = [c for c in tmux if c[:2] == ["tmux", "new-session"]]
    assert "claude" in new_session_calls[0][-1]


def test_existing_shell_session_reports_exists(root, tmux, monkeypatch):
    monkeypatch.setattr(session_create, "_live_sessions", lambda: {"claude_alpha_sh"})
    monkeypatch.setattr(session_create, "is_shell_session", lambda name: True)
    result = create_session(project="alpha", shell=True)
    assert result["status"] == "exists"


def test_name_taken_by_a_non_shell_session_is_refused(root, tmux, monkeypatch):
    """A plain Claude session already holds the '<name>_sh' name (unlikely,
    but not impossible -- a project literally named '..._sh'); creating a
    shell session there must not silently reuse someone else's pane."""
    monkeypatch.setattr(session_create, "_live_sessions", lambda: {"claude_alpha_sh"})
    monkeypatch.setattr(session_create, "is_shell_session", lambda name: False)
    with pytest.raises(CreateError) as exc:
        create_session(project="alpha", shell=True)
    assert exc.value.code == "name_taken"
