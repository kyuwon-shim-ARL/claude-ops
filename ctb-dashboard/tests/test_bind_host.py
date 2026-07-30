"""Bind-host resolution must never make the service fail to boot.

The dashboard runs under systemd with Restart=always. If it hard-binds to a
specific address (e.g. the tailscale IP) and that interface is not up yet at
boot -- or the IP changed after a tailscale re-login -- bind fails, systemd
restarts, and the service never comes up. So a requested address that is not
assignable must degrade to 0.0.0.0 with a warning instead of raising.
"""

from ctb_dashboard.server import resolve_bind_host


def test_wildcard_is_returned_without_probing():
    """0.0.0.0 is always assignable; don't waste a syscall on it."""
    probed = []

    def probe(host):
        probed.append(host)
        return True

    assert resolve_bind_host("0.0.0.0", probe=probe) == "0.0.0.0"
    assert probed == []


def test_assignable_address_is_honoured():
    assert resolve_bind_host("100.85.200.72", probe=lambda host: True) == "100.85.200.72"


def test_unassignable_address_falls_back_to_wildcard():
    """The boot-loop guard: a dead tailscale IP must not stop the service."""
    assert resolve_bind_host("100.85.200.72", probe=lambda host: False) == "0.0.0.0"


def test_empty_or_none_falls_back_to_wildcard():
    assert resolve_bind_host("", probe=lambda host: False) == "0.0.0.0"
    assert resolve_bind_host(None, probe=lambda host: False) == "0.0.0.0"


def test_localhost_is_honoured_when_assignable():
    """Desktop-only deployments may legitimately want loopback."""
    assert resolve_bind_host("127.0.0.1", probe=lambda host: True) == "127.0.0.1"


def test_real_probe_accepts_loopback_and_rejects_bogus_address():
    """Exercise the real socket probe, not a stub."""
    from ctb_dashboard.server import _address_assignable

    assert _address_assignable("127.0.0.1") is True
    # 203.0.113.0/24 is TEST-NET-3 (RFC 5737) -- never assigned to a local NIC.
    assert _address_assignable("203.0.113.7") is False
