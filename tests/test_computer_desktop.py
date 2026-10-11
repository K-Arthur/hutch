"""Native desktop driver contract with fake capture/input: validation, fencing, outcomes (deterministic)."""

from __future__ import annotations

import struct
import zlib

import pytest

from hutch.computer.control import ControlLease, ControlOwner, StaleControl
from hutch.computer.desktop import DesktopSession
from hutch.computer.frames import FrameStore


def png(width: int, height: int, fill: int) -> bytes:
    raw = b"".join(b"\x00" + bytes([fill]) * width for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeInput:
    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_with: Exception | None = None
        self.killed = False

    def _do(self, *call):
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append(call)

    def click(self, x, y, button=272):
        self._do("click", x, y, button)

    def pointer_to(self, x, y):
        self._do("pointer", x, y)

    def type_text(self, text):
        self._do("type", text)

    def chord(self, spec):
        self._do("chord", spec)

    def release_all(self):
        self.calls.append(("release_all",))

    def emergency_kill(self):
        self.killed = True


def make(tmp_path, frames=(10, 10, 20, 20, 30), size=(200, 100)):
    shots = list(frames)
    seen = []

    def capture():
        fill = shots.pop(0) if len(shots) > 1 else shots[0]
        seen.append(fill)
        return png(size[0], size[1], fill)

    backend = FakeInput()
    session = DesktopSession(session_id="s", capture=capture, input_backend=backend,
                             frames=FrameStore(tmp_path / "run"), lease=ControlLease("s"), settle_seconds=0,
                             sleep=lambda s: None, environment={"mode": "isolated"})
    return session, backend, seen


def test_observe_stores_a_frame_and_describes_the_screen(tmp_path):
    session, _, _ = make(tmp_path)
    result = session.observe()
    assert result.ok and result.image.frame_id == "f000001"
    record = result.data["observation"]
    assert record["screen"] == {"width": 200, "height": 100, "scale": 1.0, "origin": [0, 0]}
    assert record["status"] == "fresh" and record["environment"] == {"mode": "isolated"}
    assert result.data["images"][0]["frame_id"] == "f000001"


def test_input_before_any_observation_is_refused(tmp_path):
    session, backend, _ = make(tmp_path)
    for result in (session.click("f000001", 5, 5), session.type_text("f000001", "x"), session.key("f000001", "enter")):
        assert not result.ok and result.data["outcome"] == "not_dispatched"
    assert backend.calls == []


def test_stale_frame_ids_and_bad_coordinates_are_refused_without_input(tmp_path):
    session, backend, _ = make(tmp_path)
    first = session.observe().image.frame_id
    second = session.observe().image.frame_id
    assert second != first
    assert not session.click(first, 5, 5).ok                       # an older frame
    for x, y in ((200, 5), (5, 100), (-1, 5), (float("nan"), 5), ("a", 1)):
        refused = session.click(second, x, y)
        assert not refused.ok and refused.data["dispatched"] is False, (x, y)
    assert backend.calls == [], "nothing may reach the input channel for a refused action"


def test_a_click_dispatches_once_then_returns_a_fresh_frame_and_reports_visual_change(tmp_path):
    session, backend, _ = make(tmp_path, frames=(10, 20))
    frame = session.observe().image.frame_id
    result = session.click(frame, 40, 30)
    assert result.ok and backend.calls == [("click", 40.0, 30.0, 272)]
    assert result.data["outcome"] == "dispatched" and result.data["visual_change"] is True
    assert result.image.frame_id != frame and "verification" in result.data
    # the follow-up frame re-armed observation: the next action may use it, the old frame may not
    assert session.click(frame, 1, 1).ok is False
    assert session.type_text(result.image.frame_id, "hello").ok


def test_an_unchanged_screen_is_reported_as_unchanged_not_as_success(tmp_path):
    session, _, _ = make(tmp_path, frames=(10, 10))
    frame = session.observe().image.frame_id
    result = session.click(frame, 40, 30)
    assert result.ok and result.data["visual_change"] is False and "did not visibly change" in result.output


def test_a_takeover_between_validation_and_dispatch_prevents_input(tmp_path):
    session, backend, _ = make(tmp_path)
    frame = session.observe().image.frame_id
    original = session.lease.check

    def check_after_takeover(ticket, **kw):
        session.lease.take_over("a person grabbed the desktop")
        return original(ticket, **kw)

    session.lease.check = check_after_takeover
    result = session.click(frame, 10, 10)
    assert not result.ok and result.data["outcome"] == "not_dispatched" and backend.calls == []
    assert result.data["control"]["owner"] == "human"


def test_a_failed_input_channel_is_reported_unknown_and_invalidates_the_frame(tmp_path):
    session, backend, _ = make(tmp_path)
    frame = session.observe().image.frame_id
    backend.fail_with = RuntimeError("the input worker stopped answering and was ended; the outcome of the last input is unknown")
    result = session.type_text(frame, "abc")
    assert not result.ok and result.data["outcome"] == "unknown"
    backend.fail_with = None
    assert not session.type_text(frame, "abc").ok               # must observe again before more input
    assert session.observe().ok


def test_stop_fences_then_kills_input_and_nothing_more_runs(tmp_path):
    session, backend, _ = make(tmp_path)
    frame = session.observe().image.frame_id
    assert session.stop() == 0
    assert backend.killed and session.lease.snapshot().owner is ControlOwner.stopped
    assert not session.click(frame, 5, 5).ok and backend.calls == []


def test_long_or_empty_text_is_refused(tmp_path):
    session, backend, _ = make(tmp_path)
    frame = session.observe().image.frame_id
    assert not session.type_text(frame, "").ok
    assert not session.type_text(frame, "x" * 2001).ok
    assert backend.calls == []


def test_capture_failure_is_reported_and_blocks_coordinate_use(tmp_path):
    def broken():
        raise RuntimeError("compositor gone")
    session = DesktopSession(session_id="s", capture=broken, input_backend=FakeInput(),
                             frames=FrameStore(tmp_path / "r"), lease=ControlLease("s"), settle_seconds=0,
                             sleep=lambda s: None)
    result = session.observe()
    assert not result.ok and result.data["observation"]["status"] == "unavailable"
    assert not session.click("f000001", 1, 1).ok


def test_strict_offline_withholds_the_computer_tool(store, config, tmp_path):
    from hutch.models import Bot, InferenceMode, Run, RunStatus
    from hutch.tools import build_tools
    from tests.test_tools import make_ctx
    bot = Bot(name="offline-desk", tools=["files", "computer", "browser"], inference_mode=InferenceMode.offline,
              computer_apps=["kwrite"])
    ctx = make_ctx(store, config, tmp_path, bot=bot)
    tools = build_tools(bot.tools, ctx)
    assert "computer" not in tools and "browser" not in tools and "read_file" in tools
    online = Bot(name="online-desk", tools=["computer"], computer_apps=["kwrite"])
    (tmp_path / "o").mkdir()
    assert "computer" in build_tools(online.tools, make_ctx(store, config, tmp_path / "o", bot=online))


def test_typed_text_and_keys_are_recorded_without_the_text():
    from hutch.tools.computer import ComputerTool
    tool = ComputerTool()
    recorded = tool.recorded_arguments({"action": "type", "frame_id": "f000003", "text": "SENTINEL-SECRET-123"}, None)
    assert recorded == {"action": "type", "frame_id": "f000003", "text": "[redacted]", "text_chars": 19}
    assert "SENTINEL" not in str(recorded)
    assert tool.recorded_arguments({"action": "click", "frame_id": "f000003", "x": 5, "y": 6}, None) == {
        "action": "click", "frame_id": "f000003", "x": 5, "y": 6}
    assert tool.effect({"action": "observe"}, None) == "" and tool.effect({"action": "type"}, None) == "process"
