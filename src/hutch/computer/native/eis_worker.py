#!/usr/bin/env python3
"""Out-of-process libei (EIS) input worker for the native desktop driver.

Why a separate process: acquiring an EIS socket needs D-Bus file-descriptor passing (GLib/Gio), which Hutch's own
interpreter may not have, and a native input path must be *killable* independently of the agent loop and of whatever
inference is running. The parent speaks one JSON object per line on stdin/stdout:

    {"id": 1, "cmd": "pointer_abs", "x": 640.0, "y": 400.0}
    {"id": 2, "cmd": "button", "button": 272, "press": true}      # evdev code, 272 = BTN_LEFT
    {"id": 3, "cmd": "key", "code": 30, "press": true}            # evdev code, 30 = KEY_A
    {"id": 4, "cmd": "release_all"}                               # release everything THIS worker holds down
    {"id": 5, "cmd": "quit"}

Replies are ``{"id": n, "ok": true}`` or ``{"id": n, "ok": false, "error": "..."}``. The first line printed is
``{"ready": true, "regions": [[x, y, w, h], ...], "capabilities": [...]}`` or ``{"ready": false, "error": ...}``.

Safety: this worker only runs inside a session the caller declared isolated (``HUTCH_ISOLATED_SESSION=1``) and refuses the
user's default session bus, so it can never be pointed at a personal desktop by accident. The supported way to get input
into a *personal* desktop is the RemoteDesktop portal with the person's consent, which is a different acquisition path
(``--fd``) feeding this same protocol.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import select
import sys
import time

CAP_POINTER_ABSOLUTE, CAP_KEYBOARD, CAP_BUTTON, CAP_SCROLL = 1 << 1, 1 << 2, 1 << 5, 1 << 4
EV_CONNECT, EV_DISCONNECT, EV_SEAT_ADDED, EV_DEVICE_ADDED, EV_DEVICE_REMOVED, EV_DEVICE_PAUSED, EV_DEVICE_RESUMED = 1, 2, 3, 5, 6, 7, 8


_DEBUG = os.environ.get("HUTCH_EIS_DEBUG") == "1"
_EVENT_NAMES = {1: "CONNECT", 2: "DISCONNECT", 3: "SEAT_ADDED", 4: "SEAT_REMOVED", 5: "DEVICE_ADDED", 6: "DEVICE_REMOVED",
                7: "DEVICE_PAUSED", 8: "DEVICE_RESUMED", 9: "KEYBOARD_MODIFIERS", 90: "PONG", 91: "SYNC", 100: "FRAME"}


def _debug(message: str) -> None:
    if _DEBUG:
        sys.stderr.write("eis: " + message + "\n")
        sys.stderr.flush()


def _out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _refuse_if_not_isolated() -> None:
    if os.environ.get("HUTCH_ISOLATED_SESSION") != "1":
        raise SystemExit("refused: HUTCH_ISOLATED_SESSION=1 is required (this worker is for disposable sessions)")
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    user_bus = f"/run/user/{os.getuid()}/bus"
    if not address or user_bus in address or runtime == f"/run/user/{os.getuid()}":
        raise SystemExit("refused: this looks like the user's own session bus/runtime directory")


class _KwinSession:
    """The EIS socket plus the D-Bus connection that requested it.

    KWin ties an EIS context to the *requesting D-Bus peer*: when that connection goes away the context is torn down and the
    socket reads as a broken pipe. The connection therefore has to outlive every use of the socket (an earlier version let it
    be garbage-collected, which made input work or fail depending on collection timing)."""

    def __init__(self, capabilities: int) -> None:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        self._gio = Gio
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result, fds = self.connection.call_with_unix_fd_list_sync(
            "org.kde.KWin", "/org/kde/KWin/EIS/RemoteDesktop", "org.kde.KWin.EIS.RemoteDesktop", "connectToEIS",
            GLib.Variant("(i)", (capabilities,)), GLib.VariantType("(hi)"), Gio.DBusCallFlags.NONE, 5000, None, None)
        handle, self.cookie = result.unpack()
        self.fd = fds.get(handle)
        self._GLib = GLib

    def close(self) -> None:
        try:
            self.connection.call_sync(
                "org.kde.KWin", "/org/kde/KWin/EIS/RemoteDesktop", "org.kde.KWin.EIS.RemoteDesktop", "disconnect",
                self._GLib.Variant("(i)", (self.cookie,)), None, self._gio.DBusCallFlags.NONE, 2000, None)
        except Exception:
            pass

    def surface(self) -> dict:
        """Bounded focus/stacking/geometry identity from this private compositor, without titles or contents."""
        from gi.repository import Gio, GLib
        connection = self.connection
        nonce = secrets.token_hex(12)
        object_path = "/HutchGeometry" + nonce
        script = Path(os.environ["XDG_RUNTIME_DIR"]) / ("geometry-" + nonce + ".js")
        info = Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.hutch.PrivateGeometry"><method name="Set">'
                                          '<arg name="state" type="s" direction="in"/></method></interface></node>')
        def call(path, interface, method, signature=None, args=None):
            return connection.call_sync("org.kde.KWin", path, interface, method,
                GLib.Variant(signature, args) if signature else None, None, Gio.DBusCallFlags.NONE, 750, None).unpack()
        owner = connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner",
            GLib.Variant("(s)", ("org.kde.KWin",)), None, Gio.DBusCallFlags.NONE, 750, None).unpack()[0]
        answers = []
        def receive(_conn, sender, _path, _interface, _method, parameters, invocation):
            value = parameters.unpack()[0]
            if sender != owner or len(value) > 16384 or answers:
                invocation.return_dbus_error("org.hutch.Refused", "surface identity refused")
                return
            answers.append(value)
            invocation.return_value(GLib.Variant("()", ()))
        registration = connection.register_object(object_path, info.interfaces[0], receive, None, None)
        loaded = False
        try:
            code = """const windows = workspace.stackingOrder;
if (windows.length <= 64) {
 const state = {active: workspace.activeWindow ? String(workspace.activeWindow.internalId) : null,
   desktop: String(workspace.currentDesktop.id), windows: windows.map(w => ({id: String(w.internalId),
     x: w.frameGeometry.x, y: w.frameGeometry.y, width: w.frameGeometry.width, height: w.frameGeometry.height,
     minimized: w.minimized, desktops: w.desktops.map(d => String(d.id))}))};
 callDBus(SERVICE, OBJECT, 'org.hutch.PrivateGeometry', 'Set', JSON.stringify(state));
}""".replace("SERVICE", json.dumps(connection.get_unique_name())).replace("OBJECT", json.dumps(object_path))
            fd = os.open(script, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(code)
            index = call("/Scripting", "org.kde.kwin.Scripting", "loadScript", "(ss)", (str(script), nonce))[0]
            if not isinstance(index, int) or index < 0:
                raise RuntimeError("private compositor rejected the identity probe")
            loaded = True
            call(f"/Scripting/Script{index}", "org.kde.kwin.Script", "run")
            context, deadline = GLib.MainContext.default(), time.monotonic() + .75
            while time.monotonic() < deadline and not answers:
                while context.pending():
                    context.iteration(False)
                time.sleep(.005)
            if not answers:
                raise RuntimeError("private compositor identity probe did not answer")
            state = json.loads(answers[0])
            if not isinstance(state, dict) or len(state.get("windows", [])) > 64:
                raise RuntimeError("private compositor identity exceeded its bound")
            return state
        finally:
            connection.unregister_object(registration)
            if loaded:
                try: call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", "(s)", (nonce,))
                except Exception: pass
            script.unlink(missing_ok=True)


class Ei:
    def __init__(self) -> None:
        lib = ctypes.CDLL("libei.so.1")
        vp, ci, cu32, cu64, cd, cb = (ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_uint64,
                                      ctypes.c_double, ctypes.c_bool)
        sig = {
            "ei_new_sender": (vp, [vp]), "ei_setup_backend_fd": (ci, [vp, ci]), "ei_get_fd": (ci, [vp]),
            "ei_dispatch": (None, [vp]), "ei_get_event": (vp, [vp]), "ei_event_get_type": (ci, [vp]),
            "ei_event_unref": (None, [vp]), "ei_event_get_seat": (vp, [vp]), "ei_event_get_device": (vp, [vp]),
            "ei_device_has_capability": (cb, [vp, ci]), "ei_device_ref": (vp, [vp]),
            "ei_device_start_emulating": (None, [vp, cu32]), "ei_device_stop_emulating": (None, [vp]),
            "ei_device_pointer_motion_absolute": (None, [vp, cd, cd]), "ei_device_button_button": (None, [vp, cu32, cb]),
            "ei_device_keyboard_key": (None, [vp, cu32, cb]), "ei_device_frame": (None, [vp, cu64]),
            "ei_now": (cu64, [vp]), "ei_device_get_region": (vp, [vp, ctypes.c_size_t]),
            "ei_region_get_x": (cu32, [vp]), "ei_region_get_y": (cu32, [vp]),
            "ei_region_get_width": (cu32, [vp]), "ei_region_get_height": (cu32, [vp]),
            "ei_configure_name": (None, [vp, ctypes.c_char_p]), "ei_unref": (vp, [vp]),
            "ei_seat_bind_capabilities": (None, None),   # variadic: called with explicit varargs below
        }
        for name, (restype, argtypes) in sig.items():
            fn = getattr(lib, name)
            fn.restype = restype
            if argtypes is not None:
                fn.argtypes = argtypes
        self.lib = lib


class Worker:
    def __init__(self, fd: int, kwin_session=None) -> None:
        self.kwin_session = kwin_session
        self.ei = Ei().lib
        self.ctx = self.ei.ei_new_sender(None)
        self.ei.ei_configure_name(self.ctx, b"hutch-computer-use")
        rc = self.ei.ei_setup_backend_fd(self.ctx, fd)
        if rc != 0:
            raise RuntimeError(f"ei_setup_backend_fd failed ({rc})")
        self.pointer = None       # device handle with absolute pointer + button
        self.keyboard = None
        self.paused: dict[int, bool] = {}
        self.regions: list[list[int]] = []
        self.caps_seen: set[str] = set()
        self.held_keys: set[int] = set()
        self.held_buttons: set[int] = set()
        self.sequence = 0
        self.disconnected = False

    # ------------------------------------------------------------- events

    def pump(self, timeout: float = 0.0) -> None:
        fd = self.ei.ei_get_fd(self.ctx)
        if select.select([fd], [], [], timeout)[0]:
            self.ei.ei_dispatch(self.ctx)
        while True:
            event = self.ei.ei_get_event(self.ctx)
            if not event:
                break
            try:
                self._handle(event)
            finally:
                self.ei.ei_event_unref(event)

    def _handle(self, event) -> None:
        kind = self.ei.ei_event_get_type(event)
        _debug(f"event {_EVENT_NAMES.get(kind, kind)}")
        if kind == EV_DISCONNECT:
            self.disconnected = True
        elif kind == EV_SEAT_ADDED:
            seat = self.ei.ei_event_get_seat(event)
            self.ei.ei_seat_bind_capabilities(
                ctypes.c_void_p(seat), ctypes.c_int(CAP_POINTER_ABSOLUTE), ctypes.c_int(CAP_BUTTON),
                ctypes.c_int(CAP_KEYBOARD), ctypes.c_int(CAP_SCROLL), ctypes.c_int(0))
        elif kind == EV_DEVICE_ADDED:
            device = self.ei.ei_device_ref(self.ei.ei_event_get_device(event))
            has = lambda cap: bool(self.ei.ei_device_has_capability(device, cap))
            _debug("device caps: " + ",".join(n for n, c in (("pointer_abs", CAP_POINTER_ABSOLUTE), ("keyboard", CAP_KEYBOARD),
                                                              ("button", CAP_BUTTON), ("scroll", CAP_SCROLL)) if has(c)))
            if has(CAP_POINTER_ABSOLUTE) and has(CAP_BUTTON) and self.pointer is None:
                self.pointer = device
                self.caps_seen.update({"pointer_absolute", "button"})
                index = 0
                while True:
                    region = self.ei.ei_device_get_region(device, index)
                    if not region:
                        break
                    self.regions.append([self.ei.ei_region_get_x(region), self.ei.ei_region_get_y(region),
                                         self.ei.ei_region_get_width(region), self.ei.ei_region_get_height(region)])
                    index += 1
            if has(CAP_KEYBOARD) and self.keyboard is None:
                self.keyboard = device
                self.caps_seen.add("keyboard")
            self.paused[device] = True
        elif kind == EV_DEVICE_PAUSED:
            self.paused[self.ei.ei_event_get_device(event)] = True
        elif kind == EV_DEVICE_RESUMED:
            device = self.ei.ei_event_get_device(event)
            for known in list(self.paused):
                if known == device:
                    self.paused[known] = False
                    self.sequence += 1
                    self.ei.ei_device_start_emulating(known, self.sequence)
        elif kind == EV_DEVICE_REMOVED:
            device = self.ei.ei_event_get_device(event)
            if self.pointer == device:
                self.pointer = None
            if self.keyboard == device:
                self.keyboard = None

    def ready(self) -> bool:
        return bool(self.pointer or self.keyboard) and not self.disconnected and all(
            not self.paused.get(d, True) for d in (self.pointer, self.keyboard) if d)

    # ----------------------------------------------------------- commands

    def _frame(self, device) -> None:
        self.ei.ei_device_frame(device, self.ei.ei_now(self.ctx))
        self.pump(0.0)

    def execute(self, message: dict) -> dict | None:
        cmd = message.get("cmd")
        if self.disconnected:
            raise RuntimeError("the input connection was closed by the compositor")
        self.pump(0.0)
        if cmd == "pointer_abs":
            if self.pointer is None or self.paused.get(self.pointer, True):
                raise RuntimeError("no active absolute pointer device")
            x, y = float(message["x"]), float(message["y"])
            if not any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in self.regions):
                raise RuntimeError(f"({x}, {y}) is outside every input region {self.regions}")
            self.ei.ei_device_pointer_motion_absolute(self.pointer, x, y)
            self._frame(self.pointer)
        elif cmd == "button":
            if self.pointer is None or self.paused.get(self.pointer, True):
                raise RuntimeError("no active button device")
            button, press = int(message["button"]), bool(message["press"])
            self.ei.ei_device_button_button(self.pointer, button, press)
            (self.held_buttons.add if press else self.held_buttons.discard)(button)
            self._frame(self.pointer)
        elif cmd == "key":
            if self.keyboard is None or self.paused.get(self.keyboard, True):
                raise RuntimeError("no active keyboard device")
            code, press = int(message["code"]), bool(message["press"])
            self.ei.ei_device_keyboard_key(self.keyboard, code, press)
            (self.held_keys.add if press else self.held_keys.discard)(code)
            self._frame(self.keyboard)
        elif cmd == "release_all":
            self.release_all()
        elif cmd == "state":
            pass
        elif cmd == "surface":
            if self.kwin_session is None:
                raise RuntimeError("surface identity requires the private KWin session")
            return {"surface": self.kwin_session.surface()}
        else:
            raise RuntimeError(f"unknown command {cmd!r}")

    def release_all(self) -> None:
        if self.keyboard is not None and not self.paused.get(self.keyboard, True):
            for code in sorted(self.held_keys):
                self.ei.ei_device_keyboard_key(self.keyboard, code, False)
            if self.held_keys:
                self._frame(self.keyboard)
        if self.pointer is not None and not self.paused.get(self.pointer, True):
            for button in sorted(self.held_buttons):
                self.ei.ei_device_button_button(self.pointer, button, False)
            if self.held_buttons:
                self._frame(self.pointer)
        self.held_keys.clear()
        self.held_buttons.clear()


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--kwin", action="store_true", help="ask the isolated session's KWin for an EIS socket")
    source.add_argument("--fd", type=int, help="an EIS socket inherited from a consent-gated portal session")
    parser.add_argument("--wait", type=float, default=8.0, help="seconds to wait for usable devices")
    parser.add_argument("--need", default="pointer_absolute,button,keyboard",
                        help="comma-separated capabilities that must be present before reporting ready")
    args = parser.parse_args()
    if args.kwin:
        _refuse_if_not_isolated()
    kwin_session = None
    try:
        # KWin's connectToEIS takes libei capability bits (POINTER|POINTER_ABSOLUTE|KEYBOARD|SCROLL|BUTTON), not the
        # portal's device-type bits (a mask of 3 would mean pointer-only here).
        if args.kwin:
            kwin_session = _KwinSession(int(os.environ.get("HUTCH_EIS_MASK", "55")))
            fd = kwin_session.fd
        else:
            fd = args.fd
        worker = Worker(fd, kwin_session)
        needed = {n.strip() for n in args.need.split(",") if n.strip()}
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline and not (worker.ready() and needed <= worker.caps_seen):
            worker.pump(0.1)
        if not (worker.ready() and needed <= worker.caps_seen):
            _out({"ready": False, "error": f"required input capabilities {sorted(needed)} did not all appear "
                                           f"(saw {sorted(worker.caps_seen)}, disconnected={worker.disconnected})"})
            return 3
    except SystemExit:
        raise
    except Exception as exc:
        _out({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 2
    _out({"ready": True, "regions": worker.regions, "capabilities": sorted(worker.caps_seen)})

    try:
        while True:
            readable, _, _ = select.select([sys.stdin, worker.ei.ei_get_fd(worker.ctx)], [], [], 0.2)
            if worker.ei.ei_get_fd(worker.ctx) in readable:
                worker.pump(0.0)
            if sys.stdin in readable:
                line = sys.stdin.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    _out({"ok": False, "error": "invalid JSON"})
                    continue
                if message.get("cmd") == "quit":
                    _out({"id": message.get("id"), "ok": True})
                    break
                try:
                    result = worker.execute(message) or {}
                    _out({"id": message.get("id"), "ok": True, "held_keys": len(worker.held_keys),
                          "held_buttons": len(worker.held_buttons), **result})
                except Exception as exc:
                    _out({"id": message.get("id"), "ok": False, "error": str(exc)})
    finally:
        try:
            worker.release_all()        # never leave a key or button down when the parent goes away
        except Exception:
            pass
        if kwin_session is not None:
            kwin_session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
