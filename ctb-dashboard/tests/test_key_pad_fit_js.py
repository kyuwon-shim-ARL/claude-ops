"""Folding the key pad to two rows on a narrow phone.

The pad wraps, so its height belongs to the device: on an iPhone 12 the
seventeenth key tipped it to three rows, and the third row comes out of the
pane. These drive the shipped row arithmetic and the folding plan with
measured widths standing in for a real layout -- what matters is that the
result fits, and that what survives is what you actually need in a hurry.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CONSOLE_JS = (
    Path(__file__).resolve().parents[1]
    / "src" / "ctb_dashboard" / "static" / "js" / "session-control.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
global.window = {{ location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}} }};
global.document = {{
  addEventListener(){{}}, readyState:'complete',
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const args = JSON.parse({payload});
process.stdout.write(JSON.stringify(window.ctbConsole.{fn}(...args)));
"""


def _call(fn, *args):
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        payload=json.dumps(json.dumps(list(args))),
        fn=fn,
    )
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def rows(widths, gap, tray):
    return _call("_rowsNeeded", widths, gap, tray)


def plan(widths, prios, gap, tray, max_rows=2, more=38):
    return _call("_planKeys", widths, prios, gap, tray, max_rows, more)


# The real pad, as it renders on a phone: 15 key caps, then 입력 지우기 and
# 가져오기 as icon-only buttons. Widths and priorities mirror the source.
PHONE_W = [36] * 15 + [38, 38]
PHONE_P = [9, 9, 8, 8, 7, 3, 2, 6, 6, 4, 4, 3, 5, 8, 9, 4, 5]
IPHONE12_TRAY = 366 - 12   # 390 viewport less the sheet's padding, less the tray's


# --- the arithmetic ---------------------------------------------------------

def test_rows_counts_the_way_flex_wrap_wraps():
    # 4 keys of 100 with a gap of 10 in 340: 100+10+100+10+100 = 320 fits, the
    # fourth does not.
    assert rows([100, 100, 100, 100], 10, 340) == 2


def test_an_exact_fit_does_not_spill():
    assert rows([100, 100, 100], 10, 320) == 1


def test_one_pixel_short_spills():
    assert rows([100, 100, 100], 10, 319) == 2


def test_a_single_key_wider_than_the_tray_is_still_one_row():
    assert rows([500], 8, 300) == 1


def test_no_width_to_lay_out_in_does_not_divide_by_zero():
    assert rows([36, 36], 8, 0) == 1


# --- the plan ---------------------------------------------------------------

def test_a_pad_that_already_fits_is_left_alone():
    assert plan([36] * 8, [5] * 8, 5, IPHONE12_TRAY) == []


def test_the_iphone_12_pad_is_folded_to_two_rows():
    hidden = plan(PHONE_W, PHONE_P, 5, IPHONE12_TRAY)
    assert hidden, "seventeen keys do not fit two rows on a 390px phone"
    kept = [w for i, w in enumerate(PHONE_W) if i not in hidden] + [38]
    assert rows(kept, 5, IPHONE12_TRAY) <= 2


def test_what_survives_is_what_answers_a_prompt():
    """예 아니오 Enter esc are the keys you reach for in a hurry."""
    hidden = set(plan(PHONE_W, PHONE_P, 5, IPHONE12_TRAY))
    for keep in (0, 1, 13, 14):        # y, n, Enter, esc
        assert keep not in hidden
    assert 6 in hidden, "5번 is the least used key and should fold first"


def test_it_folds_from_the_least_important_up():
    hidden = plan(PHONE_W, PHONE_P, 5, IPHONE12_TRAY)
    prios = [PHONE_P[i] for i in hidden]
    assert prios == sorted(prios), "folded in priority order"
    assert max(prios) < 9


def test_ties_fold_the_later_key_first():
    """Equal priority: the pad reads left to right, so the right one goes."""
    widths = [36] * 6
    hidden = plan(widths, [5] * 6, 5, 120, max_rows=1, more=38)
    assert hidden[0] == 5


def test_the_more_key_gets_a_slot_of_its_own():
    """Folding must leave room for ⋯, or it spills the row it just saved."""
    hidden = plan(PHONE_W, PHONE_P, 5, IPHONE12_TRAY)
    kept = [w for i, w in enumerate(PHONE_W) if i not in hidden]
    assert rows(kept + [38], 5, IPHONE12_TRAY) <= 2
    # Without reserving the slot the plan would have stopped one key earlier.
    assert rows(kept + [PHONE_W[hidden[-1]]] + [38], 5, IPHONE12_TRAY) > 2


def test_a_wider_phone_folds_less_than_a_narrow_one():
    narrow = plan(PHONE_W, PHONE_P, 5, 320)
    wide = plan(PHONE_W, PHONE_P, 5, 430)
    assert len(narrow) > len(wide)


def test_a_desktop_width_folds_nothing():
    assert plan([44] * 15 + [96, 96], PHONE_P, 8, 900) == []


def test_a_tray_too_narrow_for_anything_folds_all_it_can_and_stops():
    hidden = plan(PHONE_W, PHONE_P, 5, 40)
    assert len(hidden) <= len(PHONE_W)
