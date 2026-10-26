"""Read-only KDE Connect adapter over the local user's D-Bus session.

This uses the published D-Bus interfaces, not KDE source code. It never pairs,
starts the daemon, changes plugins, or accesses phone messages/notifications.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


DEVICE_ID = re.compile(r"^[A-Za-z0-9_]{1,128}$")
SERVICE = "org.kde.kdeconnect"
DEVICE_INTERFACE = SERVICE + ".device"
BUSCTL = Path("/usr/bin/busctl")
MAX_BYTES = 32 * 1024


class KDEConnectError(ValueError):
    pass


def available() -> bool:
    return sys.platform == "linux" and BUSCTL.is_file() and os.access(BUSCTL, os.X_OK)


def validate_device(device_id):
    if not isinstance(device_id, str) or not DEVICE_ID.fullmatch(device_id):
        raise KDEConnectError("Invalid KDE Connect device reference")
    return device_id


def _call(arguments, *, deadline, cancelled):
    if not available():
        raise KDEConnectError("KDE Connect reads need Linux and /usr/bin/busctl")
    if cancelled():
        raise KDEConnectError("KDE Connect read cancelled")
    if time.monotonic() >= deadline:
        raise KDEConnectError("KDE Connect did not respond in time")
    # Do not pass provider credentials or interactive authorization to a child.
    env = {key: os.environ[key] for key in ("HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS") if key in os.environ}
    address = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    if address and (any(not part.startswith("unix:") for part in address.split(";")) or any(ord(c) < 32 for c in address)):
        raise KDEConnectError("KDE Connect requires a local Unix session bus")
    env["LANG"] = "C.UTF-8"
    command = [str(BUSCTL), "--user", "--no-pager", "--json=short", "--auto-start=no",
               "--allow-interactive-authorization=no", "--timeout=2", *arguments]
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL, env=env)
            try:
                while process.poll() is None:
                    if cancelled():
                        raise KDEConnectError("KDE Connect read cancelled")
                    if time.monotonic() >= deadline:
                        raise KDEConnectError("KDE Connect did not respond in time")
                    if os.fstat(output.fileno()).st_size > MAX_BYTES:
                        raise KDEConnectError("KDE Connect returned too much data")
                    time.sleep(.02)
                if process.returncode:
                    raise KDEConnectError("KDE Connect is unavailable. Open KDE Connect and check the device connection.")
                output.seek(0)
                raw = output.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise KDEConnectError("KDE Connect returned too much data")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
        return json.loads(raw)
    except (OSError, ValueError) as error:
        if isinstance(error, KDEConnectError):
            raise
        raise KDEConnectError("KDE Connect returned an unreadable response") from None


def _value(reply, signature):
    if not isinstance(reply, dict) or reply.get("type") != signature:
        raise KDEConnectError("Unexpected KDE Connect response type")
    data = reply.get("data")
    if not isinstance(data, list) or len(data) != 1:
        raise KDEConnectError("Unexpected KDE Connect response shape")
    value = data[0]
    expected = {"s": str, "b": bool, "i": int, "as": list}[signature]
    if type(value) is not expected:
        raise KDEConnectError("Unexpected KDE Connect value")
    return value


def _property(device_id, name, signature, deadline, cancelled, *, battery=False):
    path = "/modules/kdeconnect/devices/" + validate_device(device_id)
    interface = DEVICE_INTERFACE
    if battery:
        path += "/battery"
        interface += ".battery"
    return _value(_call(["get-property", SERVICE, path, interface, name], deadline=deadline, cancelled=cancelled), signature)


def device_status(device_id, *, cancelled=lambda: False, deadline=None):
    deadline = deadline or time.monotonic() + 8
    validate_device(device_id)
    if not _property(device_id, "isPaired", "b", deadline, cancelled):
        raise KDEConnectError("Device is no longer paired in KDE Connect; no phone data was read")
    name = _property(device_id, "name", "s", deadline, cancelled)
    name = "".join(c for c in name if c.isprintable())[:160]
    reachable = _property(device_id, "isReachable", "b", deadline, cancelled)
    result = {"device_id": device_id, "name": name, "paired": True, "reachable": reachable,
              "battery": None, "battery_status": "device_offline" if not reachable else "unavailable"}
    if reachable:
        try:
            has_battery = _property(device_id, "hasBattery", "b", deadline, cancelled, battery=True)
            if has_battery:
                charge = _property(device_id, "charge", "i", deadline, cancelled, battery=True)
                charging = _property(device_id, "isCharging", "b", deadline, cancelled, battery=True)
                if 0 <= charge <= 100:
                    result.update(battery={"percent": charge, "charging": charging}, battery_status="available")
            else:
                result["battery_status"] = "no_battery"
        except KDEConnectError:
            if cancelled() or time.monotonic() >= deadline:
                raise
            # Missing/disabled battery plugin is a useful partial status, never 0%.
    if cancelled():
        raise KDEConnectError("KDE Connect read cancelled")
    if not _property(device_id, "isPaired", "b", deadline, cancelled):
        raise KDEConnectError("Device was unpaired during this read; status was withheld")
    return result


def discover():
    deadline = time.monotonic() + 8
    ids = _value(_call(["call", SERVICE, "/modules/kdeconnect", SERVICE + ".daemon", "devices", "bb", "false", "true"],
                      deadline=deadline, cancelled=lambda: False), "as")
    if len(ids) > 32 or len(set(validate_device(item) for item in ids)) != len(ids):
        raise KDEConnectError("KDE Connect returned too many or duplicate devices")
    return [device_status(item, deadline=deadline) for item in ids]
