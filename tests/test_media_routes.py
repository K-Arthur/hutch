"""Table-driven media routes (Phase 6).

What is verified here is the PROTOCOL a route declares: the request each route builds, how each
answer is read, and how failures are told apart. Provider responses come from
``httpx.MockTransport`` shaped after each vendor's documented reply; that is protocol evidence
only. No vendor account was exercised, so every route stays implemented-unverified (the table
test below fails if one claims more).
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
import pytest

from hutch.media.cost import estimate, load_prices
from hutch.media.providers.base import MediaRefused
from hutch.media.providers.route_backend import RouteBackendError, SyncRouteBackend
from hutch.media.providers.route_spec import (BUILDABLE, RouteSpecError, load_routes,
                                              routes_for_kind)
from hutch.media.providers.route_task import TaskRouteBackend
from hutch.media.providers.route_values import RouteInputError, request_values
from hutch.media.providers.wire import (dig, dig_all, envelope_problem, error_detail, fill,
                                        fill_path, media_item)
from hutch.media.spool import MediaSpool
from tests.test_media_durability import PNG, _wav, loopback  # noqa: F401 - loopback is a fixture

ROUTES = load_routes()
WAV = _wav()


# ---------------------------------------------------------------- wire rules


def test_fill_keeps_types_and_drops_absent_fields():
    template = {"model": "{model}", "n": 1, "ratio": "{ratio}", "d": "{seconds}",
                "nested": {"voice": "{voice}"}, "list": ["{a}", "{missing}"], "text": "hi {model}"}
    assert fill(template, {"model": "m", "seconds": 5, "voice": "v", "a": "x"}) == {
        "model": "m", "n": 1, "d": 5, "nested": {"voice": "v"}, "list": ["x"], "text": "hi m"}


def test_fill_path_encodes_values_so_a_value_cannot_add_a_segment():
    assert fill_path("/v1/tts/{voice}", {"voice": "a/b?c"}) == "/v1/tts/a%2Fb%3Fc"
    assert fill_path("/{model}/x", {"model": "fal-ai/flux/dev"}) == "/fal-ai/flux/dev/x"
    with pytest.raises(Exception, match="needs voice"):
        fill_path("/v1/{voice}", {})


def test_dig_expands_wildcards_and_indexes():
    body = {"steps": [{"type": "model_output", "content": [{"type": "text"}, {"type": "audio", "data": "A"}]},
                      {"content": [{"type": "audio", "data": "B"}]}], "data": [{"b": "1"}]}
    assert [c.get("data") for c in dig_all(body, "steps.*.content.*") if "data" in c] == ["A", "B"]
    assert dig(body, "data.0.b") == "1" and dig(body, "data.-1.b") == "1"
    assert dig(body, "nope.here", "d") == "d" and dig_all(body, "steps.9") == []


def test_media_item_filters_picks_and_reads_lists_of_strings():
    body = {"steps": [{"content": [{"type": "audio", "data": "A"}, {"type": "audio", "data": "B"}]}]}
    spec = {"path": "steps.*.content.*", "where": {"type": "audio"}, "pick": "last", "key": "data"}
    assert media_item(body, spec) == "B"
    assert media_item({"data": {"image_base64": ["X", "Y"]}}, {"path": "data.image_base64"}) == "X"
    assert media_item({"data": []}, {"path": "data", "key": "b64_json"}) is None
    assert media_item({"data": {"audio": None}}, {"path": "data.audio"}) is None


def test_envelope_reads_the_in_body_status_not_the_http_status():
    env = {"code_path": "base_resp.status_code", "ok": 0, "message_path": "base_resp.status_msg",
           "refusal_codes": [1026]}
    assert envelope_problem({"base_resp": {"status_code": 0}}, env) is None
    message, refused = envelope_problem({"base_resp": {"status_code": 1026, "status_msg": "sensitive"}}, env)
    assert refused and "sensitive" in message
    assert envelope_problem({"base_resp": {"status_code": 1008, "status_msg": "balance"}}, env)[1] is False
    assert "no status envelope" in envelope_problem({"data": {}}, env)[0]


def test_error_detail_prefers_the_providers_specific_sentence():
    assert error_detail({"error": {"message": "bad  key"}}, 401) == "bad key"
    assert error_detail({"detail": [{"msg": "field required"}]}, 422) == "field required"
    assert error_detail({}, 500) == "HTTP 500"


# ---------------------------------------------------------------- the table itself


def test_every_route_cites_a_dated_source_and_claims_no_more_than_unverified():
    assert ROUTES, "the table is empty"
    for route in ROUTES.values():
        assert route.sources and all(s["read"] == "2026-11-06" or re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["read"])
                                     for s in route.sources), route.id
        assert route.status in (BUILDABLE, "documented", "blocked", "retired"), route.id
        if route.status == "retired":
            assert route.retired_on, route.id


def test_only_buildable_routes_carry_requests_and_every_one_has_a_price_row():
    prices = load_prices()
    for route in ROUTES.values():
        if route.buildable:
            assert route.price in prices, f"{route.id} names price row {route.price!r}"
            assert route.protocol in ("sync", "task", "adapter")
        else:
            assert not route.request and not route.task, f"{route.id} is {route.status}"


def test_retired_and_documented_routes_are_never_offered_for_building():
    kinds = {r.id for k in ("image", "video", "audio") for r in routes_for_kind(k)}
    for rid in ("openai-video", "google-veo", "runway-video", "minimax-video", "google-omni-video"):
        assert rid in ROUTES and rid not in kinds


def test_no_route_sends_a_credential_to_a_non_https_origin_or_embeds_one():
    for route in ROUTES.values():
        if route.env_var:
            assert route.credential["base_url"].startswith("https://"), route.id
        assert not re.search(r"(?i)(secret|token)\s*[:=]\s*\S{8,}", json.dumps(dict(route.request))), route.id


def test_a_malformed_table_row_is_refused(monkeypatch):
    from hutch.media.providers import route_spec

    with pytest.raises(RouteSpecError, match="source"):
        route_spec._parse("x", {"kind": "image", "status": "documented", "sources": []})
    with pytest.raises(RouteSpecError, match="retired"):
        route_spec._parse("x", {"kind": "video", "status": "retired",
                                "sources": [{"url": "u", "read": "2026-11-06"}]})


# ---------------------------------------------------------------- request values


def test_aspect_ratio_is_the_nearest_the_route_offers():
    route = ROUTES["xai-image"]
    assert request_values(route, {"prompt": "x", "width": 1920, "height": 1080})["aspect_ratio"] == "16:9"
    assert request_values(route, {"prompt": "x", "width": 1000, "height": 1000})["aspect_ratio"] == "1:1"
    assert request_values(route, {"prompt": "x"})["aspect_ratio"] is None


def test_out_of_range_requests_are_refused_with_the_number():
    with pytest.raises(RouteInputError, match="at most 1500"):
        request_values(ROUTES["minimax-image"], {"prompt": "x" * 1501})
    with pytest.raises(RouteInputError, match="1 to 15"):
        request_values(ROUTES["xai-video"], {"prompt": "x", "seconds": 30})
    with pytest.raises(RouteInputError, match="not offered"):
        request_values(ROUTES["xai-speech"], {"prompt": "x", "voice": "nobody"})
    with pytest.raises(RouteInputError, match="style"):
        request_values(ROUTES["xai-speech"], {"prompt": "x", "style": "cheerful"})
    assert request_values(ROUTES["openai-speech"], {"prompt": "x", "style": "calm"})["style"] == "calm"


# ---------------------------------------------------------------- sync routes


def sync(route_id: str, handler, *, spool=None, key="unit-key") -> SyncRouteBackend:
    return SyncRouteBackend(ROUTES[route_id], base_url="https://unit.test/v1", api_key=key,
                            connection="acct", billing="per_token", credential_label="test",
                            client=httpx.Client(transport=httpx.MockTransport(handler)), spool=spool)


def captured(response: httpx.Response):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return handler, seen


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def held(backend: SyncRouteBackend, req: dict) -> bytes:
    handle = backend.submit(req)
    return backend.fetch({"upstream_job_id": handle})


def test_xai_image_request_and_response():
    handler, seen = captured(httpx.Response(200, json={"data": [{"b64_json": b64(PNG)}]}))
    backend = sync("xai-image", handler)
    assert held(backend, {"prompt": "a fox", "width": 1920, "height": 1080}) == PNG
    request = seen[0]
    assert request.url == "https://unit.test/v1/images/generations"
    assert request.headers["authorization"] == "Bearer unit-key"
    assert json.loads(request.content) == {"model": "grok-imagine-image-2.0", "prompt": "a fox", "n": 1,
                                           "aspect_ratio": "16:9", "response_format": "b64_json"}


def test_google_image_uses_the_interactions_wire_and_picks_the_last_image_block():
    body = {"steps": [{"type": "model_output", "content": [
        {"type": "text", "text": "here"}, {"type": "image", "data": b64(PNG)}]}]}
    handler, seen = captured(httpx.Response(200, json=body))
    assert held(sync("google-image", handler), {"prompt": "a fox"}) == PNG
    request = seen[0]
    assert request.headers["x-goog-api-key"] == "unit-key" and "authorization" not in request.headers
    assert request.headers["api-revision"] == "2026-05-20"
    assert json.loads(request.content) == {"model": "gemini-3.1-flash-lite-image",
                                           "input": [{"type": "text", "text": "a fox"}],
                                           "response_format": {"type": "image"}}


def test_google_speech_with_no_audio_block_is_a_failure_that_names_the_billing_risk():
    body = {"steps": [{"type": "model_output", "content": []}]}
    handler, _ = captured(httpx.Response(200, json=body))
    with pytest.raises(RouteBackendError, match="without any media.*may have billed"):
        sync("google-speech", handler).submit({"prompt": "hello", "voice": "Kore"})


def test_google_speech_reads_the_wav_and_sends_the_voice():
    body = {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": b64(WAV)}]}]}
    handler, seen = captured(httpx.Response(200, json=body))
    backend = sync("google-speech", handler)
    handle = backend.submit({"prompt": "hello", "voice": "Puck"})
    assert backend.fetch({"upstream_job_id": handle}) == WAV
    assert backend.duration_seconds({"upstream_job_id": handle}) == pytest.approx(0.1, abs=0.01)
    assert json.loads(seen[0].content)["generation_config"] == {"speech_config": [{"voice": "Puck"}]}


def test_minimax_http_200_with_a_failure_envelope_is_not_success():
    body = {"base_resp": {"status_code": 1008, "status_msg": "insufficient balance"}}
    handler, _ = captured(httpx.Response(200, json=body))
    with pytest.raises(RouteBackendError, match="1008.*insufficient balance.*may have billed"):
        sync("minimax-speech", handler).submit({"prompt": "hi"})


def test_minimax_sensitive_content_is_a_refusal():
    body = {"base_resp": {"status_code": 1026, "status_msg": "input new_sensitive"}}
    handler, _ = captured(httpx.Response(200, json=body))
    with pytest.raises(MediaRefused, match="1026"):
        sync("minimax-image", handler).submit({"prompt": "x"})


def test_minimax_image_blocked_by_the_safety_filter_counts_as_a_refusal():
    body = {"base_resp": {"status_code": 0}, "data": {"image_base64": []}, "metadata": {"failed_count": 1}}
    handler, _ = captured(httpx.Response(200, json=body))
    with pytest.raises(MediaRefused, match="safety"):
        sync("minimax-image", handler).submit({"prompt": "x"})


def test_minimax_speech_decodes_hex_and_requests_wav():
    body = {"base_resp": {"status_code": 0}, "data": {"audio": WAV.hex(), "status": 2}}
    handler, seen = captured(httpx.Response(200, json=body))
    assert held(sync("minimax-speech", handler), {"prompt": "hi"}) == WAV
    sent = json.loads(seen[0].content)
    assert sent["audio_setting"]["format"] == "wav" and sent["output_format"] == "hex"
    assert sent["voice_setting"] == {"voice_id": "English_expressive_narrator"}


def test_binary_speech_routes_check_the_content_type_before_trusting_the_body():
    for route_id, header in (("xai-speech", "Bearer unit-key"), ("openai-speech", "Bearer unit-key"),
                             ("elevenlabs-speech", None), ("deepgram-speech", "Token unit-key")):
        handler, seen = captured(httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"}))
        assert held(sync(route_id, handler), {"prompt": "hello"}) == WAV, route_id
        if header:
            assert seen[0].headers["authorization"] == header
    handler, _ = captured(httpx.Response(200, content=b'{"error":"x"}',
                                         headers={"content-type": "application/json"}))
    with pytest.raises(RouteBackendError, match="instead of audio"):
        sync("deepgram-speech", handler).submit({"prompt": "hello"})


def test_elevenlabs_puts_the_voice_in_the_path_and_the_key_in_its_own_header():
    handler, seen = captured(httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"}))
    held(sync("elevenlabs-speech", handler), {"prompt": "hello", "voice": "voiceA"})
    request = seen[0]
    assert request.url.path == "/v1/v1/text-to-speech/voiceA"       # base_url in this test ends in /v1
    assert request.url.params["output_format"] == "wav_24000"
    assert request.headers["xi-api-key"] == "unit-key" and "authorization" not in request.headers


def test_deepgram_413_is_reported_with_the_vendors_limit_in_mind():
    handler, _ = captured(httpx.Response(413, json={"err_msg": "too long"}))
    with pytest.raises(RouteBackendError, match="refused the request"):
        sync("deepgram-speech", handler).submit({"prompt": "x" * 100})


@pytest.mark.parametrize("status,words", [(401, "rejected the credential"), (402, "no available credit"),
                                          (429, "rate-limited"), (503, "failed on its side")])
def test_http_failures_name_their_cause_class(status, words):
    handler, _ = captured(httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(RouteBackendError, match=words):
        sync("xai-image", handler).submit({"prompt": "x"})


def test_a_failed_call_is_made_once_and_never_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={})

    with pytest.raises(RouteBackendError):
        sync("xai-image", handler).submit({"prompt": "x"})
    assert len(calls) == 1


def test_a_timeout_says_the_provider_may_have_billed():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(RouteBackendError, match="may have received and billed"):
        sync("xai-image", handler).submit({"prompt": "x"})


def test_the_key_never_appears_in_an_error_message():
    handler, _ = captured(httpx.Response(401, json={"error": {"message": "bad"}}))
    with pytest.raises(RouteBackendError) as raised:
        sync("xai-image", handler, key="sk-very-secret-value").submit({"prompt": "x"})
    assert "sk-very-secret-value" not in str(raised.value)


def test_a_sync_result_survives_a_restart_and_is_not_regenerated(tmp_path):
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})

    handle = sync("xai-speech", handler, spool=MediaSpool(tmp_path)).submit({"prompt": "hello"})
    reborn = sync("xai-speech", handler, spool=MediaSpool(tmp_path))
    job = {"upstream_job_id": handle}
    assert reborn.can_recover(job) and reborn.fetch(job) == WAV and len(calls) == 1


def test_approval_detail_names_who_receives_the_prompt_and_who_pays():
    detail = sync("xai-image", captured(httpx.Response(200))[0]).approval_detail({"prompt": "a fox"})
    assert detail["provider"] == "xai" and detail["connection"] == "acct"
    assert detail["credential"] == "test" and detail["billing"] == "per_token"
    assert detail["prompt_chars"] == 5 and "leaves this machine" in detail["note"]
