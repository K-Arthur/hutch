"""The governed transcribe_audio tool: refusals, approval, usage and honest failures."""

from __future__ import annotations

import httpx

from hutch.connections import ConnectionBook
from hutch.tools import ALL_TOOL_NAMES, GROUPS, expand_tools
from hutch.tools.transcribe import TranscribeAudioTool
from tests.support.audio import (OBSERVED_ASR_RESPONSE, add_xiaomi, install_fake_transport,
                                 make_ctx, no_xiaomi_env, wav_bytes)


def test_the_tool_is_registered_in_its_own_group():
    assert "transcribe_audio" in ALL_TOOL_NAMES
    assert GROUPS["audio"] == ["transcribe_audio"]
    assert expand_tools(["audio"]) == ["transcribe_audio"]


def test_a_path_outside_the_workspace_is_refused_before_any_route_lookup(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    ctx, gate = make_ctx(store, config, tmp_path)
    result = TranscribeAudioTool().run({"path": "../outside.wav"}, ctx)
    assert not result.ok and "workspace" in result.output
    assert gate.calls == []


def test_an_unsupported_container_is_refused_without_asking(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.ogg").write_bytes(b"OggS" + b"\x00" * 64)
    result = TranscribeAudioTool().run({"path": "note.ogg"}, ctx)
    assert not result.ok
    assert "not wav or mp3" in result.output
    assert gate.calls == []


def test_with_no_capable_connection_the_tool_says_so_instead_of_improvising(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    ConnectionBook(config.state_dir).add("openai-api", name="openai-work",
                                         api_key_env="TEST_OPENAI_KEY")
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav"}, ctx)
    assert not result.ok and "no configured connection offers transcription" in result.output
    assert gate.calls == []


def test_several_accounts_are_never_picked_silently(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    book = add_xiaomi(config, name="mimo-a")
    book.add("xiaomi-token-plan-sgp", name="mimo-b")
    book.set_key("mimo-b", "tp-other")
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav"}, ctx)
    assert not result.ok
    assert "mimo-a" in result.output and "mimo-b" in result.output
    assert "connection" in result.output
    assert gate.calls == []


def test_an_explicit_connection_resolves_the_ambiguity(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    book = add_xiaomi(config, name="mimo-a")
    book.add("xiaomi-token-plan-sgp", name="mimo-b")
    book.set_key("mimo-b", "tp-other")
    install_fake_transport(monkeypatch, lambda request: httpx.Response(
        200, json=OBSERVED_ASR_RESPONSE))
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav", "connection": "mimo-b"}, ctx)
    assert result.ok, result.output
    assert gate.calls[0]["detail"]["connection"] == "mimo-b"


def test_a_missing_key_names_the_variable_instead_of_failing_at_the_provider(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config, key=None)
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav"}, ctx)
    assert not result.ok
    assert "XIAOMI_TOKEN_PLAN_API_KEY" in result.output
    assert gate.calls == []


def test_the_approval_names_the_exact_destination_and_usage_reaches_the_ledger(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=OBSERVED_ASR_RESPONSE)

    install_fake_transport(monkeypatch, handler)
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())

    result = TranscribeAudioTool().run({"path": "note.wav", "language": "en"}, ctx)
    assert result.ok, result.output
    assert result.data["transcript"] == "Hutch audio check. One, two, three."
    assert result.data["model"] == "mimo-v2.5-asr"
    assert result.data["audio_seconds"] == 4.0
    assert len(seen) == 1

    assert len(gate.calls) == 1
    call = gate.calls[0]
    assert call["decision"].outward is True
    assert call["detail"]["connection"] == "mimo"
    assert call["detail"]["model"] == "mimo-v2.5-asr"
    assert call["detail"]["endpoint"].startswith("https://token-plan-sgp.xiaomimimo.com/")

    row = tuple(store._db.execute(
        "SELECT provider, model, prompt_tokens, completion_tokens, kind, account_id "
        "FROM usage WHERE run_id = ?", (ctx.run.id,)).fetchone())
    assert row == ("xiaomi", "mimo-v2.5-asr", 42, 15, "transcription", "mimo")
    assert (ctx.run.prompt_tokens, ctx.run.completion_tokens) == (42, 15)
    assert "42 prompt / 15 completion tokens" in result.output


def test_rehearsal_describes_the_call_and_sends_nothing(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)

    def handler(request):  # pragma: no cover - must never run
        raise AssertionError("rehearsal must not reach the network")

    install_fake_transport(monkeypatch, handler)
    ctx, gate = make_ctx(store, config, tmp_path)
    ctx.dry_run = True
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav"}, ctx)
    assert result.ok and result.data.get("simulated") is True
    assert "would transcribe note.wav" in result.output
    assert gate.calls == []


def test_a_provider_failure_is_returned_without_a_hidden_retry(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    attempts: list[httpx.Request] = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(500, json={"error": {"message": "upstream exploded"}})

    install_fake_transport(monkeypatch, handler)
    ctx, gate = make_ctx(store, config, tmp_path)
    (ctx.workspace / "note.wav").write_bytes(wav_bytes())
    result = TranscribeAudioTool().run({"path": "note.wav"}, ctx)
    assert not result.ok
    assert "transcription failed (server)" in result.output
    assert "did not retry" in result.output
    assert len(attempts) == 1
