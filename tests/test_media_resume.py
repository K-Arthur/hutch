"""Jobs that outlive the tool call: advance, recover after a crash, cancel, and the dashboard API.

The crash case is the one the spool exists for: the provider answered (and billed), the process
died before the media store committed, a new process finishes the job without a second request.
Provider replies are ``httpx.MockTransport`` shaped after vendor docs; the SQLite store, the spool,
the media store and the FastAPI routes are real.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hutch.media import MediaJobService, MediaStorage, service_status
from hutch.media.backends import build_backends
from hutch.media.routes import build_media_router
from hutch.media.spool import MediaSpool
from hutch.server.app import REMOTE_ROUTE_CAPABILITIES
from tests.support.audio import install_fake_transport, make_ctx
from tests.test_media_backends import NO_ENV, connect
from tests.test_media_durability import PNG, _wav
from tests.test_media_validate import make_mp4

WAV = _wav()


def service_for(store, config) -> MediaJobService:
    backends = build_backends(config.state_dir, spool=MediaSpool(MediaStorage(config).root), environ=NO_ENV)
    return MediaJobService(store, MediaStorage(config), backends=backends)


@pytest.fixture()
def ctx(store, config, tmp_path):
    return make_ctx(store, config, tmp_path)[0]


def submit(service, ctx, backend, kind, prompt, key, **extra):
    return service.submit(run_id=ctx.run.id, conversation_id=ctx.run.conversation_id, kind=kind,
                          prompt=prompt, idempotency_key=key, backend_hint=backend, **extra)


def test_a_paid_result_is_finished_by_a_new_process_without_a_second_request(
        store, config, ctx, monkeypatch):
    connect(config, "xai")
    requests: list[int] = []

    def handler(request):
        requests.append(1)
        return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})

    install_fake_transport(monkeypatch, handler)
    first = service_for(store, config)
    row = submit(first, ctx, "xai-speech:xai", "audio", "hello there", "k-crash")
    assert row["status"] == "running" and len(requests) == 1
    # --- the process dies here: the provider billed, nothing was stored ---
    reborn = service_for(store, config)
    summary = reborn.reconcile(run_ids=[ctx.run.id])
    assert summary["recoverable"] == 1 and summary["marked_orphaned"] == 0
    from hutch.media import resume

    out = resume.advance(reborn, store, row["id"])
    assert out["action"] == "finalized", out
    assert out["job"]["media"]["mime"] == "audio/wav" and out["job"]["status"] == "succeeded"
    assert len(requests) == 1, "recovery must not pay a second time"
    served = MediaStorage(config).read_version(out["job"]["media"]["media_id"], 1)[0]
    assert served == WAV
    usage = store._db.execute("SELECT kind, cost_source FROM usage WHERE run_id = ?", (ctx.run.id,)).fetchone()
    assert (usage["kind"], usage["cost_source"]) == ("speech", "unpriced")


def test_a_task_job_is_observed_then_finished_with_its_bytes_stored(store, config, ctx, monkeypatch):
    connect(config, "xai")
    state = {"polls": 0}

    def handler(request):
        if request.url.host == "media.test":        # the result download shares the patched seam
            return httpx.Response(200, content=make_mp4())
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "vid-1"})
        state["polls"] += 1
        if state["polls"] < 2:
            return httpx.Response(200, json={"status": "pending"})
        return httpx.Response(200, json={"status": "done", "video": {"url": "https://media.test/v.mp4"}})

    install_fake_transport(monkeypatch, handler)
    service = service_for(store, config)
    row = submit(service, ctx, "xai-video:xai", "video", "waves", "k-task", seconds=3)
    from hutch.media import resume

    first = resume.advance(service, store, row["id"])
    assert first["action"] == "polled" and first["observed"]["status"] == "running"
    second = resume.advance(service_for(store, config), store, row["id"])
    assert second["action"] == "finalized", second
    media = second["job"]["media"]
    assert media["mime"] == "video/mp4"
    assert MediaStorage(config).read_version(media["media_id"], 1)[0] == make_mp4()
    assert second["job"]["status"] == "succeeded"


def test_a_job_whose_backend_is_gone_is_blocked_not_guessed_at(store, config, ctx, monkeypatch):
    connect(config, "xai")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={"request_id": "v"}))
    row = submit(service_for(store, config), ctx, "xai-video:xai", "video", "waves", "k-gone")
    from hutch.connections import ConnectionBook
    from hutch.media import resume

    ConnectionBook(config.state_dir).remove("xai")
    out = resume.advance(service_for(store, config), store, row["id"])
    assert out["action"] == "blocked" and "not configured" in out["note"]
    assert store.get_media_job(row["id"])["status"] == "running", "nothing was invented"


def test_cancel_is_confirmed_only_when_the_provider_says_so(store, config, ctx, monkeypatch):
    connect(config, "xai")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={"request_id": "v"}))
    service = service_for(store, config)
    row = submit(service, ctx, "xai-video:xai", "video", "waves", "k-cancel")
    from hutch.media import resume

    out = resume.cancel(service, row["id"], wait_seconds=0.0)
    assert out["job"]["status"] == "cancel_unconfirmed", "xAI documents no cancel call"
    assert "may still be running and billing" in out["job"]["error"]


def test_fal_cancel_200_is_confirmed(store, config, ctx, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-unit")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={"request_id": "r1", "status": "OK"}))
    backends = build_backends(config.state_dir, environ={"FAL_KEY": "fal-unit"})
    service = MediaJobService(store, MediaStorage(config), backends=backends)
    row = submit(service, ctx, "fal-image", "image", "x", "k-fal")
    from hutch.media import resume

    assert resume.cancel(service, row["id"])["job"]["status"] == "cancelled"


# ---------------------------------------------------------------- the dashboard API


@pytest.fixture()
def client(store, config):
    app = FastAPI()
    app.include_router(build_media_router(store, MediaStorage(config)))
    return TestClient(app)


def test_the_jobs_api_lists_advances_and_cancels_with_no_key_in_any_answer(
        store, config, ctx, monkeypatch, client):
    connect(config, "xai", key="sk-api-secret-value")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={"request_id": "v-api"}))
    row = submit(service_for(store, config), ctx, "xai-video:xai", "video", "waves", "k-api")
    listing = client.get("/api/v1/media/jobs").json()["jobs"]
    assert [j["id"] for j in listing] == [row["id"]] and listing[0]["status"] == "running"
    assert listing[0]["prompt_preview"] == "waves"
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={"status": "pending"}))
    advanced = client.post(f"/api/v1/media/jobs/{row['id']}/advance")
    assert advanced.status_code == 200 and advanced.json()["action"] == "polled"
    cancelled = client.post(f"/api/v1/media/jobs/{row['id']}/cancel").json()
    assert cancelled["job"]["status"] == "cancel_unconfirmed"
    assert "sk-api-secret-value" not in json.dumps([listing, advanced.json(), cancelled])
    assert client.get("/api/v1/media/jobs").json()["jobs"] == []
    assert len(client.get("/api/v1/media/jobs?open=false").json()["jobs"]) == 1


def test_the_jobs_api_rejects_ids_that_are_not_job_ids(client):
    for bad in ("../x", "mj_zz", "mj_" + "0" * 15):
        assert client.get(f"/api/v1/media/jobs/{bad}").status_code in (404, 422)
    assert client.get("/api/v1/media/jobs/mj_0000000000000000").status_code == 404
    assert client.post("/api/v1/media/jobs/mj_0000000000000000/advance").status_code == 404


def test_job_routes_are_not_granted_to_paired_phones():
    assert not any(path.startswith("/api/v1/media/jobs") for _, path in REMOTE_ROUTE_CAPABILITIES)
    assert PNG


# ---------------------------------------------------------------- housekeeping and races


def test_the_held_copy_is_released_once_the_media_store_has_the_bytes(store, config, ctx, monkeypatch):
    connect(config, "xai")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(
        200, content=WAV, headers={"content-type": "audio/wav"}))
    service = service_for(store, config)
    row = submit(service, ctx, "xai-speech:xai", "audio", "hello there", "k-release")
    spool = MediaSpool(MediaStorage(config).root)
    assert spool.has(row["upstream_job_id"])
    from hutch.media import resume

    assert resume.advance(service, store, row["id"])["action"] == "finalized"
    assert not spool.has(row["upstream_job_id"]), "the duplicate must not stay on disk forever"
    again = resume.advance(service, store, row["id"])
    assert again["action"] == "none" and again["job"]["media"]["media_id"]


def test_a_second_advance_that_loses_the_race_reports_the_finished_job_not_a_failure(
        store, config, ctx, monkeypatch):
    connect(config, "xai")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(
        200, content=WAV, headers={"content-type": "audio/wav"}))
    first, second = service_for(store, config), service_for(store, config)
    row = submit(first, ctx, "xai-speech:xai", "audio", "hello there", "k-race")
    from hutch.media import resume

    original = second.finalize

    def finalize_after_the_other_finished(job_id, **kwargs):
        resume.advance(first, store, job_id)                # the other request wins first
        return original(job_id, **kwargs)

    second.finalize = finalize_after_the_other_finished
    out = resume.advance(second, store, row["id"])
    assert out["action"] == "none" and "another request" in out["note"]


def test_sweep_removes_only_old_entries_that_no_open_job_references(store, config, ctx, monkeypatch):
    from hutch.media.ledger import sweep_orphans
    import os

    connect(config, "xai")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(
        200, content=WAV, headers={"content-type": "audio/wav"}))
    service = service_for(store, config)
    row = submit(service, ctx, "xai-speech:xai", "audio", "hello there", "k-sweep")
    spool = MediaSpool(MediaStorage(config).root)
    orphan = spool.put(WAV)
    for handle in (row["upstream_job_id"], orphan):
        os.utime(spool.root / f"{handle}.json", (1_000_000_000, 1_000_000_000))
    assert sweep_orphans(store, spool) == 1
    assert spool.has(row["upstream_job_id"]) and not spool.has(orphan)


def test_a_route_that_cannot_be_filled_fails_before_sending_and_does_not_claim_a_charge():
    import dataclasses
    from hutch.media.providers.route_backend import RouteBackendError, SyncRouteBackend
    from hutch.media.providers.route_spec import load_routes

    route = dataclasses.replace(load_routes()["elevenlabs-speech"], defaults={})
    sent: list[int] = []
    backend = SyncRouteBackend(route, base_url="https://unit.test", api_key="k",
                               client=httpx.Client(transport=httpx.MockTransport(
                                   lambda r: sent.append(1) or httpx.Response(200))))
    with pytest.raises(RouteBackendError) as raised:
        backend.submit({"prompt": "hello"})
    assert "nothing was sent" in str(raised.value) and "billed" not in str(raised.value)
    assert sent == []


def test_a_resumed_speech_job_keeps_the_providers_measured_tokens(store, config, ctx, monkeypatch):
    from hutch.media import resume
    from tests.support.audio import add_xiaomi, no_xiaomi_env
    from tests.test_media_speech import tts_response

    no_xiaomi_env(monkeypatch)
    add_xiaomi(config, name="mimo")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json=tts_response()))
    row = submit(service_for(store, config), ctx, "speech:mimo", "audio", "Hutch speech check.", "k-mimo")
    out = resume.advance(service_for(store, config), store, row["id"])          # a "new process"
    assert out["action"] == "finalized", out
    usage = store._db.execute("SELECT prompt_tokens, completion_tokens, kind, account_id FROM usage "
                              "WHERE run_id = ?", (ctx.run.id,)).fetchone()
    assert tuple(usage) == (12, 90, "speech", "mimo")
