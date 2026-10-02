"""Starting the dashboard takes the port back from a previous dashboard -- and
from nothing else.

`lsof -ti :PORT` lists every process with a socket on that port, clients
included: a browser tab, or tailscaled proxying `tailscale serve` to it. The
old code SIGKILLed all of them. Only a LISTENING process that is itself
ctb-dashboard may be killed.
"""

import os
import subprocess
import sys

import pytest

from ctb_dashboard import server


class _Run:
    def __init__(self, out):
        self.out = out
        self.argv = None

    def __call__(self, argv, **kw):
        self.argv = argv
        return subprocess.CompletedProcess(argv, 0, stdout=self.out, stderr="")


@pytest.fixture
def killed(monkeypatch):
    sent = []
    monkeypatch.setattr(server.os, "kill", lambda pid, sig: sent.append(pid))
    return sent


def test_only_listeners_are_asked_for(monkeypatch, killed):
    run = _Run("")
    monkeypatch.setattr(subprocess, "run", run)
    server._kill_previous_on_port(8420)
    assert "-sTCP:LISTEN" in run.argv


def test_a_previous_dashboard_is_killed(monkeypatch, killed):
    monkeypatch.setattr(subprocess, "run", _Run("111\n"))
    monkeypatch.setattr(server, "_cmdline", lambda pid: "/x/.venv/bin/python3 /x/.venv/bin/ctb-dashboard")
    server._kill_previous_on_port(8420)
    assert killed == [111]


def test_some_other_program_on_the_port_is_left_alone(monkeypatch, killed):
    monkeypatch.setattr(subprocess, "run", _Run("222\n"))
    monkeypatch.setattr(server, "_cmdline", lambda pid: "/usr/sbin/tailscaled --state=x")
    server._kill_previous_on_port(8420)
    assert killed == []


def test_an_unreadable_process_is_left_alone(monkeypatch, killed):
    monkeypatch.setattr(subprocess, "run", _Run("333\n"))
    monkeypatch.setattr(server, "_cmdline", lambda pid: "")
    server._kill_previous_on_port(8420)
    assert killed == []


def test_the_port_comes_from_the_environment():
    out = subprocess.run(
        [sys.executable, "-c", "from ctb_dashboard import server; print(server.BIND_PORT)"],
        capture_output=True, text=True, env={**os.environ, "CTB_BIND_PORT": "18421"},
    )
    assert out.stdout.strip().splitlines()[-1] == "18421"
