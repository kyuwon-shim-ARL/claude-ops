"""CTB Dashboard - Real-time Claude Code session monitoring."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("ctb-dashboard")
except PackageNotFoundError:
    __version__ = "0.1.0"  # fallback for editable/dev installs
