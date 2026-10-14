"""The trash button's automatic retry for a plain session must still catch
the case where the server's second look says it is a worktree after all --
the same "arm" the console's Ctrl+Q gives a blocked worktree, not an error
toast.
"""

import pytest  # noqa: F401

from live_board import board  # noqa: F401  (fixture)

DELETE_MODAL = "#delete-modal"


def _queue_retry_finds_worktree(board, name):
    # First answer: blocked, plain session -> handleTrashClick retries
    # automatically. Second answer (the forced retry): the server's own
    # check says it is a worktree after all -- must open the confirmation,
    # not show "삭제 실패".
    board.ctb_delete_queue[name] = [
        (409, {"status": "blocked", "check": {"is_worktree": False, "reasons": ["dirty"]}}),
        (409, {"status": "blocked", "check": {"is_worktree": True, "reasons": ["dirty"]}}),
    ]


def test_a_retry_the_server_finds_is_a_worktree_opens_the_confirm_not_an_error(board):
    name = "claude_gamma"
    _queue_retry_finds_worktree(board, name)
    board.eval_on_selector(f'[data-delete-session="{name}"]', "el => el.click()")
    board.wait_for_selector(DELETE_MODAL, state="visible")
    assert not board.eval_on_selector_all(
        "#board-toast", "els => els.some(e => e.style.display !== 'none' "
        "&& e.textContent.includes('삭제 실패'))"
    ), "an error toast means the retry's worktree answer was mishandled"


def test_a_second_click_mid_request_is_ignored_even_after_a_rerender(board):
    """Guarded by session name, not by the button element: a card re-render
    swaps in a fresh, enabled button while the first delete is in flight."""
    name = "claude_gamma"
    board.ctb_delete_queue[name] = [(200, {"status": "deleted"})]
    board.evaluate(
        "(name) => {"
        "  const btn = document.querySelector(`[data-delete-session=\"${name}\"]`);"
        "  btn.click();"
        "  const btn2 = btn.cloneNode(true);"
        "  btn2.disabled = false;"
        "  btn.replaceWith(btn2);"
        "  btn2.click();"
        "}",
        name,
    )
    board.wait_for_timeout(300)
    deletes = [p for p in board.ctb_requests if p == f"/api/sessions/{name}/delete"]
    assert len(deletes) == 1


def test_the_confirm_trashes_the_worktree_with_its_reasons_shown(board):
    """Also covers fix #2: the modal must show the check's reasons, not
    just the generic worktree warning."""
    name = "claude_gamma"
    _queue_retry_finds_worktree(board, name)
    board.eval_on_selector(f'[data-delete-session="{name}"]', "el => el.click()")
    board.wait_for_selector(DELETE_MODAL, state="visible")
    body = board.eval_on_selector("#delete-modal-body", "e => e.textContent")
    assert "dirty" in body
