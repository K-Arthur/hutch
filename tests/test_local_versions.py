"""Version gates name the feature and the upgrade, and never guess an unknown version."""

from __future__ import annotations

import pytest

from hutch.health import runtime_health
from hutch.hardware import Hardware, RuntimeInfo
from hutch.providers.base import Health
from hutch.providers.local.versions import at_least, compare, parse_version, unmet, upgrade_advice


@pytest.mark.parametrize("text,expected", [
    ("0.40.13", (0, 40, 13)),
    ("v0.9.0", (0, 9, 0)),
    ("1.2", (1, 2)),
    (" 0.4.0 ", (0, 4, 0)),
    ("b12144-69ee2ecc0", None),
    ("", None),
    (None, None),
])
def test_version_parsing(text, expected):
    assert parse_version(text) == expected


def test_numeric_segments_compare_as_numbers_not_strings():
    assert compare((0, 10, 0), (0, 9, 6)) > 0
    assert compare((0, 9, 0), (0, 9, 0, 1)) < 0
    assert compare((1,), (1, 0, 0)) == 0


def test_at_least_is_tri_state_for_an_unknown_runtime():
    assert at_least("0.10.0", (0, 10, 0)) is True
    assert at_least("0.9.0", (0, 10, 0)) is False
    assert at_least("b12144", (0, 10, 0)) is None


def test_ollama_gates_match_the_published_release_notes():
    assert [gate.feature for gate in unmet("ollama", "0.2.9")] == [
        "tools", "structured_output", "thinking", "measured_window"]
    assert [gate.feature for gate in unmet("ollama", "0.9.0")] == ["measured_window"]
    assert unmet("ollama", "0.10.0") == []
    assert unmet("ollama", "0.40.13") == []


def test_lmstudio_gates_match_the_api_changelog():
    assert [gate.feature for gate in unmet("lmstudio", "0.3.5")] == ["tools", "ttl", "native_api"]
    assert unmet("lmstudio", "0.4.0") == []


def test_llamacpp_has_no_invented_build_floor():
    assert unmet("llamacpp", "b12144-69ee2ecc0") == []
    assert upgrade_advice("llama.cpp", "b12144-69ee2ecc0") == ""


def test_advice_names_the_highest_required_version_and_the_features():
    advice = upgrade_advice("ollama", "0.4.0")
    assert advice == ("upgrade Ollama to 0.10.0 or newer for schema-constrained output, thinking "
                      "control, the applied context window in /api/ps")
    assert upgrade_advice("ollama", "0.40.13") == ""
    assert upgrade_advice("ollama", "") == ""


class _Provider:
    def __init__(self, version: str):
        self.version = version

    def health(self):
        return Health(ok=True, version=self.version)


def test_health_keeps_the_reported_version_and_says_what_to_upgrade(config, store):
    hw = Hardware(ram_total_gb=16, ram_available_gb=12, runtimes=[
        RuntimeInfo("ollama", True, True, "http://x", "", "running")])
    row = [h for h in runtime_health(config, store, hw, ollama=_Provider("0.9.0")) if h.name == "ollama"][0]
    assert row.version == "0.9.0"
    assert "running 0.9.0" in row.detail
    assert row.fix == "upgrade Ollama to 0.10.0 or newer for the applied context window in /api/ps"


def test_health_advises_lmstudio_from_its_reported_version(config, store):
    hw = Hardware(ram_total_gb=16, ram_available_gb=12, runtimes=[
        RuntimeInfo("lmstudio", True, True, "http://y", "0.3.5", "running")])
    row = [h for h in runtime_health(config, store, hw) if h.name == "lmstudio"][0]
    assert "upgrade LM Studio to 0.4.0 or newer" in row.fix
