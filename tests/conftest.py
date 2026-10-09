"""Shared fixtures: isolated state dir + store per test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hutch.config import hutchConfig, get_config
from hutch.store import Store


@pytest.fixture(autouse=True)
def _allow_testclient_host(monkeypatch):
    """Starlette's TestClient sends `Host: testserver`; the dashboard only accepts loopback hosts."""
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")


@pytest.fixture(autouse=True)
def _deterministic_execution_fixture(monkeypatch):
    """Inject scenarios into tests without making the product selector test-aware."""
    monkeypatch.setenv("HUTCH_TESTING", "1")
    project = str(Path(__file__).resolve().parent.parent)
    support = str(Path(__file__).resolve().parent / "support")
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(part for part in (support, project, inherited) if part))

    from hutch import engine, modelchoices
    from hutch.runtime import get_runtime
    from tests.support.runtime import test_model_choices_for, test_runtime_for, test_validate_override_for

    monkeypatch.setattr(engine, "get_runtime", lambda bot: test_runtime_for(bot, get_runtime))
    choices_factory = modelchoices.model_choices
    validate_factory = modelchoices.validate_override
    monkeypatch.setattr(modelchoices, "model_choices", lambda *args, **kwargs:
                        test_model_choices_for(args[2], args, kwargs, choices_factory))
    monkeypatch.setattr(modelchoices, "validate_override", lambda config, store, bot, spec, *args, **kwargs:
                        test_validate_override_for(bot, spec, (config, store, bot, spec, *args), kwargs,
                                                   validate_factory))


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
