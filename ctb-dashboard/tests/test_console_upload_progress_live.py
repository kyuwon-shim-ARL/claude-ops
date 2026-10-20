"""While files upload, the status line says how far along they are.

Which file of how many (by number: a name would not fit one line on a
phone) and its percent, the whole batch's percent and size,
and once a second of data exists, the time left at the rate so far:
  업로드 2/5 · 43% · 전체 31% 12/40MB · 2분 남음

The words come from a pure function, tested directly. The wiring -- that
the upload's progress events reach that line, file by file -- is driven
through a stand-in XMLHttpRequest whose progress the test releases step by
step, since a local route answers too fast to ever be caught mid-body.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)
import live_board

MB = 1024 * 1024


def text(page, *args):
    return page.evaluate("a => window.ctbConsole._uploadProgressText(...a)", list(args))


def test_one_file_shows_its_percent_size_and_time_left(board):
    # 10MB file, 4MB through after 2s: 2MB/s, 3s to go.
    t = text(board, 0, 1, 4 * MB, 10 * MB, 0, 10 * MB, 2000)
    assert t == "업로드 1/1 · 40% · 4.0/10MB · 3초 남음"


def test_several_files_add_the_batch_percent(board):
    # Second of three; the first (6MB) is done, 2MB of the second (4MB).
    # 8 of 20MB in 4s: 2MB/s, 12MB left -> 6s.
    t = text(board, 1, 3, 2 * MB, 4 * MB, 6 * MB, 20 * MB, 4000)
    assert t == "업로드 2/3 · 50% · 전체 40% 8.0/20MB · 6초 남음"


def test_minutes_round_up(board):
    # 1MB of 100MB in 2s: 0.5MB/s, 99MB left -> 198s, rounded up to 4분.
    t = text(board, 0, 2, 1 * MB, 60 * MB, 0, 100 * MB, 2000)
    assert t == "업로드 1/2 · 1% · 전체 1% 1.0/100MB · 4분 남음"


def test_no_estimate_before_a_second_of_data(board):
    t = text(board, 0, 1, 1 * MB, 10 * MB, 0, 10 * MB, 400)
    assert "남음" not in t and "10%" in t


FAKE_XHR = """
window.__xhrs = [];
window.XMLHttpRequest = function () {
  var self = this;
  this.upload = {};
  this.headers = {};
  this.open = function (m, u) { self.url = u; };
  this.setRequestHeader = function (k, v) { self.headers[k] = v; };
  this.send = function (body) { self.body = body; window.__xhrs.push(self); };
  this.progress = function (n) { self.upload.onprogress({ loaded: n }); };
  this.fail = function (status) { self.status = status; self.responseText = '{"detail":"no"}'; self.onload(); };
  this.error = function () { self.onerror(); };
  this.expire = function () { self.ontimeout(); };   // not .timeout: the page sets that
  this.finish = function (name) {
    self.status = 200;
    self.responseText = JSON.stringify({ path: '/p/' + name, dir: '/p' });
    self.onload();
  };
};
"""


def status(page):
    return page.evaluate("window.ctbConsole._el().status.textContent")


def test_progress_events_reach_the_status_line_file_by_file():
    with live_board.open_board(init=FAKE_XHR) as page:
        page.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
        page.wait_for_selector("#ctb-console", state="visible")
        page.evaluate("""() => {
          const dt = new DataTransfer();
          dt.items.add(new File([new Uint8Array(1000)], 'one.bin'));
          dt.items.add(new File([new Uint8Array(3000)], 'two.bin'));
          const el = document.querySelector('#ctb-console');
          for (const t of ['dragenter', 'dragover', 'drop'])
            el.dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt}));
        }""")
        page.wait_for_function("window.__xhrs.length === 1")
        assert "업로드 1/2 · 0%" in status(page)
        page.wait_for_timeout(300)                    # past the paint throttle
        page.evaluate("window.__xhrs[0].progress(500)")
        assert "업로드 1/2 · 50% · 전체 12%" in status(page)
        page.evaluate("window.__xhrs[0].finish('one.bin')")
        page.wait_for_function("window.__xhrs.length === 2")
        assert "업로드 2/2 · 0% · 전체 25%" in status(page)
        page.wait_for_timeout(300)
        page.evaluate("window.__xhrs[1].progress(1500)")
        assert "업로드 2/2 · 50% · 전체 62%" in status(page)
        page.evaluate("window.__xhrs[1].finish('two.bin')")
        page.wait_for_function(
            "window.ctbConsole._el().status.textContent.includes('2개 업로드됨')")


def test_the_worst_case_line_fits_one_line_on_an_iphone_12(board):
    """The status line keeps its height so the pane does not move."""
    board.set_viewport_size({"width": 390, "height": 844})
    board.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
    board.wait_for_selector("#ctb-console", state="visible")
    # Two-digit index, 99% twice, mixed units, an hours estimate.
    # 99% of the batch took 99 x 11h50m, so the last 1% has 11h50m to go.
    worst = text(board, 9, 12, 1013 * 1024, 1024 * 1024,
                 1246 * MB, 1259 * MB, 99 * (11 * 3600 + 50 * 60) * 1000)
    assert worst.startswith("업로드 10/12 · 98% · 전체 99% 1.2/1.2GB · 1") and "시간" in worst, worst
    h = board.evaluate("""t => { const s = window.ctbConsole._el().status;
      const glyph = document.createElement('span');   // stands in for the 15px icon
      glyph.style.cssText = 'display:inline-block;width:15px;height:15px;flex-shrink:0';
      s.textContent = ''; s.append(glyph, t); s.style.visibility = 'visible';
      return s.getBoundingClientRect().height; }""", worst)
    assert h <= 24, (worst, h)


def test_gigabytes_and_hours(board):
    # 1GB of 10GB in 10 min: 9GB left at that rate -> 90 min, said as 2시간.
    t = text(board, 0, 1, 1024 * MB, 10240 * MB, 0, 10240 * MB, 600000)
    assert t == "업로드 1/1 · 10% · 1.0/10.0GB · 2시간 남음"


def test_formats_at_the_edges(board):
    f = lambda *a: text(board, 0, 1, *a)
    assert "0KB/" in f(0, 40 * MB, 0, 40 * MB, 0)
    assert "1.0/2.0MB" in f(1023.9 * 1024, 2 * MB, 0, 2 * MB, 0)  # not 1024KB
    assert "10/20MB" in f(10 * MB - 1, 20 * MB, 0, 20 * MB, 0)    # not 10.0
    # 3599s left is an hour, not "60분".
    assert f(1 * MB, 3600 * MB, 0, 3600 * MB, 1000).endswith("· 1시간 남음")


def drop_two(page):
    page.evaluate("n => window.ctbConsole.open(n)", "claude_alpha")
    page.wait_for_selector("#ctb-console", state="visible")
    page.evaluate("""() => {
      const dt = new DataTransfer();
      dt.items.add(new File([new Uint8Array(1000)], 'one.bin'));
      dt.items.add(new File([new Uint8Array(3000)], 'two.bin'));
      const el = document.querySelector('#ctb-console');
      for (const t of ['dragenter', 'dragover', 'drop'])
        el.dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt}));
    }""")
    page.wait_for_function("window.__xhrs.length === 1")


@pytest.mark.parametrize("how, word", [("error()", "전송 실패"), ("expire()", "시간 초과"),
                                       ("fail(413)", "no")])
def test_a_failed_file_is_reported_and_the_next_still_goes(how, word):
    with live_board.open_board(init=FAKE_XHR) as page:
        drop_two(page)
        page.evaluate(f"window.__xhrs[0].{how}")
        page.wait_for_function("window.__xhrs.length === 2")
        # The failed file's bytes count as through: the batch moves on.
        assert "업로드 2/2 · 0% · 전체 25%" in status(page)
        page.evaluate("window.__xhrs[1].finish('two.bin')")
        page.wait_for_function(
            "window.ctbConsole._el().status.textContent.includes('1개 실패')")
        assert word in status(page)


def test_the_token_rides_on_the_request_and_a_403_retries_with_the_new_one():
    with live_board.open_board(init=FAKE_XHR) as page:
        page.on("dialog", lambda d: d.accept("fresh-token"))
        drop_two(page)
        assert page.evaluate("window.__xhrs[0].headers['X-CTB-Secret']") == "test-token"
        page.evaluate("window.__xhrs[0].fail(403)")
        page.wait_for_function("window.__xhrs.length === 2")
        retry = page.evaluate("[window.__xhrs[1].headers['X-CTB-Secret'], window.__xhrs[1].body.name]")
        assert retry == ["fresh-token", "one.bin"]
