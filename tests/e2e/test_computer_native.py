"""Native desktop task through the `computer` tool, in a disposable KWin Wayland session (never the personal desktop).

Evidence class: a REAL native Wayland compositor, real toolkit windows (KWrite), real EIS input and real KWin capture. It is
not evidence about GNOME, a portal consent flow, or a physical display. Skipped when the prerequisites are absent.
"""

from __future__ import annotations

import time
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hutch.computer.native.eis import find_gi_python
from hutch.computer.native.virtual import ManagedDesktop
from hutch.models import Bot
from hutch.tools.base import ProcRegistry
from hutch.tools.computer import ComputerTool

_ok, _why = ManagedDesktop.available()
pytestmark = pytest.mark.skipif(not _ok or find_gi_python() is None or not ManagedDesktop.available()[0],
                                reason=_why or "no PyGObject interpreter or KWin virtual session available")
pytest.importorskip("shutil")
import shutil  # noqa: E402
import subprocess

if shutil.which("kwrite") is None:                      # the editor under test
    pytestmark = pytest.mark.skip(reason="kwrite is not installed")


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
    gate = Gate()
    bot = Bot(name="native-bot", computer_apps=["kwrite"])
    ctx = SimpleNamespace(
        config=config, bot=bot, run=SimpleNamespace(id="run-native"), workspace=workspace, gate=gate, dry_run=False,
        begin_effect=lambda: None, emit=events.append, on_finish=[], cancel_hooks=[], procs=ProcRegistry(),
        headless=True)
    tool = ComputerTool()
    try:
        yield SimpleNamespace(tool=tool, ctx=ctx, gate=gate, workspace=workspace, events=events)
    finally:
        tool._shutdown(ctx)
        ctx.procs.kill_all(0.2)


def _frame(result) -> str:
    return result.data["observation"]["frame_id"]


def _shot(native, result, name):
    target = os.environ.get("HUTCH_EVIDENCE_DIR")
    if not target:
        return
    from hutch.computer.frames import FrameStore, ImageRef
    frames = FrameStore(native.ctx.config.run_dir(native.ctx.bot.name, native.ctx.run.id))
    ref = ImageRef.from_internal(result.data["images"][0])
    Path(target).mkdir(parents=True, exist_ok=True)
    (Path(target) / f"native-{name}.png").write_bytes(frames.load(ref))


def _wait_for(predicate, seconds=8.0, step=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def test_native_idle_authority_revocation_stops_private_processes(native, store):
    native.ctx.bot.tools = ["computer"]
    native.ctx.bot = store.create_bot(native.ctx.bot)
    native.ctx.store = store
    result = native.tool.run({"action": "observe"}, native.ctx)
    assert result.ok, result.output
    processes = list(native.tool._desktop._procs)
    changed = store.get_bot(native.ctx.bot.id)
    changed.tools = []
    store.upsert_bot(changed)
    assert _wait_for(lambda: native.tool._stopped, seconds=4)
    assert _wait_for(lambda: all(proc.poll() is not None for proc in processes), seconds=3)
    refused = native.tool.run({"action": "type", "frame_id": _frame(result), "text": "revoked"}, native.ctx)
    assert not refused.ok


@pytest.mark.parametrize("change", ["move", "resize"])
def test_real_window_geometry_change_refuses_old_coordinates(native, monkeypatch, change):
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok, launched.output
    identity = tool._input.surface()
    script = tool._desktop.root / "move-for-regression.js"
    adjustment = "x: r.x + 60, y: r.y + 30, width: r.width, height: r.height" if change == "move" else \
                 "x: r.x, y: r.y, width: r.width + 80, height: r.height + 40"
    script.write_text("const w=workspace.activeWindow; const r=w.frameGeometry; w.frameGeometry={" + adjustment + "};")
    name = "hutch-geometry-regression"
    def call(path, interface, method, *args):
        return subprocess.run(["busctl", "--user", "call", "org.kde.KWin", path, interface, method, *args],
                              env=tool._desktop.env, capture_output=True, text=True, timeout=3, check=True).stdout
    index = int(call("/Scripting", "org.kde.kwin.Scripting", "loadScript", "ss", str(script), name).split()[1])
    try:
        call(f"/Scripting/Script{index}", "org.kde.kwin.Script", "run")
        assert _wait_for(lambda: tool._input.surface() != identity, seconds=3)
        calls, original = [], tool._input.click
        def counted(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)
        monkeypatch.setattr(tool._input, "click", counted)
        result = tool.run({"action": "click", "frame_id": _frame(launched), "x": 430, "y": 367}, ctx)
        assert not result.ok and result.data["identity_changed"] and result.data["outcome"] == "not_dispatched"
        assert calls == []
        fresh = tool.run({"action": "observe"}, ctx)
        assert fresh.ok, fresh.output
    finally:
        call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", name)
        script.unlink(missing_ok=True)


def test_real_takeover_interrupts_a_native_typing_burst_and_releases_keys(native, monkeypatch):
    tool, ctx = native.tool, native.ctx
    path = native.workspace / "partial.txt"
    path.write_text("")
    launched = tool.run({"action": "launch", "app": "kwrite", "path": "partial.txt"}, ctx)
    assert launched.ok, launched.output
    focused = tool.run({"action": "click", "frame_id": _frame(launched), "x": 640, "y": 400}, ctx)
    assert focused.ok, focused.output
    original, pressed = tool._input._send, []
    def observed(message, **kwargs):
        reply = original(message, **kwargs)
        if message.get("cmd") == "key" and message.get("press") is True and message.get("code") in (30, 48, 46):
            pressed.append(message["code"])
            if len(pressed) == 1:
                tool._lease.take_over("controlled interruption during typing")
        return reply
    monkeypatch.setattr(tool._input, "_send", observed)
    result = tool.run({"action": "type", "frame_id": _frame(focused), "text": "abc"}, ctx)
    assert not result.ok and result.data["outcome"] == "unknown" and pressed == [30]
    state = original({"cmd": "state"})
    assert state["held_keys"] == 0 and state["held_buttons"] == 0
    # The controlled human verifies the partial effect; the agent does not retry.
    tool._input.chord("ctrl+s")
    assert _wait_for(lambda: path.read_text() == "a\n")  # KWrite's normal final-newline save behavior


def test_edit_save_through_a_native_file_dialog_reopen_and_verify(native):
    tool, ctx, workspace = native.tool, native.ctx, native.workspace

    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok, launched.output
    assert launched.data["launched"]["alive"] is True
    # exactly one approval described the session boundary honestly, one the launch
    session_approval = next(d for a, d in native.gate.decisions if a.startswith("operate an isolated desktop"))
    assert session_approval["applications"] == ["kwrite"] and "workspace-only files" in \
        session_approval["boundary"]
    _shot(native, launched, "welcome")

    # KWrite starts on a Welcome page when launched without a file: the observation shows it, so click "New File"
    # first (a scripted click on a remembered position would have typed into the wrong widget).
    welcome = tool.run({"action": "click", "frame_id": _frame(launched), "x": 430, "y": 367}, ctx)
    assert welcome.ok and welcome.data["visual_change"] is True, welcome.output
    clicked = tool.run({"action": "click", "frame_id": _frame(welcome), "x": 640, "y": 400}, ctx)   # the text area
    assert clicked.ok, clicked.output
    typed = tool.run({"action": "type", "frame_id": _frame(clicked), "text": "Native desktop task 7"}, ctx)
    assert typed.ok and typed.data["visual_change"] is True, typed.output

    # Ctrl+S on an untitled document opens the toolkit's file dialog
    dialog = tool.run({"action": "key", "frame_id": _frame(typed), "keys": "ctrl+s"}, ctx)
    assert dialog.ok and dialog.data["visual_change"] is True, "a save dialog should have appeared"
    _shot(native, dialog, "save-dialog")
    target = workspace / "saved-by-hutch.txt"
    entered = tool.run({"action": "type", "frame_id": _frame(dialog), "text": str(target)}, ctx)
    assert entered.ok
    # Path completion can change popup stacking after typing; inspect its settled native frame before confirming.
    entered = tool.run({"action": "observe"}, ctx)
    assert entered.ok, entered.output
    confirmed = tool.run({"action": "key", "frame_id": _frame(entered), "keys": "enter"}, ctx)
    assert confirmed.ok

    # the driver only reports "dispatched"; the postcondition is the file on disk
    assert _wait_for(lambda: target.exists() and target.read_text().strip() == "Native desktop task 7"), \
        f"the document was not saved with the typed content: {target.exists() and target.read_text()!r}"

    # close the editor, reopen the same file, edit and save again: the reopened document must have held the old text
    quit_result = tool.run({"action": "key", "frame_id": _frame(confirmed), "keys": "ctrl+q"}, ctx)
    assert quit_result.ok
    relaunched = tool.run({"action": "launch", "app": "kwrite", "path": "saved-by-hutch.txt"}, ctx)
    assert relaunched.ok, relaunched.output
    _shot(native, relaunched, "reopened")
    focus = tool.run({"action": "click", "frame_id": _frame(relaunched), "x": 640, "y": 400}, ctx)
    edit = tool.run({"action": "key", "frame_id": _frame(focus), "keys": "ctrl+home"}, ctx)
    typed2 = tool.run({"action": "type", "frame_id": _frame(edit), "text": "REOPENED "}, ctx)
    assert typed2.ok
    saved = tool.run({"action": "key", "frame_id": _frame(typed2), "keys": "ctrl+s"}, ctx)
    assert saved.ok
    _shot(native, saved, "saved")
    assert _wait_for(lambda: target.read_text().strip() == "REOPENED Native desktop task 7"), \
        f"reopen/edit/save did not preserve content: {target.read_text()!r}"


def test_a_menu_opens_and_closes_and_the_screen_change_is_reported(native):
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok
    menu = tool.run({"action": "click", "frame_id": _frame(launched), "x": 340, "y": 189}, ctx)      # "File"
    assert menu.ok and menu.data["visual_change"] is True and menu.data["outcome"] == "dispatched"
    _shot(native, menu, "menu")
    closed = tool.run({"action": "key", "frame_id": _frame(menu), "keys": "escape"}, ctx)
    assert closed.ok and closed.data["visual_change"] is True


def test_input_is_refused_for_stale_frames_bad_coordinates_and_during_takeover(native):
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    frame = _frame(launched)

    assert not tool.run({"action": "click", "frame_id": "f999999", "x": 5, "y": 5}, ctx).ok
    outside = tool.run({"action": "click", "frame_id": frame, "x": 1280, "y": 10}, ctx)
    assert not outside.ok and "outside the 1280x800 frame" in outside.output

    tool._lease.take_over("a person is operating the desktop")
    blocked = tool.run({"action": "click", "frame_id": frame, "x": 640, "y": 400}, ctx)
    assert not blocked.ok and blocked.data["outcome"] == "not_dispatched" and "a person is controlling" in blocked.output
    tool._lease.hand_back()
    still_stale = tool.run({"action": "click", "frame_id": frame, "x": 640, "y": 400}, ctx)
    assert not still_stale.ok and "observe again" in still_stale.output       # handoff forces a fresh observation
    fresh = tool.run({"action": "observe"}, ctx)
    assert tool.run({"action": "click", "frame_id": _frame(fresh), "x": 640, "y": 400}, ctx).ok


def test_launch_is_limited_to_allowed_apps_and_workspace_files(native):
    tool, ctx = native.tool, native.ctx
    assert not tool.run({"action": "launch", "app": "konsole"}, ctx).ok
    outside = tool.run({"action": "launch", "app": "kwrite", "path": "/etc/passwd"}, ctx)
    assert not outside.ok and "workspace" in outside.output


def test_emergency_stop_ends_the_whole_desktop_and_nothing_more_runs(native):
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok
    procs = list(tool._desktop._procs)
    assert procs and all(p.poll() is None for p in procs[:2])

    started = time.monotonic()
    for hook in list(ctx.cancel_hooks):
        hook()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(p.poll() is None for p in procs):
        time.sleep(0.05)
    latency = time.monotonic() - started
    print(f"MEASURED native stop-to-all-processes-ended latency: {latency:.2f}s")
    assert all(p.poll() is not None for p in procs), "compositor/bus/app must be gone after stop"
    again = tool.run({"action": "observe"}, ctx)
    assert not again.ok and "stopped" in again.output


def test_a_bot_without_allowed_apps_cannot_start_a_session(config, tmp_path):
    ctx = SimpleNamespace(config=config, bot=Bot(name="no-apps"), run=SimpleNamespace(id="r"), workspace=tmp_path,
                          gate=Gate(), dry_run=False, begin_effect=lambda: None, emit=lambda e: None, on_finish=[],
                          cancel_hooks=[], procs=ProcRegistry(), headless=True)
    result = ComputerTool().run({"action": "observe"}, ctx)
    assert not result.ok and "no applications allowed" in result.output


def test_native_app_namespace_cannot_read_outside_workspace_or_reach_host_loopback(tmp_path):
    import json
    import socket
    workspace = tmp_path / "granted"
    workspace.mkdir()
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("SENTINEL-OUTSIDE-WORKSPACE")
    with socket.socket() as listener, ManagedDesktop() as desktop:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        script = ("import pathlib,socket,json,sys; result={'outside':pathlib.Path(sys.argv[1]).exists()}; "
                  "s=socket.socket();s.settimeout(1);result['network']=s.connect_ex(('127.0.0.1',int(sys.argv[2])))==0;"
                  "pathlib.Path('containment.json').write_text(json.dumps(result))")
        proc = desktop.launch(["/usr/bin/python3", "-c", script, str(outside), str(listener.getsockname()[1])],
                              "containment-probe", cwd=str(workspace))
        assert proc.wait(timeout=12) == 0
        assert json.loads((workspace / "containment.json").read_text()) == {"outside": False, "network": False}


def test_human_step_input_edits_and_saves_the_real_native_application_without_model_observation(native):
    from tests.test_computer_human import _call
    from hutch.computer.human import HumanError
    native.ctx.bot.remote_computer_access = "control"
    launched = native.tool.run({"action": "launch", "app": "kwrite"}, native.ctx)
    assert launched.ok, launched.output
    channel = native.tool._human
    grant = channel.takeover("native-human")
    sequence = 0
    frame = {}
    def heartbeat():
        nonlocal grant
        state = channel.command("native-human", {"action": "heartbeat",
                                  "control_token": grant["control_token"], "generation": grant["generation"]})
        if isinstance(state, HumanError):
            assert "control expired" in str(state), str(state)
            # This low-level test drives HumanSession directly, so it must model
            # the browser's keepalive and explicit reacquisition after expiry.
            grant = channel.takeover("native-human")
        else:
            assert isinstance(state, dict), str(state)
    def command(action, **args):
        nonlocal sequence, frame
        heartbeat()
        sequence += 1
        time.sleep(0.21)
        result = _call(channel, "native-human", {"action": action, "sequence": sequence,
                       "control_token": grant["control_token"], "generation": grant["generation"],
                       "frame_id": frame.get("frame_id", ""), **args})
        if (action != "capture" and isinstance(result, HumanError)
                and "Input was dispatched, but its follow-up capture failed" in str(result)):
            # The input is already dispatched. Never retry it: follow the channel's
            # instruction and make a new read-only observation before any more input.
            return command("capture")
        assert isinstance(result, dict), str(result)
        frame = result["frame"]
        return result
    command("capture")
    command("click", x=430, y=367)
    command("click", x=640, y=400)
    command("type", text="HUMAN-PRIVATE-NATIVE-NOTE")
    command("key", keys="ctrl+s")
    target = native.workspace / "human-native.txt"
    command("type", text=str(target))
    command("capture")  # explicit fresh inspection after native file-name completion
    command("key", keys="enter")
    assert _wait_for(lambda: target.exists() and target.read_text().strip() == "HUMAN-PRIVATE-NATIVE-NOTE")
    assert "HUMAN-PRIVATE-NATIVE-NOTE" not in str([e.model_dump() for e in native.events])
    channel.command("native-human", {"action": "resume", "control_token": grant["control_token"], "generation": grant["generation"]})
    stale = native.tool.run({"action": "click", "frame_id": _frame(launched), "x": 640, "y": 400}, native.ctx)
    assert not stale.ok and "observe again" in stale.output


def test_mixed_workflow_terminal_generates_a_file_the_desktop_app_edits_and_saves(store, config, tmp_path):
    """A real shell command produces the file; the editor opens that exact workspace path; the saved bytes are the proof.

    Upload to a destination is deliberately absent: Hutch refuses file uploads it cannot show for review."""
    from hutch.models import ApprovalMode
    from hutch.tools.shell import ShellTool
    from tests.test_tools import make_ctx

    bot = Bot(name="mixed-bot", tools=["shell", "computer"], computer_apps=["kwrite"], approval_mode=ApprovalMode.auto)
    ctx = make_ctx(store, config, tmp_path, bot=bot)
    ctx.gate = Gate()                                      # a person approves in this scenario
    shell, computer = ShellTool(), ComputerTool()
    try:
        made = shell.run({"command": "printf 'report line from the terminal\\n' > report.txt"}, ctx)
        assert made.ok, made.output
        report = ctx.workspace / "report.txt"
        assert report.read_text() == "report line from the terminal\n"

        launched = computer.run({"action": "launch", "app": "kwrite", "path": "report.txt"}, ctx)
        assert launched.ok, launched.output
        focus = computer.run({"action": "click", "frame_id": _frame(launched), "x": 640, "y": 400}, ctx)
        to_end = computer.run({"action": "key", "frame_id": _frame(focus), "keys": "ctrl+End"}, ctx)
        typed = computer.run({"action": "type", "frame_id": _frame(to_end), "text": "appended in the editor"}, ctx)
        assert typed.ok
        saved = computer.run({"action": "key", "frame_id": _frame(typed), "keys": "ctrl+s"}, ctx)
        assert saved.ok
        assert _wait_for(lambda: report.read_text() == "report line from the terminal\nappended in the editor\n"), \
            f"the editor did not save onto the terminal-generated file: {report.read_text()!r}"
        # provenance: the only file touched is the one the shell created inside this run's workspace
        assert sorted(p.name for p in ctx.workspace.iterdir()) == ["report.txt"]
    finally:
        computer._shutdown(ctx)
        ctx.procs.kill_all(0.2)
