"""The poller must never read a bash-only session's screen.

_probe_session parses screen content into last_prompt/last_reply/recap, and
those land in the SSE snapshot, the completion push body, and
_last_known_prompt -- any one of which would put typed secrets somewhere
they must never go. So a session marked @ctb_shell skips the probe
entirely and gets a blank, state-"idle" entry instead.
"""

import ctb_dashboard.server as _srv


def test_shell_session_is_not_probed(monkeypatch):
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: ["claude_a", "claude_b_sh"])
    monkeypatch.setattr(_srv, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(_srv, "load_context_by_tmux_session", lambda: {})
    monkeypatch.setattr(_srv, "shell_sessions", lambda *a, **k: {"claude_b_sh"})
    monkeypatch.setattr(_srv, "get_session_path", lambda name: f"/tmp/{name}")

    probed = []

    def fake_probe(name):
        probed.append(name)
        return (name, "working", f"/tmp/{name}", 10, "secret prompt", "ctx",
                None, None, None, "secret reply", "secret recap")

    monkeypatch.setattr(_srv, "_probe_session", fake_probe)

    snapshot = _srv._poll_sessions()

    assert probed == ["claude_a"], "the shell session must never reach _probe_session"
    by_name = {s["name"]: s for s in snapshot["sessions"]}

    shell_entry = by_name["claude_b_sh"]
    assert shell_entry["shell"] is True
    assert shell_entry["state"] == "idle"
    assert shell_entry["last_prompt"] == ""
    assert shell_entry["work_context"] == ""
    assert shell_entry["last_reply"] == ""
    assert shell_entry["recap"] == ""
    assert shell_entry["pending_count"] is None
    assert shell_entry["context_percent"] is None
    assert shell_entry["path"] == "/tmp/claude_b_sh"

    assert by_name["claude_a"]["shell"] is False


def test_poll_passes_the_session_list_as_candidates(monkeypatch):
    """shell_sessions()'s name-suffix fallback (item 5) only works if it is
    given the live session list to check -- the poller is the one caller
    that has it, so it must pass it through."""
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: ["claude_a", "claude_b_sh"])
    monkeypatch.setattr(_srv, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(_srv, "load_context_by_tmux_session", lambda: {})
    monkeypatch.setattr(_srv, "get_session_path", lambda name: f"/tmp/{name}")
    monkeypatch.setattr(_srv, "_probe_session",
                        lambda name: (name, "idle", f"/tmp/{name}", None, None, "",
                                      None, None, None, "", ""))

    seen = {}

    def spy(candidates=None):
        seen["candidates"] = candidates
        return set()

    monkeypatch.setattr(_srv, "shell_sessions", spy)
    _srv._poll_sessions()
    assert seen["candidates"] == ["claude_a", "claude_b_sh"]


def test_shell_sessions_are_excluded_from_pushes(monkeypatch):
    pushed = []
    monkeypatch.setattr(_srv, "pinned_session_names", lambda: {"claude_b_sh"})
    monkeypatch.setattr(_srv.push, "notify",
                        lambda name, body, title=None: pushed.append(name) or 1)

    entry = {"name": "claude_b_sh", "completed_at": 1234.0, "shell": True}
    _srv._push_completions([entry])
    assert pushed == []


def test_shell_sessions_are_excluded_from_unsent_draft_nags(monkeypatch):
    """A naive check here passes even with the guard missing: on a single
    call, _push_unsent_drafts only ever *starts* the wait clock (it needs
    _UNSENT_AFTER_S of the same text before it pushes), so a plain "no push
    yet" assertion is true regardless. Pre-seeding _unsent_seen with an old
    timestamp is what makes this test fail without the guard -- and
    asserting _box_draft is never even called is the part that would catch
    a guard that checked `shell` too late, after already reading the box."""
    pushed = []
    box_draft_calls = []
    monkeypatch.setattr(_srv, "pinned_session_names", lambda: {"claude_b_sh"})
    monkeypatch.setattr(_srv.push, "notify",
                        lambda name, body, title=None: pushed.append(name) or 1)

    def spy_box_draft(name):
        box_draft_calls.append(name)
        return ("secret text", False)

    monkeypatch.setattr(_srv, "_box_draft", spy_box_draft)
    _srv._unsent_seen["claude_b_sh"] = ("secret text", 0.0)  # far in the past
    try:
        entry = {"name": "claude_b_sh", "shell": True}
        _srv._push_unsent_drafts([entry])
        assert pushed == []
        assert box_draft_calls == [], "a shell session's input box must never be read at all"
    finally:
        _srv._unsent_seen.pop("claude_b_sh", None)
