"""Observation frames reach a model only as real image input, per route, bounded, and never as a leaked reference.

These run the real BuiltinRuntime against wire-level fake provider servers and assert on the *actual request bodies*. They are
protocol-level evidence (the fakes follow each provider's documented schema); no hosted model or local weights were used.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest

from hutch.computer.frames import FrameStore
from hutch.models import EventType
from hutch.tools.base import Tool, ToolResult, _schema
from tests.fakes import FakeAnthropic, FakeOllama, FakeOpenAI
from tests.test_runtime_builtin import _fresh_providers, build, factory, run_it, runtime  # noqa: F401


def _png(width: int, height: int, fill: int) -> bytes:
    raw = b"".join(b"\x00" + bytes([fill]) * width for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


FRAMES = [_png(40, 30, 0x30), _png(40, 30, 0xC0), _png(40, 30, 0x70)]


class ObserveTool(Tool):
    name = "observe_fake"
    description = "Return a frame (test double for a computer-use observation)."
    parameters = _schema([], {})

    def __init__(self):
        self.calls = 0

    def run(self, args, ctx):
        store = FrameStore(ctx.config.run_dir(ctx.bot.name, ctx.run.id))
        ref = store.save(FRAMES[self.calls % len(FRAMES)], "image/png")
        self.calls += 1
        return ToolResult(True, f"observed frame {ref.frame_id}", {"images": [ref.internal()]})


def _tool_script(turns: int):
    """Call observe_fake ``turns`` times, then answer."""
    state = {"n": 0}

    def script(body):
        state["n"] += 1
        if state["n"] <= turns:
            return {"tool_calls": [{"name": "observe_fake", "arguments": {}}]}
        return {"content": "done"}
    return script


def _image_blocks(messages):
    blocks = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            blocks += [p for p in content if isinstance(p, dict) and p.get("type") == "image"]
    return blocks


def test_claude_receives_only_the_newest_frame_as_a_real_image_block(store, config, tmp_path):
    srv = FakeAnthropic()
    try:
        srv.script = _tool_script(2)
        ctx, run, emitted, tools = build(store, config, tmp_path, model="anthropic/claude-opus-5-5",
                                         observation_to_hosted=True)
        tools["observe_fake"] = ObserveTool()
        assert run_it(runtime(provider_factory=factory(claude=srv)), run, ctx, tools) == "done"

        bodies = [r["body"] for r in srv.of("/v1/messages")]
        assert len(bodies) == 3
        assert _image_blocks(bodies[0]["messages"]) == [], "no frame exists before the first observation"
        second = _image_blocks(bodies[1]["messages"])
        third = _image_blocks(bodies[2]["messages"])
        assert len(second) == 1 and len(third) == 1, "exactly one frame is ever in the request"
        assert second[0]["source"] == {"type": "base64", "media_type": "image/png",
                                       "data": base64.b64encode(FRAMES[0]).decode()}
        assert third[0]["source"]["data"] == base64.b64encode(FRAMES[1]).decode(), "the newest frame replaces the old"
        wire = json.dumps(bodies[2])
        assert "frames/f0000" not in wire and '"images"' not in wire, "internal references must not reach the provider"
        results = [b["content"] for m in bodies[2]["messages"] if isinstance(m.get("content"), list)
                   for b in m["content"] if b.get("type") == "tool_result"]
        assert any("superseded" in str(c) for c in results)
    finally:
        srv.close()


def test_tool_result_events_carry_public_frame_refs_without_paths(store, config, tmp_path):
    srv = FakeAnthropic()
    try:
        srv.script = _tool_script(1)
        ctx, run, emitted, tools = build(store, config, tmp_path, model="anthropic/claude-opus-5-5")
        tools["observe_fake"] = ObserveTool()
        run_it(runtime(provider_factory=factory(claude=srv)), run, ctx, tools)
        results = [e.data for e in emitted if e.type is EventType.tool_result and e.data.get("tool") == "observe_fake"]
        assert results and results[0]["frames"][0]["frame_id"] == "f000001"
        assert set(results[0]["frames"][0]) == {"frame_id", "sha256", "bytes", "media_type", "width", "height"}
    finally:
        srv.close()


@pytest.fixture()
def vision_ollama():
    server = FakeOllama({"vis:7b": {"caps": ["completion", "tools", "vision"]},
                         "text:7b": {"caps": ["completion", "tools"]}})
    yield server
    server.close()


def _ollama_script(turns: int):
    return _tool_script(turns)


def test_a_local_vision_model_gets_the_frame_in_ollamas_images_field(store, config, tmp_path, vision_ollama):
    vision_ollama.script = _ollama_script(1)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/vis:7b")
    tools["observe_fake"] = ObserveTool()
    assert run_it(runtime(provider_factory=factory(vision_ollama)), run, ctx, tools) == "done"
    chats = [c["body"] for c in vision_ollama.of("/api/chat")]
    last = chats[-1]["messages"]
    carriers = [m for m in last if m.get("images")]
    assert len(carriers) == 1 and carriers[0]["role"] == "user"
    assert carriers[0]["images"] == [base64.b64encode(FRAMES[0]).decode()]
    assert not any("images" in m for m in chats[0]["messages"])


def test_a_text_only_local_model_is_told_instead_of_being_sent_bytes(store, config, tmp_path, vision_ollama):
    vision_ollama.script = _ollama_script(1)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/text:7b")
    tools["observe_fake"] = ObserveTool()
    assert run_it(runtime(provider_factory=factory(vision_ollama)), run, ctx, tools) == "done"
    last = vision_ollama.of("/api/chat")[-1]["body"]["messages"]
    assert not any(m.get("images") for m in last)
    tool_text = [m["content"] for m in last if m["role"] == "tool"][-1]
    assert "cannot receive images" in tool_text and "observed frame f000001" in tool_text


def test_an_openai_compatible_route_never_receives_image_parts_or_internal_keys(store, config, tmp_path):
    srv = FakeOpenAI()
    try:
        srv.script = _tool_script(1)
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o")
        tools["observe_fake"] = ObserveTool()
        assert run_it(runtime(provider_factory=factory(oai=srv)), run, ctx, tools) == "done"
        wire = json.dumps([r["body"] for r in srv.requests if r["path"].endswith("/chat/completions")])
        assert "image_url" not in wire and '"images"' not in wire and "frames/" not in wire
        assert "cannot receive images" in wire
    finally:
        srv.close()


def test_a_hosted_route_receives_no_images_until_the_bot_owner_allows_it(store, config, tmp_path):
    srv = FakeAnthropic()
    try:
        srv.script = _tool_script(1)
        ctx, run, emitted, tools = build(store, config, tmp_path, model="anthropic/claude-opus-5-5")  # default: not allowed
        tools["observe_fake"] = ObserveTool()
        assert run_it(runtime(provider_factory=factory(claude=srv)), run, ctx, tools) == "done"
        bodies = [r["body"] for r in srv.of("/v1/messages")]
        assert all(_image_blocks(b["messages"]) == [] for b in bodies)
        wire = json.dumps(bodies[-1])
        assert "has not allowed sending screen or page images to a hosted model" in wire
        notes = [e.data for e in emitted if e.type is EventType.log and "observation images" in str(e.data.get("note", ""))]
        assert notes and "withheld_by_policy" in notes[0]["note"]
    finally:
        srv.close()
