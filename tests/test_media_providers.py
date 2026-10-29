"""Provider adapters, protocol verification against in-process fakes only.

NO NETWORK: the OpenAI adapter runs through the SDK with a fake httpx transport,
the ComfyUI adapter through ``httpx.MockTransport``. What is verified here is the
PROTOCOL usage (endpoints, payload shapes, state mapping, cancel honesty); both
adapters self-report ``protocol-verified, live-unverified`` in capabilities().
"""

from __future__ import annotations

import base64
import json
import struct
import zlib

import httpx
import pytest

from hutch.media.providers.base import MediaBackend, VERIFICATION_TAG
from hutch.media.providers.comfyui import ComfyUIBackend, ComfyUIError
from hutch.media.providers.openai_images import (OpenAIImagesBackend,
                                                 OpenAIImagesError)


def make_png(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        blob = struct.pack(">I", len(data)) + tag + data
        return blob + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x0a\x0b\x0c" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = make_png()


# ---------------------------------------------------------------- openai


def test_openai_images_backend_satisfies_the_protocol_and_reports_honesty():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"created": 1700000000,
                                         "data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    backend = OpenAIImagesBackend(
        api_key="unit-key", base_url="http://unit.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert isinstance(backend, MediaBackend), "the adapter implements the protocol"
    caps = backend.capabilities()
    assert caps["kinds"] == ["image"] and caps["editing"] is True
    assert caps["partial_previews"] is False
    assert caps["verified"] == VERIFICATION_TAG
    assert "protocol-verified" in caps["verified"]
    assert "live-unverified" in caps["verified"]


def test_openai_images_submit_poll_fetch_round_trip_with_a_fake_transport():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"created": 1700000000,
                                         "data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    backend = OpenAIImagesBackend(
        api_key="unit-key", base_url="http://unit.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    handle = backend.submit({"kind": "image", "prompt": "a lighthouse",
                             "width": 1024, "height": 1024})
    assert isinstance(handle, str) and handle
    assert captured["url"].endswith("/images/generations")
    assert captured["body"]["prompt"] == "a lighthouse"
    assert captured["body"]["size"] == "1024x1024"
    assert backend.poll({"upstream_job_id": handle})["status"] == "succeeded"
    assert backend.fetch({"upstream_job_id": handle}) == PNG


def test_openai_images_fetch_consumes_an_expiring_url_exactly_once(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"created": 1700000000,
                                         "data": [{"url": "https://expiring/blob"}]})

    downloads: list[str] = []

    def fake_get(url, timeout=None, headers=None):
        downloads.append(url)

        class R:
            status_code = 200
            content = PNG

        return R()

    monkeypatch.setattr("httpx.get", fake_get)
    backend = OpenAIImagesBackend(
        api_key="unit-key", base_url="http://unit.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    handle = backend.submit({"kind": "image", "prompt": "x"})
    assert backend.poll({"upstream_job_id": handle})["status"] == "succeeded"
    assert backend.fetch({"upstream_job_id": handle}) == PNG
    assert downloads == ["https://expiring/blob"], "the URL is consumed, never stored"


def test_openai_images_errors_surface_with_the_provider_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad size"}})

    backend = OpenAIImagesBackend(
        api_key="unit-key", base_url="http://unit.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OpenAIImagesError, match="bad size"):
        backend.submit({"kind": "image", "prompt": "x"})


def test_openai_images_cancel_is_honestly_none_for_a_synchronous_api():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "AAAA"}]})

    backend = OpenAIImagesBackend(
        api_key="unit-key", base_url="http://unit.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    handle = backend.submit({"kind": "image", "prompt": "x"})
    assert backend.cancel({"upstream_job_id": handle}) is None, \
        "the charge already happened; claiming a confirmed cancel would be a lie"


# ---------------------------------------------------------------- comfyui


def make_comfy(transport_handler) -> ComfyUIBackend:
    return ComfyUIBackend("http://comfy.test",
                          client=httpx.Client(transport=httpx.MockTransport(transport_handler)))


def test_comfyui_satisfies_the_protocol_and_reports_honesty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    backend = make_comfy(handler)
    assert isinstance(backend, MediaBackend)
    caps = backend.capabilities()
    assert set(caps["kinds"]) == {"image", "video"}
    assert caps["partial_previews"] is True and caps["editing"] is True
    assert caps["verified"] == VERIFICATION_TAG
    assert caps["endpoint"] == "http://comfy.test"


def test_comfyui_submit_history_view_round_trip():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt" and request.method == "POST":
            body = json.loads(request.content)
            assert body["prompt"]["1"]["class_type"] == "KSampler"
            assert body["client_id"].startswith("hutch-")
            return httpx.Response(200, json={"prompt_id": "prompt-1", "number": 1})
        if request.url.path == "/history/prompt-1":
            return httpx.Response(200, json={"prompt-1": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"9": {"images": [{"filename": "out.png",
                                              "subfolder": "", "type": "output"}]}}}})
        if request.url.path == "/view":
            assert request.url.params["filename"] == "out.png"
            return httpx.Response(200, content=PNG)
        return httpx.Response(404, json={"error": "nope"})

    backend = make_comfy(handler)
    handle = backend.submit({"kind": "image",
                             "workflow": {"1": {"class_type": "KSampler"}}})
    assert handle == "prompt-1"
    assert backend.poll({"upstream_job_id": handle})["status"] == "succeeded"
    assert backend.fetch({"upstream_job_id": handle}) == PNG


def test_comfyui_poll_maps_states_honestly():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p"})
        if request.url.path == "/history/p":
            return httpx.Response(200, json={})     # not in history yet: queued
        return httpx.Response(404)

    backend = make_comfy(handler)
    handle = backend.submit({"kind": "image", "workflow": {"1": {}}})
    assert backend.poll({"upstream_job_id": handle})["status"] == "running"

    def erroring(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "e"})
        if request.url.path == "/history/e":
            return httpx.Response(200, json={"e": {"status": {
                "completed": False, "status_str": "error",
                "messages": [["execution_error", {"node_type": "KSampler"}]]},
                "outputs": {}}})
        return httpx.Response(404)

    backend2 = make_comfy(erroring)
    handle2 = backend2.submit({"kind": "image", "workflow": {"1": {}}})
    state = backend2.poll({"upstream_job_id": handle2})
    assert state["status"] == "failed" and "KSampler" in state["error"]

    def restarted(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "lost"})
        return httpx.Response(404)

    backend3 = make_comfy(restarted)
    handle3 = backend3.submit({"kind": "image", "workflow": {"1": {}}})
    state = backend3.poll({"upstream_job_id": handle3})
    assert state["status"] == "failed" and "no history" in state["error"], \
        "a server that forgot the job is reported, never guessed"


def test_comfyui_cancel_confirms_only_on_an_explicit_ack():
    def cancellable(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/queue":
            assert json.loads(request.content) == {"delete": ["p"]}
            return httpx.Response(200, json={})
        return httpx.Response(404)

    backend = make_comfy(cancellable)
    assert backend.cancel({"upstream_job_id": "p"}) == {"cancelled": True,
                                                        "how": "queue-delete"}

    def refusing(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/queue":
            return httpx.Response(404)
        if request.method == "POST" and request.url.path == "/interrupt":
            return httpx.Response(500)
        return httpx.Response(404)

    backend2 = make_comfy(refusing)
    assert backend2.cancel({"upstream_job_id": "p"}) is None, \
        "without an ack the job service must record cancel_unconfirmed, not cancelled"


def test_comfyui_submit_requires_a_workflow_and_surfaces_http_errors():
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "validation failed"})

    backend = make_comfy(failing)
    with pytest.raises(ComfyUIError, match="no ComfyUI workflow"):
        backend.submit({"kind": "image"})
    with pytest.raises(ComfyUIError, match="400"):
        backend.submit({"kind": "image", "workflow": {"1": {}}})
