"""Relaunching Claude in a pane attaches to a background session that holds it.

Claude Code 2.1.x can move a conversation into its background daemon (a
slash command forked claude_hire's conversation that way). After that,
``claude --continue`` in the pane refuses: "Your most recent conversation is
running in the background", and drops to bash. The dashboard's relaunch then
typed the same refused command again on every tap, which read as a session
restarting for no reason. The right command in that state is
``claude attach <id>``; ``claude agents --json`` says which id.
"""

import json
from pathlib import Path

import ctb_dashboard.session_create as sc


def _agents(monkeypatch, rows):
    monkeypatch.setattr(sc, "_agents_json", lambda: rows)


def test_attaches_when_a_live_background_session_holds_the_directory(monkeypatch):
    _agents(monkeypatch, [
        {"pid": 1, "id": "3a924ddc", "cwd": "/home/u/projects/hire", "kind": "background",
         "startedAt": 1788767350367, "sessionId": "3a924ddc-d296"},
    ])
    assert sc.claude_command(Path("/home/u/projects/hire")) == "claude attach 3a924ddc"


def test_newest_live_background_session_wins(monkeypatch):
    _agents(monkeypatch, [
        {"pid": 1, "id": "old1", "cwd": "/p", "kind": "background", "startedAt": 10},
        {"pid": 2, "id": "new2", "cwd": "/p", "kind": "background", "startedAt": 20},
    ])
    assert sc.claude_command(Path("/p")) == "claude attach new2"


def test_ignores_dead_background_and_other_directories_and_interactive(monkeypatch):
    _agents(monkeypatch, [
        {"id": "dead", "cwd": "/p", "kind": "background", "startedAt": 30},          # no pid
        {"pid": 5, "id": "else", "cwd": "/q", "kind": "background", "startedAt": 40},
        {"pid": 6, "id": "me", "cwd": "/p", "kind": "interactive", "startedAt": 50},
    ])
    monkeypatch.setattr(sc, "_claude_history_exists", lambda p: True)
    assert sc.claude_command(Path("/p")) == "claude --continue --dangerously-skip-permissions"


def test_fresh_directory_gets_no_continue(monkeypatch):
    _agents(monkeypatch, [])
    monkeypatch.setattr(sc, "_claude_history_exists", lambda p: False)
    assert sc.claude_command(Path("/p")) == "claude --dangerously-skip-permissions"


def test_agents_query_failure_falls_back_to_continue(monkeypatch):
    def boom():
        raise RuntimeError("no daemon")
    monkeypatch.setattr(sc, "_agents_json", boom)
    monkeypatch.setattr(sc, "_claude_history_exists", lambda p: True)
    assert sc.claude_command(Path("/p")) == "claude --continue --dangerously-skip-permissions"


def test_honours_claude_bin_override(monkeypatch):
    _agents(monkeypatch, [{"pid": 1, "id": "abc", "cwd": "/p", "kind": "background", "startedAt": 1}])
    monkeypatch.setenv("CTB_CLAUDE_BIN", "/opt/claude")
    assert sc.claude_command(Path("/p")) == "/opt/claude attach abc"


def test_agents_json_parses_the_cli_output(monkeypatch):
    class R:
        returncode = 0
        stdout = json.dumps([{"id": "x", "cwd": "/p", "kind": "background", "pid": 1}])
    monkeypatch.setattr(sc, "_run", lambda argv, timeout=0: R())
    assert sc._agents_json()[0]["id"] == "x"
