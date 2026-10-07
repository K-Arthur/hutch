"""Shared fixtures: isolated state dir + store per test."""

from __future__ import annotations

import pytest

from openbot.config import OpenBotConfig, get_config
from openbot.store import Store


@pytest.fixture()
def config(tmp_path, monkeypatch) -> OpenBotConfig:
    monkeypatch.setenv("OPENBOT_STATE_DIR", str(tmp_path / "state"))
    return get_config()


@pytest.fixture()
def store(config) -> Store:
    s = Store(config)
    yield s
    s.close()
