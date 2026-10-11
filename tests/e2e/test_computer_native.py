"""Native desktop task through the `computer` tool, in a disposable KWin Wayland session (never the personal desktop).

Evidence class: a REAL native Wayland compositor, real toolkit windows (KWrite), real EIS input and real KWin capture. It is
not evidence about GNOME, a portal consent flow, or a physical display. Skipped when the prerequisites are absent.
"""

from __future__ import annotations

import time
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


def _wait_for(predicate, seconds=8.0, step=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def test_edit_save_through_a_native_file_dialog_reopen_and_verify(native):
    tool, ctx, workspace = native.tool, native.ctx, native.workspace

    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok, launched.output
    assert launched.data["launched"]["alive"] is True
    # exactly one approval described the session boundary honestly, one the launch
    session_approval = next(d for a, d in native.gate.decisions if a.startswith("operate an isolated desktop"))
    assert session_approval["applications"] == ["kwrite"] and "NOT a process, network or filesystem sandbox" in \
        session_approval["boundary"]

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
    target = workspace / "saved-by-hutch.txt"
    entered = tool.run({"action": "type", "frame_id": _frame(dialog), "text": str(target)}, ctx)
    assert entered.ok
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
    focus = tool.run({"action": "click", "frame_id": _frame(relaunched), "x": 640, "y": 400}, ctx)
    edit = tool.run({"action": "key", "frame_id": _frame(focus), "keys": "ctrl+home"}, ctx)
    typed2 = tool.run({"action": "type", "frame_id": _frame(edit), "text": "REOPENED "}, ctx)
    assert typed2.ok
    saved = tool.run({"action": "key", "frame_id": _frame(typed2), "keys": "ctrl+s"}, ctx)
    assert saved.ok
    assert _wait_for(lambda: target.read_text().strip() == "REOPENED Native desktop task 7"), \
        f"reopen/edit/save did not preserve content: {target.read_text()!r}"


def test_a_menu_opens_and_closes_and_the_screen_change_is_reported(native):
    tool, ctx = native.tool, native.ctx
    launched = tool.run({"action": "launch", "app": "kwrite"}, ctx)
    assert launched.ok
    menu = tool.run({"action": "click", "frame_id": _frame(launched), "x": 340, "y": 189}, ctx)      # "File"
    assert menu.ok and menu.data["visual_change"] is True and menu.data["outcome"] == "dispatched"
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
    assert not outside.ok and "outside this run's workspace" in outside.output


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
