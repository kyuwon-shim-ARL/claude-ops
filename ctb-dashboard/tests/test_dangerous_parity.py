"""The vendored dangerous-command list must not drift from the bot's.

Deliberately does NOT import claude_ctb. That package is not installed in the
dashboard venv, so an import-based check degrades to pytest.skip and silently
guards nothing -- which is exactly what happened to
tests/test_session_state_parity.py (2 skipped in this environment). Reading
the canonical file off disk and parsing the literal with ast keeps the check
executing wherever the repo is checked out, and needs no import side effects.
"""

import ast
from pathlib import Path

import pytest

from ctb_dashboard.dangerous_commands import DANGEROUS_PATTERNS, is_dangerous_command

CANONICAL = (
    Path(__file__).resolve().parents[2]
    / "claude_ctb" / "telegram" / "dangerous_commands.py"
)


def _canonical_patterns() -> list[str]:
    if not CANONICAL.exists():
        pytest.skip(f"canonical source not present at {CANONICAL} (isolated install)")
    tree = ast.parse(CANONICAL.read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "DANGEROUS_PATTERNS":
                return ast.literal_eval(node.value)
    raise AssertionError(f"DANGEROUS_PATTERNS not found in {CANONICAL}")


def test_canonical_source_is_reachable():
    """Guard the guard: if this path breaks, the parity check goes quiet."""
    assert CANONICAL.exists(), (
        f"canonical file not found at {CANONICAL} -- fix the path, do not "
        "let the parity test skip silently"
    )


def test_pattern_lists_are_identical():
    assert DANGEROUS_PATTERNS == _canonical_patterns(), (
        "vendored DANGEROUS_PATTERNS drifted from "
        f"{CANONICAL}. Update the canonical list first, then re-vendor."
    )


def test_length_cap_matches_canonical():
    """The over-long-input cap is part of the contract, not an implementation detail."""
    source = CANONICAL.read_text()
    assert "10000" in source
    from ctb_dashboard.dangerous_commands import _MAX_COMMAND_LENGTH

    assert _MAX_COMMAND_LENGTH == 10000


@pytest.mark.parametrize("command", [
    "rm -rf /",
    "sudo rm -rf /home",
    "sudo systemctl stop everything",
    "chmod 777 /etc/passwd",
    "dd if=/dev/zero of=/dev/sda",
    "mkfs.ext4 /dev/sda1",
    "RM -RF /",  # case-insensitive
])
def test_destructive_commands_are_flagged(command):
    assert is_dangerous_command(command) is True


@pytest.mark.parametrize("command", [
    "테스트 좀 돌려줘",
    "git status",
    "uv run pytest -q",
    "설명해줘: 이 함수가 왜 느린지",
    "ls -la",
    "",
])
def test_ordinary_prompts_are_not_flagged(command):
    assert is_dangerous_command(command) is False


def test_over_long_input_is_flagged_without_scanning():
    assert is_dangerous_command("a" * 10001) is True
    assert is_dangerous_command("a" * 10000) is False
