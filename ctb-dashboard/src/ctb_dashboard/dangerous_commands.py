"""Dangerous-command screening for dashboard-driven session input.

Vendored stateless subset of ``claude_ctb/telegram/dangerous_commands.py``.

Why a copy and not an import: ctb-dashboard is a separate distribution and
does not depend on claude_ctb (it is not in this venv). The repo's existing
convention for shared logic is to vendor the stateless part with provenance
and pin it with a parity test -- see ``sessions.py`` and ``state_detector.py``.
The bot's confirmation machinery (PendingConfirmation, the pending-map, the
Telegram inline-keyboard flow) is stateful and interface-specific, so it is
deliberately NOT copied; only the screening predicate is.

Keep DANGEROUS_PATTERNS byte-identical to the canonical list.
``tests/test_dangerous_parity.py`` fails if the two drift.
"""

import logging
import re

logger = logging.getLogger(__name__)

_MAX_COMMAND_LENGTH = 10000

# Copied verbatim from claude_ctb/telegram/dangerous_commands.py.
# NOTE: the fork-bomb entry is a weak pattern -- ':(){ :|:& };:' contains regex
# metacharacters that are not escaped, so it does not reliably match a real
# fork bomb. It is reproduced as-is on purpose: this module's contract is
# parity with the bot, not improving the pattern set. Any hardening must land
# in the canonical file first so both sides move together.
DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/',  # rm -rf /
    r'\bsudo\s+rm',  # sudo rm
    r'\bsudo\s+',  # any sudo command
    r'\bchmod\s+777',  # chmod 777
    r'\bchown\s+.*\s+/',  # chown on root
    r'\bdd\s+if=',  # dd command
    r'\bmkfs\.',  # format filesystem
    r'\b:(){ :|:& };:',  # fork bomb
]


def is_dangerous_command(command: str) -> bool:
    """Does this text look like a destructive shell command?

    Over-long input is treated as dangerous rather than scanned, matching
    the bot: a multi-kilobyte blob pasted at a shell prompt is not something
    we want to forward blind.
    """
    if len(command) > _MAX_COMMAND_LENGTH:
        logger.warning("Dangerous command rejected (too long): length=%d", len(command))
        return True

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning(
                "Dangerous command rejected (pattern=%r): %s", pattern, command[:100]
            )
            return True

    return False
