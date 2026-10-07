"""Shared fixtures: isolated state dir + store per test."""

from __future__ import annotations

import pytest

from hutch.config import hutchConfig, get_config
from hutch.store import Store


@pytest.fixture()
def config(tmp_path, monkeypatch) -> hutchConfig:
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    return get_config()


@pytest.fixture()
def store(config) -> Store:
    s = Store(config)
    yield s
    s.close()
