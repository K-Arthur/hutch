#!/usr/bin/env python3
"""Validate Hutch's machine-readable agent constitution and role registry.

Every rule and role must point at enforcement that already exists in this
checkout, so deleting a guard script, renaming a test, dropping a package.json
script or moving a role file fails here instead of leaving decorative prose.

Validated contract (agent-constitution-v1): schema/version/repo at the top;
unique role ids with existing files, scope paths and package.json check keys;
unique CON-### rules with severity, title/statement, an existing source doc that
is reachable from AGENTS.md within MAX_SOURCE_HOPS markdown-link hops, and one
enforcement kind (command key, existing script, existing test paths, or manual
with at least two checklist items and an existing review doc); every
.ai/roles/*.md except README.md registered exactly once.

Usage: uv run --frozen --no-sync python scripts/audit_constitution.py [--json]
Exit codes: 0 pass, 1 policy findings, 2 unusable constitution/package.json.
Tests: tests/test_constitution.py. Policy narrative: docs/agent-workflow.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION_PATH = ".ai/constitution.json"
SCHEMA = "agent-constitution-v1"
VERSION = 1
REPO = "hutch"
MAX_REPORTED = 40
RULE_ID_PATTERN = re.compile(r"CON-\d{3}")
SEVERITIES = frozenset({"blocking", "advisory"})
ENFORCEMENT_KINDS = frozenset({"command", "script", "test", "manual"})
MIN_MANUAL_CHECKLIST = 2
ROLES_DIR = ".ai/roles"
ROLES_README = "README.md"
SOURCE_ROOT = "AGENTS.md"
MAX_SOURCE_HOPS = 2
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class ConstitutionError(RuntimeError):
    """The constitution or package.json cannot be read or parsed."""


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _repo_path(root: Path, relative: Any) -> Path | None:
    """Resolve a repo-relative path, refusing absolute or escaping paths."""
    if not _non_empty_string(relative):
        return None
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    base = Path(root).resolve()
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    return resolved


def _path_finding(where: str, label: str, root: Path, relative: Any) -> str | None:
    """Finding for a value that must be an existing repo-relative path."""
    resolved = _repo_path(root, relative)
    if resolved is None:
        return f"{where}: {label} must be a repo-relative path (got {relative!r})"
    if not resolved.exists():
        return f"{where}: {label} {relative!r} does not exist"
    return None


def load_package_scripts(root: Path = ROOT) -> dict[str, str]:
    """The npm script map that commands and role checks must key into."""
    path = Path(root) / "package.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConstitutionError(f"missing npm manifest {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstitutionError(f"cannot read {path}: {exc}") from exc
    scripts = raw.get("scripts") if isinstance(raw, dict) else None
    if not isinstance(scripts, dict) or not scripts:
        raise ConstitutionError(f"{path} has no scripts map")
    return {key: value for key, value in scripts.items() if isinstance(value, str)}


def load_constitution(root: Path = ROOT) -> dict[str, Any]:
    """Parse the constitution; raise ConstitutionError when unusable."""
    path = Path(root) / CONSTITUTION_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConstitutionError(f"missing constitution {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstitutionError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConstitutionError(f"{path} must be a JSON object")
    return raw


def validate_roles(root: Path, roles: Any, script_keys: set[str]) -> list[str]:
    """Findings for the roles registry; empty means valid."""
    if not isinstance(roles, list) or not roles:
        return ["constitution: roles must be a non-empty list"]
    findings: list[str] = []
    seen: set[str] = set()
    for index, role in enumerate(roles):
        where = f"role[{index}]"
        if not isinstance(role, dict):
            findings.append(f"{where}: must be an object")
            continue
        role_id = role.get("id")
        if not _non_empty_string(role_id):
            findings.append(f"{where}: id must be a non-empty string")
        else:
            where = f"role {role_id}"
            if role_id in seen:
                findings.append(f"{where}: duplicate role id")
            seen.add(role_id)
        for label, value in (("file", role.get("file")),):
            finding = _path_finding(where, label, root, value)
            if finding:
                findings.append(finding)
        applies_to = role.get("applies_to")
        if not isinstance(applies_to, list) or not applies_to:
            findings.append(f"{where}: applies_to must be a non-empty list")
        else:
            for relative in applies_to:
                finding = _path_finding(where, "applies_to path", root, relative)
                if finding:
                    findings.append(finding)
        checks = role.get("required_checks")
        if not isinstance(checks, list) or not checks:
            findings.append(f"{where}: required_checks must be a non-empty list")
        else:
            for key in checks:
                if not isinstance(key, str) or key not in script_keys:
                    findings.append(
                        f"{where}: required check {key!r} is not a package.json script key")
    return findings


def _validate_enforcement(root: Path, where: str, enforcement: Any,
                          script_keys: set[str]) -> list[str]:
    """Findings for one rule's enforcement block."""
    if not isinstance(enforcement, dict):
        return [f"{where}: enforcement must be an object"]
    kind = enforcement.get("kind")
    if kind not in ENFORCEMENT_KINDS:
        return [f"{where}: enforcement kind {kind!r} must be one of "
                + ", ".join(sorted(ENFORCEMENT_KINDS))]
    if kind == "command":
        value = enforcement.get("value")
        return [] if isinstance(value, str) and value in script_keys else [
            f"{where}: command {value!r} is not a package.json script key"]
    if kind == "script":
        finding = _path_finding(where, "script", root, enforcement.get("value"))
        return [finding] if finding else []
    if kind == "test":
        paths = enforcement.get("paths")
        if not isinstance(paths, list) or not paths:
            return [f"{where}: test enforcement needs a non-empty paths list"]
        return [finding for finding in
                (_path_finding(where, "test path", root, relative)
                 for relative in paths) if finding]
    checklist = enforcement.get("checklist")
    findings: list[str] = []
    if (not isinstance(checklist, list) or len(checklist) < MIN_MANUAL_CHECKLIST
            or any(not _non_empty_string(item) for item in checklist)):
        findings.append(f"{where}: manual enforcement needs at least "
                        f"{MIN_MANUAL_CHECKLIST} non-empty checklist items")
    finding = _path_finding(where, "review_doc", root,
                            enforcement.get("review_doc"))
    if finding:
        findings.append(finding)
    return findings


def validate_rules(root: Path, rules: Any, script_keys: set[str]) -> list[str]:
    """Findings for the rules registry; empty means valid."""
    if not isinstance(rules, list) or not rules:
        return ["constitution: rules must be a non-empty list"]
    findings: list[str] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        where = f"rule[{index}]"
        if not isinstance(rule, dict):
            findings.append(f"{where}: must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not RULE_ID_PATTERN.fullmatch(rule_id):
            findings.append(f"{where}: id must match CON-### (got {rule_id!r})")
        else:
            where = f"rule {rule_id}"
            if rule_id in seen:
                findings.append(f"{where}: duplicate rule id")
            seen.add(rule_id)
        for field_name in ("title", "statement"):
            if not _non_empty_string(rule.get(field_name)):
                findings.append(f"{where}: {field_name} must be a non-empty string")
        severity = rule.get("severity")
        if severity not in SEVERITIES:
            findings.append(
                f"{where}: severity {severity!r} must be blocking or advisory")
        source = rule.get("source")
        if not _non_empty_string(source):
            findings.append(f"{where}: source must be a non-empty doc path")
        else:
            finding = _path_finding(where, "source doc", root,
                                    source.split("#", 1)[0])
            if finding:
                findings.append(finding)
        findings.extend(_validate_enforcement(
            root, where, rule.get("enforcement"), script_keys))
    return findings


def _markdown_links(doc: Path, root: Path) -> list[Path]:
    """Existing local Markdown targets linked from one document."""
    try:
        text = doc.read_text(encoding="utf-8")
    except OSError:
        return []
    root = Path(root).resolve()
    links: list[Path] = []
    for match in LINK_PATTERN.finditer(text):
        target = match.group(1).strip().strip("<>").strip()
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0].strip()
        if not target:
            continue
        resolved = (doc.parent / target).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.suffix.lower() == ".md" and resolved.is_file():
            links.append(resolved)
    return links


def reachable_docs(root: Path, max_hops: int = MAX_SOURCE_HOPS) -> set[Path]:
    """Markdown docs reachable from AGENTS.md within max_hops link hops.

    AGENTS.md is depth 0; docs it links are depth 1; docs those link are
    depth 2. The always-loaded index must keep a short pointer chain to every
    rule's canonical source.
    """
    start = (Path(root) / SOURCE_ROOT).resolve()
    if not start.is_file():
        return set()
    reachable = {start}
    frontier = [start]
    for _hop in range(max_hops):
        next_frontier: list[Path] = []
        for doc in frontier:
            for link in _markdown_links(doc, root):
                if link not in reachable:
                    reachable.add(link)
                    next_frontier.append(link)
        frontier = next_frontier
    return reachable


def validate_role_registration(root: Path, roles: Any) -> list[str]:
    """Findings for role files that are unregistered or registered twice."""
    if not isinstance(roles, list):
        return []  # the shape finding is reported by validate_roles
    registered = Counter(Path(role["file"]).as_posix()
                         for role in roles if isinstance(role, dict)
                         and _non_empty_string(role.get("file")))
    roles_dir = Path(root) / ROLES_DIR
    if not roles_dir.is_dir():
        return []
    findings: list[str] = []
    base = Path(root).resolve()
    for discovered in sorted(roles_dir.glob("*.md")):
        if discovered.name == ROLES_README:
            continue
        relative = discovered.resolve().relative_to(base).as_posix()
        count = registered.get(relative, 0)
        if count == 0:
            findings.append(f"role registration: {relative} is not registered "
                            "in constitution.roles[].file")
        elif count > 1:
            findings.append(f"role registration: {relative} is registered {count} times")
    return findings


def validate_source_reachability(root: Path, rules: Any) -> list[str]:
    """Findings for rule sources not reachable from AGENTS.md in <=2 hops."""
    if not isinstance(rules, list):
        return []
    reachable = reachable_docs(root)
    findings: list[str] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        label = f"rule {rule_id}" if isinstance(rule_id, str) else f"rule[{index}]"
        source = rule.get("source")
        if not _non_empty_string(source):
            continue
        doc = source.split("#", 1)[0].strip()
        resolved = _repo_path(root, doc)
        if resolved is None or not resolved.is_file():
            continue  # the missing source is already a validate_rules finding
        if resolved not in reachable:
            findings.append(f"{label}: source doc {doc!r} is not reachable from "
                            f"{SOURCE_ROOT} within {MAX_SOURCE_HOPS} markdown-link hops")
    return findings


def validate(root: Path, constitution: dict[str, Any],
             script_keys: set[str]) -> list[str]:
    """All findings for one parsed constitution document."""
    findings: list[str] = []
    if constitution.get("schema") != SCHEMA:
        findings.append(f"constitution: schema must be {SCHEMA!r}")
    version = constitution.get("version")
    if version != VERSION or isinstance(version, bool):
        findings.append(f"constitution: version must be {VERSION}")
    repo = constitution.get("repo")
    if repo != REPO:
        findings.append(f"constitution: repo must be {REPO!r} (got {repo!r})")
    roles = constitution.get("roles")
    rules = constitution.get("rules")
    findings.extend(validate_roles(root, roles, script_keys))
    findings.extend(validate_role_registration(root, roles))
    findings.extend(validate_rules(root, rules, script_keys))
    findings.extend(validate_source_reachability(root, rules))
    return findings


def audit(root: Path = ROOT) -> list[str]:
    """Policy findings for the constitution under root; empty means valid."""
    base = Path(root)
    constitution = load_constitution(base)
    script_keys = set(load_package_scripts(base))
    return validate(base, constitution, script_keys)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Hutch's agent constitution and role registry.")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable summary")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = (args.root or ROOT).resolve()
    try:
        constitution = load_constitution(root)
        script_keys = set(load_package_scripts(root))
    except ConstitutionError as exc:
        print(f"Constitution check failed to load: {exc}", file=sys.stderr)
        return 2
    findings = validate(root, constitution, script_keys)
    if args.json:
        roles = constitution.get("roles")
        rules = constitution.get("rules")
        print(json.dumps({
            "ok": not findings,
            "constitution": CONSTITUTION_PATH,
            "schema": constitution.get("schema"),
            "roles": len(roles) if isinstance(roles, list) else 0,
            "rules": len(rules) if isinstance(rules, list) else 0,
            "findings_total": len(findings),
            "findings": findings,
        }, sort_keys=True))
        return 1 if findings else 0
    if findings:
        print(f"Constitution violations ({len(findings)}):", file=sys.stderr)
        for finding in findings[:MAX_REPORTED]:
            print(f"  {finding}", file=sys.stderr)
        if len(findings) > MAX_REPORTED:
            print(f"  ... and {len(findings) - MAX_REPORTED} more", file=sys.stderr)
        return 1
    print(f"Constitution check passed ({len(constitution.get('roles', []))} roles, "
          f"{len(constitution.get('rules', []))} rules; every rule maps to existing "
          "enforcement).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
