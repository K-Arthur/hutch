"""Turning a declared skill dependency into a next step an operator can actually take.

`hutch.requires-skills` already refuses a skill whose dependency cannot load, and names the
dependency. That leaves the operator with a decision but no route: the dependency has to be found,
downloaded and reviewed like anything else. This module answers "where would that come from" from
two facts Hutch already has: what is installed, and what the configured indexes list.

Three rules shape it:

* **Resolution is a report, not an install.** Nothing here downloads anything. It says what is
  missing, whether a configured registry lists it, and what would happen next. Installing stays a
  separate, explicit act.
* **A listed package is not a solution.** A dependency that a registry lists is reported with the
  caveat that installing it lands untrusted, so the operator knows the follow-on work before
  starting.
* **A dependency cycle is reported, not chased.** The walk is bounded and remembers the path it
  came by, so two skills that require each other produce one clear sentence instead of a hang.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .skill_registry_index import RegistryError
from .skills import SKILL_FILENAME, SkillError, inspect_package

#: How deep a dependency report may walk. Two levels answers the question; more is a cycle.
MAX_DEPTH = 3


def _declared(directory: Path) -> list[str]:
    """The skill names one installed package declares as dependencies."""
    try:
        parsed, _diagnostics, _hash = inspect_package(directory, enforce_bounds=False)
    except OSError:
        return []
    return list(parsed.requires_skills) if parsed else []


def resolve_dependencies(registry, name: str, *, index=None, depth: int = 0,
                         path: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
    """Report what ``name`` depends on, what is missing, and where each missing one can come from.

    ``index`` is an optional ``RegistryIndex``; without one the report simply says that nothing
    configured lists the package, which is the truth when no registry is configured.
    """
    path = path or ()
    if name in path:
        return {"name": name, "status": "cycle", "detail": "dependency cycle: " + " -> ".join(path + (name,)),
                "dependencies": []}
    if depth > MAX_DEPTH:
        return {"name": name, "status": "too_deep",
                "detail": f"dependency nesting goes deeper than {MAX_DEPTH} levels",
                "dependencies": []}

    directory = registry.package_path(name)
    if not directory.is_dir():
        installed = False
        declared: list[str] = []
    else:
        installed = True
        declared = _declared(directory)

    rows = []
    for dependency in declared:
        rows.append(
            resolve_dependencies(registry, dependency, index=index, depth=depth + 1,
                                 path=path + (name,))
            if registry.package_path(dependency).is_dir()
            else _row_for(dependency, registry, index))

    problems = _problems(rows)
    return {"name": name, "installed": installed, "declared": declared,
            "status": "ok" if not problems else "blocked",
            "dependencies": rows,
            "problems": problems,
            "missing_at_top": [row["name"] for row in rows if row["status"] == "missing"],
            "note": ("This is a report, not an install. Anything installed from a registry lands "
                     "untrusted, exactly like a download: review it before trusting it.")}


def _problems(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Every non-ok row in the tree, flattened.

    A cycle two levels down is still the reason the top-level skill cannot run, so leaving it
    inside the nested structure would make the report technically complete and practically
    useless. One flat list is what an operator acts on.
    """
    found: list[dict[str, str]] = []
    for row in rows:
        if row.get("status") != "ok":
            found.append({"name": str(row.get("name", "")), "status": str(row.get("status", "")),
                          "detail": str(row.get("detail", ""))})
        found.extend(_problems(row.get("dependencies") or []))
    return found


def _row_for(name: str, registry, index) -> dict[str, Any]:
    """One dependency that is not installed: what it is, and whether anything lists it."""
    entry = None
    if index is not None:
        try:
            entry = index.find(name)
        except RegistryError:
            entry = None
    if entry is None:
        return {"name": name, "status": "missing",
                "detail": (f"not installed, and no configured registry lists it; install it from a "
                           "package you have reviewed"),
                "available_from": None}
    return {"name": name, "status": "missing",
            "detail": (f"not installed; the {entry.registry_id} registry lists version "
                       f"{entry.version or '(unspecified)'}"),
            "available_from": {"registry_id": entry.registry_id, "url": entry.url,
                               "version": entry.version, "publisher": entry.publisher,
                               "sha256": entry.sha256,
                               "pinned": bool(entry.sha256)}}


__all__ = ["MAX_DEPTH", "resolve_dependencies"]
