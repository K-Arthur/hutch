"""A skill that depends on another skill.

`hutch.requires-tools` and `hutch.requires-connections` answer "does the assistant have what this
procedure needs". This is the third form: the procedure assumes another procedure. Installing the
other skill is not enough to satisfy it, because a skill that is installed but unreviewed, disabled
or not assigned to the assistant is one the model cannot load. The check therefore looks at the
same three states the loader does, and says which one is missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hutch import skills as sk
from hutch.models import ApprovalMode, Bot
from hutch.readiness import bot_readiness

TEMPLATE = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "1.0"
  hutch.requires-tools: "files"
{depends}
---

## Steps
1. Follow the procedure.
"""


def make_skill(root: Path, name: str, depends_on: str = "") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    depends = f'  hutch.requires-skills: "{depends_on}"' if depends_on else ""
    (directory / "SKILL.md").write_text(
        TEMPLATE.format(name=name, description=f"The {name} procedure.", depends=depends),
        encoding="utf-8")
    return directory


@pytest.fixture
def registry(tmp_path, store):
    root = tmp_path / "incoming"
    return sk.SkillRegistry(store.config.state_dir, roots=[sk.SkillRoot("project", "hutch", root)]), root, store


def install(registry: sk.SkillRegistry, root: Path, name: str, depends_on: str = "",
            *, trust: bool = True, enable: bool = True) -> dict:
    make_skill(root, name, depends_on)
    entry = registry.install_path(root / name)
    if trust:
        # Trust is what enables a skill; an untrusted one cannot be enabled at all.
        registry.trust(name)
        if not enable:
            registry.disable(name)
    return entry


def _bind(registry, bot, name):
    return registry.resolve_binding(bot, name, available_connections=set(), connector_tools=set())


def test_a_dependency_that_is_installed_reviewed_enabled_and_assigned_is_satisfied(registry):
    reg, root, store = registry
    install(reg, root, "base")
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["base", "derived"], approval_mode=ApprovalMode.auto))
    skill, reason, code = _bind(reg, bot, "derived")
    assert code == "ok", reason
    assert skill is not None


def test_an_uninstalled_dependency_blocks_with_its_own_code(registry):
    reg, root, store = registry
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["derived"], approval_mode=ApprovalMode.auto))
    skill, reason, code = _bind(reg, bot, "derived")
    assert skill is None
    assert code == "requires_skills"
    assert "base" in reason and "not installed" in reason


def test_an_unreviewed_dependency_blocks(registry):
    reg, root, store = registry
    install(reg, root, "base", trust=False)
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["base", "derived"], approval_mode=ApprovalMode.auto))
    _skill, reason, code = _bind(reg, bot, "derived")
    assert code == "requires_skills"
    assert "has not been reviewed" in reason


def test_a_disabled_dependency_blocks(registry):
    reg, root, store = registry
    install(reg, root, "base", enable=False)
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["base", "derived"], approval_mode=ApprovalMode.auto))
    _skill, reason, code = _bind(reg, bot, "derived")
    assert code == "requires_skills"
    assert "is disabled" in reason


def test_a_dependency_that_is_not_assigned_blocks(registry):
    """Installed and reviewed is not enough: an unassigned skill cannot be loaded by the model."""
    reg, root, store = registry
    install(reg, root, "base")
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["derived"], approval_mode=ApprovalMode.auto))
    _skill, reason, code = _bind(reg, bot, "derived")
    assert code == "requires_skills"
    assert "not assigned to this Bot" in reason


def test_dependencies_are_checked_one_level_only(registry):
    """A stated limit, pinned so it cannot drift silently.

    A dependency that is itself unsatisfiable still counts as satisfied here, because its own
    binding is evaluated when the model or the assistant tries to load it. Extending the check to
    a transitive closure would also need a cycle guard; until then this is the contract.
    """
    reg, root, store = registry
    install(reg, root, "leaf", depends_on="missing-leaf")
    install(reg, root, "middle", depends_on="leaf")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["leaf", "middle"], approval_mode=ApprovalMode.auto))
    _skill, reason, code = _bind(reg, bot, "middle")
    assert code == "ok", reason
    # ...while the leaf itself is correctly refused.
    _leaf, leaf_reason, leaf_code = _bind(reg, bot, "leaf")
    assert leaf_code == "requires_skills" and "missing-leaf" in leaf_reason


def test_readiness_names_the_missing_dependency(registry):
    reg, root, store = registry
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["derived"], approval_mode=ApprovalMode.auto))
    report = bot_readiness(store, store.config, bot)
    area = next(item for item in report["areas"] if item["id"] == "skills")
    entry = next(item for item in area["items"] if item["name"] == "derived")
    assert entry["status"] == "warning"
    assert "depends on the 'base' skill" in entry["detail"]


def test_the_runtime_and_readiness_reach_the_same_verdict(registry):
    reg, root, store = registry
    install(reg, root, "derived", depends_on="base")
    bot = store.create_bot(Bot(name="dep-bot", model="mock/demo", tools=["files"],
                               skills=["derived"], approval_mode=ApprovalMode.auto))
    resolved = reg.effective_for_bot(bot)
    assert resolved.catalog == []
    assert any("depends on the 'base' skill" in warning for warning in resolved.warnings)
