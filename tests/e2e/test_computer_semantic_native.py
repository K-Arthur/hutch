"""Semantic desktop control: act on an application's accessibility tree, not on pixels.

Evidence class: a REAL disposable KWin Wayland session, a REAL toolkit window (KWrite), a REAL private at-spi bus and the
real out-of-process worker. The assertion that matters is an effect outside the tool: the edited file on disk. Skipped when
the prerequisites (KWin virtual, KWrite, a PyGObject interpreter with Atspi) are absent.

This file deliberately contains no coordinates. If a semantic action ever needed one, the test would still pass because it
never supplies any.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from hutch.computer.native.eis import find_gi_python
from hutch.computer.native.virtual import ManagedDesktop
from hutch.models import Bot
from hutch.tools.base import ProcRegistry
from hutch.tools.computer import ComputerTool

_ok, _why = ManagedDesktop.available()
pytestmark = pytest.mark.skipif(not _ok or find_gi_python() is None,
                                reason=_why or "no PyGObject interpreter or KWin virtual session available")
pytest.importorskip("shutil")
import shutil  # noqa: E402


def _atspi_python() -> str | None:
    from hutch.computer.accessibility import find_atspi_python
    return find_atspi_python()


if shutil.which("kwrite") is None:
    pytestmark = pytest.mark.skip(reason="kwrite is not installed")

pytestmark = [pytestmark, pytest.mark.skipif(_atspi_python() is None, reason="no interpreter with the Atspi typelib")]


class Gate:
    def __init__(self):
        self.decisions: list[tuple[str, dict]] = []

    def decide(self, tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        self.decisions.append((action, detail))

    def cancelled(self):
        return False


@pytest.fixture()
def native(config, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    events: list = []
    bot = Bot(name="semantic-bot", computer_apps=["kwrite"])
    ctx = SimpleNamespace(
        config=config, bot=bot, run=SimpleNamespace(id="run-semantic"), workspace=workspace, gate=Gate(),
        dry_run=False, begin_effect=lambda: None, emit=events.append, on_finish=[], cancel_hooks=[],
        procs=ProcRegistry(), headless=True)
    tool = ComputerTool()
    try:
        yield SimpleNamespace(tool=tool, ctx=ctx, workspace=workspace, events=events)
    finally:
        tool._shutdown(ctx)
        ctx.procs.kill_all(0.2)


def _wait_for(predicate, seconds=8.0, step=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def _find(elements: dict, **match) -> dict | None:
    """An element in a snapshot matching every given attribute (role/name/text substring)."""
    for node in elements["nodes"]:
        if all((node.get(key) or "") == value for key, value in match.items()):
            return node
    return None


def test_closed_menus_do_not_consume_the_tree_budget(native):
    """A toolkit builds its whole menu hierarchy up front; those closed menus must not crowd out real content."""
    tool, ctx, workspace = native.tool, native.ctx, native.workspace
    (workspace / "menus.txt").write_text("a\n")
    launched = tool.run({"action": "launch", "app": "kwrite", "path": "menus.txt"}, ctx)
    assert launched.ok, launched.output
    elements = tool.run({"action": "elements"}, ctx)
    assert elements.ok, elements.output
    snapshot = elements.data["elements"]
    assert snapshot["pruned"] > 0, "KWrite's closed menus should have been pruned"
    assert not snapshot["truncated"], "with closed menus pruned the tree fits its budget"
    # The editor and the toolbar survive pruning; the menu bar itself is still reported as existing.
    assert any(node["role"] == "text" and node.get("name") == "menus.txt" for node in snapshot["nodes"])
    assert any(node["role"] == "menu bar" for node in snapshot["nodes"])
    assert 'closed menu(s) and their items are not listed' in elements.output


def test_semantic_edit_and_save_produce_the_file_on_disk(native):
    """Read the tree, replace the editor's contents by element id, press Save by name, verify the bytes."""
    tool, ctx, workspace = native.tool, native.ctx, native.workspace
    target = workspace / "semantic.txt"
    target.write_text("original content\n")

    launched = tool.run({"action": "launch", "app": "kwrite", "path": "semantic.txt"}, ctx)
    assert launched.ok, launched.output
    assert tool._session.semantic, "the isolated session did not start its accessibility bus"

    elements = tool.run({"action": "elements"}, ctx)
    assert elements.ok, elements.output
    snapshot = elements.data["elements"]
    assert snapshot["snapshot_id"] and snapshot["app"].lower().startswith("kwrite")
    assert isinstance(elements.data.get("elements"), dict)

    editor = next((node for node in snapshot["nodes"]
                   if node["role"] == "text" and node.get("name") == "semantic.txt"), None)
    assert editor is not None, [node for node in snapshot["nodes"] if node["role"] == "text"]
    assert editor.get("text") == "original content"

    written = tool.run({"action": "set_text", "snapshot_id": snapshot["snapshot_id"], "element_id": editor["id"],
                        "text": "semantic write sentinel"}, ctx)
    assert written.ok, written.output
    assert written.data["outcome"] == "effect_verified", written.output

    # The Save button is found by its accessible name. No pixel was used to reach it.
    tree = written.data["elements"]
    save = next((node for node in tree["nodes"]
                 if node["role"] in ("button", "push button") and node.get("name") == "Save"), None)
    assert save is not None, [(node["role"], node.get("name")) for node in tree["nodes"][:40]]
    pressed = tool.run({"action": "activate", "snapshot_id": written.data["snapshot_id"], "element_id": save["id"]},
                       ctx)
    assert pressed.ok, pressed.output
    assert pressed.data["outcome"] == "dispatched"
    assert _wait_for(lambda: target.read_text(encoding="utf-8").strip() == "semantic write sentinel"), \
        repr(target.read_text(encoding="utf-8"))


def test_semantic_snapshot_ids_are_fenced_to_the_latest_tree(native):
    """An id from a superseded snapshot must be refused instead of acting on a tree that moved on."""
    tool, ctx, workspace = native.tool, native.ctx, native.workspace
    (workspace / "fenced.txt").write_text("a\n")
    launched = tool.run({"action": "launch", "app": "kwrite", "path": "fenced.txt"}, ctx)
    assert launched.ok, launched.output

    first = tool.run({"action": "elements"}, ctx)
    assert first.ok, first.output
    stale_id = first.data["elements"]["snapshot_id"]
    editor = next(node for node in first.data["elements"]["nodes"]
                  if node["role"] == "text" and node.get("name") == "fenced.txt")

    second = tool.run({"action": "elements"}, ctx)
    assert second.ok and second.data["elements"]["snapshot_id"] != stale_id

    refused = tool.run({"action": "set_text", "snapshot_id": stale_id, "element_id": editor["id"], "text": "x"}, ctx)
    assert not refused.ok
    assert "not the latest" in refused.output
    assert refused.data["outcome"] == "not_dispatched"
    assert (workspace / "fenced.txt").read_text().strip() == "a"


def test_semantic_actions_refuse_an_unknown_element(native):
    tool, ctx, workspace = native.tool, native.ctx, native.workspace
    (workspace / "unknown.txt").write_text("a\n")
    launched = tool.run({"action": "launch", "app": "kwrite", "path": "unknown.txt"}, ctx)
    assert launched.ok, launched.output
    elements = tool.run({"action": "elements"}, ctx)
    assert elements.ok, elements.output
    snapshot = elements.data["elements"]
    refused = tool.run({"action": "activate", "snapshot_id": snapshot["snapshot_id"], "element_id": "n9999"}, ctx)
    assert not refused.ok
    assert "not in the latest tree" in refused.output


def test_semantic_actions_are_fenced_by_control_ownership(native):
    """A person holding control fences semantic actions exactly as it fences pointer input."""
    from hutch.computer.control import StaleControl

    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok, launched.output
    elements = tool.run({"action": "elements"}, ctx)
    assert elements.ok, elements.output
    tool._lease.take_over("a person is editing this window")
    try:
        refused = tool.run({"action": "elements"}, ctx)
        assert not refused.ok and refused.data["outcome"] == "not_dispatched"
        button = elements.data["elements"]["nodes"][0]
        action = tool.run({"action": "activate", "snapshot_id": elements.data["elements"]["snapshot_id"],
                           "element_id": button["id"]}, ctx)
        assert not action.ok and action.data["outcome"] == "not_dispatched"
    finally:
        try:
            tool._lease.hand_back()
        except StaleControl:  # pragma: no cover - only if the session ended first
            pass


def test_semantic_control_reports_when_the_session_has_no_bus(native, monkeypatch):
    """Without an accessibility bus the tool says so and keeps pixel control; it never pretends to have a tree."""
    from hutch.computer.native.a11y_bus import AccessibilityBus, BusUnavailable

    def refuse(self):
        raise BusUnavailable("at-spi2-registryd is not installed (install at-spi2-core)")

    monkeypatch.setattr(AccessibilityBus, "start", refuse)
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok, launched.output
    assert not tool._session.semantic
    observed = tool.run({"action": "observe"}, ctx)
    assert observed.ok, observed.output
    environment = observed.data["observation"]["environment"]
    assert environment["semantics"] == "unavailable"
    assert "at-spi2-registryd" in environment["semantics_reason"]
    missing = tool.run({"action": "elements"}, ctx)
    assert not missing.ok
    assert "no accessibility tree" in missing.output
