"""_poll_sessions prefers Claude Code's own per-session context-usage file
over the screen-scraped value, falling back to the scrape when the file has
no entry for that tmux session."""

import ctb_dashboard.server as _srv


def test_file_source_overrides_scrape_and_scrape_is_fallback(monkeypatch):
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: ["claude_a", "claude_b"])
    monkeypatch.setattr(_srv, "get_sessions_activity", lambda: {})
    monkeypatch.setattr(_srv, "load_context_by_tmux_session", lambda: {"claude_a": 72})

    def fake_probe(name):
        scraped = 10 if name == "claude_a" else 33
        return (name, "idle", "/tmp/" + name, scraped, None, "", None, None, None, "", "")

    monkeypatch.setattr(_srv, "_probe_session", fake_probe)

    snapshot = _srv._poll_sessions()
    by_name = {s["name"]: s for s in snapshot["sessions"]}
    assert by_name["claude_a"]["context_percent"] == 72
    assert by_name["claude_b"]["context_percent"] == 33
