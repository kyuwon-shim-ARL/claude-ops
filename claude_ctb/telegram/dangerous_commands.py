"""
Dangerous command detection and confirmation handling.
"""
import re
import time
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)


# Dangerous command patterns
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
    """
    Check if command matches dangerous patterns.

    Args:
        command: Command to check

    Returns:
        True if dangerous, False otherwise
    """
    # Limit command length
    if len(command) > 10000:
        # T041: Log dangerous command detection
        logger.warning(f"Dangerous command detected (too long): length={len(command)}")
        return True

    # Check against patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            # T041: Log pattern match
            logger.warning(f"Dangerous command detected (pattern='{pattern}'): {command[:100]}")
            return True

    return False


@dataclass
class PendingConfirmation:
    """
    Pending confirmation for dangerous command.

    Attributes:
        confirmation_id: Unique ID for this confirmation
        session_name: Target session
        command: Command to execute
        created_at: Creation timestamp
        status: Current status (PENDING, CONFIRMED, CANCELLED, EXPIRED)
    """

    confirmation_id: str
    session_name: str
    command: str
    created_at: float
    status: str = "PENDING"

    def is_expired(self, timeout: int = 60) -> bool:
        """Check if confirmation has expired."""
        expired = (time.time() - self.created_at) > timeout
        if expired and self.status == "PENDING":
            # T041: Log timeout
            logger.warning(f"Confirmation EXPIRED for session '{self.session_name}' after {timeout}s")
        return expired

    @staticmethod
    def generate_id(session_name: str, command: str) -> str:
        """Generate unique confirmation ID."""
        data = f"{session_name}:{command}:{time.time()}"
        return hashlib.md5(data.encode()).hexdigest()


# Global pending confirmations (in-memory)
pending_confirmations: Dict[str, PendingConfirmation] = {}


def create_confirmation(session_name: str, command: str) -> PendingConfirmation:
    """Create new pending confirmation."""
    conf_id = PendingConfirmation.generate_id(session_name, command)
    confirmation = PendingConfirmation(
        confirmation_id=conf_id,
        session_name=session_name,
        command=command,
        created_at=time.time()
    )
    pending_confirmations[conf_id] = confirmation

    # T041: Log confirmation request
    logger.info(f"Confirmation requested for session '{session_name}': {command[:100]}")

    return confirmation


def get_confirmation(conf_id: str) -> Optional[PendingConfirmation]:
    """Get confirmation by ID."""
    return pending_confirmations.get(conf_id)


def cleanup_expired_confirmations(timeout: int = 60):
    """Remove expired confirmations."""
    expired = [
        conf_id for conf_id, conf in pending_confirmations.items()
        if conf.is_expired(timeout)
    ]
    for conf_id in expired:
        pending_confirmations[conf_id].status = "EXPIRED"
        del pending_confirmations[conf_id]
