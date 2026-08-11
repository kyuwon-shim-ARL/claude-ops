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
    limiter.reset()
    yield
    limiter.reset()

import os
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
    for name in ("run", "Popen"):
        real = getattr(subprocess, name)

        def guard(args, *a, _real=real, **k):
            argv = args if isinstance(args, (list, tuple)) else [args]
            program = os.path.basename(str(argv[0])) if argv else ""
            if program == "tmux":
                raise AssertionError(
                    "a test invoked live tmux: " + " ".join(map(str, list(argv)[:4]))
                    + " -- stub it; this host has real sessions."
                )
            return _real(args, *a, **k)

        monkeypatch.setattr(subprocess, name, guard)

    from ctb_dashboard import server
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(tmp_path / "pinned.json"))
    monkeypatch.setattr(server, "_TS_PERSIST_PATH", str(tmp_path / "timestamps.json"))

    # Endpoints read the pane before acting. Harmless defaults, so a test about
    # something else does not have to know tmux exists; tests that care set
    # their own afterwards and win, since this fixture runs first.
    monkeypatch.setattr(server, "pane_command", lambda name: "claude")
    monkeypatch.setattr(server, "pane_has_claude", lambda name: True)
