"""Parent-side client for the out-of-process EIS input worker (``eis_worker.py``).

Everything the native driver sends goes through here, so the guarantees live in one place: every command has a deadline,
a worker that stops answering is killed (not waited for), the keys and buttons *this* client pressed are released on
``release_all``/``close``, and a printable-ASCII typing helper refuses characters it cannot map rather than guessing.

Keyboard events are evdev *keycodes*; the compositor turns them into characters with the active keymap. This module maps ASCII
for a US layout and says so (``LAYOUT``); a different layout types different characters, which the driver's read-back
verification then reports as a mismatch instead of success.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional

LAYOUT = "us"
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 272, 273, 274
KEY_LEFTSHIFT, KEY_LEFTCTRL, KEY_LEFTALT = 42, 29, 56

_LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19,
                                                     31, 20, 22, 47, 17, 45, 21, 44)))
_DIGITS = dict(zip("1234567890", range(2, 12)))
_PLAIN = {**_LETTERS, **_DIGITS, " ": 57, "\n": 28, "\t": 15, "-": 12, "=": 13, "[": 26, "]": 27, "\\": 43, ";": 39,
          "'": 40, "`": 41, ",": 51, ".": 52, "/": 53}
_SHIFTED = {**{c.upper(): code for c, code in _LETTERS.items()},
            **dict(zip("!@#$%^&*()", range(2, 12))),
            "_": 12, "+": 13, "{": 26, "}": 27, "|": 43, ":": 39, '"': 40, "~": 41, "<": 51, ">": 52, "?": 53}
NAMED_KEYS = {"enter": 28, "return": 28, "tab": 15, "backspace": 14, "escape": 1, "esc": 1, "space": 57, "delete": 111,
              "home": 102, "end": 107, "up": 103, "down": 108, "left": 105, "right": 106, "pageup": 104, "pagedown": 109,
              **{f"f{n}": 58 + n - 1 for n in range(1, 11)}}
MODIFIERS = {"ctrl": KEY_LEFTCTRL, "control": KEY_LEFTCTRL, "shift": KEY_LEFTSHIFT, "alt": KEY_LEFTALT}


class InputError(Exception):
    """Input could not be delivered (or its delivery could not be confirmed); the message is safe to show."""


def find_gi_python() -> Optional[str]:
    """An interpreter that can pass D-Bus file descriptors (needs PyGObject); None if there is none."""
    for candidate in (os.environ.get("HUTCH_GI_PYTHON"), "/usr/bin/python3", sys.executable):
        if not candidate or not Path(candidate).exists():
            continue
        try:
            done = subprocess.run([candidate, "-c", "import gi; gi.require_version('Gio','2.0')"],
                                  capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            return candidate
    return None


def keycodes_for_text(text: str) -> list[tuple[int, bool]]:
    """``(keycode, needs_shift)`` per character, or ``InputError`` naming the first character that cannot be typed."""
    out: list[tuple[int, bool]] = []
    for char in text:
        if char in _PLAIN:
            out.append((_PLAIN[char], False))
        elif char in _SHIFTED:
            out.append((_SHIFTED[char], True))
        else:
            raise InputError(f"cannot type {char!r}: only printable ASCII is mapped (layout {LAYOUT}); "
                             "other text needs an input method or a semantic action")
    return out


class EisInput:
    """A running EIS worker. Use ``EisInput.start_in_isolated_session`` for a disposable compositor."""

    def __init__(self, process: subprocess.Popen, ready: Mapping[str, Any]):
        self._proc = process
        self.regions: list[list[int]] = [list(r) for r in ready.get("regions", [])]
        self.capabilities: list[str] = list(ready.get("capabilities", []))
        self._seq = 0

    # ----------------------------------------------------------- lifecycle

    @classmethod
    def start_in_isolated_session(cls, env: Mapping[str, str], *, python: Optional[str] = None,
                                  timeout: float = 15.0) -> "EisInput":
        interpreter = python or find_gi_python()
        if interpreter is None:
            raise InputError("no Python with PyGObject (gi) was found to acquire an EIS socket; install python-gobject "
                             "or set HUTCH_GI_PYTHON")
        worker = Path(__file__).with_name("eis_worker.py")
        full_env = {**dict(env), "HUTCH_ISOLATED_SESSION": "1", "PYTHONUNBUFFERED": "1"}
        process = subprocess.Popen([interpreter, "-u", str(worker), "--kwin"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=full_env, text=True,
                                   start_new_session=True)
        line = cls._readline(process, timeout)
        if line is None:
            cls._kill(process)
            raise InputError("the input worker did not report ready in time")
        try:
            ready = json.loads(line)
        except json.JSONDecodeError:
            cls._kill(process)
            raise InputError(f"the input worker sent an unreadable status: {line[:120]!r}") from None
        if not ready.get("ready"):
            cls._kill(process)
            raise InputError(f"input is unavailable: {ready.get('error', 'unknown reason')}")
        return cls(process, ready)

    @staticmethod
    def _readline(process: subprocess.Popen, timeout: float) -> Optional[str]:
        assert process.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None and not select.select([process.stdout], [], [], 0)[0]:
                return None
            if select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                return line or None
        return None

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, 15)
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, 9)
                except OSError:
                    pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def close(self) -> None:
        if self.alive:
            try:
                self._send({"cmd": "release_all"}, timeout=1.0)
                self._send({"cmd": "quit"}, timeout=1.0)
            except InputError:
                pass
        self._kill(self._proc)

    def emergency_kill(self) -> None:
        """Stop input *now* without a handshake (the worker releases held keys when its connection closes)."""
        self._kill(self._proc)

    # ------------------------------------------------------------ commands

    def _send(self, message: dict, *, timeout: float = 3.0) -> dict:
        if not self.alive or self._proc.stdin is None:
            raise InputError("the input worker is not running")
        self._seq += 1
        message = {**message, "id": self._seq}
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise InputError(f"could not reach the input worker: {exc}") from exc
        line = self._readline(self._proc, timeout)
        if line is None:
            self.emergency_kill()                  # an unanswered command is a hung driver: end it, never wait on it
            raise InputError("the input worker stopped answering and was ended; the outcome of the last input is unknown")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise InputError(str(reply.get("error", "input was refused")))
        return reply

    def pointer_to(self, x: float, y: float) -> None:
        self._send({"cmd": "pointer_abs", "x": float(x), "y": float(y)})

    def click(self, x: float, y: float, button: int = BTN_LEFT) -> None:
        self.pointer_to(x, y)
        self._send({"cmd": "button", "button": button, "press": True})
        self._send({"cmd": "button", "button": button, "press": False})

    def key(self, code: int, *, modifiers: tuple[int, ...] = ()) -> None:
        try:
            for mod in modifiers:
                self._send({"cmd": "key", "code": mod, "press": True})
            self._send({"cmd": "key", "code": code, "press": True})
            self._send({"cmd": "key", "code": code, "press": False})
        finally:
            for mod in reversed(modifiers):
                try:
                    self._send({"cmd": "key", "code": mod, "press": False})
                except InputError:
                    break

    def chord(self, spec: str) -> None:
        """``"ctrl+s"``, ``"enter"``, ``"ctrl+shift+a"``."""
        parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
        if not parts:
            raise InputError("empty key chord")
        *mods, last = parts
        unknown = [m for m in mods if m not in MODIFIERS]
        if unknown:
            raise InputError(f"unknown modifier {unknown[0]!r}")
        if last in NAMED_KEYS:
            code = NAMED_KEYS[last]
        elif len(last) == 1 and (last in _PLAIN):
            code = _PLAIN[last]
        else:
            raise InputError(f"unknown key {last!r}")
        self.key(code, modifiers=tuple(MODIFIERS[m] for m in mods))

    def type_text(self, text: str) -> None:
        mapped = keycodes_for_text(text)               # validate everything before sending anything
        for code, shift in mapped:
            self.key(code, modifiers=(KEY_LEFTSHIFT,) if shift else ())

    def release_all(self) -> None:
        self._send({"cmd": "release_all"})
