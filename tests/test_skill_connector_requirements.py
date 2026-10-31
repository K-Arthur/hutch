"""A skill that needs a connector tool, and readiness that says so.

Before the connector plane existed, a skill could only require a native tool. Once connector
tools became grantable store rows, a skill requiring one looked permanently unsatisfiable: the
tool was not in the Bot's allowlist and never would be, and neither the runtime nor the readiness
report read the grant. These tests pin the connector-aware resolution in both places, because a
report that disagrees with execution is worse than no report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hutch import skills as sk
from hutch.models import ApprovalMode, Bot, InferenceMode
from hutch.readiness import bot_readiness

CONNECTOR_SKILL = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "1.0"
  hutch.requires-tools: "{tool}"
---

## Steps
1. Ask the connector for the current time.
2. Report it.
"""

TOOL = "mcp__time__get_current_time"


def make_skill(root: Path, name: str, tool: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        CONNECTOR_SKILL.format(name=name, description="Needs a connector tool.", tool=tool),
        encoding="utf-8")
    return directory


@pytest.fixture
def skill_bot(tmp_path, store):
    """An installed, reviewed, enabled skill bound to a persisted Bot."""
    root = tmp_path / "incoming"
    registry = sk.SkillRegistry(store.config.state_dir, roots=[sk.SkillRoot("project", "hutch", root)])
    make_skill(root, "clock", TOOL)
    registry.install_path(root / "clock")
    registry.trust("clock")
    registry.enable("clock")
    bot = store.create_bot(Bot(name="skill-bot", model="mock/demo", tools=["files"],
                               skills=["clock"], approval_mode=ApprovalMode.auto))
    return registry, bot, store


def _bind(registry, bot, *, connector_tools):
    return registry.resolve_binding(bot, "clock", available_connections=set(),
                                    connector_tools=connector_tools)


def test_an_ungranted_connector_tool_blocks_the_skill_with_its_own_code(skill_bot):
    registry, bot, _store = skill_bot
    skill, reason, code = _bind(registry, bot, connector_tools=set())
    assert skill is None
    assert code == "requires_connector_tools"
    assert "Connectors" in reason and TOOL in reason


def test_a_granted_connector_tool_satisfies_the_skill(skill_bot):
    registry, bot, _store = skill_bot
    skill, reason, code = _bind(registry, bot, connector_tools={TOOL})
    assert code == "ok", reason
    assert skill is not None and skill.name == "clock"


def test_a_native_tool_requirement_still_uses_the_native_code(skill_bot):
    """The connector code must not swallow ordinary missing tools."""
    registry, bot, _store = skill_bot
    package = registry.package_path("clock")
    text = (package / "SKILL.md").read_text(encoding="utf-8")
    (package / "SKILL.md").write_text(text.replace(TOOL, "some_native_tool"), encoding="utf-8")
    registry.trust("clock")
    _skill, reason, code = _bind(registry, bot, connector_tools={TOOL})
    assert code == "requires_tools", reason
    assert "some_native_tool" in reason


def test_readiness_and_the_runtime_agree_about_the_skill(skill_bot):
    """The report is only useful if execution reaches the same verdict."""
    registry, bot, _store = skill_bot
    resolved = registry.effective_for_bot(bot, connector_tools=set())
    assert resolved.catalog == []
    assert any("connector tool" in warning for warning in resolved.warnings)

    resolved = registry.effective_for_bot(bot, connector_tools={TOOL})
    assert [skill.name for skill in resolved.catalog] == ["clock"]


def test_readiness_names_the_missing_connector_grant(skill_bot):
    _registry, bot, store = skill_bot
    report = bot_readiness(store, store.config, bot)
    area = next(item for item in report["areas"] if item["id"] == "skills")
    entry = next(item for item in area["items"] if item["name"] == "clock")
    assert entry["status"] == "warning"
    assert "Connectors" in entry["detail"]


def test_a_granted_connector_tool_makes_the_skill_ready(skill_bot):
    _registry, bot, store = skill_bot
    grant_connector_tool(store, bot, TOOL)
    report = bot_readiness(store, store.config, bot)
    area = next(item for item in report["areas"] if item["id"] == "skills")
    entry = next(item for item in area["items"] if item["name"] == "clock")
    assert entry["status"] == "ok", entry["detail"]


def test_strict_offline_withholds_connector_tools_from_skills(skill_bot):
    """A grant is not a route: an offline Bot has no host network, so the tool cannot run."""
    registry, bot, _store = skill_bot
    offline = bot.model_copy(update={"inference_mode": InferenceMode.offline})
    _skill, reason, code = registry.resolve_binding(
        offline, "clock", available_connections=set(), connector_tools={TOOL})
    assert code == "requires_connector_tools", reason


# --------------------------------------------------------------------------- helper


def grant_connector_tool(store, bot, canonical_name: str) -> None:
    """Write the reviewed rows a connector grant consists of, without a real server."""
    integration_id, _, server_tool = canonical_name.removeprefix("mcp__").partition("__")
    with store._tx() as db:
        db.execute("INSERT INTO integrations(integration_id, revision, title, transport, credential_id, "
                   "state, enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
                   (integration_id, "0" * 64, "Time", "mcp_stdio", "", "operation_authorized", 1,
                    "2026-10-31T00:00:00+00:00"))
        db.execute("INSERT INTO integration_tool_catalog(integration_id, server_tool_name, canonical_name, "
                   "schema_revision, title, description, input_schema_json, annotations_json, supported, "
                   "diagnostics_json, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (integration_id, server_tool, canonical_name, "1" * 64, server_tool, "",
                    json.dumps({"type": "object", "properties": {}}), "{}", 1, "[]",
                    "2026-10-31T00:00:00+00:00"))
        db.execute("INSERT INTO integration_tool_grants(integration_id, bot_id, server_tool_name, "
                   "canonical_name, schema_revision, operation_class, granted_at) VALUES (?,?,?,?,?,?,?)",
                   (integration_id, bot.id, server_tool, canonical_name, "1" * 64, "read",
                    "2026-10-31T00:00:00+00:00"))
