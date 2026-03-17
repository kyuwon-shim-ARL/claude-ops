"""Shared fixtures for CTB test suite."""

import os
import pytest
from claude_ctb.utils.session_state import SessionStateAnalyzer


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def analyzer():
    """Fresh SessionStateAnalyzer instance (no cache)."""
    return SessionStateAnalyzer()


def load_fixture(name: str) -> str:
    """Load a golden screen-capture fixture by name.

    Files live in tests/fixtures/<name>.txt
    """
    path = os.path.join(FIXTURES_DIR, f"{name}.txt")
    with open(path, "r") as f:
        return f.read()
