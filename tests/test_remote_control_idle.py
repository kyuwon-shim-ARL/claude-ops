"""Tests for idle-aware /remote-control auto-registration.

Ticket EXP-20260604001639 (tcrit v2). All tests are tmux-independent: they feed
captured-pane text straight into the pure classifier or monkeypatch ``_capture``
(design decision D2 — CI does not require tmux).
"""

import json

from claude_ctb.utils import remote_control as rc


# ── Realistic captured-pane fixtures ──────────────────────────────────────────
# The live Claude TUI renders the prompt as "❯ " on its own line between two
# full-width borders (no side bars). \xa0 is the nbsp the TUI pads with.
IDLE_PANE = (
    "Some earlier output line\n"
    "────────────────────────────────────────\n"
    "❯\xa0\n"
    "────────────────────────────────────────\n"
    "  [OMC#4.14.1] | Model: Opus 4.8 | ctx:5%\n"
    "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
)

BUSY_PANE = (
    "✶ Hatching… (33s · ↓ 1.5k tokens · esc to interrupt)\n"
    "────────────────────────────────────────\n"
    "❯\xa0\n"
    "────────────────────────────────────────\n"
    "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
)

TYPED_PANE = (
    "────────────────────────────────────────\n"
    "❯ hello there\n"
    "────────────────────────────────────────\n"
)

BOXED_IDLE_PANE = (  # alternate TUI: prompt boxed with side bars
    "╭────────────────────────╮\n"
    "│ ❯                      │\n"
    "╰────────────────────────╯\n"
)

NO_PROMPT_PANE = "loading...\n░░░░░░░░\n"

SCROLLBACK_OLD_PROMPT = (  # an old ❯ in scrollback, live prompt is busy at bottom
    "❯ previous command result\n"
    "✻ Synthesizing… (5s · ↓ 200 tokens · esc to interrupt)\n"
    "❯\xa0\n"
)


# ── T1: pure classifier ───────────────────────────────────────────────────────
def test_idle_empty_prompt_is_ready():
    s = rc.pane_ready_from_text(IDLE_PANE)
    assert s["ready"] is True
    assert s["idle"] and s["empty_input"] and s["prompt_found"]
    assert s["reason"] == "ready"


def test_busy_pane_not_ready():
    s = rc.pane_ready_from_text(BUSY_PANE)
    assert s["ready"] is False
    assert s["idle"] is False
    assert s["reason"] == "busy"


def test_typed_input_not_ready():
    s = rc.pane_ready_from_text(TYPED_PANE)
    assert s["ready"] is False
    assert s["empty_input"] is False
    assert s["reason"] == "input_not_empty"


def test_boxed_prompt_empty_is_ready():
    s = rc.pane_ready_from_text(BOXED_IDLE_PANE)
    assert s["ready"] is True


def test_no_prompt_not_ready():
    s = rc.pane_ready_from_text(NO_PROMPT_PANE)
    assert s["ready"] is False
    assert s["reason"] == "no_prompt"


def test_scrollback_old_prompt_ignored_when_busy():
    # Bottom-most ❯ is the live prompt, but the pane is busy → not ready.
    s = rc.pane_ready_from_text(SCROLLBACK_OLD_PROMPT)
    assert s["ready"] is False
    assert s["reason"] == "busy"


def test_empty_text_not_ready():
    s = rc.pane_ready_from_text("")
    assert s["ready"] is False
    assert s["reason"] == "no_prompt"


# ── D1/D6: busy markers ───────────────────────────────────────────────────────
def test_busy_markers_loaded_from_file():
    markers, fallback = rc.load_busy_markers()
    assert "esc to interrupt" in markers
    assert fallback is False


def test_busy_markers_fallback_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rc, "_MARKERS_FILE", str(tmp_path / "nope.txt"))
    markers, fallback = rc.load_busy_markers()
    assert fallback is True
    assert "esc to interrupt" in markers


def test_busy_markers_fallback_when_empty(monkeypatch, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    monkeypatch.setattr(rc, "_MARKERS_FILE", str(empty))
    _, fallback = rc.load_busy_markers()
    assert fallback is True


# ── T6: already-registered guard ──────────────────────────────────────────────
def test_already_registered_detected_via_env(monkeypatch):
    monkeypatch.setenv("CTB_REMOTE_CONTROL_INDICATOR", "REMOTE-ON")
    assert rc.is_remote_control_active("foo REMOTE-ON bar") is True
    assert rc.is_remote_control_active("nothing here") is False


# ── T8: telemetry ─────────────────────────────────────────────────────────────
def test_record_telemetry_increments(monkeypatch, tmp_path):
    tele = tmp_path / "tele.json"
    monkeypatch.setattr(rc, "_TELEMETRY_FILE", str(tele))
    rc.record_telemetry("success", "sess")
    rc.record_telemetry("success", "sess")
    rc.record_telemetry("fallback_timeout", "sess")
    data = json.loads(tele.read_text())
    assert data["counts"]["success"] == 2
    assert data["counts"]["fallback_timeout"] == 1
    assert data["last"]["outcome"] == "fallback_timeout"


# ── CTB_AUTO_REMOTE_CONTROL toggle (regression) ───────────────────────────────
def test_disabled_blocks_send(monkeypatch):
    monkeypatch.setenv("CTB_AUTO_REMOTE_CONTROL", "0")
    assert rc.is_enabled() is False
    assert rc.send_remote_control("sess") is False


def test_enabled_by_default(monkeypatch):
    monkeypatch.delenv("CTB_AUTO_REMOTE_CONTROL", raising=False)
    assert rc.is_enabled() is True


# ── T0/T2/T3: wait_until_ready behavior (monkeypatched capture) ────────────────
def test_fresh_fires_immediately_on_empty_prompt(monkeypatch):
    monkeypatch.setattr(rc, "_capture", lambda s: IDLE_PANE)
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    ready, reason = rc.wait_until_ready("sess", mode="fresh")
    assert ready is True and reason == "ready"


def test_restart_requires_stable_two(monkeypatch):
    captures = [BUSY_PANE, IDLE_PANE, IDLE_PANE]  # busy, then two stable idle
    monkeypatch.setattr(rc, "_capture", lambda s: captures.pop(0) if captures else IDLE_PANE)
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    ready, reason = rc.wait_until_ready("sess", mode="restart", timeout=5)
    assert ready is True and reason == "ready"


def test_restart_timeout_when_always_busy(monkeypatch):
    monkeypatch.setattr(rc, "_capture", lambda s: BUSY_PANE)
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    monkeypatch.setattr(rc.time, "monotonic", _fake_clock())
    ready, reason = rc.wait_until_ready("sess", mode="restart", timeout=3)
    assert ready is False
    assert reason == "busy"


def _fake_clock():
    """Monotonic clock that advances 1s per call so timeout loops terminate."""
    state = {"t": 0.0}

    def _clock():
        state["t"] += 1.0
        return state["t"]

    return _clock


# ── T3 + T6 in send_remote_control ────────────────────────────────────────────
def test_send_skips_when_not_ready_and_notifies(monkeypatch):
    monkeypatch.delenv("CTB_AUTO_REMOTE_CONTROL", raising=False)
    monkeypatch.setattr(rc, "wait_until_ready", lambda *a, **k: (False, "busy"))
    notified = {}
    monkeypatch.setattr(rc, "_notify_fallback", lambda s, r: notified.update(s=s, r=r))
    monkeypatch.setattr(rc, "record_telemetry", lambda *a, **k: None)
    sent = {"called": False}
    monkeypatch.setattr(rc, "_send_keys", lambda s: sent.update(called=True))
    assert rc.send_remote_control("sess") is False
    assert sent["called"] is False  # no blind-fire
    assert notified.get("s") == "sess"


def test_send_skips_when_already_registered(monkeypatch):
    monkeypatch.delenv("CTB_AUTO_REMOTE_CONTROL", raising=False)
    monkeypatch.setattr(rc, "wait_until_ready", lambda *a, **k: (True, "ready"))
    monkeypatch.setattr(rc, "_capture", lambda s: "Remote control active now")
    monkeypatch.setattr(rc, "record_telemetry", lambda *a, **k: None)
    sent = {"called": False}
    monkeypatch.setattr(rc, "_send_keys", lambda s: sent.update(called=True))
    assert rc.send_remote_control("sess") is False
    assert sent["called"] is False  # guard prevented re-fire (toggle-off bug)
