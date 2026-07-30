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


def send_prompt(name: str, text: str) -> None:
    """Type `text` into the session and submit it.

    Raises ValueError for unusable input and RuntimeError if tmux refuses.
    """
    body = _validate(text)
    # Normalise line endings so CRLF from a browser textarea does not read as
    # two separate newlines further down.
    body = body.replace("\r\n", "\n").replace("\r", "\n")

    if "\n" not in body:
        _tmux(["tmux", "send-keys", "-t", name, body, "Enter"])
        return

    _tmux(["tmux", "load-buffer", "-b", _BUFFER_NAME, "-"], stdin_text=body)
    _tmux(["tmux", "paste-buffer", "-b", _BUFFER_NAME, "-t", name, "-p", "-d"])
    _tmux(["tmux", "send-keys", "-t", name, "Enter"])


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
})


def send_key(name: str, key: str) -> None:
    """Send a single key from ALLOWED_KEYS to the session.

    Raises ValueError for anything outside the allowlist.
    """
    if key not in ALLOWED_KEYS:
        raise ValueError(f"key {key!r} is not in the allowlist")
    _tmux(["tmux", "send-keys", "-t", name, key])
