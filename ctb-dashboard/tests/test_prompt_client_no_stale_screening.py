"""The client must not claim the deleted destructive-command screening still runs.

Once dangerous_commands.py was deleted, the endpoint stopped returning 400 for
a pattern match -- it returns 413 for the byte-size limit instead. The old
400-branch in session-control.js's prompt-send handler would either never
fire or fire on an unrelated 400 and tell the user a false reason ("위험 명령
패턴으로 차단되었습니다"). This is a source-level regression test, not a DOM
harness: the response handler lives inside a closure over fetch results,
`state`, `el`, and `say()` from the surrounding send() function, and building
a harness that drives that closure would mean inventing DOM/fetch scaffolding
this handler does not otherwise expose as public API -- unlike, say,
test_strip_context_gauge_js.py, which exercises a standalone function. This
test instead pins what a harness would only restate: the false-reason string
is gone, and the client reacts to the real 413 status the server now sends.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/ctb_dashboard/static/js/session-control.js"


def test_no_stale_dangerous_pattern_message():
    text = SRC.read_text()
    assert "위험 명령" not in text
    assert "차단되었습니다" not in text


def test_prompt_handler_reacts_to_413():
    text = SRC.read_text()
    assert "r.status === 413" in text
