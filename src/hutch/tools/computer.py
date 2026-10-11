"""Computer tool — operate native desktop applications in an isolated, disposable desktop session.

Environment mode: ``isolated`` only. Hutch starts its own compositor (display, input, session bus) for the run, launches
applications the bot is allowed to use, observes the screen as bounded frames and acts through validated pointer/keyboard
commands. The personal desktop is never the target: its input stack is not touched. Controlling the user's existing desktop
is a deliberately different, weaker-isolation mode that is not offered by this build.

What the boundary is NOT: applications run as the same user with the same network and file access. A person approves the
session (naming the applications and saying so) before anything starts.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ..approvals import DeniedError
from ..computer.control import ControlLease
from ..computer.desktop import DesktopSession
from ..computer.frames import FrameStore
from ..models import Event, EventType
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, rehearsed

_ACTIONS = {
    "launch": "Start an allowed application in the isolated desktop (optionally opening a file in the workspace).",
    "observe": "Capture the screen as an image frame; returns a frame_id that input actions must quote.",
    "click": "Click at pixel (x, y) of the latest frame. Needs that frame_id; refused if it is not the latest.",
    "type": "Type text into the focused control. Needs the latest frame_id.",
    "key": "Press a key or chord such as enter, escape, ctrl+s. Needs the latest frame_id.",
    "wait": "Wait up to 10 seconds, then capture a new frame.",
    "close": "End the isolated desktop session and everything started in it.",
}
_LAUNCH_TIMEOUT_SECONDS = 12.0     # how long a launched window may take to appear and settle
_LAUNCH_POLL_SECONDS = 0.4


class ComputerTool(Tool):
    name = "computer"
    description = (
        "Operate native desktop applications in an isolated desktop session. Workflow: launch an app, observe, then "
        "act on the latest frame (click/type/key); every action returns a fresh frame. Actions: "
        + "; ".join(f"{k} — {v}" for k, v in _ACTIONS.items()))
    parameters = _schema(["action"], {
        "action": {"type": "string", "enum": list(_ACTIONS)},
        "app": {"type": "string", "description": "for launch: an allowed application name"},
        "path": {"type": "string", "description": "for launch: a file inside the workspace to open"},
        "frame_id": {"type": "string", "description": "for click/type/key: the latest frame_id"},
        "x": {"type": "number", "description": "for click: horizontal pixel of the frame"},
        "y": {"type": "number", "description": "for click: vertical pixel of the frame"},
        "button": {"type": "string", "enum": ["left", "right", "middle"]},
        "count": {"type": "integer", "description": "for click: 1 or 2 (double click)"},
        "text": {"type": "string", "description": "for type: text to enter (printable ASCII)"},
        "keys": {"type": "string", "description": "for key: e.g. enter, ctrl+s, ctrl+shift+z"},
        "seconds": {"type": "number", "description": "for wait"},
    })

    def __init__(self, *, desktop_factory=None, input_factory=None):
        self._desktop_factory = desktop_factory      # test seams; production uses the KWin-backed managers
        self._input_factory = input_factory
        self._desktop: Any = None
        self._session: Optional[DesktopSession] = None
        self._input: Any = None
        self._approved = False
        self._stopped = False
        self._owner_thread: Optional[int] = None
        self._lease: Optional[ControlLease] = None

    # ------------------------------------------------------------- recording

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "process" if (args.get("action") or "") in ("launch", "click", "type", "key") else ""

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        action = (args.get("action") or "").strip()
        if action == "type":
            text = args.get("text") if isinstance(args.get("text"), str) else ""
            return {"action": "type", "frame_id": args.get("frame_id", ""), "text": "[redacted]",
                    "text_chars": len(text)}
        return {k: args[k] for k in ("action", "app", "path", "frame_id", "x", "y", "button", "count", "keys", "seconds")
                if k in args}

    # ---------------------------------------------------------------- run

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = (args.get("action") or "").strip()
        if action not in _ACTIONS:
            return ToolResult(False, f"error: unknown action '{action}'")
        if self._stopped:
            return ToolResult(False, "error: this run was stopped and its desktop was closed; no further action runs")
        if ctx.dry_run and action in ("launch", "click", "type", "key"):
            return rehearsed(f"computer {action}")
        try:
            return self._run(action, args, ctx)
        except DeniedError as exc:
            return ToolResult(False, f"error: {exc}")
        except Exception as exc:
            if self._stopped:
                return ToolResult(False, "error: the run was stopped; the desktop was closed mid-action, so the outcome "
                                         "of that action is unknown", {"stopped": True, "outcome": "unknown"})
            return ToolResult(False, f"computer error: {exc}")

    def _run(self, action: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if action == "close":
            self._shutdown(ctx)
            return ToolResult(True, "the isolated desktop session was closed")
        if self._owner_thread is not None and self._owner_thread != threading.get_ident():
            return ToolResult(False, "error: this desktop session belongs to another thread; nothing was done",
                              {"thread_affinity": True})
        session = self._ensure(ctx)
        if self._owner_thread is None:
            self._owner_thread = threading.get_ident()
        session.before_dispatch = ctx.begin_effect

        if action == "launch":
            return self._launch(args, ctx, session)
        if action == "observe":
            return self._result(session.observe())
        if action == "wait":
            time.sleep(min(max(float(args.get("seconds") or 1), 0.0), 10.0))
            return self._result(session.observe())
        frame_id = str(args.get("frame_id") or "")
        if action == "click":
            count = int(args.get("count") or 1)
            return self._result(session.click(frame_id, args.get("x"), args.get("y"),
                                               button=str(args.get("button") or "left"), count=count))
        if action == "type":
            return self._result(session.type_text(frame_id, args.get("text") or ""))
        if action == "key":
            return self._result(session.key(frame_id, str(args.get("keys") or "")))
        return ToolResult(False, f"unhandled action {action}")  # pragma: no cover

    @staticmethod
    def _result(res) -> ToolResult:
        return ToolResult(res.ok, res.output, dict(res.data))

    # ----------------------------------------------------------- environment

    def _ensure(self, ctx: ToolContext) -> DesktopSession:
        if self._session is not None:
            return self._session
        apps = list(getattr(ctx.bot, "computer_apps", []) or [])
        if not apps:
            raise DeniedError("this Bot has no applications allowed for the computer tool; add one in its settings")
        # One approval for the whole session, describing what actually bounds it (and what does not).
        ctx.gate.decide(
            "computer", f"operate an isolated desktop session (applications: {', '.join(apps)})",
            {"environment": "isolated", "applications": apps,
             "boundary": "separate display, input and session bus; NOT a process, network or filesystem sandbox",
             "reads": "screen frames are sent to the model route this Bot uses",
             "profile_bot_id": ctx.bot.id},
            Decision(Verdict.ask, "start an isolated desktop session", "computer:session", rule="ask:computer-session",
                     risk="medium"))
        self._approved = True

        from ..computer.native.eis import EisInput
        from ..computer.native.virtual import DesktopUnavailable, ManagedDesktop
        desktop = (self._desktop_factory or ManagedDesktop)()
        try:
            desktop.__enter__()
        except DesktopUnavailable as exc:
            raise DeniedError(f"the isolated desktop could not start: {exc}") from exc
        self._desktop = desktop
        for proc in getattr(desktop, "_procs", []):
            ctx.procs.register(proc, "computer")
        try:
            eis = (self._input_factory or EisInput.start_in_isolated_session)(desktop.env)
        except Exception as exc:
            self._shutdown(ctx)
            raise DeniedError(f"input could not be established: {exc}") from exc
        self._input = eis
        proc = getattr(eis, "_proc", None)
        if proc is not None:
            ctx.procs.register(proc, "computer")

        run_id = getattr(ctx.run, "id", "")

        def announce(snap) -> None:
            if ctx.emit is not None and run_id:
                ctx.emit(Event(run_id=run_id, type=EventType.log,
                               data={"kind": "computer_control", "surface": "desktop", **snap.public()}))

        self._lease = ControlLease(f"{run_id}:desktop", on_change=announce)
        self._session = DesktopSession(
            session_id=f"{run_id}:desktop", capture=desktop.capture_png, input_backend=eis,
            frames=FrameStore(ctx.config.run_dir(ctx.bot.name, run_id)), lease=self._lease,
            environment={"mode": "isolated",
                         "boundary": "display/input/session bus only; not a process, network or filesystem sandbox",
                         "applications": apps, "keyboard_layout": "us (assumed)"})
        ctx.on_finish.append(lambda: self._shutdown(ctx))
        ctx.cancel_hooks.append(self._emergency_stop)
        return self._session

    def _launch(self, args: dict[str, Any], ctx: ToolContext, session: DesktopSession) -> ToolResult:
        app = str(args.get("app") or "").strip()
        allowed = list(getattr(ctx.bot, "computer_apps", []) or [])
        if app not in allowed:
            return ToolResult(False, f"error: '{app}' is not an allowed application; allowed: {allowed}. Nothing was started.")
        binary = shutil.which(app)
        if binary is None:
            return ToolResult(False, f"error: '{app}' is not installed on this host. Nothing was started.")
        argv = [binary]
        path = str(args.get("path") or "").strip()
        if path:
            workspace = ctx.workspace.resolve()
            candidate = (workspace / path) if not os.path.isabs(path) else Path(path)
            resolved = Path(os.path.abspath(candidate))
            try:
                resolved.relative_to(workspace)
            except ValueError:
                return ToolResult(False, "error: the file is outside this run's workspace; nothing was started.")
            if resolved.exists() and (resolved.is_symlink() or not resolved.is_file()):
                return ToolResult(False, "error: only a regular workspace file can be opened; nothing was started.")
            argv.append(str(resolved))
        ctx.gate.decide("computer", f"launch {app}" + (f" with {path}" if path else ""),
                        {"application": app, "path": path, "profile_bot_id": ctx.bot.id},
                        Decision(Verdict.ask, f"launch {app}", f"computer:launch:{app}", rule="ask:computer-launch",
                                 risk="medium"))
        if (refusal := ctx.begin_effect()):
            return ToolResult(False, f"error: {refusal}")
        before = session.observe()                       # what the screen shows before the application exists
        before_hash = before.image.sha256 if before.ok and before.image else None
        proc = self._desktop.launch(argv, f"app-{app}", cwd=str(ctx.workspace))
        ctx.procs.register(proc, "computer")
        # Wait for the window to appear (the screen differs from before) and then to hold still for two captures, rather
        # than sleeping a fixed time that is wrong on a loaded host.
        deadline = time.monotonic() + _LAUNCH_TIMEOUT_SECONDS
        result, previous_hash, stable = before, before_hash, False
        while time.monotonic() < deadline and proc.poll() is None:
            time.sleep(_LAUNCH_POLL_SECONDS)
            result = session.observe()
            current = result.image.sha256 if result.ok and result.image else None
            if current is not None and current != before_hash and current == previous_hash:
                stable = True
                break
            previous_hash = current
        if proc.poll() is None and not stable:
            result = session.observe() if not result.ok else result
        data = dict(result.data)
        data["launch_settled"] = stable
        data["launched"] = {"app": app, "pid": proc.pid, "alive": proc.poll() is None}
        output = f"launched {app}; " + result.output
        if proc.poll() is not None:
            output = f"error: {app} exited immediately (code {proc.returncode}); " + result.output
            return ToolResult(False, output, data)
        return ToolResult(result.ok, output, data)

    # ------------------------------------------------------------- lifecycle

    def _emergency_stop(self) -> None:
        """Run-cancel hook on the supervisor thread: fence, end input, end the whole desktop. Model-independent."""
        self._stopped = True
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:
                pass
        if self._desktop is not None:
            try:
                self._desktop.kill_all()
            except Exception:
                pass

    def _shutdown(self, ctx: Optional[ToolContext] = None) -> None:
        session, self._session = self._session, None
        eis, self._input = self._input, None
        desktop, self._desktop = self._desktop, None
        if session is not None:
            session.release_all()
            if self._lease is not None and not self._stopped:
                self._lease.request_stop("session closed")
                self._lease.confirm_stopped(0)
        if eis is not None:
            try:
                eis.close()
            except Exception:
                pass
        if desktop is not None:
            try:
                desktop.__exit__(None, None, None)
            except Exception:
                pass
