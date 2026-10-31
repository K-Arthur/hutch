"""Tests for the runtime registry (no provider calls; no credential reads)."""

from __future__ import annotations

import pytest

from hutch.runtime.registry import (
    ENABLED_RUNTIME_IDS,
    RUNTIMES,
    descriptor,
    detect_installed_clis,
    enabled,
    registry_json,
    STATUSES,
)


def test_registry_contract_is_complete_and_explicit():
    ids = [item.id for item in RUNTIMES]
    assert len(ids) == len(set(ids))
    assert {"builtin", "opencode", "pi", "claude-code", "codex", "gemini-cli"} <= set(ids)
    for item in RUNTIMES:
        assert item.status in STATUSES
        assert item.title and item.process_model and item.credential_boundary
        assert item.permission_boundary and item.cancellation and item.session
    assert descriptor("builtin").usage_reservation is True
    # Only the built-in runtime reserves provider usage before a model call.
    assert [item.id for item in RUNTIMES if item.usage_reservation] == ["builtin"]
    assert descriptor("not-a-runtime") is None


def test_enabled_runtimes_match_the_switch_only_for_implemented_engines():
    assert tuple(item.id for item in enabled()) == ENABLED_RUNTIME_IDS
    assert descriptor("pi").enabled is False
    assert descriptor("claude-code").enabled is False
    assert descriptor("opencode").enabled is True


def test_cli_detection_reports_installed_without_touching_credentials():
    calls = []

    def finder(binary):
        return "/usr/bin/" + binary if binary in ("opencode", "claude") else None

    def runner(path):
        calls.append(path)
        return {"installed": True, "version": "9.9.9-test", "error": ""}

    def noisy(path):
        calls.append(path)
        return {"installed": True, "version": "PlatformError: Unknown: FileSystem.open (/home/user/log/x)", "error": ""}

    found = detect_installed_clis(finder=finder, runner=runner)
    assert set(found) == {"opencode", "claude-code", "codex", "pi", "gemini-cli"}
    assert found["opencode"]["installed"] is True
    assert found["opencode"]["version"] == "9.9.9-test"
    assert found["codex"]["installed"] is False
    assert len(calls) == 2
    assert all("secret" not in str(value).lower() for value in found.values())
    noisy_found = detect_installed_clis(finder=finder, runner=noisy)
    assert noisy_found["opencode"]["version"] == ""  # error text is never rendered as a version or path


def test_registry_json_omits_binary_paths_and_can_skip_detection():
    body = registry_json(detect=False)
    assert body["enabled"] == list(ENABLED_RUNTIME_IDS)
    assert body["runtimes"]
    assert all("cli" in item for item in body["runtimes"])
    assert "usage_reservation" in body["runtimes"][0]
