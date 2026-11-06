"""Phase 6: a paid result survives a crash, downloads are bounded, refusals are refusals.

The spool and download tests use real files and a real loopback HTTP server. The OpenAI adapter
tests run the real SDK against ``httpx.MockTransport``: that is failure injection (a 400 with a
specific error code, a 500 the SDK would retry), not live evidence.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import threading

import httpx
import pytest

from hutch.media import MediaJobService, MediaStorage, service_status
from hutch.media.fetch import FetchError, download
from hutch.media.providers.base import MediaRefused
from hutch.media.providers.openai_images import (OpenAIImagesBackend, OpenAIImagesError,
                                                 choose_size, takes_response_format)
from hutch.media.spool import MediaSpool, ResultHold, SpoolError
from tests.test_media_jobs import FakeBackend, make_png

PNG = make_png()


# ---------------------------------------------------------------- spool


def test_spool_round_trips_and_is_owner_only(tmp_path):
    spool = MediaSpool(tmp_path)
    handle = spool.put(PNG, meta={"model": "m"})
    assert spool.has(handle) and spool.get(handle) == PNG and spool.meta(handle) == {"model": "m"}
    assert (spool.root.stat().st_mode & 0o777) == 0o700
    assert (spool.root / f"{handle}.bin").stat().st_mode & 0o777 == 0o600


def test_spool_survives_a_new_process_view_of_the_same_directory(tmp_path):
    handle = MediaSpool(tmp_path).put(PNG)
    assert MediaSpool(tmp_path).get(handle) == PNG


def test_spool_refuses_a_handle_that_could_name_another_path(tmp_path):
    spool = MediaSpool(tmp_path)
    for bad in ("../x", "spool_zz", "spool_" + "a" * 23, "", "/etc/passwd"):
        with pytest.raises(SpoolError):
            spool.get(bad)
        assert spool.has(bad) is False


def test_spool_detects_corruption_instead_of_returning_wrong_bytes(tmp_path):
    spool = MediaSpool(tmp_path)
    handle = spool.put(PNG)
    (spool.root / f"{handle}.bin").write_bytes(PNG[:-1] + b"X")
    with pytest.raises(SpoolError, match="digest"):
        spool.get(handle)


def test_spool_refuses_empty_and_oversize_results(tmp_path, monkeypatch):
    spool = MediaSpool(tmp_path)
    with pytest.raises(SpoolError):
        spool.put(b"")
    monkeypatch.setattr("hutch.media.spool.MAX_MEDIA_BYTES", 8)
    with pytest.raises(SpoolError, match="exceeds"):
        spool.put(b"123456789")


def test_a_failed_write_leaves_no_partial_entry(tmp_path, monkeypatch):
    spool = MediaSpool(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        spool.put(PNG)
    assert list(spool.root.iterdir()) == [], "no temp or half entry may remain"


def test_sweep_removes_only_old_unreferenced_entries(tmp_path):
    spool = MediaSpool(tmp_path)
    kept, gone, fresh = spool.put(PNG), spool.put(PNG), spool.put(PNG)
    old = 1_000_000_000
    for handle in (kept, gone):
        os.utime(spool.root / f"{handle}.json", (old, old))
    assert spool.sweep(keep={kept}) == 1
    assert spool.has(kept) and spool.has(fresh) and not spool.has(gone)


def test_hold_without_a_spool_reports_that_it_is_not_durable():
    hold = ResultHold()
    handle = hold.put(PNG)
    assert hold.durable is False and hold.get(handle) == PNG


# ---------------------------------------------------------------- bounded download


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/ok":
            body = PNG
        elif self.path == "/big":
            body = b"x" * 5000
        elif self.path == "/hop":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        elif self.path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
            return
        elif self.path == "/empty":
            body = b""
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def loopback():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_download_returns_the_body_through_the_pinned_client(loopback):
    assert download(f"{loopback}/ok") == PNG


def test_download_follows_a_redirect_and_stops_a_loop(loopback):
    assert download(f"{loopback}/hop") == PNG
    with pytest.raises(FetchError, match="redirected more than"):
        download(f"{loopback}/loop")


def test_download_stops_at_the_limit_and_says_so(loopback):
    with pytest.raises(FetchError, match="byte limit"):
        download(f"{loopback}/big", max_bytes=1000)


def test_download_reports_an_expired_or_empty_result(loopback):
    with pytest.raises(FetchError, match="expired"):
        download(f"{loopback}/gone")
    with pytest.raises(FetchError, match="empty"):
        download(f"{loopback}/empty")


def test_download_refuses_credentials_in_the_url_and_a_metadata_address():
    with pytest.raises(FetchError, match="credentials"):
        download("https://user:secret@example.com/x")
    with pytest.raises(FetchError):
        download("http://169.254.169.254/latest/meta-data")


def test_download_refuses_a_non_http_scheme():
    with pytest.raises(FetchError, match="http"):
        download("file:///etc/passwd")


# ---------------------------------------------------------------- openai images


def _backend(handler, spool=None, model="gpt-image-1-mini"):
    return OpenAIImagesBackend(api_key="unit-key", base_url="http://unit.test/v1", model=model,
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                               spool=spool)


def _ok(request):
    return httpx.Response(200, json={"created": 1, "data": [
        {"b64_json": base64.b64encode(PNG).decode()}]})


def test_gpt_image_models_never_receive_response_format():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return _ok(request)

    for model in ("gpt-image-1", "gpt-image-1.5", "gpt-image-2", "gpt-image-1-mini"):
        _backend(handler, model=model).submit({"prompt": "x"})
    assert all("response_format" not in body for body in seen)
    _backend(handler, model="dall-e-3").submit({"prompt": "x"})
    assert seen[-1]["response_format"] == "b64_json"


def test_size_follows_the_model_family():
    assert takes_response_format("dall-e-3") and not takes_response_format("gpt-image-2")
    assert choose_size("gpt-image-1-mini", 1600, 900) == "1536x1024"
    assert choose_size("gpt-image-1-mini", 900, 1600) == "1024x1536"
    assert choose_size("dall-e-3", 1600, 900) == "1792x1024"
    assert choose_size("gpt-image-1-mini", None, None) == "1024x1024"


def test_the_paid_image_survives_a_restart_when_a_spool_is_present(tmp_path):
    spool = MediaSpool(tmp_path)
    handle = _backend(_ok, spool).submit({"prompt": "x"})
    reborn = _backend(_ok, MediaSpool(tmp_path))           # a new process, same state directory
    job = {"upstream_job_id": handle}
    assert reborn.poll(job) == {"status": "succeeded"}
    assert reborn.can_recover(job) and reborn.fetch(job) == PNG


def test_without_a_spool_a_restart_loses_the_image_and_says_it_cannot_recover():
    handle = _backend(_ok).submit({"prompt": "x"})
    reborn = _backend(_ok)
    job = {"upstream_job_id": handle}
    assert reborn.poll(job)["status"] == "failed" and not reborn.can_recover(job)


def test_moderation_blocked_is_a_refusal_not_an_error():
    def handler(request):
        return httpx.Response(400, json={"error": {
            "message": "Your request was rejected by the safety system.",
            "type": "invalid_request_error", "code": "moderation_blocked"}})

    with pytest.raises(MediaRefused, match="moderation_blocked"):
        _backend(handler).submit({"prompt": "x"})


def test_other_client_errors_stay_errors():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "bad size", "code": "invalid_value"}})

    with pytest.raises(OpenAIImagesError, match="bad size"):
        _backend(handler).submit({"prompt": "x"})


def test_a_server_error_is_not_retried_by_the_sdk_because_a_retry_could_bill_twice():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(OpenAIImagesError):
        _backend(handler).submit({"prompt": "x"})
    assert len(calls) == 1


# ---------------------------------------------------------------- the ledger


@pytest.fixture()
def service(store, config):
    return MediaJobService(store, MediaStorage(config))


class RefusingBackend(FakeBackend):
    def submit(self, req):
        self.submit_calls += 1
        raise MediaRefused("the prompt names a real person")


class RefusingPollBackend(FakeBackend):
    def poll(self, job):
        self.poll_calls += 1
        return {"status": "failed", "refused": True, "error": "content moderation failed"}


def test_a_refused_submit_is_recorded_as_refused_with_the_provider_reason(service):
    service.backends["fake"] = RefusingBackend()
    row = service.submit(run_id="r", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-refuse", backend_hint="fake")
    assert service_status(row) == "refused"
    assert "real person" in row["error"] and row["upstream_job_id"] is None
    assert "declined" in row["cost_note"]


def test_a_refusal_found_while_polling_is_refused_too(service):
    service.backends["fake"] = RefusingPollBackend()
    row = service.submit(run_id="r", conversation_id="c", kind="video", prompt="x",
                         idempotency_key="k-refuse-poll", backend_hint="fake")
    assert service_status(row) == "running"
    polled = service.poll(row["id"])
    assert service_status(polled) == "refused" and "moderation" in polled["error"]


def test_a_plain_failure_is_still_a_failure(service):
    service.backends["fake"] = FakeBackend(poll_status="failed", poll_error="gpu out of memory")
    row = service.submit(run_id="r", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-plain", backend_hint="fake")
    polled = service.poll(row["id"])
    assert service_status(polled) == "failed"


def _restarted(service):
    """A new service over the same store and backends: what a restarted process sees."""
    return MediaJobService(service.store, service.media_store, backends=dict(service.backends))


class RecoverableBackend(FakeBackend):
    def can_recover(self, job):
        return True


def test_reconcile_leaves_a_recoverable_success_running_instead_of_marking_it_unfetched(service):
    service.backends["fake"] = RecoverableBackend()
    row = service.submit(run_id="r-rec", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-rec", backend_hint="fake")
    reborn = _restarted(service)
    summary = reborn.reconcile(run_ids=["r-rec"])
    assert summary["recoverable"] == 1
    assert reborn.store.get_media_job(row["id"])["status"] == "running"
    payload, final = reborn.finalize(row["id"], alt_text="a picture")
    assert final["status"] == "succeeded" and payload["sha256"]


def test_reconcile_still_marks_a_non_recoverable_success_as_unfetched(service):
    service.backends["fake"] = FakeBackend()
    row = service.submit(run_id="r-nr", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-nr", backend_hint="fake")
    reborn = _restarted(service)
    summary = reborn.reconcile(run_ids=["r-nr"])
    assert summary["resolved"] == 1
    assert reborn.store.get_media_job(row["id"])["result"]["bytes"] == "not_fetched"


# ---------------------------------------------------------------- speech


def _wav() -> bytes:
    import struct
    rate, frames = 8000, 800
    data = b"\x00\x00" * frames
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<I", 16)
            + fmt + b"data" + struct.pack("<I", len(data)) + data)


def test_synthesized_speech_survives_a_restart_with_its_usage(tmp_path):
    from hutch.media.providers.speech import SpeechBackend, route_from_template
    from hutch.connections import ConnectionBook

    template = ConnectionBook(tmp_path).templates()["xiaomi"]
    route = route_from_template(template)
    body = {"model": route.model, "choices": [{"finish_reason": "stop", "message": {
        "audio": {"data": base64.b64encode(_wav()).decode()}}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 11}}

    def make(spool):
        return SpeechBackend(
            connection="mimo", base_url="http://speech.test/v1", api_key="unit-key", route=route,
            http_client=httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=body))), spool=spool)

    handle = make(MediaSpool(tmp_path)).submit({"prompt": "hello there"})
    reborn = make(MediaSpool(tmp_path))
    job = {"upstream_job_id": handle}
    assert reborn.poll(job) == {"status": "succeeded"} and reborn.can_recover(job)
    spoken = reborn.result_for(job)
    assert spoken.audio == _wav() and spoken.prompt_tokens == 7 and spoken.completion_tokens == 11
    assert reborn.duration_seconds(job) is not None


class FetchRefusesBackend(FakeBackend):
    def fetch(self, job):
        self.fetch_calls += 1
        raise MediaRefused("the safety checker flagged the image")


class FetchBreaksBackend(FakeBackend):
    def fetch(self, job):
        self.fetch_calls += 1
        raise RuntimeError("connection reset")


def test_finalize_always_returns_a_payload_and_a_row_even_when_the_job_failed(service):
    service.backends["fake"] = FetchBreaksBackend()
    row = service.submit(run_id="r", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-fin-fail", backend_hint="fake")
    payload, final = service.finalize(row["id"], alt_text="a picture")
    assert payload == {} and final["status"] == "failed" and "connection reset" in final["error"]


def test_a_refusal_found_while_fetching_is_recorded_as_a_refusal(service):
    service.backends["fake"] = FetchRefusesBackend()
    row = service.submit(run_id="r", conversation_id="c", kind="image", prompt="x",
                         idempotency_key="k-fin-ref", backend_hint="fake")
    payload, final = service.finalize(row["id"], alt_text="a picture")
    assert payload == {} and service_status(final) == "refused" and "safety checker" in final["error"]
