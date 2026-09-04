"""The console's mic: present, gated on the server saying it has a key,
absent from the VSCode webview, and it drafts -- it never sends."""

import re
from pathlib import Path

CONSOLE_JS = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/js/session-control.js"


def _stt_block():
    js = CONSOLE_JS.read_text()
    start = js.index("/* --- speech to text")
    end = js.index("/* --- actions")
    return js[start:end]


def test_mic_shows_only_when_the_server_has_a_key():
    js = CONSOLE_JS.read_text()
    assert "/api/stt/config" in js
    assert "mic.style.display = 'none'" in js  # hidden until told otherwise
    assert "!IS_VSCODE" in _stt_block()


def test_stt_never_submits():
    block = _stt_block()
    assert "submit(" not in block
    assert "sendKey(" not in block
    assert "/prompt" not in block


def test_transcript_goes_into_the_box_as_a_draft():
    block = _stt_block()
    assert "state.drafts[state.session] = box.value" in block
    assert "con-flash" in block


def test_clip_is_posted_with_the_control_token():
    block = _stt_block()
    assert re.search(r"ctbControl\.send\('/api/stt\?session=", block)


def test_a_late_transcript_for_another_session_is_dropped():
    assert "if (state.session !== forSession) return;" in _stt_block()


def test_recording_is_aborted_on_close_and_switch():
    js = CONSOLE_JS.read_text()
    hide = js[js.index("  function hide() {"):]
    assert "sttAbort();" in hide[:200]
    assert js.count("sttAbort();") >= 2  # hide() and the switch in show()


def test_hold_and_tap_toggle_both_exist():
    block = _stt_block()
    assert "'pointerdown'" in block and "'pointerup'" in block and "'pointercancel'" in block
    assert "< 350" in block  # a short press leaves it recording


def test_mutation_guard_no_autosend_flag():
    """No 'auto send' knob exists anywhere: the design is Enter-only."""
    assert "autoSend" not in CONSOLE_JS.read_text()


def test_mic_press_keeps_the_keyboard_up():
    """A button press blurs the textarea on iOS and folds the keyboard, which
    threw the sheet around on every recording. The touch is claimed."""
    block = _stt_block()
    assert "addEventListener('touchstart', function (e) { e.preventDefault(); }, { passive: false })" in block
    assert "setPointerCapture" in block and "'pointerleave'" not in block


def test_recording_state_lives_on_the_mic_key_only():
    """No bar, no toast: the key is red while listening, amber while the clip
    is out, plain otherwise -- and every exit path resets it."""
    js = CONSOLE_JS.read_text()
    assert "con-recbar" not in js and "recBarShow" not in js
    assert '.con-mic[data-listening]' in js and '.con-mic[data-transcribing]' in js
    block = _stt_block()
    assert "micPhase('recording')" in block and "micPhase('transcribing')" in block
    assert block.count("micPhase('')") >= 4
