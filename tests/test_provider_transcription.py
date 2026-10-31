"""Speech-to-text route declaration, wire contract, parsing and refusal rules.

The response body used here is the shape a live MiMo-V2.5-ASR call returned on 2026-10-31
(recorded in docs/research/2026-10-provider-platform/06-VALIDATION-LEDGER.md).
"""

from __future__ import annotations

import json

import httpx
import pytest

from hutch.connections import load_templates
from hutch.providers.base import ProviderError
from hutch.providers.transcription import (MAX_AUDIO_BASE64_BYTES, ChatAudioTranscriber,
                                           build_payload, encoded_size, parse_transcription_response,
                                           route_from_template, sniff_audio)
from tests.support.audio import (OBSERVED_ASR_RESPONSE, install_fake_transport, mp3_bytes,
                                 observed_response, wav_bytes)


def route(**overrides):
    block = {"protocol": "chat-audio", "model": "mimo-v2.5-asr"}
    block.update(overrides)
    return route_from_template({"transcription": block})


# ------------------------------------------------------------------ route data


def test_the_bundled_xiaomi_route_parses_and_is_shared_by_every_xiaomi_template():
    templates = load_templates()
    xiaomi = {name: row for name, row in templates.items() if row.get("provider") == "xiaomi"}
    assert len(xiaomi) == 4
    routes = {name: route_from_template(row) for name, row in xiaomi.items()}
    assert all(item is not None for item in routes.values())
    first = next(iter(routes.values()))
    for item in routes.values():
        assert item == first
    assert first.model == "mimo-v2.5-asr"
    assert first.languages == ("auto", "zh", "en")
    assert first.max_audio_base64_bytes == 10 * 1024 * 1024
    assert first.source.startswith("https://mimo.mi.com/")


@pytest.mark.parametrize("block", [
    {"protocol": "openai-audio"},
    {"protocol": "chat-audio", "model": ""},
    {"protocol": "chat-audio", "model": "m", "languages": []},
    {"protocol": "chat-audio", "model": "m", "languages": [""]},
    {"protocol": "chat-audio", "model": "m", "max_audio_base64_bytes": 0},
    {"protocol": "chat-audio", "model": "m", "max_audio_base64_bytes": True},
    {"protocol": "chat-audio", "model": "m", "max_audio_base64_bytes": MAX_AUDIO_BASE64_BYTES + 1},
    {"protocol": "chat-audio", "model": "m", "source": "http://example.com"},
])
def test_a_malformed_route_is_refused_loudly(block):
    with pytest.raises(ValueError):
        route_from_template({"transcription": block})


def test_a_template_without_the_block_offers_no_transcription():
    assert route_from_template({}) is None
    assert route_from_template({"protocol": "openai-chat"}) is None


# ------------------------------------------------------------------ sniffing


def test_sniffing_accepts_wav_and_mp3_only():
    assert sniff_audio(wav_bytes()) == "wav"
    assert sniff_audio(mp3_bytes()) == "mp3"
    assert sniff_audio(b"OggS" + b"\x00" * 40) is None
    assert sniff_audio(b"\xff\xff\xff\xff" * 4) is None
    assert sniff_audio(b"short") is None


def test_base64_length_is_computed_from_bytes_not_guessed():
    assert encoded_size(0) == 0
    assert encoded_size(1) == 4
    assert encoded_size(3) == 4
    assert encoded_size(4) == 8


# ------------------------------------------------------------------ payload / parsing


def test_payload_carries_the_audio_as_a_data_url_and_omits_auto_language():
    payload = build_payload(route(), wav_bytes(), "wav", "auto")
    part = payload["messages"][0]["content"][0]
    assert part["type"] == "input_audio"
    assert part["input_audio"]["data"].startswith("data:audio/wav;base64,")
    assert "asr_options" not in payload
    explicit = build_payload(route(languages=["auto", "en"]), wav_bytes(), "wav", "en")
    assert explicit["asr_options"] == {"language": "en"}


def test_the_observed_reply_keeps_usage_and_the_provider_model():
    result = parse_transcription_response(OBSERVED_ASR_RESPONSE, route())
    assert result.text == "Hutch audio check. One, two, three."
    assert result.model == "mimo-v2.5-asr"
    assert (result.prompt_tokens, result.completion_tokens, result.audio_tokens) == (42, 15, 21)
    assert result.audio_seconds == 4.0
    assert result.notes == ()


def test_a_reply_from_another_model_is_reported_not_hidden():
    result = parse_transcription_response(observed_response(model="some-other-asr"), route())
    assert result.substituted_model is True
    assert "answered with some-other-asr" in result.notes[0]


def test_empty_content_is_a_failure_never_an_empty_transcript():
    body = observed_response()
    body["choices"][0]["message"]["content"] = ""
    with pytest.raises(ProviderError) as caught:
        parse_transcription_response(body, route())
    assert caught.value.kind == "incomplete"
    assert "no transcript" in str(caught.value)
    with pytest.raises(ProviderError):
        parse_transcription_response({"error": {"message": "bad audio"}}, route())


# ------------------------------------------------------------------ transport


def test_the_key_goes_only_to_the_configured_endpoint(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=OBSERVED_ASR_RESPONSE)

    install_fake_transport(monkeypatch, handler)
    transcriber = ChatAudioTranscriber(
        base_url="https://token-plan-sgp.xiaomimimo.com/v1", api_key="tp-secret",
        route=route(languages=["auto", "en"]), provider_name="mimo")
    result = transcriber.transcribe(wav_bytes(), language="en")
    assert result.text.startswith("Hutch audio check")
    assert str(seen[0].url) == "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer tp-secret"
    body = json.loads(seen[0].content)
    assert body["model"] == "mimo-v2.5-asr"
    assert body["asr_options"] == {"language": "en"}


def test_oversized_audio_is_refused_before_a_request_is_made(monkeypatch):
    called: list[httpx.Request] = []
    install_fake_transport(monkeypatch, lambda request: called.append(request))
    transcriber = ChatAudioTranscriber(
        base_url="https://example.invalid/v1", api_key="k",
        route=route(max_audio_base64_bytes=100))
    with pytest.raises(ProviderError) as caught:
        transcriber.transcribe(wav_bytes(64))
    assert caught.value.kind == "bad_request" and "too large" in str(caught.value)
    assert called == []


def test_a_declared_format_that_contradicts_the_bytes_is_refused(monkeypatch):
    install_fake_transport(monkeypatch, lambda request: pytest.fail("must not reach the network"))
    transcriber = ChatAudioTranscriber(base_url="https://example.invalid/v1",
                                       api_key="k", route=route())
    with pytest.raises(ProviderError) as caught:
        transcriber.transcribe(wav_bytes(), audio_format="mp3")
    assert "declared 'mp3'" in str(caught.value)


def test_auth_failure_is_typed_and_never_echoes_the_key(monkeypatch):
    install_fake_transport(monkeypatch, lambda request: httpx.Response(
        401, json={"error": {"message": "invalid api key"}}))
    transcriber = ChatAudioTranscriber(base_url="https://example.invalid/v1",
                                       api_key="tp-secret", route=route())
    with pytest.raises(ProviderError) as caught:
        transcriber.transcribe(wav_bytes())
    assert caught.value.kind == "auth"
    assert "rejected the credential" in str(caught.value)
    assert "tp-secret" not in str(caught.value)


def test_a_redirect_is_refused_rather_than_followed_with_the_key(monkeypatch):
    install_fake_transport(monkeypatch, lambda request: httpx.Response(
        302, headers={"location": "https://elsewhere.invalid/collect"}))
    transcriber = ChatAudioTranscriber(base_url="https://example.invalid/v1",
                                       api_key="k", route=route())
    with pytest.raises(ProviderError) as caught:
        transcriber.transcribe(wav_bytes())
    assert "redirect" in str(caught.value)
    assert "does not follow" in str(caught.value)
