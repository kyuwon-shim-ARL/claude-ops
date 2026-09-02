"""Send text and control keys into a live Claude Code session via tmux.

Kept out of server.py so the tmux argv contract can be tested directly.

Two send paths, because tmux send-keys treats a newline as an Enter keystroke:

* single line  -> ``send-keys <text> Enter`` in one call, matching the bot
  (claude_ctb/session_manager.py:354). One call matters: if the text and Enter
  arrive as separate invocations the session can process the text first and
  submit on its own, splitting a prompt in two.
* multiple lines -> ``load-buffer`` + ``paste-buffer -p`` (bracketed paste), so
  the TUI inserts the whole block as text, then a separate Enter submits it.
  Without ``-p`` the first newline submits and the rest of the prompt lands in
  a fresh, empty input.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 4000
_TMUX_TIMEOUT = 5
_BUFFER_NAME = "ctb-prompt"


def session_exists(name: str) -> bool:
    """Does this tmux session exist right now?"""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True, text=True, timeout=_TMUX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("tmux has-session timed out for %s", name)
        return False
    return result.returncode == 0


def pane_command(name: str) -> str | None:
    """Foreground command running in the session's pane, e.g. 'claude' or 'bash'.

    This is what tells a live Claude session apart from a bare shell. Screen
    glyphs were tried first and were wrong: Claude Code draws its input with
    '❯' and └┴┘ box characters, not the ╭╰ set that was guessed, so every real
    session read as a shell. The running process is a fact rather than a
    rendering detail, so it survives Claude changing its UI.

    Returns None if tmux cannot answer -- callers must not treat that as
    evidence of anything.
    """
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", name, "#{pane_current_command}"],
            capture_output=True, text=True, timeout=_TMUX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("tmux display-message timed out for %s", name)
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def pane_has_claude(name: str) -> bool:
    """Is a claude process running under this session's pane?

    pane_command() alone is not enough. tmux reports the foreground process
    *group leader*, and when claude shares a process group with the bash that
    launched it that leader is bash -- so a live Claude session reads as a
    shell. Ten sessions were refused this way before this existed.

    False on any uncertainty: a failed query is not evidence that Claude is
    there, and the caller falls back to judging by the pane command alone,
    which is what it did before.
    """
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", name, "#{pane_pid}"],
            capture_output=True, text=True, timeout=_TMUX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("tmux pane_pid query timed out for %s", name)
        return False
    if result.returncode != 0:
        return False
    pane_pid = (result.stdout or "").strip()
    if not pane_pid.isdigit():
        return False

    try:
        # The whole process table once, then walk down from the pane: launched
        # through a wrapper (uv, a shell function), claude is a grandchild
        # rather than a direct child.
        table = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm="],
            capture_output=True, text=True, timeout=_TMUX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ps query timed out for %s", name)
        return False
    if table.returncode != 0:
        return False

    children: dict[str, list[tuple[str, str]]] = {}
    for line in (table.stdout or "").splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid, ppid, comm = parts
        children.setdefault(ppid, []).append((pid, comm.strip()))

    # Exact command names: a 'claude-something' log tailer is not Claude.
    seen, stack = set(), [pane_pid]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for pid, comm in children.get(current, ()):
            if comm == "claude":
                return True
            stack.append(pid)
    return False


def _tmux(argv: list[str], stdin_text: str | None = None) -> None:
    """Run a tmux command, raising on anything but success."""
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": _TMUX_TIMEOUT,
    }
    if stdin_text is not None:
        kwargs["input"] = stdin_text
    result = subprocess.run(argv, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(
            f"tmux {' '.join(argv[1:3])} failed (rc={result.returncode}): "
            f"{(result.stderr or '').strip()}"
        )


def _validate(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("prompt is empty")
    if len(text) > MAX_PROMPT_LENGTH:
        raise ValueError(
            f"prompt is {len(text)} chars, over the {MAX_PROMPT_LENGTH} limit"
        )
    return stripped


# Characters Claude Code reads as a mode switch rather than as text: '!' opens
# the bash box, '#' the memory box. Both are consumed at keypress time, so they
# only work when they arrive alone -- see _send_lead_char.
_MODE_CHARS = ("!", "#")


def _send_lead_char(name: str, char: str) -> None:
    """Deliver a mode-switch character as its own keystroke.

    ``send-keys -t s '!cf' Enter`` reaches the pane as a single 4-byte read
    (verified against a raw-mode reader), and a TUI that reads stdin in chunks
    treats a multi-byte chunk as a paste -- inserted as literal text, with no
    keypress for the '!' to act on. So a phone typing '!cf' got the string
    '!cf' in the prompt box instead of the bash box.

    Sent on its own the character arrives in its own read and switches the mode.
    Consecutive send-keys calls do not coalesce in the pty (checked back to
    back, ~4ms apart), so this needs no delay.
    """
    _tmux(["tmux", "send-keys", "-t", name, "-l", char])


def send_prompt(name: str, text: str) -> None:
    """Type `text` into the session and submit it.

    Raises ValueError for unusable input and RuntimeError if tmux refuses.
    """
    body = _validate(text)
    # Normalise line endings so CRLF from a browser textarea does not read as
    # two separate newlines further down.
    body = body.replace("\r\n", "\n").replace("\r", "\n")

    opened_a_box = False
    if body[0] in _MODE_CHARS:
        if len(body) == 1:
            raise ValueError("prompt is only a mode character")
        _send_lead_char(name, body[0])
        body = body[1:]
        opened_a_box = True

    try:
        # A body starting with '-' would be read by tmux as a flag ("command
        # send-keys: invalid flag --"), and send-keys has no '--' terminator.
        # The paste path carries text as data, so it does not care.
        if "\n" not in body and not body.startswith("-"):
            _tmux(["tmux", "send-keys", "-t", name, body, "Enter"])
            return

        _tmux(["tmux", "load-buffer", "-b", _BUFFER_NAME, "-"], stdin_text=body)
        _tmux(["tmux", "paste-buffer", "-b", _BUFFER_NAME, "-t", name, "-p", "-d"])
        _tmux(["tmux", "send-keys", "-t", name, "Enter"])
    except (RuntimeError, subprocess.TimeoutExpired):
        # The mode character already landed, so the session is sitting in an
        # open shell (or memory) box with nothing in it. Leaving it that way is
        # worse than the failed send: the NEXT prompt -- ordinary prose, no '!'
        # -- would be typed into that box and run as a shell command. Escape
        # closes it. Best effort; the original failure is what the caller needs
        # to hear.
        if opened_a_box:
            try:
                _tmux(["tmux", "send-keys", "-t", name, "Escape"])
            except Exception:
                logger.warning("could not close the mode box on %s after a failed send", name)
        raise


def send_interrupt(name: str) -> None:
    """Send ESC -- the same key the bot's /stop uses to halt Claude."""
    _tmux(["tmux", "send-keys", "-t", name, "Escape"])

# Keys the dashboard may send. An allowlist, not an escape hatch: this endpoint
# exists to answer Claude's permission prompts (y/n, numbered choices, arrow
# selection) from a phone. Arbitrary key sequences would be a way to type
# commands while bypassing the destructive-command screening on send_prompt.
ALLOWED_KEYS = frozenset({
    "Enter", "Escape", "Tab", "Space", "BSpace",
    "Up", "Down", "Left", "Right",
    "y", "n", "Y", "N",
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "C-c",
    # Clearing the input line. Ctrl+U is the edit, not the interrupt: verified
    # against a live Claude Code pane with a Bash tool call in flight -- the
    # queued text vanished, the pane offered "Ctrl+Y to paste deleted text",
    # and the command ran to completion. Escape-Escape rewinds the
    # conversation and Ctrl+C interrupts the work; neither is what "clear what
    # I was typing" should cost.
    "C-u",
})


def send_key(name: str, key: str) -> None:
    """Send a single key from ALLOWED_KEYS to the session.

    Raises ValueError for anything outside the allowlist.
    """
    if key not in ALLOWED_KEYS:
        raise ValueError(f"key {key!r} is not in the allowlist")
    _tmux(["tmux", "send-keys", "-t", name, key])
