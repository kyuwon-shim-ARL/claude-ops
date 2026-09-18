"""extract_context_percent must match the ASCII OMC HUD (ctx:[#---]NN%), the
block-glyph HUD it always supported, the bare form, and the native
'Context left until auto-compact' fallback."""

from ctb_dashboard.state_detector import SessionStateAnalyzer


def _analyzer():
    return SessionStateAnalyzer()


def test_ascii_hud_hash_dash_glyphs():
    screen = "[OMC#5.1.0L] some/path ctx:[######----]56%"
    assert _analyzer().extract_context_percent(screen) == 56


def test_block_glyph_hud_still_matches():
    screen = "[OMC#5.1.0L] some/path ctx:[████░░░░░░]40%"
    assert _analyzer().extract_context_percent(screen) == 40


def test_bare_percentage():
    screen = "[OMC#5.1.0L] some/path ctx:67%"
    assert _analyzer().extract_context_percent(screen) == 67


def test_native_fallback_returns_used_not_remaining():
    screen = "Context left until auto-compact: 30%"
    assert _analyzer().extract_context_percent(screen) == 70


def test_none_when_absent():
    assert _analyzer().extract_context_percent("no ctx marker here") is None
