"""Dashboard state must outlive /tmp.

Reported (2026-08-07): completion alerts "used to come reliably, then stopped".
Pins gate every completion alert -- the in-page one and the push -- and they
were kept in /tmp, where this host's tmpfiles policy is `q /tmp ... 10d`. Ten
days without a pin change and the file is removed; the next dashboard restart
loads an empty set and alerts go quiet with nothing to see. The pin file on
disk was indeed empty when this was found.

Session timestamps had the same home and the same fate, which resets every idle
badge -- the bug fixed in f5c4c92, reachable again by a different route.
"""

import json
from pathlib import Path

import pytest

from ctb_dashboard import server


def _shipped(constant: str) -> str:
    """One constant as written, not as the test fixture redirects it."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "ctb_dashboard" / "server.py").read_text()
    start = src.index(f"{constant} = ")
    return src[start:src.index("\n", start)]


@pytest.mark.parametrize("constant", ["_PINNED_PERSIST_PATH", "_TS_PERSIST_PATH"])
def test_state_is_not_kept_in_tmp(constant):
    """/tmp is swept on a timer; these are user configuration."""
    assert "/tmp" not in _shipped(constant), _shipped(constant)


@pytest.mark.parametrize("constant", ["_PINNED_PERSIST_PATH", "_TS_PERSIST_PATH"])
def test_state_lives_beside_the_other_dashboard_state(constant):
    """One place to look, and the one already used for keys and subscriptions."""
    assert "_STATE_DIR" in _shipped(constant)


def test_pins_written_then_loaded_survive(tmp_path, monkeypatch):
    pins = {"Q1": ["claude_a"], "Q2": [], "Q3": ["claude_b"], "Q4": []}
    path = tmp_path / "pinned.json"
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(path))
    server._atomic_json_write(str(path), pins)
    assert server._load_pinned() == pins


def test_pins_left_in_the_old_tmp_location_are_still_read(tmp_path, monkeypatch):
    """Upgrading must not silently drop whatever was pinned at the time."""
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    pins = {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": []}
    old.write_text(json.dumps(pins))
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(new))
    monkeypatch.setattr(server, "_LEGACY_PINNED_PATH", str(old))
    assert server._load_pinned() == pins


def test_the_new_location_wins_over_the_legacy_one(tmp_path, monkeypatch):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps({"Q1": ["stale"], "Q2": [], "Q3": [], "Q4": []}))
    new.write_text(json.dumps({"Q1": ["current"], "Q2": [], "Q3": [], "Q4": []}))
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(new))
    monkeypatch.setattr(server, "_LEGACY_PINNED_PATH", str(old))
    assert server._load_pinned()["Q1"] == ["current"]


def test_a_missing_file_is_empty_pins_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(tmp_path / "nope.json"))
    monkeypatch.setattr(server, "_LEGACY_PINNED_PATH", str(tmp_path / "also-nope.json"))
    assert server._load_pinned() == {"Q1": [], "Q2": [], "Q3": [], "Q4": []}


def test_the_state_directory_is_created_if_absent(tmp_path, monkeypatch):
    """First run on a fresh machine must not lose the first pin."""
    target = tmp_path / "fresh" / "pinned.json"
    monkeypatch.setattr(server, "_PINNED_PERSIST_PATH", str(target))
    server._atomic_json_write(str(target), {"Q1": ["claude_a"], "Q2": [], "Q3": [], "Q4": []})
    assert json.loads(target.read_text())["Q1"] == ["claude_a"]


def test_the_gate_tests_cannot_reach_the_real_pin_file():
    """They post an empty pin set with a valid token; without isolation that
    lands on the user's actual pins, and every suite run wiped them."""
    src = (Path(__file__).resolve().parents[1] / "tests" / "test_control_auth.py").read_text()
    assert "_PINNED_PERSIST_PATH" in src
