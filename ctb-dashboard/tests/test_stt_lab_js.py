"""STT Lab page: scores GPT vs iOS dictation against a fixed eval set. It
never sends anything to a live session -- every mutating call goes through
window.ctbControl.send (the token layer), and the mic/iOS-textarea paths
both post only to /api/stt or /api/stt/eval*."""

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/js/stt-lab.js"
HTML = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/stt-lab.html"


def _js():
    return JS.read_text()


def test_never_touches_session_prompt_or_key_endpoints():
    js = _js()
    assert "/api/sessions/" not in js
    assert "/prompt" not in js
    assert "/api/key" not in js


def test_every_mutating_call_uses_the_control_token():
    js = _js()
    # the three write endpoints all go through ctbControl.send
    assert re.search(r"ctbControl\.send\('/api/stt' \+ qs", js)
    assert re.search(r"ctbControl\.send\('/api/stt/eval'", js)
    assert re.search(r"ctbControl\.send\('/api/stt/eval/rebuild'", js)
    # config/set/results are read-only GETs and may use plain fetch
    assert "fetch(window.ctbControl.api('/api/stt/config')" in js
    assert "fetch(window.ctbControl.api('/api/stt/eval/set')" in js
    assert "fetch(window.ctbControl.api('/api/stt/eval/results')" in js


def test_mic_path_exists_and_mirrors_console_behaviour():
    js = _js()
    for fn in ("sttStart", "sttStop", "sttFinish", "sttRelease", "bindMic", "sttMime"):
        assert ("function " + fn) in js
    assert "'pointerdown'" in js and "'pointerup'" in js and "'pointercancel'" in js
    assert "< 350" in js  # short press leaves it recording (tap-toggle)
    assert "MediaRecorder" in js


def test_ios_dictation_path_exists():
    js = _js()
    assert "submitIosScore" in js
    assert "stt-ios-box" in js
    assert "stt-ios-score" in js
    # iOS path never records audio itself; seconds is null for it
    assert re.search(r"score\(item, hyp, 'ios', null\)", js)


def test_gpt_path_scores_with_engine_gpt():
    js = _js()
    assert re.search(r"score\(item, text, 'gpt', seconds\)", js)


def test_disabled_when_stt_not_configured():
    js = _js()
    assert "OPENAI_API_KEY" in js
    assert "el.mic.disabled = true" in js


def test_handles_403_and_503():
    js = _js()
    assert js.count("403") >= 2
    assert js.count("503") >= 2


def test_hints_toggle_is_sent_on_both_stt_and_eval_calls():
    js = _js()
    assert "state.hints" in js
    assert "hints=' + (state.hints" in js
    assert "hints: state.hints" in js


def test_persists_current_index_in_localstorage_safely():
    js = _js()
    assert "localStorage" in js
    assert "try {" in js and "catch (e)" in js


def test_diff_is_computed_client_side_lcs():
    js = _js()
    assert "function diffChars" in js
    assert "stt-diff-del" in js and "stt-diff-ins" in js


def test_rebuild_reloads_set_and_stats():
    js = _js()
    block = js[js.index("function rebuild()"):]
    block = block[:block.index("\n  }\n")]
    assert "loadSet()" in block
    assert "loadStats()" in block


def test_html_loads_control_token_before_page_script():
    html = HTML.read_text()
    ct = html.index("control-token.js")
    lab = html.index("stt-lab.js")
    assert ct < lab


def test_html_has_no_jinja_and_is_dark_theme():
    html = HTML.read_text()
    assert "{{" not in html and "{%" not in html
    assert "color-scheme: dark" in html


def test_html_inputs_are_16px_to_avoid_ios_zoom():
    html = HTML.read_text()
    assert "font-size: 16px" in html


def test_mutation_guard_no_theme_toggle_wiring_to_session_console():
    """This page is standalone: it must not import session-control.js."""
    html = HTML.read_text()
    assert "session-control.js" not in html
