"""Dropping a file on the console, and picking one on a phone.

Driven in a real browser because all of it is DOM behaviour: a DataTransfer
carrying a file, an <input type=file> the page never shows, and the drag
counter that decides whether the overlay is up. A jsdom stand-in would only
prove the stub.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

CONSOLE = "#ctb-console"
CLIP = "#ctb-console button[aria-label='파일 올리기']"


def open_console(page, name="claude_alpha"):
    page.evaluate("name => window.ctbConsole.open(name)", name)
    page.wait_for_selector(CONSOLE, state="visible")
    page.wait_for_selector("#ctb-console [data-line]")


def drop_files(page, files, target=CONSOLE):
    """A real drop: a DataTransfer with real File objects on it."""
    page.evaluate(
        """({sel, files}) => {
            const dt = new DataTransfer();
            for (const f of files) dt.items.add(new File([f.body], f.name, {type: 'text/plain'}));
            const el = document.querySelector(sel);
            for (const type of ['dragenter', 'dragover', 'drop']) {
              el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt}));
            }
        }""",
        {"sel": target, "files": files},
    )
    page.wait_for_timeout(250)


def box(page):
    return page.eval_on_selector("#ctb-console textarea", "el => el.value")


def test_a_dropped_file_is_uploaded_to_the_open_session(board):
    open_console(board)
    drop_files(board, [{"name": "notes.csv", "body": "a,b\n1,2\n"}])
    assert board.ctb_uploads == [{
        "session": "claude_alpha",
        "filename": "notes.csv",
        "body": "a,b\n1,2\n",
        "token": "test-token",
        "content_type": "text/plain",
    }]


def test_the_path_lands_in_the_box_and_is_not_sent(board):
    """The whole point: the user says what to do with the file in words, so
    the path has to be where the words are typed."""
    open_console(board)
    drop_files(board, [{"name": "shot.png", "body": "x"}])
    assert "/home/someone/projects/demo/.ctb-uploads/shot.png" in box(board)
    # Nothing was typed into the session -- no prompt request went out.
    assert not [u for u in board.ctb_requests if u.endswith("/prompt")]


def test_several_files_go_one_at_a_time_and_all_arrive(board):
    open_console(board)
    drop_files(board, [{"name": "a.txt", "body": "1"},
                       {"name": "b.txt", "body": "2"},
                       {"name": "c.txt", "body": "3"}])
    assert [u["filename"] for u in board.ctb_uploads] == ["a.txt", "b.txt", "c.txt"]
    value = box(board)
    for name in ("a.txt", "b.txt", "c.txt"):
        assert name in value


def test_a_failed_upload_says_so_and_puts_no_path_in_the_box(board):
    open_console(board)
    board.ctb_upload_fail = 413
    drop_files(board, [{"name": "huge.bin", "body": "x"}])
    assert board.ctb_uploads, "the request was not even attempted"
    assert ".ctb-uploads" not in box(board)
    status = board.eval_on_selector("#ctb-console [role='status'], #ctb-console div",
                                    "el => el.textContent") or ""
    assert board.evaluate(
        "() => [...document.querySelectorAll('#ctb-console *')]"
        "  .some(e => e.textContent.includes('실패'))"), status


def test_a_drag_without_files_does_not_raise_the_overlay(board):
    """Selecting text in the pane and dragging it is not an upload."""
    open_console(board)
    board.evaluate(
        """() => {
            const dt = new DataTransfer();
            dt.setData('text/plain', 'just words');
            document.querySelector('#ctb-console').dispatchEvent(
              new DragEvent('dragenter', {bubbles: true, cancelable: true, dataTransfer: dt}));
        }""")
    assert not overlay_up(board)


def overlay_up(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#ctb-console div')]"
        "  .some(e => e.textContent === '놓으면 업로드' && e.style.display === 'flex')")


def test_the_overlay_survives_crossing_a_child_element(board):
    """dragenter/leave fire per element; a naive handler flickers it off over
    every button on the way to the drop."""
    open_console(board)
    board.evaluate(
        """() => {
            const dt = new DataTransfer();
            dt.items.add(new File(['x'], 'x.txt'));
            const root = document.querySelector('#ctb-console');
            const child = root.querySelector('textarea');
            const ev = t => new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt});
            root.dispatchEvent(ev('dragenter'));
            child.dispatchEvent(ev('dragenter'));   /* moved onto the box */
            root.dispatchEvent(ev('dragleave'));    /* ...and off the root */
        }""")
    assert overlay_up(board), "the overlay vanished while the file was still in the air"


def test_the_clip_button_uploads_to_the_session_it_was_tapped_on(board):
    """A phone's picker takes seconds; switching console meanwhile must not
    redirect the file into another project."""
    open_console(board, "claude_alpha")
    board.click(CLIP)
    board.evaluate("name => window.ctbConsole.open(name)", "claude_beta")
    board.wait_for_timeout(150)
    board.set_input_files("#ctb-console input[type=file]",
                          files=[{"name": "late.txt", "mimeType": "text/plain",
                                  "buffer": b"late"}])
    board.wait_for_timeout(300)
    assert [u["session"] for u in board.ctb_uploads] == ["claude_alpha"]


def test_a_stray_drop_on_the_page_does_not_navigate_away(board):
    """Without the guard the browser replaces the dashboard with the file and
    a home-screen PWA has no way back."""
    open_console(board)
    prevented = board.evaluate(
        """() => {
            const dt = new DataTransfer();
            dt.items.add(new File(['x'], 'x.txt'));
            const ev = new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt});
            document.body.appendChild(document.createElement('span')).dispatchEvent(ev);
            return ev.defaultPrevented;
        }""")
    assert prevented


def test_no_page_errors(board):
    open_console(board)
    drop_files(board, [{"name": "a.txt", "body": "1"}])
    assert board.ctb_errors == []


def test_a_path_that_lands_after_a_switch_waits_in_its_own_session(board):
    """A phone upload takes seconds and the user reads something else
    meanwhile. The path used to be dropped on the floor: the file was on disk
    and its path was nowhere."""
    open_console(board, "claude_alpha")
    board.click(CLIP)
    board.evaluate("name => window.ctbConsole.open(name)", "claude_beta")
    board.wait_for_timeout(150)
    board.set_input_files("#ctb-console input[type=file]",
                          files=[{"name": "late.txt", "mimeType": "text/plain",
                                  "buffer": b"late"}])
    board.wait_for_timeout(400)

    # Not in the session being read...
    assert ".ctb-uploads" not in box(board)
    # ...but waiting in the one it was uploaded for.
    board.evaluate("name => window.ctbConsole.open(name)", "claude_alpha")
    board.wait_for_timeout(250)
    assert "/home/someone/projects/demo/.ctb-uploads/late.txt" in box(board)
