"""Semantic desktop control: bounds, fences and refusals, without starting a compositor.

The real AT-SPI path is covered by ``tests/e2e/test_computer_semantic_native.py``. This file pins the properties that must
hold whatever the worker says: reply validation, snapshot fencing, redaction, and the containment mount.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hutch.computer.a11y_tree import (MAX_ACTIONS, MAX_NAME, MAX_NODES, MAX_NODE_TEXT, AccessibilityError, parse_snapshot)
from hutch.computer.accessibility import AccessibilitySession, AccessibilityUnavailable, private_bus_address
from hutch.computer.native.a11y_bus import AccessibilityBus, BusUnavailable, availability


@pytest.fixture()
def short_root():
    """A short temporary root: a unix socket pathname has a hard length limit, which pytest's tmp_path exceeds."""
    root = Path(tempfile.mkdtemp(prefix="hcs-"))
    try:
        yield root
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


class FakeTransport:
    """A worker stand-in that returns queued replies and records what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent: list[dict] = []
        self.closed = False

    def request(self, payload, *, deadline=None):
        self.sent.append(dict(payload))
        if not self.replies:
            raise AccessibilityError("no more replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self):
        self.closed = True


def _tree(*nodes, app="kwrite", window="note.txt", **extra):
    return {"ok": True, "app": app, "window": window, "nodes": list(nodes), **extra}


EDITOR = {"id": "n2", "role": "text", "name": "note.txt", "depth": 2, "text": "hello", "parent": "n1"}
BUTTON = {"id": "n3", "role": "button", "name": "Save", "depth": 1, "actions": ["Press"]}


# ------------------------------------------------------------------ parsing


def test_snapshot_parsing_clamps_every_model_visible_string():
    snapshot = parse_snapshot(_tree(
        {"id": "n1", "role": "frame", "name": "x" * 400, "depth": -5,
         "text": "y" * 5000, "description": "d" * 900, "actions": ["a", "b", "c", "d", "e", "f"]},
    ), "a0001")
    node = snapshot.nodes[0]
    assert len(node.name) == MAX_NAME
    assert len(node.text) == MAX_NODE_TEXT
    assert len(node.description) <= 160
    assert len(node.actions) == MAX_ACTIONS
    assert node.depth == 0


def test_snapshot_parsing_drops_malformed_and_duplicate_nodes():
    snapshot = parse_snapshot(_tree(
        {"id": "n1", "role": "frame", "depth": 0},
        {"id": "n1", "role": "frame", "depth": 0},          # duplicate id
        {"id": "bogus", "role": "text", "depth": 1},        # invalid id syntax
        {"id": "n4", "role": "", "depth": 1},               # no role
        "not a dict",
    ), "a0002")
    assert [node.id for node in snapshot.nodes] == ["n1"]


def test_snapshot_parsing_refuses_an_empty_or_shapeless_reply():
    with pytest.raises(AccessibilityError, match="no element list"):
        parse_snapshot({"ok": True}, "a0003")
    with pytest.raises(AccessibilityError, match="empty"):
        parse_snapshot(_tree(), "a0004")


def test_snapshot_never_exceeds_its_node_budget():
    nodes = [{"id": f"n{i}", "role": "label", "depth": 1} for i in range(1, MAX_NODES + 50)]
    snapshot = parse_snapshot(_tree(*nodes, pruned=3), "a0005")
    assert len(snapshot.nodes) == MAX_NODES
    assert snapshot.pruned == 3


def test_public_snapshot_carries_no_internal_handles():
    snapshot = parse_snapshot(_tree(EDITOR, BUTTON), "a0006")
    public = snapshot.public()
    assert public["snapshot_id"] == "a0006"
    assert set(public["nodes"][0]) <= {"id", "role", "name", "depth", "text", "actions", "state", "bounds",
                                       "description", "redacted"}


def test_rendered_tree_names_the_snapshot_and_says_what_was_pruned():
    snapshot = parse_snapshot(_tree(EDITOR, BUTTON, pruned=7), "a0009")
    rendered = snapshot.render()
    assert "snapshot a0009" in rendered
    assert "7 closed menu(s)" in rendered
    assert "n2 text" in rendered and "Save" in rendered


# ----------------------------------------------------------------- fencing


def test_ids_only_act_on_the_snapshot_that_issued_them():
    transport = FakeTransport(_tree(EDITOR), _tree(EDITOR))
    session = AccessibilitySession(transport)
    first = session.elements()
    second = session.elements()
    assert first.snapshot_id != second.snapshot_id
    with pytest.raises(AccessibilityError, match="not the latest"):
        session.require(first.snapshot_id, "n2")
    assert session.require(second.snapshot_id, "n2").name == "note.txt"


def test_require_refuses_unknown_element_and_missing_snapshot():
    session = AccessibilitySession(FakeTransport(_tree(EDITOR)))
    with pytest.raises(AccessibilityError, match="read the elements first"):
        session.require("a0001", "n2")
    snapshot = session.elements()
    with pytest.raises(AccessibilityError, match="not in the latest tree"):
        session.require(snapshot.snapshot_id, "n99")


def test_a_subtree_read_keeps_the_current_generation():
    transport = FakeTransport(_tree(EDITOR, BUTTON), _tree(EDITOR, subtree=True))
    session = AccessibilitySession(transport)
    full = session.elements()
    narrowed = session.elements(root="n2")
    assert narrowed.snapshot_id == full.snapshot_id
    assert session.require(full.snapshot_id, "n2").id == "n2"


def test_a_subtree_read_needs_a_snapshot_first():
    session = AccessibilitySession(FakeTransport())
    with pytest.raises(AccessibilityError, match="no tree to narrow"):
        session.elements(root="n1")


def test_actions_are_sent_for_the_element_that_was_required():
    transport = FakeTransport(_tree(EDITOR), {"ok": True, "action": "Press", "dispatched": True},
                              {"ok": True, "readback": "new", "verified": True})
    session = AccessibilitySession(transport)
    snapshot = session.elements()
    node = session.require(snapshot.snapshot_id, "n2")
    assert session.activate(node)["action"] == "Press"
    assert transport.sent[-1] == {"op": "activate", "element": "n2"}
    session.set_text(node, "new")
    assert transport.sent[-1] == {"op": "set_text", "element": "n2", "text": "new"}


def test_a_worker_error_is_surfaced_as_a_refusal():
    session = AccessibilitySession(FakeTransport(AccessibilityError("element is stale")))
    with pytest.raises(AccessibilityError, match="stale"):
        session.elements()


# -------------------------------------------------------------- bus safety


def test_a_bus_outside_the_private_runtime_is_refused(tmp_path):
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "run"), "AT_SPI_BUS_ADDRESS": "unix:path=/run/user/1000/at-spi/bus_0"}
    with pytest.raises(AccessibilityUnavailable, match="not inside"):
        private_bus_address(env)


def test_a_missing_or_non_socket_address_is_refused(tmp_path):
    with pytest.raises(AccessibilityUnavailable, match="no private accessibility bus"):
        private_bus_address({"XDG_RUNTIME_DIR": str(tmp_path)})
    with pytest.raises(AccessibilityUnavailable, match="no private accessibility bus"):
        private_bus_address({"AT_SPI_BUS_ADDRESS": "tcp:host=127.0.0.1"})


def test_the_private_bus_address_is_accepted(tmp_path):
    run = tmp_path / "run"
    (run / "at-spi").mkdir(parents=True)
    env = {"XDG_RUNTIME_DIR": str(run), "AT_SPI_BUS_ADDRESS": f"unix:path={run}/at-spi/bus"}
    assert private_bus_address(env) == f"unix:path={run}/at-spi/bus"


def test_availability_names_the_missing_binary():
    ok, why = availability(which=lambda name: None, exists=lambda path: "/at-spi2-registryd" not in path)
    assert not ok and "at-spi2-registryd" in why


def test_availability_accepts_binaries_outside_path():
    present = {"/usr/lib/at-spi-bus-launcher", "/usr/lib/at-spi2-registryd"}
    ok, why = availability(which=lambda name: None, exists=lambda path: path in present)
    assert ok and why == ""


# ------------------------------------------------------------- containment


def test_the_accessibility_mount_is_added_before_the_environment_is_cleared(short_root):
    """The socket must cross the containment boundary, and only through a mount declared before --clearenv."""
    import socket as socket_module

    from hutch.computer.native.virtual import ManagedDesktop

    run = short_root / "run"
    (run / "at-spi").mkdir(parents=True)
    path = run / "at-spi" / "bus"
    server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    server.bind(str(path))
    try:
        desktop = ManagedDesktop()
        desktop.root = short_root
        desktop.a11y_address = f"unix:path={path}"
        command = ["bwrap", "--ro-bind", "/usr", "/usr", "--clearenv", "--", "kwrite"]
        mounted = desktop._with_accessibility_mount(command)
        assert mounted[:3] == command[:3]
        assert mounted[mounted.index("--clearenv") - 5:mounted.index("--clearenv")] == [
            "--dir", str(path.parent), "--ro-bind", str(path), str(path)]
        assert mounted[mounted.index("--clearenv"):] == command[command.index("--clearenv"):]
        # With no address at all the command is untouched: pixel control still works.
        desktop.a11y_address = ""
        assert desktop._with_accessibility_mount(command) == command
    finally:
        server.close()


def test_the_mount_refuses_a_socket_outside_the_session(short_root):
    import socket as socket_module

    from hutch.computer.native.virtual import DesktopUnavailable, ManagedDesktop

    desktop = ManagedDesktop()
    desktop.root = short_root / "session"
    desktop.root.mkdir()
    outside = short_root / "elsewhere" / "bus"
    outside.parent.mkdir()
    server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    server.bind(str(outside))
    try:
        desktop.a11y_address = f"unix:path={outside}"
        with pytest.raises(DesktopUnavailable, match="not inside this private session"):
            desktop._with_accessibility_mount(["--clearenv"])
    finally:
        server.close()


def test_the_mount_refuses_a_path_that_is_not_a_socket(tmp_path):
    from hutch.computer.native.virtual import DesktopUnavailable, ManagedDesktop

    desktop = ManagedDesktop()
    desktop.root = tmp_path
    plain = tmp_path / "not-a-socket"
    plain.write_text("")
    desktop.a11y_address = f"unix:path={plain}"
    with pytest.raises(DesktopUnavailable, match="unavailable"):
        desktop._with_accessibility_mount(["--clearenv"])


# ------------------------------------------------------------------- tool


def test_the_tool_contract_covers_semantic_actions_and_redacts_text():
    from hutch.tools.computer import ComputerTool
    from hutch.tools.computer_contract import ACTIONS, STATEFUL

    assert {"elements", "activate", "set_text"} <= set(ACTIONS)
    assert {"activate", "set_text"} <= set(STATEFUL)
    tool = ComputerTool()
    recorded = tool.recorded_arguments(
        {"action": "set_text", "snapshot_id": "a0001", "element_id": "n2", "text": "a sentinel secret"}, None)
    assert recorded["text"] == "[redacted]" and recorded["text_chars"] == len("a sentinel secret")
    assert recorded["element_id"] == "n2" and recorded["snapshot_id"] == "a0001"
    typed = tool.recorded_arguments({"action": "type", "frame_id": "f1", "text": "abc"}, None)
    assert typed == {"action": "type", "frame_id": "f1", "text": "[redacted]", "text_chars": 3}


def test_a_frame_beyond_the_model_limit_is_refused_with_its_reason(tmp_path):
    """Frame pixels are the coordinate space a model reasons in, so an image a provider would rescale is refused."""
    from hutch.computer.frames import MAX_FRAME_EDGE, FrameError, FrameStore

    assert MAX_FRAME_EDGE <= 1568, "a longer edge is downscaled by the documented vision routes"
    store = FrameStore(tmp_path / "run")
    width, height = MAX_FRAME_EDGE + 1, 4
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big")
           + b"\x08\x02\x00\x00\x00" + b"\x00" * 8)
    with pytest.raises(FrameError, match="coordinates always refer to the pixels"):
        store.save(png, "image/png")


def test_set_text_bounds_length_before_dispatching():
    from hutch.computer.control import ControlLease
    from hutch.computer.desktop import DesktopSession

    session = DesktopSession(session_id="s", capture=lambda: b"", input_backend=None, frames=None,
                             lease=ControlLease("s"), a11y=object())
    result = session.set_element_text("a0001", "n2", "x" * 2001)
    assert not result.ok and "2000" in result.output and result.data["outcome"] == "not_dispatched"
