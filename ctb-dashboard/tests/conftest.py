"""Shared fixtures.

The control rate limiter is process-global by design -- it protects tmux and the
host, so one budget for the whole server is the point. That makes it shared
state across tests, where one module's sends would otherwise throttle the next
module's. Reset it around every test rather than weakening the production
design.
"""

import pytest

from ctb_dashboard.control_audit import limiter


@pytest.fixture(autouse=True)
def _reset_control_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()
