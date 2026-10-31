"""Shared fixtures for speech-to-text tests: real provider shape, tiny audio, a recording gate."""

from __future__ import annotations

import json
import struct

import httpx

from hutch.connections import ConnectionBook
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext

# The provider's own reply, trimmed only of the base64 audio field (this route returns text).
OBSERVED_ASR_RESPONSE = {
    "id": "e509a26bb743457e9f1572a97dc06986",
    "choices": [{
        "finish_reason": "stop",
        "index": 0,
        "message": {"content": "Hutch audio check. One, two, three.", "role": "assistant",
                    "audio": None, "tool_calls": None, "audio_tokens": []},
    }],
    "created": 1793472895,
    "model": "mimo-v2.5-asr",
    "object": "chat.completion",
    "usage": {
        "completion_tokens": 15,
        "prompt_tokens": 42,
        "total_tokens": 57,
        "completion_tokens_details": {"reasoning_tokens": 0},
        "prompt_tokens_details": {"audio_tokens": 21, "cached_tokens": 4},
        "seconds": 4,
    },
}


def observed_response(**overrides) -> dict:
    body = json.loads(json.dumps(OBSERVED_ASR_RESPONSE))
    body.update(overrides)
    return body


def wav_bytes(samples: int = 8) -> bytes:
    data = b"\x00\x00" * samples
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def mp3_bytes() -> bytes:
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" + b"\x00" * 64


class RecordingGate:
    """Records the policy decision a tool would have asked a person to make."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def decide(self, tool, action, detail, decision=None, **kwargs):
        self.calls.append({"tool": tool, "action": action, "detail": detail,
                           "decision": decision, **kwargs})


def make_ctx(store, config, tmp_path, *, model="xiaomi/mimo-v2.6-flash"):
    bot = Bot(name="audio-bot", model=model, tools=["transcribe_audio"],
              approval_mode=ApprovalMode.ask)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="transcribe", status=RunStatus.running)
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    gate = RecordingGate()
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(),
                      gate=gate, config=config, workspace=workspace)
    return ctx, gate


def add_xiaomi(config, name="mimo", key="tp-test-key"):
    book = ConnectionBook(config.state_dir)
    book.add("xiaomi-token-plan-sgp", name=name)
    if key is not None:
        book.set_key(name, key)
    return book


def install_fake_transport(monkeypatch, handler):
    """Route the adapter's real httpx client through a mock transport, keeping its headers."""
    monkeypatch.setattr(
        "hutch.offline.httpx_offline_options",
        lambda base_url, provider: (base_url, httpx.MockTransport(handler), False))


def no_xiaomi_env(monkeypatch):
    monkeypatch.delenv("XIAOMI_TOKEN_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("XIAOMI_API_KEY", raising=False)
