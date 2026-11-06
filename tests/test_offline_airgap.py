from __future__ import annotations

import socket

import pytest

from hutch import sandbox


def test_offline_egress_probe_accepts_a_host_with_only_loopback(monkeypatch):
    """An air-gapped host has no non-loopback address to test against.

    The worker still runs in its own network namespace; the probe's loopback
    listener must show that the worker cannot reach even the host's loopback.
    """
    if not sandbox.status().ok:
        pytest.skip("host lacks the resource-limited bubblewrap worker prerequisites")
    monkeypatch.setattr(sandbox, "_local_non_loopback_addresses",
                        lambda: {socket.AF_INET: [], socket.AF_INET6: []})

    result = sandbox.offline_egress_status(refresh=True)

    assert result.ok, result.reason
