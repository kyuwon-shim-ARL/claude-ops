"""T038: Performance test for 200-line capture overhead."""
import pytest
import time
import subprocess
from claude_ctb.utils.session_state import SessionStateAnalyzer


class TestScreenCapturePerformance:
    """Performance tests for 200-line screen capture."""

    def test_capture_time_for_200_lines(self, tmp_path):
        """Measure capture time for 200 lines."""
        # Create a test tmux session with 200+ lines
        session_name = "perf_test_session"

        # Create session
        subprocess.run(
            f"tmux new-session -d -s {session_name} -c /tmp",
            shell=True,
            check=True
        )

        try:
            # Generate 250 lines of output
            for i in range(250):
                subprocess.run(
                    f'tmux send-keys -t {session_name} "echo Line {i}" Enter',
                    shell=True
                )

            # Wait for output to settle
            time.sleep(0.5)

            # Measure capture time
            start = time.time()
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -200",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            elapsed = time.time() - start

            # Assert capture completes quickly
            assert elapsed < 1.0, f"Capture took {elapsed:.3f}s, expected <1s"
            assert result.returncode == 0

            # Verify we got content
            lines = result.stdout.strip().split('\n')
            assert len(lines) > 0
            # May be slightly more than 200 lines due to tmux pane height
            assert len(lines) <= 250, f"Got {len(lines)} lines, expected ≤250"

        finally:
            # Cleanup
            subprocess.run(
                f"tmux kill-session -t {session_name}",
                shell=True
            )

    def test_hash_computation_under_100ms(self):
        """Assert <100ms hash computation."""
        import hashlib

        # Generate 200 lines of test content (~10KB)
        content = "\n".join([f"Line {i}: " + "x" * 50 for i in range(200)])

        # Measure hash computation
        start = time.time()
        for _ in range(10):  # Run 10 times to get average
            hash_value = hashlib.md5(content.encode()).hexdigest()
        elapsed = (time.time() - start) / 10

        # Assert <100ms for single hash
        assert elapsed < 0.1, f"Hash computation took {elapsed*1000:.1f}ms, expected <100ms"

        # Verify hash format
        assert len(hash_value) == 32
        assert all(c in '0123456789abcdef' for c in hash_value)

    def test_capture_timeout_5_seconds(self, tmp_path):
        """Assert <5s capture timeout."""
        session_name = "timeout_test_session"

        # Create session
        subprocess.run(
            f"tmux new-session -d -s {session_name} -c /tmp",
            shell=True,
            check=True
        )

        try:
            # Test with timeout
            start = time.time()
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -200",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5  # 5-second timeout
            )
            elapsed = time.time() - start

            # Should complete well before timeout
            assert elapsed < 2.0, f"Capture took {elapsed:.3f}s, expected <2s"

        finally:
            subprocess.run(
                f"tmux kill-session -t {session_name}",
                shell=True
            )

    def test_concurrent_10_sessions(self):
        """Test with 10+ concurrent sessions."""
        import threading

        num_sessions = 10
        session_names = [f"concurrent_test_{i}" for i in range(num_sessions)]
        results = []

        def capture_session(session_name):
            """Capture a single session."""
            try:
                # Create session
                subprocess.run(
                    f"tmux new-session -d -s {session_name} -c /tmp",
                    shell=True,
                    check=True
                )

                # Generate some output
                for i in range(50):
                    subprocess.run(
                        f'tmux send-keys -t {session_name} "echo Line {i}" Enter',
                        shell=True
                    )

                # Capture
                start = time.time()
                result = subprocess.run(
                    f"tmux capture-pane -t {session_name} -p -S -200",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                elapsed = time.time() - start

                results.append(elapsed)

            finally:
                subprocess.run(
                    f"tmux kill-session -t {session_name}",
                    shell=True
                )

        # Run concurrent captures
        threads = []
        for session_name in session_names:
            thread = threading.Thread(target=capture_session, args=(session_name,))
            threads.append(thread)
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join(timeout=10)

        # Verify all completed quickly
        assert len(results) == num_sessions
        avg_time = sum(results) / len(results)
        assert avg_time < 1.0, f"Average capture time {avg_time:.3f}s, expected <1s"
        assert max(results) < 2.0, f"Max capture time {max(results):.3f}s, expected <2s"
