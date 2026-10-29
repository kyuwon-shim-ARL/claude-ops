"""The prompt box can be dragged taller, up to 80% of the console.

A grip bar above the box is dragged with pointer events (mouse and touch).
The height is clamped between the default two rows and 80% of the console,
remembered as a fraction of the console's height, re-clamped when the screen
shrinks, and reset by a double tap. The log above gives the room back and a
reader pinned to its bottom stays pinned.

Layout is the question, so it is asked of a real browser.
"""

import pytest  # noqa: F401

from live_board import open_board

GRIP = "#ctb-console .con-grip"
INPUT = "#ctb-console .con-input"
KEY = "ctb_console_input_frac"


def open_console(page, w=390, h=844):
    page.set_viewport_size({"width": w, "height": h})
    page.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
    page.wait_for_selector("#ctb-console", state="visible")
    page.wait_for_timeout(300)


def m(page):
    return page.evaluate("""(() => {
      const e = window.ctbConsole._el();
      return { input: e.input.getBoundingClientRect().height, root: e.root.clientHeight,
               tail: e.tail.clientHeight, pinned: e.tail.scrollTop + e.tail.clientHeight >= e.tail.scrollHeight - 48 };
    })()""")


def drag(page, dy, steps=8):
    box = page.locator(GRIP).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - dy, steps=steps)
    page.mouse.up()
    page.wait_for_timeout(100)


def test_drag_up_grows_the_box_to_the_drag_and_shrinks_the_log():
    with open_board() as page:
        open_console(page)
        base = m(page)
        drag(page, 150)
        now = m(page)
        assert abs(now["input"] - (base["input"] + 150)) <= 2
        assert now["tail"] < base["tail"] - 100


def test_never_exceeds_eighty_percent():
    with open_board() as page:
        open_console(page)
        before = m(page)
        drag(page, 5000)
        now = m(page)
        assert now["input"] <= now["root"] * 0.8 + 1
        # Whatever the header, strip and keys leave: the log is used up, not
        # exceeded (the short-screen test below pins the no-overflow side).
        assert now["input"] > before["input"] + 200
        assert now["tail"] < before["tail"]


def test_drag_down_clamps_to_the_default():
    with open_board() as page:
        open_console(page)
        base = m(page)
        drag(page, -400)
        assert abs(m(page)["input"] - base["input"]) <= 1
        drag(page, 120)
        drag(page, -900)
        assert abs(m(page)["input"] - base["input"]) <= 1


def test_double_click_resets_to_the_default():
    with open_board() as page:
        open_console(page)
        base = m(page)
        drag(page, 200)
        assert m(page)["input"] > base["input"] + 100
        page.dblclick(GRIP)
        page.wait_for_timeout(100)
        assert abs(m(page)["input"] - base["input"]) <= 1
        assert page.evaluate("k => localStorage.getItem(k)", KEY) is None


def test_reload_restores_the_height_as_a_fraction():
    with open_board() as page:
        open_console(page)
        drag(page, 200)
        first = m(page)
        frac = float(page.evaluate("k => localStorage.getItem(k)", KEY))
        assert abs(frac - first["input"] / first["root"]) < 0.01
        page.reload()
        open_console(page)
        assert abs(m(page)["input"] - first["input"]) <= 2


def test_a_shorter_screen_reclamps_the_saved_height():
    with open_board() as page:
        open_console(page, 390, 844)
        drag(page, 5000)
        page.set_viewport_size({"width": 390, "height": 500})
        page.wait_for_timeout(300)
        now = m(page)
        assert now["input"] <= now["root"] * 0.8 + 1
        assert now["input"] > 100


def test_dragging_does_not_focus_the_box():
    with open_board() as page:
        open_console(page)
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        drag(page, 100)
        assert not page.evaluate("() => document.activeElement.classList.contains('con-input')")


def test_a_pinned_log_stays_pinned_through_the_change():
    with open_board() as page:
        open_console(page)
        page.evaluate("() => { const t = window.ctbConsole._el().tail; t.scrollTop = t.scrollHeight; }")
        page.wait_for_timeout(150)
        assert m(page)["pinned"]
        drag(page, 250)
        page.wait_for_timeout(150)
        assert m(page)["pinned"]
        drag(page, -250)
        page.wait_for_timeout(150)
        assert m(page)["pinned"]


def test_touch_drag_with_pointer_events():
    with open_board() as page:
        open_console(page)
        base = m(page)
        page.evaluate("""() => {
          const g = document.querySelector('#ctb-console .con-grip');
          const r = g.getBoundingClientRect();
          const x = r.x + r.width / 2, y = r.y + r.height / 2;
          const ev = (t, dy) => g.dispatchEvent(new PointerEvent(t, { pointerId: 7, pointerType: 'touch',
            isPrimary: true, bubbles: true, cancelable: true, clientX: x, clientY: y - dy, button: 0 }));
          ev('pointerdown', 0); ev('pointermove', 60); ev('pointermove', 140); ev('pointerup', 140);
        }""")
        page.wait_for_timeout(100)
        assert abs(m(page)["input"] - (base["input"] + 140)) <= 2


@pytest.mark.parametrize("h", [420, 300])
def test_on_a_short_screen_the_box_never_pushes_the_console_past_its_height(h):
    with open_board() as page:
        open_console(page, 390, h)
        # At 300px the header, strip and keys alone already overrun the
        # console; the box must add nothing to that.
        base = page.evaluate("(() => { const r = window.ctbConsole._el().root; return r.scrollHeight - r.clientHeight; })()")
        drag(page, 5000)
        r = page.evaluate("""(() => {
          const e = window.ctbConsole._el();
          const R = e.root.getBoundingClientRect();
          const inside = n => { const b = n.getBoundingClientRect();
            return b.top >= R.top - 1 && b.bottom <= R.bottom + 1; };
          const grip = document.querySelector('#ctb-console .con-grip');
          return { over: e.root.scrollHeight - e.root.clientHeight, input: e.input.getBoundingClientRect().height,
                   rootH: e.root.clientHeight,
                   grip: inside(grip), keys: inside(e.keys), box: inside(e.input) };
        })()""")
        assert r["over"] <= max(base, 0) + 1, r
        if base <= 0:
            assert r["grip"] and r["keys"] and r["box"], r
        assert r["input"] <= r["rootH"] * 0.8 + 1
