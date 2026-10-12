"""Bounded human step control for an owned surface in the built-in worker process.

HTTP/IPC threads never touch Playwright/native drivers. They fence ownership immediately and queue a maximum of four
commands for the owning worker. Human pixels and typed text stay out of model history, events and disk. A restart drops
the channel and all its authority. A private Linux pathname socket bridges normal process workers; there is no TCP
listener, public relay, video stream, clipboard, drag or held-key API.
"""
from __future__ import annotations

import hashlib
import math
import secrets
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import Future, TimeoutError
from typing import Any, Callable

from .control import ControlOwner, StaleControl
from .frames import image_size

LEASE_SECONDS = 15.0
FRAME_SECONDS = 10.0
MAX_FRAME_BYTES = 900_000
MAX_TEXT = 2000
COMMAND_SECONDS = 7.0
ACK_SECONDS = 8.0
KEYS = {"enter", "escape", "tab", "backspace", "delete", "left", "right", "up", "down", "home", "end",
        "ctrl+a", "ctrl+s", "ctrl+o", "ctrl+q", "ctrl+home", "ctrl+end", "shift+tab"}
_REGISTRY: dict[tuple[str, str, str], "HumanSession"] = {}
_REGISTRY_LOCK = threading.Lock()


class HumanError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def sessions(config, run_id: str, *, fence: int = 0) -> list:
    root = str(config.state_dir.resolve())
    with _REGISTRY_LOCK:
        local = [s for (r, run, _), s in _REGISTRY.items() if r == root and run == run_id]
    if local:
        return local
    from .transport import discover
    return discover(config, run_id, fence)


class HumanSession:
    def __init__(self, ctx, surface: str, lease, capture: Callable[[], tuple[bytes, dict]],
                 dispatch: Callable[[dict, dict, Callable[[], None]], None]):
        self.ctx, self.surface, self.lease = ctx, surface, lease
        self.capture, self.dispatch = capture, dispatch
        self._lock = threading.RLock()
        self._owner_thread = threading.get_ident()
        self._viewer = self._token = ""
        self._expires = 0.0
        self._frame: dict = {}
        self._png = b""
        self._queue: deque = deque()
        self._inflight = False
        self._results: OrderedDict = OrderedDict()
        self._last_sequence = 0
        self._last_command = 0.0
        self._authorized = lambda: True
        self._closed = threading.Event()
        self._bridge = None
        self._key = (str(ctx.config.state_dir.resolve()), ctx.run.id, surface)
        with _REGISTRY_LOCK:
            if self._key in _REGISTRY:
                raise HumanError("a human channel already owns this run surface")
            _REGISTRY[self._key] = self
        ctx.computer_sessions = getattr(ctx, "computer_sessions", []) + [self]
        if getattr(ctx, "gate", None) is not None:
            ctx.gate.computer_service = lambda: pump(ctx)
        ctx.on_finish.append(self.close)
        ctx.cancel_hooks.append(self.close)
        if getattr(ctx, "store", None) is not None:
            from .transport import WorkerBridge
            try:
                self._bridge = WorkerBridge(self)
            except Exception:
                self.close()
                raise HumanError("private worker channel could not start; step control is unavailable") from None
        self._watchdog = threading.Thread(target=self._watch, name="hutch-human-lease", daemon=True)
        self._watchdog.start()

    def _watch(self):
        while not self._closed.wait(1):
            with self._lock:
                if self._viewer and (time.monotonic() >= self._expires or not self._permission_valid()):
                    self._pause_locked("remote supervision was lost; explicitly take control again")

    def _permission_valid(self):
        if not self._authorized():
            return False
        store = getattr(self.ctx, "store", None)
        if store:
            bot, run = store.get_bot(self.ctx.bot.id), store.get_run(self.ctx.run.id)
            return bool(bot and run and bot.remote_computer_access == "control" and self.surface.replace("desktop", "computer") in bot.tools
                        and run.fence == self.ctx.run.fence and run.status.value in {"running", "waiting_human", "waiting_approval"})
        return True

    def _wake(self):
        store = getattr(self.ctx, "store", None)
        if store:
            store.bus.notify(f"human:{self.ctx.run.id}", remote=False)

    def _forget_locked(self):
        self._viewer = self._token = ""
        self._authorized = lambda: True
        self._frame, self._png = {}, b""
        self._results.clear()
        for _, _, future in self._queue:
            if not future.done():
                future.set_exception(HumanError("control changed; queued input was discarded"))
        self._queue.clear()

    def _pause_locked(self, reason):
        self.lease.pause(reason)
        self._forget_locked()
        self._wake()

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        if self._bridge is not None:
            self._bridge.close()
        with self._lock:
            # The tool's stop hook independently fences/kills the driver; closing transport must never hand back.
            if self.lease.snapshot().owner in (ControlOwner.agent, ControlOwner.human):
                self.lease.pause("human channel closed")
            self._forget_locked()
        with _REGISTRY_LOCK:
            if _REGISTRY.get(self._key) is self:
                _REGISTRY.pop(self._key, None)
        self._wake()

    def public(self) -> dict:
        with self._lock:
            return {"surface": self.surface, "session_id": self.lease.session_id,
                    "control": self.lease.snapshot().public(), "controller_present": bool(self._viewer),
                    "step_control": True, "lease_seconds": LEASE_SECONDS,
                    "frame": {k: v for k, v in self._frame.items() if k not in ("identity", "monotonic")}}

    def takeover(self, viewer: str, authorized=None, auth_session="") -> dict:
        with self._lock:
            if self._closed.is_set():
                raise HumanError("this session has ended", 410)
            if self._viewer and time.monotonic() < self._expires:
                raise HumanError("another viewer already controls this surface")
            self._forget_locked()
            if auth_session:
                expected = viewer.split(":")[1] if viewer.startswith("paired:") else ""
                self._authorized = lambda: bool((self.ctx.store.authenticate_session(auth_session) or {}).get("session_id") == expected)
            else:
                self._authorized = authorized or (lambda: True)
            if not self._permission_valid():
                raise HumanError("computer permission or authenticated session was revoked", 403)
            try:
                snap = self.lease.take_over("authenticated viewer took step control")
            except StaleControl as exc:
                raise HumanError(str(exc)) from None
            self._viewer, self._token = viewer, secrets.token_urlsafe(32)
            self._expires = time.monotonic() + LEASE_SECONDS
            self._last_sequence, self._last_command = 0, 0
            self._wake()
            return {**self.public(), "control_token": self._token, "generation": snap.generation}

    def _check_locked(self, viewer, token, generation):
        snap = self.lease.snapshot()
        if not self._permission_valid():
            self._pause_locked("computer permission or authenticated session was revoked")
            raise HumanError("computer permission or authenticated session was revoked", 403)
        if self._closed.is_set() or not self._viewer or time.monotonic() >= self._expires:
            raise HumanError("control expired; explicitly take control again")
        if viewer != self._viewer or not secrets.compare_digest(str(token), self._token):
            raise HumanError("this viewer does not own control", 403)
        if snap.owner is not ControlOwner.human or snap.generation != generation:
            raise HumanError("control generation changed; capture a fresh frame")

    def command(self, viewer: str, body: dict) -> dict:
        """Authenticate before deduplication; IDs are monotonic within one ephemeral control token."""
        token, generation = body.get("control_token", ""), body.get("generation")
        action = body.get("action")
        with self._lock:
            self._check_locked(viewer, token, generation)
            if action == "heartbeat":
                self._expires = time.monotonic() + LEASE_SECONDS
                return self.public()
            if action == "pause":
                self._pause_locked("viewer paused step control")
                return self.public()
            if action == "resume":
                if self._queue or self._inflight:
                    raise HumanError("an input is still pending; inspect its result before handing back")
                self.lease.hand_back("viewer explicitly handed control back")
                self._forget_locked()
                store = getattr(self.ctx, "store", None)
                if store:
                    store.resume_run(self.ctx.run.id)
                self._wake()
                return self.public()
            if action not in {"capture", "click", "type", "key"}:
                raise HumanError("unsupported human command", 422)
            sequence = body.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                raise HumanError("a positive command sequence is required", 422)
            material = {k: body.get(k) for k in ("action", "frame_id", "x", "y", "text", "keys")}
            import json
            digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
            previous = self._results.get(sequence)
            if previous:
                if previous[0] != digest:
                    raise HumanError("this sequence was already used for a different command")
                future = previous[1]
            else:
                if sequence <= self._last_sequence:
                    raise HumanError("old or out-of-order command; nothing was replayed")
                if time.monotonic() - self._last_command < 0.2:
                    raise HumanError("step-control rate exceeded; wait before another command", 429)
                if len(self._queue) >= 4:
                    raise HumanError("input queue is full", 429)
                if action == "type" and (not isinstance(body.get("text"), str) or not 0 < len(body["text"]) <= MAX_TEXT):
                    raise HumanError(f"type requires 1–{MAX_TEXT} characters", 422)
                if action == "key" and body.get("keys", "").lower() not in KEYS:
                    raise HumanError("this key or chord is not supported", 422)
                future = Future()
                self._results[sequence] = (digest, future)
                while len(self._results) > 32:
                    self._results.popitem(last=False)
                self._last_sequence, self._last_command = sequence, time.monotonic()
                queued = dict(body)
                queued["_deadline"] = time.monotonic() + COMMAND_SECONDS
                self._queue.append((queued, viewer, future))
                self._wake()
        try:
            return future.result(timeout=ACK_SECONDS)
        except TimeoutError:
            # An unstarted command must never arrive after its HTTP caller has given up. In-flight input can have
            # reached the app: retain its sequence for reconciliation, never assume failure or replay it.
            with self._lock:
                for queued in list(self._queue):
                    if queued[2] is future:
                        self._queue.remove(queued)
                        queued[0].clear()
                        future.set_exception(HumanError("command expired before dispatch; no input was sent", 504))
                        break
            raise HumanError("worker has not acknowledged this command; inspect before retrying", 504) from None

    def pixels(self, viewer: str, token: str, generation: int, frame_id: str) -> bytes:
        with self._lock:
            self._check_locked(viewer, token, generation)
            if not self._png or self._frame.get("frame_id") != frame_id:
                raise HumanError("this human frame is no longer available", 404)
            return self._png

    def pump(self):
        """Called only by the surface's owning worker while automation is fenced."""
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("human commands must run on the driver owner thread")
        while True:
            with self._lock:
                if not self._queue:
                    return
                body, viewer, future = self._queue.popleft()
                self._inflight = True
            try:
                dispatched = False
                def check():
                    with self._lock:
                        self._check_locked(viewer, body.get("control_token"), body.get("generation"))
                        if time.monotonic() >= body["_deadline"]:
                            raise HumanError("command deadline passed; inspect before sending further input", 504)
                check()
                with self._lock:
                    before = dict(self._frame)
                if body["action"] != "capture":
                    if not before or before["frame_id"] != body.get("frame_id") or time.monotonic() - before["monotonic"] > FRAME_SECONDS:
                        raise HumanError("a fresh human frame is required before input")
                    if body["action"] == "click":
                        x, y = body.get("x"), body.get("y")
                        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)) or not (0 <= x < before["width"] and 0 <= y < before["height"]):
                            raise HumanError("coordinates are outside the captured image", 422)
                    self.dispatch(body, before["identity"], check)
                    dispatched = True
                    time.sleep(0.15)
                check()
                png, identity = self.capture()
                if len(png) > MAX_FRAME_BYTES:
                    raise HumanError("the human frame exceeds the capture budget")
                width, height = image_size(png, "image/png")
                if max(width, height) > 2000:
                    raise HumanError("the human frame exceeds the resolution budget")
                check()
                with self._lock:
                    self._frame = {"frame_id": "h" + secrets.token_hex(8), "width": width, "height": height,
                                   "identity": identity, "monotonic": time.monotonic(),
                                   "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    self._png = png
                    answer = {**self.public(), "outcome": "captured" if body["action"] == "capture" else "dispatched",
                              "sequence": body["sequence"]}
                if not future.done():
                    future.set_result(answer)
            except Exception as exc:
                # Do not expose driver errors which may contain an entered value or host path.
                error = (HumanError("Input was dispatched, but its follow-up capture failed; inspect before sending more input.")
                         if dispatched else exc if isinstance(exc, HumanError)
                         else HumanError("input/capture failed; inspect before retrying"))
                with self._lock:
                    self._frame, self._png = {}, b""
                if not future.done():
                    future.set_exception(error)
            finally:
                body.clear()  # typed input is ephemeral and never part of a result, event or model observation
                with self._lock:
                    self._inflight = False


def pump(ctx):
    for session in getattr(ctx, "computer_sessions", []):
        session.pump()


def plan_fence(ctx) -> dict[str, int]:
    return {lease.session_id: lease.snapshot().generation for lease in getattr(ctx, "computer_leases", [])}


def plan_changed(ctx, fence: dict[str, int]) -> bool:
    # Include newly opened surfaces: their initial generation is 1. A complete takeover/handback during an inference
    # or a tool call still invalidates the old plan, even though the owner has already returned to "agent".
    return any(lease.snapshot().generation != fence.get(lease.session_id, 1)
               for lease in getattr(ctx, "computer_leases", []))


def service(ctx) -> bool:
    """Suspend the planner while any surface is human-owned or paused; discard its old plan on return."""
    changed = False
    for session in getattr(ctx, "computer_sessions", []):
        if session.lease.snapshot().owner in (ControlOwner.human, ControlOwner.paused):
            changed = True
            ctx.gate.wait_for_human("A viewer is supervising the computer session.",
                                    handoff="Operate the private preview, then explicitly hand control back.",
                                    service=lambda: pump(ctx))
            if session.lease.snapshot().owner is not ControlOwner.agent:
                raise HumanError("control must be explicitly handed back through the computer panel")
    return changed
