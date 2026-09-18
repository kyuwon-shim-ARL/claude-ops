"""Context-window usage per tmux session, read from Claude Code's own files
(not screen-scraped). Fabricates a tmp config dir (sessions/*.json +
hud/cache/stdin.*.json) and a fake /proc tree for liveness."""

import json
import os

import pytest

from ctb_dashboard.context_usage import load_context_by_tmux_session, _pid_matches


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _make_proc(proc_root, pid, comm="claude", starttime="123"):
    d = proc_root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "comm").write_text(comm + "\n")
    # Minimal realistic /proc/<pid>/stat: "pid (comm) S ... <22 fields after state>"
    # field 22 (starttime) is index 22-3=19 in the space-split remainder after ')'.
    rest_fields = ["S"] + ["0"] * 18 + [starttime] + ["0", "0"]
    (d / "stat").write_text(f"{pid} ({comm}) " + " ".join(rest_fields) + "\n")


def _session_entry(tmux, session_id, pid, proc_start="123", started_at=None):
    entry = {"tmux": tmux, "sessionId": session_id, "pid": pid, "procStart": proc_start}
    if started_at is not None:
        entry["startedAt"] = started_at
    return entry


def _cache(pct):
    return {"context_window": {"used_percentage": pct, "context_window_size": 200000}}


class TestPidMatches:
    def test_matches_live_claude_pid_with_correct_starttime(self, tmp_path):
        _make_proc(tmp_path, 111, comm="claude", starttime="999")
        assert _pid_matches(111, "999", proc_root=str(tmp_path)) is True

    def test_rejects_starttime_mismatch_pid_reuse(self, tmp_path):
        _make_proc(tmp_path, 111, comm="claude", starttime="999")
        assert _pid_matches(111, "111", proc_root=str(tmp_path)) is False

    def test_rejects_non_claude_comm(self, tmp_path):
        _make_proc(tmp_path, 111, comm="bash", starttime="999")
        assert _pid_matches(111, "999", proc_root=str(tmp_path)) is False

    def test_rejects_missing_pid_dir(self, tmp_path):
        assert _pid_matches(404, "999", proc_root=str(tmp_path)) is False


class TestLoadContextByTmuxSession:
    def test_happy_path_mapping(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 42}

    def test_dead_pid_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: False)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_comm_not_claude_skipped(self, tmp_path, monkeypatch):
        # Exercise the real _pid_matches against a fabricated /proc tree
        # whose comm is not "claude".
        proc_root = tmp_path / "proc"
        _make_proc(proc_root, 111, comm="bash", starttime="999")
        monkeypatch.setattr(
            "ctb_dashboard.context_usage._pid_matches",
            lambda pid, ps, proc_root=str(proc_root), **k: _pid_matches(pid, ps, proc_root=proc_root),
        )
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111, proc_start="999"))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_duplicate_name_resolved_by_active_pane(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-1", 111))
        _write_json(cfg / "sessions" / "s2.json",
                    _session_entry("claude_a:@2.%2", "sid-2", 222))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-1.json", _cache(10))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-2.json", _cache(90))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={"claude_a": "%2"})
        assert result == {"claude_a": 90}

    def test_duplicate_name_dropped_when_no_pane_matches(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-1", 111))
        _write_json(cfg / "sessions" / "s2.json",
                    _session_entry("claude_a:@2.%2", "sid-2", 222))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-1.json", _cache(10))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-2.json", _cache(90))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={"claude_a": "%99"})
        assert result == {}

    @pytest.mark.parametrize("bad", [True, False, None, "50"])
    def test_bool_none_str_used_percentage_rejected(self, tmp_path, monkeypatch, bad):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(bad))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_clamp_above_100(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(150))
        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 100}

    def test_clamp_below_0(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(-5))
        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 0}

    def test_zero_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(0))
        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 0}

    def test_malformed_sessions_json_isolated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        (cfg / "sessions").mkdir(parents=True)
        (cfg / "sessions" / "bad.json").write_text("{not json")
        _write_json(cfg / "sessions" / "good.json",
                    _session_entry("claude_b:@1.%1", "sid-b", 222))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-b.json", _cache(33))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_b": 33}

    def test_malformed_cache_json_isolated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "sessions" / "s2.json",
                    _session_entry("claude_b:@1.%1", "sid-b", 222))
        (cfg / "hud" / "cache").mkdir(parents=True)
        (cfg / "hud" / "cache" / "stdin.sid-a.json").write_text("{not json")
        _write_json(cfg / "hud" / "cache" / "stdin.sid-b.json", _cache(20))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_b": 20}

    def test_entries_without_tmux_field_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    {"sessionId": "sid-a", "pid": 111, "procStart": "1"})
        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_missing_cache_file_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_single_entry_rejected_when_pane_does_not_match_active(self, tmp_path, monkeypatch):
        """A single live entry is not exempt from the active-pane check when
        the session's name IS present in active_panes -- only absence from
        active_panes (tmux call failed / no rows for that name) allows the
        single-entry fallback."""
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={"claude_a": "%99"})
        assert result == {}

    def test_single_entry_accepted_when_name_absent_from_active_panes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        # active_panes has rows for other sessions, but nothing for claude_a --
        # tmux either failed for it or it has no window/pane agreement.
        result = load_context_by_tmux_session(
            config_dir=str(cfg), active_panes={"claude_other": "%5"})
        assert result == {"claude_a": 42}

    def test_single_entry_accepted_when_pane_matches_active(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={"claude_a": "%1"})
        assert result == {"claude_a": 42}


class TestCacheFreshness:
    """A cache file must be at least as new as the process it is reporting
    on. startedAt is ms epoch; the cache's mtime is seconds epoch."""

    def test_cache_older_than_started_at_is_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        cache_path = cfg / "hud" / "cache" / "stdin.sid-a.json"
        _write_json(cache_path, _cache(42))
        old_mtime = 1_000_000.0
        os.utime(cache_path, (old_mtime, old_mtime))
        started_at_ms = int((old_mtime + 3600) * 1000)  # process started an hour later
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111, started_at=started_at_ms))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {}

    def test_cache_newer_than_started_at_is_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        cache_path = cfg / "hud" / "cache" / "stdin.sid-a.json"
        _write_json(cache_path, _cache(42))
        new_mtime = 2_000_000.0
        os.utime(cache_path, (new_mtime, new_mtime))
        started_at_ms = int((new_mtime - 3600) * 1000)  # process started an hour earlier
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111, started_at=started_at_ms))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 42}

    def test_missing_started_at_skips_gate(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111))  # no startedAt

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 42}

    def test_invalid_started_at_skips_gate(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ctb_dashboard.context_usage._pid_matches", lambda *a, **k: True)
        cfg = tmp_path / "cfg"
        _write_json(cfg / "hud" / "cache" / "stdin.sid-a.json", _cache(42))
        _write_json(cfg / "sessions" / "s1.json",
                    _session_entry("claude_a:@1.%1", "sid-a", 111, started_at="not-a-number"))

        result = load_context_by_tmux_session(config_dir=str(cfg), active_panes={})
        assert result == {"claude_a": 42}
