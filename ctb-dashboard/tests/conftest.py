"""Shared fixtures.

The control rate limiter is process-global by design -- it protects tmux and the
host, so one budget for the whole server is the point. That makes it shared
state across tests, where one module's sends would otherwise throttle the next
module's. Reset it around every test rather than weakening the production
design.
"""

import pytest

from ctb_dashboard.control_audit import limiter


@pytest.fixture(autouse=True)
def _reset_control_rate_limiter():
    # The project-read limiter is a second global budget with the same problem:
    # one module's reads would otherwise throttle the next module's.
    from ctb_dashboard.server import _project_read_limiter

    limiter.reset()
    _project_read_limiter.reset()
    yield
    limiter.reset()
    _project_read_limiter.reset()

import os
import shlex
import subprocess


@pytest.fixture(autouse=True)
def _no_live_system(monkeypatch, tmp_path):
    """No test may drive the machine the suite runs on.

    This suite runs on the host it monitors, against ~75 real Claude sessions.
    Twice that leaked: a gate test posted to /api/focus-session and tmux really
    switched the terminal out from under whoever was working, creating and
    removing a session called some-session; another posted an empty pin set
    that landed on the user's actual pins and wiped them on every run. Both were
    invisible because nothing recorded either action.

    Stubbing per-file did not hold -- seven test modules can reach these paths.
    So the guard is global: tmux is refused outright, and the two files that
    hold real user state are redirected into a temporary directory. Other
    programs (node, git) still run, because tests legitimately use them.
    """
    def _mentions_tmux(args) -> bool:
        """Catch tmux however it is spelled.

        argv[0] alone was not enough: sessions.py and state_detector.py run
        their tmux commands with shell=True, so the whole command arrives as
        one string and the basename check waved it through. Those reads went
        to the live server on every suite run.
        """
        words = []
        if isinstance(args, str):
            try:
                words = shlex.split(args)
            except ValueError:
                words = args.split()
        elif isinstance(args, (list, tuple)):
            words = [str(x) for x in args]
        return any(os.path.basename(w) == "tmux" for w in words)

    for name in ("run", "Popen"):
        real = getattr(subprocess, name)

        def guard(args, *a, _real=real, **k):
            if _mentions_tmux(args):
                shown = args if isinstance(args, str) else " ".join(map(str, list(args)[:4]))
                raise AssertionError(
                    "a test invoked live tmux: " + str(shown)[:120]
                    + " -- stub it; this host has real sessions."
                )
            return _real(args, *a, **k)

        monkeypatch.setattr(subprocess, name, guard)

    _real_system = os.system

    def _system_guard(cmd):
        if _mentions_tmux(cmd):
            raise AssertionError("a test invoked live tmux via os.system: " + str(cmd)[:120])
        return _real_system(cmd)

    monkeypatch.setattr(os, "system", _system_guard)

    from ctb_dashboard import server
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(server, "_TS_PERSIST_PATH", str(tmp_path / "timestamps.json"))
    # The VSCode extension watches this and focuses the terminal it names.
    monkeypatch.setattr(server, "_FOCUS_SIGNAL_PATH", str(tmp_path / "focus-signal.json"))

    # The audit log is the user's record of who drove their sessions. Test runs
    # were filling it -- 2726 entries at one point, which buried the handful of
    # real ones when a fault had to be traced.
    from ctb_dashboard import control_audit
    monkeypatch.setattr(control_audit, "AUDIT_PATH", str(tmp_path / "audit.log"))

    # Endpoints read the pane before acting. Harmless defaults, so a test about
    # something else does not have to know tmux exists; tests that care set
    # their own afterwards and win, since this fixture runs first.
    monkeypatch.setattr(server, "pane_command", lambda name: "claude")
    monkeypatch.setattr(server, "pane_has_claude", lambda name: True)

