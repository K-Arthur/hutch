"""Shared fixtures: isolated state dir + store per test."""

from __future__ import annotations

import pytest

from hutch.config import hutchConfig, get_config
from hutch.store import Store


@pytest.fixture(autouse=True)
def _allow_testclient_host(monkeypatch):
    """Starlette's TestClient sends `Host: testserver`; the dashboard only accepts loopback hosts."""
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _sandbox_off_by_default(monkeypatch):
    """The suite exercises policy, scheduling, approvals... with host commands; tests/test_sandbox.py turns containment on itself."""
    monkeypatch.setenv("HUTCH_SANDBOX", "off")


@pytest.fixture()
def config(tmp_path, monkeypatch) -> hutchConfig:
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    return get_config()


@pytest.fixture()
def store(config) -> Store:
    s = Store(config)
    yield s
    s.close()
