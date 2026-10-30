"""Import-graph and catalog-parity guards for the lazily loaded tool registry.

The tool catalog resolves tool classes on first use so cheap callers (quick CLI commands, the
dashboard process) do not import the whole tool graph. These tests pin both halves of that
contract: every catalog name still resolves to the same class/parameters, and importing the CLI
does not eagerly import heavy tool families. A regression here is a startup-latency regression,
not just a style change.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hutch.tools import ALL_TOOL_NAMES, GROUPS, _CATALOG, _SPECS, _tool_class, build_tools

_SRC = Path(__file__).resolve().parents[1] / "src"

#: Heavy tool families whose eager import was removed from the quick-command path. They are
#: still imported when a run actually grants the tool; this list only guards the import graph.
_HEAVY_MODULES = (
    "hutch.synthesis",
    "hutch.media",
    "hutch.grounding",
    "hutch.bot_deletion",
    "hutch.tools.synthesis",
    "hutch.tools.media",
    "hutch.tools.live",
    "hutch.tools.documents",
    "hutch.tools.workspace_actions",
)


def _run_python(statement: str) -> str:
    """Run one statement in a fresh interpreter and return its last stdout line."""
    code = "import json, sys\n" + statement
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    env.pop("HUTCH_TESTING", None)
    proc = subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip().splitlines()[-1]


def test_catalog_resolves_every_declared_name_to_the_declared_tool():
    for name, (module_name, class_name) in _SPECS.items():
        cls = _CATALOG[name]
        assert cls.__name__ == class_name, (name, cls.__name__, class_name)
        assert cls.__module__ == "hutch.tools." + module_name, (name, cls.__module__)
        tool = cls()
        assert tool.name == name, name + " resolves to a tool named " + tool.name
        assert isinstance(tool.parameters, dict)


def test_catalog_mapping_surface_matches_the_spec_table():
    assert list(_CATALOG) == list(_SPECS)
    assert len(_CATALOG) == len(_SPECS)
    assert list(_CATALOG.values()) == [_CATALOG[name] for name in _SPECS]
    assert dict(_CATALOG.items()) == {name: _CATALOG[name] for name in _SPECS}
    with pytest.raises(KeyError):
        _CATALOG["no_such_tool"]
    with pytest.raises(KeyError):
        _tool_class("no_such_tool")


def test_catalog_names_are_stable_and_groups_stay_resolvable():
    assert ALL_TOOL_NAMES == sorted(_SPECS) + ["browser", "computer"]
    assert ALL_TOOL_NAMES[:len(_SPECS)] == sorted(_SPECS)
    assert set(ALL_TOOL_NAMES) - set(_SPECS) == {"browser", "computer"}
    for name, members in GROUPS.items():
        for member in members:
            assert member in _SPECS or member in {"browser", "computer"}, (name, member)


def test_build_tools_instantiates_only_granted_catalog_tools():
    class _Bot:
        tools = ["shell", "read_file", "memory"]
        memory_enabled = False
        inference_mode = None

    class _Ctx:
        bot = _Bot()
        store = None
        delegation_submit = None
        skills = None
        run = None

    tools = build_tools(["shell", "read_file"], _Ctx())
    assert set(tools) == {"shell", "read_file"}
    assert tools["shell"].name == "shell"


def test_importing_the_cli_does_not_import_heavy_tool_families():
    modules = set(json.loads(_run_python(
        "import hutch.cli\nprint(json.dumps(sorted(sys.modules)))\n")))
    leaked = sorted(module for module in _HEAVY_MODULES if module in modules)
    assert not leaked, "importing hutch.cli eagerly imported " + repr(leaked)


def test_tool_submodules_stay_reachable_as_package_attributes_lazily():
    """The old eager imports also bound hutch.tools.<module>; keep that surface without the cost."""
    statement = (
        "import hutch.tools\n"
        "before = 'hutch.tools.shell' in sys.modules\n"
        "cls = hutch.tools.shell.ShellTool\n"
        "print(json.dumps({'before': before, 'name': cls.__name__}))\n"
    )
    report = json.loads(_run_python(statement))
    assert report["before"] is False
    assert report["name"] == "ShellTool"

def test_registry_import_is_cheap_and_aliasing_only_imports_the_named_tool():
    report = json.loads(_run_python(
        "import hutch.tools\n"
        "before = sorted(m for m in sys.modules if m.startswith('hutch.tools.'))\n"
        "shell = hutch.tools._CATALOG['shell']\n"
        "after = sorted(m for m in sys.modules if m.startswith('hutch.tools.'))\n"
        "print(json.dumps({'before': before, 'after': after, 'shell': shell.__name__}))\n"))
    assert "hutch.tools.synthesis" not in report["before"]
    assert "hutch.tools.media" not in report["before"]
    assert report["shell"] == "ShellTool"
    assert "hutch.tools.shell" in report["after"]
    assert "hutch.tools.synthesis" not in report["after"]
