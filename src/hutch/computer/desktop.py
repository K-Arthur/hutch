"""Native desktop driver: validated, typed commands with the same authority and observation contract as the browser.

The driver executes commands; it is not a second agent. It owns no policy: approvals live in the tool that calls it. What it
guarantees on its own:

* an action carries a ``Ticket`` from the control lease and re-checks it immediately before input is dispatched, so a
  takeover or stop that wins the race wins;
* pointer and keyboard input are only accepted against the *latest* frame (id match) and inside it (never clamped);
* every state-changing action is followed by a fresh frame, which also re-arms the observation for the next action;
* outcomes are ``dispatched`` (+ whether the screen visibly changed), ``not_dispatched`` or ``unknown`` (the input channel
  failed mid-action). A driver return is never reported as an effect: callers must verify state, e.g. a saved file.

Capture and input are injected so the same logic runs against the disposable KWin session in tests and, later, a
consent-gated portal session.
"""

from __future__ import annotations

import datetime
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from .control import ControlLease, StaleControl
from .frames import FrameError, FrameStore, ImageRef

MAX_TYPED_CHARS = 2000


class InputBackend(Protocol):
    def click(self, x: float, y: float, button: int = ...) -> None: ...
    def pointer_to(self, x: float, y: float) -> None: ...
    def type_text(self, text: str) -> None: ...
    def chord(self, spec: str) -> None: ...
    def release_all(self) -> None: ...
    def emergency_kill(self) -> None: ...


@dataclass
class DesktopResult:
    ok: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    image: Optional[ImageRef] = None


class DesktopSession:
    def __init__(self, *, session_id: str, capture: Callable[[], bytes], input_backend: InputBackend,
                 frames: FrameStore, lease: ControlLease, environment: Optional[dict[str, Any]] = None,
                 settle_seconds: float = 0.25, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, surface_identity: Optional[Callable[[], dict]] = None):
        self.session_id = session_id
        self._capture = capture
        self._input = input_backend
        self._frames = frames
        self.lease = lease
        self._environment = environment or {}
        self._settle = settle_seconds
        self._sleep = sleep
        self._clock = clock
        self._surface_identity = surface_identity
        self._identity = None
        self._last: dict[str, Any] = {}
        #: called right before input is dispatched (after the control check); a returned string refuses the action.
        #: The tool uses it to record the action's intent/receipt (ADR-0003).
        self.before_dispatch: Optional[Callable[[], Optional[str]]] = None

    # ----------------------------------------------------------- observation

    def observe(self) -> DesktopResult:
        try:
            for capture_attempt in range(1, 4):
                identity = self._surface_identity() if self._surface_identity else None
                png = self._capture()
                if not self._surface_identity or identity == self._surface_identity():
                    break
                if capture_attempt == 3:
                    raise FrameError("window focus/stacking/geometry changed during capture; observe again")
                self._sleep(.1)  # bounded observation-only settling; input is never retried
        except Exception as exc:
            self.lease.invalidate_observation("capture failed")
            return DesktopResult(False, f"error: the screen could not be captured ({exc}); nothing was done",
                                 {"observation": {"schema": 1, "status": "unavailable", "status_reason": str(exc)[:200]}})
        try:
            ref = self._frames.save(png, "image/png")
        except FrameError as exc:
            self.lease.invalidate_observation("frame rejected")
            return DesktopResult(False, f"error: the capture could not be kept as a frame ({exc})",
                                 {"observation": {"schema": 1, "status": "unavailable", "status_reason": str(exc)[:200]}})
        self._last = {"frame_id": ref.frame_id, "width": ref.width, "height": ref.height, "sha256": ref.sha256}
        self._identity = identity
        self.lease.note_observation(ref.frame_id)
        record = {
            "schema": 1,
            "capture_attempts": capture_attempt,
            "surface": {"kind": "desktop_screen", "id": "screen-0"},
            "frame_id": ref.frame_id,
            "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
            "monotonic_ms": round(self._clock() * 1000.0, 1),
            "screen": {"width": ref.width, "height": ref.height, "scale": 1.0, "origin": [0, 0]},
            "image": ref.public(),
            "transform": {"scale": 1.0, "crop": None},
            "status": "fresh", "status_reason": "",
            "environment": self._environment,
        }
        return DesktopResult(True, f"observed the desktop: frame {ref.frame_id} {ref.width}x{ref.height}",
                             {"observation": record, "images": [ref.internal()]}, ref)

    # ------------------------------------------------------------- validation

    def _authorize(self, frame_id: str, x: Optional[float] = None, y: Optional[float] = None):
        frame_id = str(frame_id or "").strip()
        if not self._last or self._last.get("frame_id") != frame_id:
            raise _Refusal(f"frame {frame_id or '(none given)'} is not the latest observation "
                           f"({self._last.get('frame_id') or 'none yet'}); observe and use the new frame_id")
        if x is not None:
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                raise _Refusal("x and y must be numbers (pixels of the frame image)") from None
            if not (math.isfinite(x) and math.isfinite(y)):
                raise _Refusal("x and y must be finite numbers")
            width, height = self._last["width"], self._last["height"]
            if not (0 <= x < width and 0 <= y < height):
                raise _Refusal(f"({x:g}, {y:g}) is outside the {width}x{height} frame; coordinates are never clamped")
        try:
            return self.lease.begin_action(needs_fresh_observation=True), x, y
        except StaleControl as exc:
            raise _Refusal(exc.reason, control=True) from None

    def _dispatch(self, ticket, action: Callable[[], None], summary: str, before: dict) -> DesktopResult:
        try:
            self.lease.check(ticket, needs_fresh_observation=True)
        except StaleControl as exc:
            return DesktopResult(False, f"error: {exc.reason}",
                                 {"outcome": "not_dispatched", "dispatched": False,
                                  "control": self.lease.snapshot().public()})
        if self.before_dispatch is not None:
            refusal = self.before_dispatch()
            if refusal:
                return DesktopResult(False, f"error: {refusal}", {"outcome": "not_dispatched", "dispatched": False})
            try:                              # the intent was recorded after the first check; confirm authority still holds
                self.lease.check(ticket, needs_fresh_observation=True)
            except StaleControl as exc:
                return DesktopResult(False, f"error: {exc.reason}",
                                     {"outcome": "not_dispatched", "dispatched": False,
                                      "control": self.lease.snapshot().public()})
        if self._surface_identity is not None:
            try:
                current = self._surface_identity()
                if current != self._identity:
                    raise FrameError("window focus/stacking/geometry changed after observation; observe again")
                self.lease.check(ticket, needs_fresh_observation=True)
            except Exception as exc:
                self.lease.invalidate_observation("surface identity changed or unavailable")
                return DesktopResult(False, f"error: {exc}; nothing was done",
                                     {"outcome": "not_dispatched", "dispatched": False, "identity_changed": True})
        old_check = getattr(self._input, "before_input", None)
        sent_before = getattr(self._input, "input_count", None)
        self._input.before_input = lambda: self.lease.check(ticket, needs_fresh_observation=True)
        try:
            action()
        except Exception as exc:
            text = str(exc)
            unknown = (sent_before is None or getattr(self._input, "input_count", None) != sent_before or
                       "stopped answering" in text or "not running" in text or "unknown" in text)
            self.lease.invalidate_observation("input failed")
            return DesktopResult(
                False, f"error: {text}", {"outcome": "unknown" if unknown else "not_dispatched",
                                          "dispatched": bool(unknown)})
        finally:
            self._input.before_input = old_check
        self.lease.invalidate_observation("input was sent")
        self._sleep(self._settle)
        after = self.observe()
        changed = bool(after.ok and after.image is not None and after.image.sha256 != before.get("sha256"))
        data = {"outcome": "dispatched", "dispatched": True, "visual_change": changed,
                "verification": "visual_change_only: confirm the intended state (for example a saved file) before "
                                "relying on it"}
        data.update({k: v for k, v in after.data.items() if k in ("observation", "images")})
        suffix = "the screen changed" if changed else "the screen did not visibly change"
        if not after.ok:
            return DesktopResult(True, f"{summary}; the follow-up capture failed: {after.output}", data)
        return DesktopResult(True, f"{summary}; {suffix}; new frame {after.image.frame_id}", data, after.image)

    # ---------------------------------------------------------------- actions

    def click(self, frame_id: str, x: float, y: float, *, button: str = "left", count: int = 1) -> DesktopResult:
        codes = {"left": 272, "right": 273, "middle": 274}
        try:
            ticket, x, y = self._authorize(frame_id, x, y)
        except _Refusal as refusal:
            return refusal.result()
        if button not in codes or count not in (1, 2):
            return DesktopResult(False, "error: button must be left/right/middle and count 1 or 2; nothing was done",
                                 {"outcome": "not_dispatched", "dispatched": False})
        before = dict(self._last)

        def act() -> None:
            for _ in range(count):
                self._input.click(x, y, codes[button])

        return self._dispatch(ticket, act, f"{button}-clicked at ({x:g}, {y:g})" + (" twice" if count == 2 else ""),
                              before)

    def type_text(self, frame_id: str, text: str) -> DesktopResult:
        if not isinstance(text, str) or not text:
            return DesktopResult(False, "error: text is required; nothing was typed",
                                 {"outcome": "not_dispatched", "dispatched": False})
        if len(text) > MAX_TYPED_CHARS:
            return DesktopResult(False, f"error: at most {MAX_TYPED_CHARS} characters per call; nothing was typed",
                                 {"outcome": "not_dispatched", "dispatched": False})
        try:
            ticket, _, _ = self._authorize(frame_id)
        except _Refusal as refusal:
            return refusal.result()
        before = dict(self._last)
        return self._dispatch(ticket, lambda: self._input.type_text(text), f"typed {len(text)} characters", before)

    def key(self, frame_id: str, chord: str) -> DesktopResult:
        try:
            ticket, _, _ = self._authorize(frame_id)
        except _Refusal as refusal:
            return refusal.result()
        before = dict(self._last)
        return self._dispatch(ticket, lambda: self._input.chord(str(chord)), f"pressed {chord}", before)

    # -------------------------------------------------------------- lifecycle

    def release_all(self) -> None:
        try:
            self._input.release_all()
        except Exception:
            pass

    def stop(self) -> int:
        """Fence first, then end the input channel. Returns the number of things that could not be confirmed ended."""
        self.lease.request_stop("stop requested")
        survivors = 0
        try:
            self._input.emergency_kill()
        except Exception:
            survivors += 1
        self.lease.confirm_stopped(survivors)
        return survivors


class _Refusal(Exception):
    def __init__(self, message: str, *, control: bool = False):
        super().__init__(message)
        self.message = message
        self.control = control

    def result(self) -> DesktopResult:
        return DesktopResult(False, f"error: {self.message}; nothing was done",
                             {"outcome": "not_dispatched", "dispatched": False})
