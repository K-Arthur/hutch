"""Speech synthesis: the chat-completions audio route and its governed media path.

NO NETWORK. The adapter runs through ``httpx.MockTransport``; the tool path uses the real
``MediaJobService``, media store and SQLite ledger against a temporary state directory.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from hutch.connections import load_templates
from hutch.media.providers.base import VERIFICATION_TAG
from hutch.media.providers.speech import (MAX_TEXT_CHARS, SpeechBackend, SpeechError,
                                          build_payload, parse_speech_response,
                                          route_from_template, wav_duration)
from hutch.tools.media import CreateMediaTool
from tests.support.audio import (add_xiaomi, install_fake_transport, make_ctx,
                                 no_xiaomi_env, wav_bytes)

WAV = wav_bytes(samples=160)          # 0.02 s at the fixture's 8 kHz mono rate


def template(**overrides) -> dict:
    block = {"protocol": "chat-speech", "model": "mimo-v2.5-tts",
             "voices": ["mimo_default", "Chloe"], "format": "wav",
             "max_text_chars": 4000, "source": "https://example.test/tts"}
    block.update(overrides)
    return {"speech": block}


def tts_response(wav: bytes = WAV, **overrides) -> dict:
    body = {
        "id": "chatcmpl-tts",
        "choices": [{
            "finish_reason": "stop", "index": 0,
            "message": {"role": "assistant", "content": "",
                        "audio": {"id": "audio_1",
                                  "data": base64.b64encode(wav).decode(),
                                  "expires_at": None, "transcript": None}},
        }],
        "created": 1793472895,
        "model": "mimo-v2.5-tts",
        "object": "chat.completion",
        "usage": {"completion_tokens": 90, "prompt_tokens": 12, "total_tokens": 102,
                  "completion_tokens_details": {"audio_tokens": 90}},
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------- route


def test_the_route_reads_the_declared_block_and_its_defaults():
    route = route_from_template(template())
    assert route is not None
    assert route.model == "mimo-v2.5-tts"
    assert route.format == "wav"
    assert route.default_voice == "mimo_default"
    assert route.check_voice("") == "mimo_default"
    assert route.check_voice("Chloe") == "Chloe"


def test_a_connection_without_a_speech_block_offers_no_route():
    assert route_from_template({}) is None
    assert route_from_template(None) is None


@pytest.mark.parametrize("bad", [
    {"protocol": "openai-chat"},
    {"model": ""},
    {"format": "mp3"},
    {"voices": []},
    {"voices": [""]},
    {"max_text_chars": 0},
    {"max_text_chars": 99999},
    {"source": "http://not-https.test/tts"},
])
def test_a_malformed_speech_block_is_loud(bad):
    with pytest.raises(ValueError):
        route_from_template(template(**bad))


# ---------------------------------------------------------------- payload


def test_the_text_to_speak_goes_in_the_assistant_message_and_style_stays_separate():
    route = route_from_template(template())
    payload = build_payload(route, "  Good morning. ", voice="Chloe",
                            style="  warm,  unhurried ")
    assert payload["model"] == "mimo-v2.5-tts"
    assert payload["messages"] == [
        {"role": "user", "content": "warm, unhurried"},
        {"role": "assistant", "content": "Good morning."},
    ]
    assert payload["audio"] == {"format": "wav", "voice": "Chloe"}


def test_without_a_style_instruction_only_the_spoken_message_is_sent():
    route = route_from_template(template())
    payload = build_payload(route, "Hello")
    assert payload["messages"] == [{"role": "assistant", "content": "Hello"}]
    assert payload["audio"]["voice"] == "mimo_default"


def test_a_voice_the_route_does_not_offer_is_refused_before_a_request():
    route = route_from_template(template())
    with pytest.raises(SpeechError, match="not offered"):
        build_payload(route, "Hello", voice="SomebodyElse")


def test_text_above_the_declared_bound_is_refused_before_a_request():
    route = route_from_template(template(max_text_chars=10))
    with pytest.raises(SpeechError, match="at most 10"):
        build_payload(route, "x" * 11)
    assert MAX_TEXT_CHARS == 4000


def test_empty_text_is_refused_rather_than_synthesised_as_silence():
    route = route_from_template(template())
    with pytest.raises(SpeechError, match="no text"):
        build_payload(route, "   ")


# ---------------------------------------------------------------- parsing


def test_a_reply_without_audio_is_a_failure_not_silence():
    route = route_from_template(template())
    body = tts_response()
    body["choices"][0]["message"]["audio"] = None
    with pytest.raises(SpeechError, match="no audio"):
        parse_speech_response(body, route)


def test_empty_audio_data_is_a_failure_not_an_empty_success():
    route = route_from_template(template())
    body = tts_response()
    body["choices"][0]["message"]["audio"]["data"] = ""
    with pytest.raises(SpeechError, match="no audio data"):
        parse_speech_response(body, route)


def test_bytes_that_are_not_wav_are_refused_even_when_base64_is_valid():
    route = route_from_template(template())
    body = tts_response(wav=b"ID3" + b"\x00" * 64)
    with pytest.raises(SpeechError, match="not a wav"):
        parse_speech_response(body, route)


def test_invalid_base64_is_reported_as_such():
    route = route_from_template(template())
    body = tts_response()
    body["choices"][0]["message"]["audio"]["data"] = "not base64!!"
    with pytest.raises(SpeechError, match="base64"):
        parse_speech_response(body, route)


def test_usage_duration_and_model_substitution_are_reported_honestly():
    route = route_from_template(template())
    body = tts_response(model="mimo-v2.5-tts-2026-10")
    result = parse_speech_response(body, route)
    assert result.substituted_model is True
    assert any("mimo-v2.5-tts-2026-10" in note for note in result.notes)
    assert (result.prompt_tokens, result.completion_tokens, result.audio_tokens) == (12, 90, 90)
    assert result.duration_seconds == pytest.approx(0.02)


def test_a_length_finish_reason_says_the_audio_may_be_truncated():
    route = route_from_template(template())
    body = tts_response()
    body["choices"][0]["finish_reason"] = "length"
    result = parse_speech_response(body, route)
    assert any("truncated" in note for note in result.notes)


def test_wav_duration_returns_none_for_a_header_it_does_not_understand():
    assert wav_duration(b"RIFF" + b"\x00" * 8) is None
    assert wav_duration(b"not a riff file at all" * 4) is None


# ---------------------------------------------------------------- backend


def speech_backend(handler, *, connection="mimo", billing="subscription"):
    return SpeechBackend(
        connection=connection, base_url="http://unit.test/v1", api_key="tp-unit-key",
        route=route_from_template(template()), provider="xiaomi", billing=billing,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_backend_declares_audio_only_and_its_verification_status():
    backend = speech_backend(lambda request: httpx.Response(200, json=tts_response()))
    caps = backend.capabilities()
    assert caps["kinds"] == ["audio"]
    assert caps["output_formats"] == ["wav"]
    assert caps["verified"] == VERIFICATION_TAG
    assert caps["model"] == "mimo-v2.5-tts"
    assert caps["connection"] == "mimo"


def test_submit_sends_the_documented_request_and_keeps_the_bytes():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=tts_response())

    backend = speech_backend(handler)
    handle = backend.submit({"kind": "audio", "prompt": "Good morning.",
                             "voice": "Chloe", "style": "warm"})
    assert captured["url"] == "http://unit.test/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer tp-unit-key"
    assert captured["body"]["messages"][-1] == {"role": "assistant", "content": "Good morning."}
    assert captured["body"]["audio"] == {"format": "wav", "voice": "Chloe"}
    assert backend.poll({"upstream_job_id": handle})["status"] == "succeeded"
    assert backend.fetch({"upstream_job_id": handle}) == WAV
    assert backend.duration_seconds({"upstream_job_id": handle}) == pytest.approx(0.02)


def test_a_lost_process_reports_that_the_audio_was_never_stored():
    backend = speech_backend(lambda request: httpx.Response(200, json=tts_response()))
    state = backend.poll({"upstream_job_id": "speech-gone"})
    assert state["status"] == "failed"
    assert "may have billed" in state["error"]
    assert "does not regenerate" in state["error"]


def test_a_provider_error_message_reaches_the_job_failure():
    backend = speech_backend(lambda request: httpx.Response(
        402, json={"error": {"message": "insufficient credits"}}))
    with pytest.raises(SpeechError, match="insufficient credits"):
        backend.submit({"kind": "audio", "prompt": "Hello"})


# ---------------------------------------------------------------- tool path


def test_create_media_speaks_through_a_configured_connection(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config, name="mimo")
    install_fake_transport(monkeypatch, lambda request: httpx.Response(200, json=tts_response()))
    ctx, gate = make_ctx(store, config, tmp_path)

    result = CreateMediaTool().run(
        {"kind": "audio", "prompt": "Hutch speech check.", "voice": "Chloe",
         "style": "calm and clear"}, ctx)

    assert result.ok, result.output
    media = result.data["media"]
    assert media["mime"] == "audio/wav" and media["kind"] == "audio"
    assert media["backend"] == "speech:mimo"
    assert media["duration_seconds"] == pytest.approx(0.02)
    assert result.data["blocks"][0]["payload"]["mime"] == "audio/wav"

    detail = gate.calls[0]["detail"]
    assert gate.calls[0]["tool"] == "audio_synthesis"
    assert detail["connection"] == "mimo"
    assert detail["provider"] == "xiaomi"
    assert detail["endpoint"] == "https://token-plan-sgp.xiaomimimo.com/v1"
    assert detail["model"] == "mimo-v2.5-tts"
    assert detail["voice"] == "Chloe"
    assert detail["billing"] == "subscription"
    assert detail["text_chars"] == len("Hutch speech check.")

    row = store.get_media_job(result.data["job_id"])
    assert row["kind"] == "audio" and row["backend"] == "speech:mimo"
    usage = tuple(store._db.execute(
        "SELECT provider, model, prompt_tokens, completion_tokens, kind, account_id "
        "FROM usage WHERE run_id = ?", (ctx.run.id,)).fetchone())
    assert usage == ("xiaomi", "mimo-v2.5-tts", 12, 90, "speech", "mimo")
    assert (ctx.run.prompt_tokens, ctx.run.completion_tokens) == (12, 90)
    assert "12 prompt / 90 completion tokens" in result.output


def test_without_a_speech_connection_the_tool_refuses_instead_of_substituting(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "audio", "prompt": "Hello"}, ctx)
    assert not result.ok
    assert "no configured backend can produce 'audio'" in result.output
    assert gate.calls == []


def test_a_connection_without_a_key_does_not_become_a_speech_backend(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config, key=None)
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "audio", "prompt": "Hello"}, ctx)
    assert not result.ok
    assert "no configured backend" in result.output
    assert gate.calls == []


def test_an_unknown_voice_is_refused_before_approval_or_submission(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    install_fake_transport(monkeypatch, lambda request: httpx.Response(200, json=tts_response()))
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run(
        {"kind": "audio", "prompt": "Hello", "voice": "not-a-voice"}, ctx)
    assert not result.ok and "not offered" in result.output
    assert gate.calls == []


def test_the_approval_gate_denial_stops_the_spend(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=tts_response())

    install_fake_transport(monkeypatch, handler)
    ctx, gate = make_ctx(store, config, tmp_path)

    def deny(*args, **kwargs):
        raise PermissionError("the operator declined speech synthesis")

    ctx.gate.decide = deny
    result = CreateMediaTool().run({"kind": "audio", "prompt": "Hello"}, ctx)
    assert not result.ok and "declined" in result.output
    assert calls == []


def test_the_bundled_xiaomi_templates_declare_the_documented_tts_route():
    templates = load_templates()
    for name in ("xiaomi-token-plan-sgp", "xiaomi-token-plan-cn",
                 "xiaomi-token-plan-ams", "xiaomi"):
        route = route_from_template(templates[name])
        assert route is not None, name
        assert route.model == "mimo-v2.5-tts"
        assert route.format == "wav"
        assert "mimo_default" in route.voices
        assert route.source == "https://mimo.mi.com/static/docs/api/audio/tts.md"
