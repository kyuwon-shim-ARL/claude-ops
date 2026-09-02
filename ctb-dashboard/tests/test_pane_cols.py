"""The pane width the console uses to tell a wrapped line from a whole one.

The value decides whether a URL split across two rows is rejoined, so the
failure modes matter more than the happy path: a wrong width joins nothing
(harmless) or joins the wrong thing (a link to an address nobody published).
"""

import subprocess

import pytest

import ctb_dashboard.server as _srv


@pytest.fixture(autouse=True)
def _clear_cache():
    _srv._PANE_COLS.clear()
    yield
    _srv._PANE_COLS.clear()


def _probe(monkeypatch, stdout="", returncode=0, exc=None):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    monkeypatch.setattr(_srv.subprocess, "run", fake_run)
    return calls


def test_asks_tmux_for_the_pane_width_not_the_window_width(monkeypatch):
    """A vertically split window holds panes half its width.

    capture-pane captures a pane, so the window's width there is about double
    the columns the text was actually wrapped at -- no row would ever match and
    the rejoin would quietly never fire.
    """
    calls = _probe(monkeypatch, stdout="97\n")
    assert _srv._pane_cols("claude_demo") == 97
    assert calls == [["tmux", "display", "-p", "-t", "claude_demo", "#{pane_width}"]]


def test_the_width_is_asked_once_and_then_remembered(monkeypatch):
    """It changes only on a resize, and the console polls every two seconds."""
    calls = _probe(monkeypatch, stdout="120\n")
    assert [_srv._pane_cols("claude_demo") for _ in range(5)] == [120] * 5
    assert len(calls) == 1


def test_a_resize_drops_the_remembered_width(monkeypatch):
    """_fit_pane widens the pane; the next poll must not describe the old one."""
    _probe(monkeypatch, stdout="80\n")
    assert _srv._pane_cols("claude_demo") == 80
    monkeypatch.setattr(_srv, "session_exists", lambda n: True)
    _probe(monkeypatch, stdout="0 80 40\n")   # attached=0 width=80 height=40
    _srv._fit_pane("claude_demo", 140)
    assert "claude_demo" not in _srv._PANE_COLS


@pytest.mark.parametrize("kwargs", [
    {"returncode": 1},                                   # tmux said no
    {"stdout": "not-a-number\n"},                        # tmux said nonsense
    {"stdout": "\n"},                                    # tmux said nothing
    {"exc": subprocess.TimeoutExpired("tmux", 5)},       # tmux said nothing, slowly
])
def test_an_unanswered_probe_reports_zero(monkeypatch, kwargs):
    """0 is the console's 'do not guess' -- it then joins nothing at all."""
    _probe(monkeypatch, **kwargs)
    assert _srv._pane_cols("claude_demo") == 0


def test_a_failed_probe_is_not_cached(monkeypatch):
    """A session that was busy once must not be written off for the session."""
    _probe(monkeypatch, returncode=1)
    assert _srv._pane_cols("claude_demo") == 0
    _probe(monkeypatch, stdout="100\n")
    assert _srv._pane_cols("claude_demo") == 100
