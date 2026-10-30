"""Constitution-registry guard: disposable fixtures plus the real checkout.

The fixtures never touch the real repository. The final test audits this
checkout, so a broken enforcement target, duplicate rule id or missing role file
fails CI even when nothing else notices.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "audit_constitution", ROOT / "scripts" / "audit_constitution.py")
constitution_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(constitution_audit)

SCRIPTS = {
    "check:agent": "uv run --frozen --no-sync python scripts/audit_context_hygiene.py",
    "test:agent": "uv run --frozen --no-sync pytest -q --no-header --tb=line",
    "audit:context": "uv run --frozen --no-sync python scripts/audit_context_hygiene.py",
    "audit:tool-contracts": "uv run --frozen --no-sync python scripts/audit_tool_contracts.py",
    "build:css": "npm run build:css:site && npm run build:css:app",
}


def valid_constitution() -> dict:
    return {
        "schema": constitution_audit.SCHEMA,
        "version": constitution_audit.VERSION,
        "repo": constitution_audit.REPO,
        "roles": [
            {
                "id": "python-tools-engineer",
                "file": ".ai/roles/python-tools-engineer.md",
                "applies_to": ["src/hutch/tools", "src/hutch/toolcalling"],
                "required_checks": ["check:agent"],
            }
        ],
        "rules": [
            {
                "id": "CON-001",
                "title": "No emoji",
                "statement": "Source and UI contain no emoji.",
                "severity": "blocking",
                "source": "AGENTS.md#hard-rules",
                "enforcement": {"kind": "script", "value": "scripts/audit_emoji.py"},
            },
            {
                "id": "CON-002",
                "title": "Focused tests",
                "statement": "Behaviour changes carry focused tests.",
                "severity": "advisory",
                "source": "docs/agent-workflow.md#quiet-verification",
                "enforcement": {"kind": "test", "paths": ["tests/test_constitution.py"]},
            },
            {
                "id": "CON-003",
                "title": "Quiet gate",
                "statement": "The default gate passes before reporting.",
                "severity": "blocking",
                "source": "AGENTS.md",
                "enforcement": {"kind": "command", "value": "check:agent"},
            },
            {
                "id": "CON-004",
                "title": "Manual review",
                "statement": "Reviewers check the boundary.",
                "severity": "blocking",
                "source": "docs/agent-workflow.md",
                "enforcement": {
                    "kind": "manual",
                    "checklist": ["first review item", "second review item"],
                    "review_doc": "docs/safety.md",
                },
            },
        ],
    }


def write_constitution(root: Path, data: dict) -> None:
    path = root / ".ai" / "constitution.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_repo(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": SCRIPTS}), encoding="utf-8")
    contents = {
        # AGENTS.md -> docs/agent-workflow.md -> docs/safety.md keeps every
        # fixture rule source inside the two-hop reachability contract.
        "AGENTS.md": "# AGENTS\n\n[agent workflow](docs/agent-workflow.md)\n",
        "docs/agent-workflow.md": "# Agent workflow\n\n[safety](safety.md)\n",
    }
    for relative in (
        ".ai/roles/README.md",
        ".ai/roles/python-tools-engineer.md",
        "src/hutch/tools/__init__.py",
        "src/hutch/toolcalling/__init__.py",
        "scripts/audit_emoji.py",
        "tests/test_constitution.py",
        "AGENTS.md",
        "docs/agent-workflow.md",
        "docs/safety.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents.get(relative, "fixture\n"), encoding="utf-8")
    write_constitution(tmp_path, valid_constitution())
    return tmp_path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return write_repo(tmp_path)


def test_valid_fixture_passes(repo: Path):
    assert constitution_audit.audit(repo) == []


@pytest.mark.parametrize("field,bad,expected", [
    ("schema", "other-schema", "schema must be"),
    ("version", 2, "version must be"),
    ("repo", "varve", "repo must be"),
])
def test_top_level_contract_fields_fail(repo: Path, field, bad, expected):
    data = valid_constitution()
    data[field] = bad
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any(expected in finding for finding in findings)


def test_boolean_version_rejected(repo: Path):
    data = valid_constitution()
    data["version"] = True  # bool compares equal to 1, but is not the schema version
    write_constitution(repo, data)
    assert any("version must be" in finding
               for finding in constitution_audit.audit(repo))


def test_duplicate_rule_id_fails(repo: Path):
    data = valid_constitution()
    data["rules"].append(dict(data["rules"][0]))
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("duplicate rule id" in finding for finding in findings)


def test_malformed_rule_id_fails(repo: Path):
    data = valid_constitution()
    data["rules"][0]["id"] = "CON-1"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("id must match CON-###" in finding for finding in findings)


def test_invalid_severity_fails(repo: Path):
    data = valid_constitution()
    data["rules"][0]["severity"] = "blocker"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("severity" in finding for finding in findings)


def test_missing_source_doc_fails(repo: Path):
    data = valid_constitution()
    data["rules"][0]["source"] = "docs/missing.md#hard-rules"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("source doc" in finding and "missing.md" in finding
               for finding in findings)


def test_duplicate_role_id_fails(repo: Path):
    data = valid_constitution()
    data["roles"].append(dict(data["roles"][0]))
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("duplicate role id" in finding for finding in findings)


def test_missing_role_file_fails(repo: Path):
    data = valid_constitution()
    data["roles"][0]["file"] = ".ai/roles/missing.md"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("file" in finding and "missing.md" in finding for finding in findings)


def test_missing_applies_to_path_fails(repo: Path):
    data = valid_constitution()
    data["roles"][0]["applies_to"] = ["src/hutch/missing"]
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("applies_to path" in finding for finding in findings)


def test_escaping_applies_to_path_fails(tmp_path: Path):
    repo = write_repo(tmp_path)
    data = valid_constitution()
    data["roles"][0]["applies_to"] = ["../outside"]
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("repo-relative path" in finding for finding in findings)


def test_unknown_required_check_fails(repo: Path):
    data = valid_constitution()
    data["roles"][0]["required_checks"] = ["missing:script"]
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("required check" in finding for finding in findings)


def test_command_enforcement_requires_package_script(repo: Path):
    data = valid_constitution()
    data["rules"][2]["enforcement"]["value"] = "audit:missing"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("command 'audit:missing'" in finding for finding in findings)


def test_script_enforcement_requires_existing_file(repo: Path):
    data = valid_constitution()
    data["rules"][0]["enforcement"]["value"] = "scripts/missing.py"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("script 'scripts/missing.py'" in finding for finding in findings)


def test_test_enforcement_requires_existing_paths(repo: Path):
    data = valid_constitution()
    data["rules"][1]["enforcement"]["paths"] = ["tests/missing.py"]
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("test path 'tests/missing.py'" in finding for finding in findings)


def test_manual_enforcement_requires_two_checklist_items(repo: Path):
    data = valid_constitution()
    data["rules"][3]["enforcement"]["checklist"] = ["only one item"]
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("manual enforcement" in finding for finding in findings)


def test_manual_enforcement_requires_existing_review_doc(repo: Path):
    data = valid_constitution()
    data["rules"][3]["enforcement"]["review_doc"] = "docs/missing.md"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("review_doc" in finding for finding in findings)


def test_unknown_enforcement_kind_fails(repo: Path):
    data = valid_constitution()
    data["rules"][0]["enforcement"] = {"kind": "auto"}
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("enforcement kind" in finding for finding in findings)


def test_missing_constitution_is_unusable(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": SCRIPTS}), encoding="utf-8")
    with pytest.raises(constitution_audit.ConstitutionError):
        constitution_audit.audit(tmp_path)


def test_invalid_json_is_unusable(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": SCRIPTS}), encoding="utf-8")
    path = tmp_path / ".ai" / "constitution.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(constitution_audit.ConstitutionError):
        constitution_audit.audit(tmp_path)


def test_missing_package_scripts_is_unusable(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    write_constitution(tmp_path, valid_constitution())
    with pytest.raises(constitution_audit.ConstitutionError):
        constitution_audit.audit(tmp_path)


def test_orphan_role_file_fails(repo: Path):
    (repo / ".ai" / "roles" / "orphan-engineer.md").write_text(
        "# Orphan\n", encoding="utf-8")
    findings = constitution_audit.audit(repo)
    assert any("not registered" in finding and "orphan-engineer.md" in finding
               for finding in findings)


def test_role_registration_readme_is_excluded(repo: Path):
    assert (repo / ".ai" / "roles" / "README.md").is_file()
    assert constitution_audit.audit(repo) == []


def test_duplicate_role_registration_fails(repo: Path):
    data = valid_constitution()
    data["roles"].append({
        "id": "second-role",
        "file": ".ai/roles/python-tools-engineer.md",
        "applies_to": ["src/hutch/tools"],
        "required_checks": ["check:agent"],
    })
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("registered 2 times" in finding for finding in findings)


def test_unreachable_rule_source_fails(repo: Path):
    (repo / "docs" / "orphan-doc.md").write_text("# Orphan\n", encoding="utf-8")
    data = valid_constitution()
    data["rules"][3]["source"] = "docs/orphan-doc.md"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("not reachable from AGENTS.md" in finding for finding in findings)


def test_depth_two_rule_source_passes(repo: Path):
    # docs/safety.md is linked only from docs/agent-workflow.md, which AGENTS.md
    # links: depth 0 -> depth 1 -> depth 2 is inside the contract.
    data = valid_constitution()
    data["rules"][3]["source"] = "docs/safety.md#review"
    write_constitution(repo, data)
    assert constitution_audit.audit(repo) == []


def test_source_beyond_two_hops_fails(repo: Path):
    # AGENTS.md -> docs/agent-workflow.md -> docs/safety.md -> docs/level-three.md
    (repo / "docs" / "safety.md").write_text(
        "# Safety\n\n[level three](level-three.md)\n", encoding="utf-8")
    (repo / "docs" / "level-three.md").write_text("# Level three\n", encoding="utf-8")
    data = valid_constitution()
    data["rules"][3]["source"] = "docs/level-three.md"
    write_constitution(repo, data)
    findings = constitution_audit.audit(repo)
    assert any("not reachable from AGENTS.md" in finding for finding in findings)


def test_external_tooling_manual_rule_passes(repo: Path):
    data = valid_constitution()
    data["rules"].append({
        "id": "CON-005",
        "title": "External agent tooling is pinned, sandboxed and verified",
        "statement": "MCP servers and code-graph tools need approval, a pin and "
                     "sandboxed access before their output is trusted.",
        "severity": "advisory",
        "source": "docs/agent-workflow.md#constitution-and-role-files",
        "enforcement": {
            "kind": "manual",
            "checklist": ["Pinned to an explicit version or commit",
                          "Sandboxed without ambient credentials",
                          "Output cross-checked against the generated map"],
            "review_doc": "docs/agent-workflow.md",
        },
    })
    write_constitution(repo, data)
    assert constitution_audit.audit(repo) == []


def test_main_passes_valid_fixture(repo: Path):
    assert constitution_audit.main(["--root", str(repo)]) == 0


def test_main_returns_one_with_findings(repo: Path):
    data = valid_constitution()
    data["repo"] = "elsewhere"
    write_constitution(repo, data)
    assert constitution_audit.main(["--root", str(repo)]) == 1


def test_main_returns_two_when_unusable(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": SCRIPTS}), encoding="utf-8")
    assert constitution_audit.main(["--root", str(tmp_path)]) == 2


def test_json_mode_reports_summary(repo: Path, capsys):
    status = constitution_audit.main(["--root", str(repo), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert payload["ok"] is True
    assert payload["schema"] == constitution_audit.SCHEMA
    assert payload["roles"] == 1
    assert payload["rules"] == 4
    assert payload["findings"] == []


def test_real_repository_has_zero_findings():
    assert constitution_audit.audit(ROOT) == []
