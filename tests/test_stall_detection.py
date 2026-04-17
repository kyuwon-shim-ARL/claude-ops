"""Tests for stall detection multi-signal logic (_check_stall_signals)."""

import pytest
from unittest.mock import patch, MagicMock
import sys


class TestCheckStallSignals:
    """Tests for MultiSessionMonitor._check_stall_signals()"""

    def _make_monitor(self):
        """Create a minimal MultiSessionMonitor with mocked dependencies."""
        from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
        monitor = MultiSessionMonitor.__new__(MultiSessionMonitor)
        monitor.notifier = MagicMock()
        return monitor

    def test_bash_child_true_returns_working(self):
        """(a) bash child 존재 시 bash_child=True 반환."""
        monitor = self._make_monitor()

        mock_child = MagicMock()
        mock_child.name.return_value = "bash"
        mock_child.cmdline.return_value = ["bash"]  # -c 없음
        mock_proc = MagicMock()
        mock_proc.children.return_value = [mock_child]

        with patch.object(monitor, '_get_claude_pid', return_value=12345):
            with patch('psutil.Process', return_value=mock_proc):
                with patch.object(monitor, '_get_net_established', return_value=0):
                    bash_child, net_est = monitor._check_stall_signals("test_session")

        assert bash_child is True
        assert net_est == 0

    def test_fallback_on_psutil_import_error(self):
        """(b1) psutil 미설치 시 subprocess ps 폴백 → 정상 동작."""
        monitor = self._make_monitor()

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'psutil':
                raise ImportError("No module named 'psutil'")
            return real_import(name, *args, **kwargs)

        with patch.object(monitor, '_get_claude_pid', return_value=12345):
            with patch('builtins.__import__', side_effect=mock_import):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(stdout="", returncode=0)
                    with patch.object(monitor, '_get_net_established', return_value=0):
                        bash_child, net_est = monitor._check_stall_signals("test_session")

        assert isinstance(bash_child, bool)
        assert isinstance(net_est, int)

    def test_fallback_on_permission_error(self):
        """(b2) psutil.AccessDenied → 외부 except Exception 에 잡혀 (False, 0) 반환."""
        monitor = self._make_monitor()

        import psutil as _psutil

        with patch.object(monitor, '_get_claude_pid', return_value=12345):
            with patch('psutil.Process', side_effect=_psutil.AccessDenied(12345)):
                bash_child, net_est = monitor._check_stall_signals("test_session")

        assert bash_child is False
        assert net_est == 0

    def test_fallback_on_no_claude_pid(self):
        """(b3) claude PID 없음 → early return (False, 0)."""
        monitor = self._make_monitor()

        with patch.object(monitor, '_get_claude_pid', return_value=None):
            bash_child, net_est = monitor._check_stall_signals("test_session")

        assert bash_child is False
        assert net_est == 0

    def test_no_bash_child_no_net_falls_through(self):
        """(c) bash_child=False, net_est=0 → screen 로직으로 넘어가야 함."""
        monitor = self._make_monitor()

        mock_proc = MagicMock()
        mock_proc.children.return_value = []  # 자식 없음

        with patch.object(monitor, '_get_claude_pid', return_value=12345):
            with patch('psutil.Process', return_value=mock_proc):
                with patch.object(monitor, '_get_net_established', return_value=0):
                    bash_child, net_est = monitor._check_stall_signals("test_session")

        assert bash_child is False
        assert net_est == 0

    def test_net_established_positive_returns_working(self):
        """(d) net_est>0 → inference 중, stall skip 해야 함."""
        monitor = self._make_monitor()

        mock_proc = MagicMock()
        mock_proc.children.return_value = []  # bash child 없음

        with patch.object(monitor, '_get_claude_pid', return_value=12345):
            with patch('psutil.Process', return_value=mock_proc):
                with patch.object(monitor, '_get_net_established', return_value=2):
                    bash_child, net_est = monitor._check_stall_signals("test_session")

        assert bash_child is False
        assert net_est == 2


class TestGetNetEstablished:
    """Tests for _get_net_established()"""

    def _make_monitor(self):
        from claude_ctb.monitoring.multi_monitor import MultiSessionMonitor
        monitor = MultiSessionMonitor.__new__(MultiSessionMonitor)
        return monitor

    def test_returns_zero_on_error(self):
        """모든 오류 시 0 반환."""
        monitor = self._make_monitor()
        with patch('subprocess.run', side_effect=Exception("ss not found")):
            # /proc fallback도 막기 위해 open도 실패하게
            with patch('builtins.open', side_effect=Exception("no proc")):
                with patch('os.path.exists', return_value=False):
                    result = monitor._get_net_established(99999)
        assert result == 0

    def test_counts_established_connections(self):
        """ss 출력에서 ESTAB :443 라인 카운트."""
        monitor = self._make_monitor()
        ss_output = (
            "State   Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "ESTAB   0      0      192.168.1.1:54321  52.2.1.1:443\n"
            "ESTAB   0      0      192.168.1.1:54322  52.2.1.2:443\n"
            "ESTAB   0      0      192.168.1.1:54323  10.0.0.1:80\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=ss_output, returncode=0)
            result = monitor._get_net_established(12345)
        assert result == 2

    def test_zero_count_with_successful_ss(self):
        """ESTAB :443 없어도 ss 성공 시 0 반환 (returncode==0 경로)."""
        monitor = self._make_monitor()
        ss_output = (
            "State   Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "ESTAB   0      0      192.168.1.1:54323  10.0.0.1:80\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=ss_output, returncode=0)
            result = monitor._get_net_established(12345)
        assert result == 0


# ---------------------------------------------------------------------------
# T4: Ticket Registry Tests (e023)
# ---------------------------------------------------------------------------

class TestTicketRegistry:
    """Unit tests for claude_ctb/utils/ticket_registry.py"""

    def _make_gh_mock(self, state: str):
        """Return a mock subprocess.run result for gh issue view."""
        import json as _json
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = _json.dumps({"state": state})
        mock.stderr = ""
        return mock

    def _clear_cache(self):
        from claude_ctb.utils import ticket_registry
        with ticket_registry._cache_lock:
            ticket_registry._gh_cache.clear()

    def test_register_and_is_ticket_done_github_open(self, tmp_path, monkeypatch):
        """OPEN issue → False."""
        self._clear_cache()
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-a", "github_issue", 99, state_dir)
        with patch("subprocess.run", return_value=self._make_gh_mock("OPEN")):
            result = is_ticket_done("sess-a", state_dir)
        assert result is False

    def test_register_and_is_ticket_done_github_closed(self, tmp_path):
        """CLOSED issue → True."""
        self._clear_cache()
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-b", "github_issue", 100, state_dir)
        with patch("subprocess.run", return_value=self._make_gh_mock("CLOSED")):
            result = is_ticket_done("sess-b", state_dir)
        assert result is True

    def test_gh_failure_returns_false(self, tmp_path):
        """gh CLI exception → False (fail-open)."""
        self._clear_cache()
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-c", "github_issue", 101, state_dir)
        with patch("subprocess.run", side_effect=Exception("network error")):
            result = is_ticket_done("sess-c", state_dir)
        assert result is False

    def test_gh_cache_hit_no_subprocess(self, tmp_path):
        """Cache hit within TTL → subprocess not called again."""
        self._clear_cache()
        from claude_ctb.utils import ticket_registry
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-d", "github_issue", 102, state_dir)
        # Prime cache with a CLOSED result
        with patch("subprocess.run", return_value=self._make_gh_mock("CLOSED")) as mock_run:
            is_ticket_done("sess-d", state_dir)
            call_count_after_first = mock_run.call_count

        # Second call within TTL — should hit cache
        with patch("subprocess.run", return_value=self._make_gh_mock("OPEN")) as mock_run2:
            result = is_ticket_done("sess-d", state_dir)
            assert mock_run2.call_count == 0  # no subprocess call
        assert result is True  # cached value (CLOSED)

    def test_gh_fallback_within_600s(self, tmp_path):
        """TTL expired + gh failure → last-success fallback within 600s."""
        self._clear_cache()
        import time as _time
        from claude_ctb.utils import ticket_registry
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-e", "github_issue", 103, state_dir)

        now = _time.time()
        # Inject stale cache entry (TTL expired, but within fallback window)
        with ticket_registry._cache_lock:
            ticket_registry._gh_cache[103] = (True, now - 200, now - 200)  # checked 200s ago

        # gh fails → should return cached True via fallback
        with patch("subprocess.run", side_effect=Exception("timeout")):
            result = is_ticket_done("sess-e", state_dir)
        assert result is True

    def test_omc_state_active_false_returns_true(self, tmp_path):
        """OMC state active=False → completed → True."""
        import json as _json
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        state_file = tmp_path / "ralph-state.json"
        state_file.write_text(_json.dumps({"active": False}))
        register("sess-f", "omc_task", str(state_file), state_dir)
        result = is_ticket_done("sess-f", state_dir)
        assert result is True

    def test_omc_state_file_missing_returns_true(self, tmp_path):
        """OMC state file missing → completed → True (M14)."""
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-g", "omc_task", "/nonexistent/path/state.json", state_dir)
        result = is_ticket_done("sess-g", state_dir)
        assert result is True

    def test_no_registration_returns_none(self, tmp_path):
        """Unregistered session → None."""
        from claude_ctb.utils.ticket_registry import is_ticket_done
        result = is_ticket_done("unregistered-session", str(tmp_path))
        assert result is None

    def test_stale_cleanup_24h(self, tmp_path):
        """Entries older than 24h are removed on next write."""
        import time as _time
        import json as _json
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)

        # Manually inject a stale entry
        stale_ts = _time.time() - 90000  # 25 hours ago
        registry = {"old-sess": {"type": "github_issue", "ref": 200,
                                  "registered_at": "2000-01-01T00:00:00Z",
                                  "registered_at_ts": stale_ts}}
        reg_path = tmp_path / "session-tickets.json"
        reg_path.write_text(_json.dumps(registry))

        # Registering a new session triggers cleanup
        register("new-sess", "github_issue", 201, state_dir)

        reg_data = _json.loads(reg_path.read_text())
        assert "old-sess" not in reg_data
        assert "new-sess" in reg_data

    def test_register_unregister(self, tmp_path):
        """Register then unregister removes entry."""
        import json as _json
        from claude_ctb.utils.ticket_registry import register, unregister, is_ticket_done
        state_dir = str(tmp_path)
        register("sess-h", "github_issue", 300, state_dir)
        unregister("sess-h", state_dir)
        result = is_ticket_done("sess-h", state_dir)
        assert result is None

    def test_atomic_write_no_corruption(self, tmp_path):
        """Registry file should be valid JSON after write."""
        import json as _json
        from claude_ctb.utils.ticket_registry import register
        state_dir = str(tmp_path)
        register("sess-i", "github_issue", 400, state_dir)
        reg_path = tmp_path / "session-tickets.json"
        data = _json.loads(reg_path.read_text())
        assert "sess-i" in data
        assert data["sess-i"]["ref"] == 400

    def test_filelock_graceful_fallback(self, tmp_path, monkeypatch):
        """When filelock import fails, registry still works."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "filelock":
                raise ImportError("filelock not available")
            return real_import(name, *args, **kwargs)

        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        with patch("builtins.__import__", side_effect=mock_import):
            # Should not raise
            register("sess-j", "github_issue", 500, state_dir)
        result = is_ticket_done("sess-j", state_dir)
        assert result is not None  # registered or None, but no exception

    def test_cache_lock_thread_safety(self, tmp_path):
        """10 concurrent threads reading cache should not raise."""
        import threading
        self._clear_cache()
        from claude_ctb.utils import ticket_registry
        from claude_ctb.utils.ticket_registry import register
        state_dir = str(tmp_path)
        register("sess-k", "github_issue", 600, state_dir)

        # Prime cache
        import time as _time
        now = _time.time()
        with ticket_registry._cache_lock:
            ticket_registry._gh_cache[600] = (False, now, now)

        errors = []

        def read_cache():
            try:
                from claude_ctb.utils.ticket_registry import is_ticket_done
                is_ticket_done("sess-k", state_dir)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=read_cache) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Thread errors: {errors}"

    def test_register_from_critique_lock_skip_no_session(self, tmp_path, monkeypatch):
        """CLAUDE_SESSION_ID and TMUX missing → skip + return False."""
        import json as _json
        from claude_ctb.utils.ticket_registry import register_from_critique_lock
        state_dir = str(tmp_path)
        lock_path = str(tmp_path / "critique-lock.json")
        (tmp_path / "critique-lock.json").write_text(_json.dumps({"github_issue": 42}))

        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        monkeypatch.delenv("TMUX", raising=False)

        result = register_from_critique_lock(state_dir, lock_path=lock_path)
        assert result is False


class TestTicketRegistryIntegration:
    """Integration tests for concurrent access and fallback paths."""

    def _clear_cache(self):
        from claude_ctb.utils import ticket_registry
        with ticket_registry._cache_lock:
            ticket_registry._gh_cache.clear()

    def test_concurrent_write_same_issue(self, tmp_path):
        """M12: 2 threads writing same session simultaneously — no exception, consistent state."""
        import threading
        import time as _time
        import json as _json
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        errors = []

        def write_and_check():
            try:
                _time.sleep(0.1)  # synchronize start
                register("shared-sess", "github_issue", 700, state_dir)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write_and_check)
        t2 = threading.Thread(target=write_and_check)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Concurrent write errors: {errors}"

        # Final state must be consistent JSON
        reg_path = tmp_path / "session-tickets.json"
        data = _json.loads(reg_path.read_text())
        assert "shared-sess" in data
        assert data["shared-sess"]["ref"] == 700

    def test_ttl_expired_gh_failure_fallback(self, tmp_path):
        """TTL expired + gh failure → last-success fallback within 600s."""
        import time as _time
        from claude_ctb.utils import ticket_registry
        from claude_ctb.utils.ticket_registry import register, is_ticket_done
        state_dir = str(tmp_path)
        self._clear_cache()

        register("fb-sess", "github_issue", 800, state_dir)
        now = _time.time()
        # Stale cache: 200s old (TTL=120s expired, fallback window=600s OK)
        with ticket_registry._cache_lock:
            ticket_registry._gh_cache[800] = (True, now - 200, now - 200)

        with patch("subprocess.run", side_effect=Exception("gh timeout")):
            result = is_ticket_done("fb-sess", state_dir)

        assert result is True  # served from last-success fallback
