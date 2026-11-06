"""Task-protocol media routes (submit, poll, fetch, cancel) and the price estimates (Phase 6).

Same evidence rule as ``test_media_routes.py``: the protocol each route declares is verified
against ``httpx.MockTransport`` replies shaped after the vendor documentation, and the result
download goes through a real loopback server and the real pinned client. No vendor account was
exercised.
"""

from __future__ import annotations

import json

import httpx
import pytest

from hutch.media.cost import estimate, load_prices
from hutch.media.providers.base import MediaRefused
from hutch.media.providers.route_backend import RouteBackendError
from hutch.media.providers.route_spec import load_routes
from hutch.media.providers.route_task import TaskRouteBackend
from tests.test_media_durability import PNG, loopback  # noqa: F401 - loopback is a fixture

ROUTES = load_routes()


# ---------------------------------------------------------------- task routes


def task(route_id: str, handler) -> TaskRouteBackend:
    return TaskRouteBackend(ROUTES[route_id], base_url="https://unit.test", api_key="unit-key",
                            credential_label="test",
                            client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_xai_video_full_lifecycle_through_a_real_result_server(loopback):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "req-1"})
        pending = sum(1 for r in seen if r.method == "GET") < 2
        return httpx.Response(200, json={"status": "pending"} if pending else
                              {"status": "done", "video": {"url": f"{loopback}/ok"}})

    backend = task("xai-video", handler)
    task_id = backend.submit({"prompt": "waves", "seconds": 4})
    assert task_id == "req-1"
    sent = json.loads(seen[0].content)
    assert sent == {"model": "grok-imagine-video", "prompt": "waves", "duration": 4}
    job = {"upstream_job_id": task_id}
    assert backend.poll(job)["status"] == "running"
    assert backend.poll(job)["status"] == "succeeded"
    assert backend.fetch(job) == PNG
    assert seen[1].url.path == "/videos/req-1"


def test_xai_video_has_no_documented_cancel_so_cancel_is_unconfirmed():
    assert task("xai-video", lambda r: httpx.Response(200, json={})).cancel({"upstream_job_id": "x"}) is None


def test_an_unlisted_status_keeps_polling_and_an_expired_one_fails():
    states = iter(["queued-somewhere", "expired"])
    backend = task("xai-video", lambda r: httpx.Response(200, json={"status": next(states)}))
    job = {"upstream_job_id": "x"}
    assert backend.poll(job)["status"] == "running"
    failed = backend.poll(job)
    assert failed["status"] == "failed" and "expired" in failed["error"]


def test_a_poll_hiccup_does_not_fail_paid_work_but_an_unknown_task_does():
    job = {"upstream_job_id": "x"}
    assert task("xai-video", lambda r: httpx.Response(503, json={})).poll(job)["status"] == "running"
    assert task("xai-video", lambda r: httpx.Response(401, json={})).poll(job)["status"] == "running"
    gone = task("xai-video", lambda r: httpx.Response(404, json={})).poll(job)
    assert gone["status"] == "failed" and "no longer knows" in gone["error"]


def test_a_task_accepted_without_an_id_says_the_provider_may_have_billed():
    with pytest.raises(RouteBackendError, match="no task id.*may have billed"):
        task("xai-video", lambda r: httpx.Response(200, json={})).submit({"prompt": "x"})


def test_fal_uses_key_auth_no_retry_owner_app_urls_and_honest_cancel(loopback):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "r9"})
        if path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if path.endswith("/cancel"):
            return httpx.Response(int(request.url.params.get("code", "200")), json={})
        return httpx.Response(200, json={"images": [{"url": f"{loopback}/ok"}], "has_nsfw_concepts": [False]})

    backend = task("fal-image", handler)
    job = {"upstream_job_id": backend.submit({"prompt": "x"})}
    assert seen[0].url.path == "/fal-ai/flux/dev"
    assert seen[0].headers["authorization"] == "Key unit-key" and seen[0].headers["x-fal-no-retry"] == "1"
    assert backend.poll(job) == {"status": "succeeded", }
    assert seen[1].url.path == "/fal-ai/flux/requests/r9/status", "a sub-path on the status URL returns 405"
    assert backend.fetch(job) == PNG
    assert backend.cancel(job) == {"cancelled": True, "how": "PUT 200"}


def test_fal_cancel_202_means_requested_not_confirmed():
    backend = task("fal-video", lambda r: httpx.Response(202, json={"status": "CANCELLATION_REQUESTED"}))
    assert backend.cancel({"upstream_job_id": "r"}) is None


def test_fal_completed_with_an_error_is_a_failure():
    backend = task("fal-image", lambda r: httpx.Response(
        200, json={"status": "COMPLETED", "error": "model crashed", "error_type": "x"}))
    state = backend.poll({"upstream_job_id": "r"})
    assert state["status"] == "failed" and "model crashed" in state["error"]


def test_fal_nsfw_flag_is_a_refusal_not_a_blank_image(loopback):
    def handler(request):
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(200, json={"images": [{"url": f"{loopback}/ok"}], "has_nsfw_concepts": [True]})

    with pytest.raises(MediaRefused, match="blank"):
        task("fal-image", handler).fetch({"upstream_job_id": "r"})


def pixverse_handler(status: int, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"ErrCode": 0, "ErrMsg": "Success", "Resp": {"video_id": 77}})
        return httpx.Response(200, json={"ErrCode": 0, "Resp": {"status": status, "url": "http://x"}})
    return handler


def test_pixverse_sends_a_fresh_trace_id_per_request_and_moderation_is_a_refusal():
    seen: list = []
    backend = task("pixverse-video", pixverse_handler(7, seen))
    job = {"upstream_job_id": backend.submit({"prompt": "x", "seconds": 5})}
    backend.poll(job)
    refused = backend.poll(job)
    assert refused["status"] == "failed" and refused["refused"] is True
    traces = [r.headers["ai-trace-id"] for r in seen]
    assert len(set(traces)) == len(traces) >= 3, "reusing a trace id blocks a new generation"
    assert seen[0].headers["api-key"] == "unit-key" and "authorization" not in seen[0].headers
    assert json.loads(seen[0].content)["quality"] == "540p" and job["upstream_job_id"] == "77"


def test_pixverse_statuses_map_to_running_done_and_failed():
    for status, expected in ((5, "running"), (1, "succeeded"), (8, "failed")):
        assert task("pixverse-video", pixverse_handler(status, [])).poll(
            {"upstream_job_id": "77"})["status"] == expected


def test_pixverse_error_code_on_submit_is_an_error_not_a_job():
    handler = lambda r: httpx.Response(200, json={"ErrCode": 500039, "ErrMsg": "balance"})  # noqa: E731
    with pytest.raises(RouteBackendError, match="500039.*balance"):
        task("pixverse-video", handler).submit({"prompt": "x"})


def test_a_task_backend_needs_nothing_but_the_ledger_row_after_a_restart(loopback):
    handler = lambda r: httpx.Response(200, json={"status": "done", "video": {"url": f"{loopback}/ok"}})  # noqa: E731
    reborn = task("xai-video", handler)           # a different instance than the one that submitted
    job = {"upstream_job_id": "req-from-before-the-restart"}
    assert reborn.poll(job)["status"] == "succeeded" and reborn.fetch(job) == PNG


# ---------------------------------------------------------------- prices


def test_cost_estimates_are_labeled_estimates_and_unknown_is_unknown():
    priced = estimate("google-image", {})
    assert priced.priced and priced.usd == pytest.approx(0.0336)
    assert "estimate, not a quote" in priced.sentence()
    speech = estimate("google-speech", {"prompt": "x" * 150})
    assert speech.usd == pytest.approx(10 * 0.000225) and "2027-01-01" in speech.sentence()
    unknown = estimate("xai-video", {"seconds": 5})
    assert not unknown.priced and unknown.sentence().startswith("cost unknown")
    assert not estimate("no-such-route", {}).priced


def test_no_estimate_is_ever_printed_without_its_source_and_date():
    for key, row in load_prices().items():
        assert row["source"].startswith("https://") and row["read"] == "2026-11-06", key
