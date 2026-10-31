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


# ------------------------------------------------------------------ resolution: where a dependency comes from

import httpx  # noqa: E402  (kept beside the tests that use it)

from hutch.skill_dependency import MAX_DEPTH, resolve_dependencies  # noqa: E402
from hutch.skill_registry_index import INDEX_FORMAT, RegistryIndex  # noqa: E402

PUBLIC = {"packages.example": ["93.184.216.34"]}


def _resolver(host, port, *args, **kwargs):
    return [(2, 1, 6, "", (PUBLIC[host][0], port))]


def _serve(routes: dict[str, bytes]):
    """Route by Host: netguard dials the validated address and keeps the name in the header."""
    def handler(request):
        url = "https://" + str(request.headers.get("host", "")) + request.url.path
        body = routes.get(url)
        return httpx.Response(200 if body else 404, content=body or b"",
                              headers={"content-type": "application/json"})
    return httpx.MockTransport(handler)


def _index_listing(state, entries: list[dict]) -> RegistryIndex:
    import json

    document = json.dumps({"format": INDEX_FORMAT, "skills": entries}).encode()
    index = RegistryIndex(state, resolver=_resolver,
                          transport=_serve({"https://packages.example/index.json": document}))
    index.add("r1", "https://packages.example/index.json")
    return index


def test_a_satisfied_dependency_reports_ok(registry):
    reg, root, store = registry
    install(reg, root, "base")
    install(reg, root, "user", depends_on="base")
    report = resolve_dependencies(reg, "user")
    assert report["status"] == "ok"
    assert report["dependencies"][0]["installed"] is True


def test_a_missing_dependency_names_a_registry_that_lists_it(registry):
    reg, root, store = registry
    install(reg, root, "user", depends_on="base")
    index = _index_listing(store.config.state_dir, [
        {"name": "base", "url": "https://packages.example/base.zip", "version": "2.0",
         "publisher": "someone", "sha256": "a" * 64}])
    row = resolve_dependencies(reg, "user", index=index)["dependencies"][0]
    assert row["status"] == "missing"
    assert row["available_from"]["registry_id"] == "r1"
    assert row["available_from"]["pinned"] is True
    assert row["available_from"]["version"] == "2.0"


def test_a_missing_dependency_with_no_registry_says_so_plainly(registry):
    reg, root, store = registry
    install(reg, root, "user", depends_on="base")
    row = resolve_dependencies(reg, "user")["dependencies"][0]
    assert row["status"] == "missing" and row["available_from"] is None
    assert "no configured registry lists it" in row["detail"]


def test_a_dependency_cycle_is_reported_rather_than_chased(registry):
    reg, root, store = registry
    install(reg, root, "a", depends_on="b")
    install(reg, root, "b", depends_on="a")
    report = resolve_dependencies(reg, "a")
    assert report["status"] == "blocked"
    cycle = [problem for problem in report["problems"] if problem["status"] == "cycle"]
    assert cycle, report
    assert "cycle" in cycle[0]["detail"]


def test_dependency_nesting_is_bounded(registry):
    reg, root, store = registry
    for number in range(MAX_DEPTH + 2):
        install(reg, root, f"level{number}", depends_on=f"level{number + 1}")
    report = resolve_dependencies(reg, "level0")
    assert "too_deep" in str(report) or report["status"] in {"ok", "blocked"}


def test_the_api_serves_the_dependency_report(registry, monkeypatch):
    reg, root, store = registry
    install(reg, root, "user", depends_on="base")
    monkeypatch.setenv("HUTCH_STATE_DIR", str(store.config.state_dir))
    from fastapi.testclient import TestClient

    from hutch.server.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/skills/user/dependencies")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dependencies"][0]["name"] == "base"
    assert "registry" in body["note"]
