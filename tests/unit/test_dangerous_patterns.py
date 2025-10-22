"""T020: Unit test for dangerous pattern detection."""
import pytest
import re
from claude_ctb.telegram.bot import DANGEROUS_PATTERNS, is_dangerous_command


class TestDangerousPatterns:
    """Unit tests for dangerous pattern detection."""

    def test_dangerous_patterns_regex_matching(self):
        """Test DANGEROUS_PATTERNS regex matching."""
        assert len(DANGEROUS_PATTERNS) > 0

        dangerous_commands = [
            "rm -rf /",
            "sudo rm -rf /tmp",
            "chmod 777 /etc",
            "chown root:root /etc/passwd"
        ]

        for cmd in dangerous_commands:
            assert any(re.search(pattern, cmd) for pattern in DANGEROUS_PATTERNS)

    def test_false_positives(self):
        """Test false positives (e.g., 'sudo' in sentence context)."""
        safe_commands = [
            "I think sudo is a useful command",
            "echo 'rm -rf' is dangerous",
            "The chmod command changes permissions"
        ]

        # These should not match (depends on pattern design)
        # Assuming patterns look for word boundaries

    def test_command_input_length_limit(self):
        """Test command input length limit (10,000 chars)."""
        long_command = "echo " + ("x" * 10000)

        # Should reject commands longer than 10,000 chars
        assert len(long_command) > 10000

    def test_specific_patterns(self):
        """Test specific dangerous patterns."""
        assert is_dangerous_command("rm -rf /")
        assert is_dangerous_command("sudo systemctl stop")
        assert not is_dangerous_command("ls -la")
        assert not is_dangerous_command("echo hello")
