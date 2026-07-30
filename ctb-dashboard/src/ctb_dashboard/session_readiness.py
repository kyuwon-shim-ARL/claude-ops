"""Decide whether a session can accept a typed prompt right now.

Sending blind is the failure mode that matters on a phone: the screen is not
visible, tmux send-keys succeeds regardless of what is on it, and the text is
silently eaten by a shell, a permission prompt, or a running task. So the
prompt endpoint asks here first and refuses with the observed state.

State detection is reused from SessionStateAnalyzer rather than reimplemented;
this module only maps states to a send/refuse decision.
"""

from .state_detector import SessionState

# Claude Code draws a bordered input area. If none of these are on screen the
# pane is showing something else -- most often a plain shell -- and a prompt
# typed into it would be executed as a shell command instead of reaching Claude.
# "> " alone is too loose -- it appears in ordinary shell output and would make
# a shell read as Claude, which is the exact confusion this guards against.
CLAUDE_UI_MARKERS = ("╭─", "╰─", "│ >")

# Refusals that are about *when*, with the reason surfaced to the caller.
_REFUSALS = {
    SessionState.WORKING: (
        "working",
        "세션이 작업 중입니다. 완료를 기다리거나 먼저 중단(interrupt)하세요.",
    ),
    SessionState.WAITING_INPUT: (
        "awaiting_choice",
        "세션이 선택/승인을 기다리고 있습니다. 텍스트 대신 키 전송을 쓰세요.",
    ),
    SessionState.CONTEXT_LIMIT: (
        "context_limit",
        "컨텍스트 한도에 도달했습니다. 세션을 재시작해야 합니다.",
    ),
    SessionState.ERROR: (
        "error",
        "세션이 오류 상태입니다. 화면을 확인하세요.",
    ),
    SessionState.STUCK_AFTER_AGENT: (
        "stuck_after_agent",
        "에이전트 결과 후 멈춘 상태입니다. 화면을 확인하세요.",
    ),
}


def claude_ui_present(screen: str | None) -> bool:
    """Does the pane look like Claude Code's interface (vs a bare shell)?"""
    if not screen:
        return False
    tail = "\n".join(screen.split("\n")[-15:])
    return any(marker in tail for marker in CLAUDE_UI_MARKERS)


def classify_readiness(state: SessionState, screen: str | None) -> tuple[bool, str, str]:
    """-> (can_send, reason_code, human_message).

    UNKNOWN is treated as sendable on purpose: screen reads fail transiently and
    refusing on every hiccup would make remote control unusable. The post-send
    screen diff is what catches a send that went nowhere.
    """
    refusal = _REFUSALS.get(state)
    if refusal is not None:
        code, message = refusal
        return False, code, message

    if not claude_ui_present(screen):
        return (
            False,
            "shell",
            "Claude 입력창이 보이지 않습니다(셸 상태로 보임). "
            "프롬프트가 셸 명령으로 실행될 수 있어 전송을 막았습니다.",
        )

    return True, "ready", ""
