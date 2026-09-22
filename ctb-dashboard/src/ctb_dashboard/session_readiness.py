"""Decide whether a session can accept a typed prompt right now.

Sending blind is the failure mode that matters on a phone: the screen is not
visible, tmux send-keys succeeds regardless of what is on it, and the text is
silently eaten by a shell, a permission prompt, or a running task. So the
prompt endpoint asks here first and refuses with the observed state.

State detection is reused from SessionStateAnalyzer rather than reimplemented;
this module only maps states to a send/refuse decision.
"""

import re

from .state_detector import SessionState

# Claude Code draws a bordered input area. If none of these are on screen the
# pane is showing something else -- most often a plain shell -- and a prompt
# typed into it would be executed as a shell command instead of reaching Claude.
# Shells, by the name tmux reports as the pane's foreground command.
# A denylist of shells, not an allowlist of Claude: the risk being guarded
# against is a prompt being executed as a shell command, and anything that is
# not a shell cannot do that. An allowlist was tried first and blocked every
# real session, because it was built from guessed screen glyphs rather than
# from what Claude Code actually draws.
SHELL_COMMANDS = frozenset({
    "bash", "sh", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "ash",
})

# The one thing worth typing at a shell: the command that starts Claude in it.
#
# The guard below exists because a prompt typed at a shell is executed as a
# shell command. Launching Claude is the case where that is the whole point,
# and refusing it left the pane in a state only a keyboard on the machine
# could get out of -- a session that has exited Claude could not be restarted
# from a phone at all.
#
# First word only, and the argument forms all belong to the same binaries:
# `cf` and `cr` are this user's own wrappers around `claude` (fresh session /
# restart with --continue).
SHELL_LAUNCHERS = frozenset({"claude", "cf", "cr", "crl"})

# What turns an allowed command into a different one. Anything that chains
# (`;` `&` `|`), redirects (`<` `>`), substitutes (`$` backtick `(` `)`), or
# expands out of interactive bash's history (`!`). Quotes are NOT here on
# purpose: `cf "첫 프롬프트"` is a documented way to use the launcher.
_SHELL_META = re.compile(r"[;&|<>`$()\\!\n\r]")


def is_shell_launch(text: str | None) -> bool:
    """Is `text` a bare command that starts Claude in this shell?

    Deliberately narrow: one line, first word in the allowlist, and nothing in
    it that could make the shell run something else. A caller who wants to run
    an arbitrary command at a shell has the key endpoint, which types without
    this check and without pretending the result reached Claude.
    """
    if not text:
        return False
    line = text.strip()
    if not line or _SHELL_META.search(line):
        return False
    return line.split()[0] in SHELL_LAUNCHERS


# Refusals that are about *when*, with the reason surfaced to the caller.
#
# WORKING is deliberately absent. Claude Code queues a prompt typed while it is
# busy and runs it in turn -- checked against a live session: a second prompt
# sent eight seconds into a 25-second task was submitted immediately and
# answered after the first, in order. Refusing it blocked the way this is
# actually used, chaining follow-ups while the model works, to guard against a
# loss that does not happen. WAITING_INPUT stays refused: there, free text
# would be read as an answer to a choice.
_REFUSALS = {
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


def is_shell(pane_command: str | None) -> bool:
    """Is the pane sitting at a shell rather than running Claude?

    Unknown or unavailable commands are not shells as far as this is concerned:
    refusing on a failed tmux query would block real work to guard against a
    case we have no evidence for.
    """
    if not pane_command:
        return False
    return pane_command.strip().lstrip("-").lower() in SHELL_COMMANDS


def classify_readiness(
    state: SessionState,
    screen: str | None,
    pane_command: str | None = None,
    claude_running: bool = False,
    text: str | None = None,
) -> tuple[bool, str, str]:
    """-> (can_send, reason_code, human_message).

    UNKNOWN is treated as sendable on purpose: screen reads fail transiently and
    refusing on every hiccup would make remote control unusable. The post-send
    screen diff is what catches a send that went nowhere.

    `claude_running` outranks the pane command. tmux names the foreground
    process *group leader*, so a session whose claude shares a group with the
    bash that launched it reports 'bash' while Claude is plainly running --
    ten live sessions were refused that way. It defaults to False so a caller
    that has not checked keeps the old, stricter behaviour.

    `text` is consulted only to let the command that starts Claude through a
    shell pane; it defaults to None so a caller that does not pass it keeps
    the blanket refusal.
    """
    at_shell = is_shell(pane_command) and not claude_running

    # Checked before the state refusals on purpose: those describe a Claude UI,
    # and there is not one on screen. A shell pane that happens to read as
    # ERROR or WAITING_INPUT -- an old traceback still on screen, a `[y/n]`
    # from whatever ran last -- would otherwise be unable to start the very
    # thing that would clear it.
    if at_shell and is_shell_launch(text):
        return True, "shell_launch", ""

    refusal = _REFUSALS.get(state)
    if refusal is not None:
        code, message = refusal
        return False, code, message

    if at_shell:
        return (
            False,
            "shell",
            f"이 세션은 Claude가 아니라 셸({pane_command})이 떠 있습니다. "
            "프롬프트가 셸 명령으로 실행될 수 있어 전송을 막았습니다. "
            f"({'/'.join(sorted(SHELL_LAUNCHERS))} 로 Claude를 먼저 띄울 수는 있습니다)",
        )

    return True, "ready", ""
