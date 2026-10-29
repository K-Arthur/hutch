"""MediaJobService: the honest state machine. State transitions, idempotent
submit (no double billing), immediate upstream-id recording, cancel_unconfirmed,
startup reconcile, and the deterministic record_local path, against a fake
backend, an in-process protocol stand-in. Also pins the two tools' contracts."""

from __future__ import annotations

import struct
import zlib

import pytest

from hutch.media import (MEDIA_KINDS, MediaJobError, MediaJobService, MediaStorage,
                         MediaUnavailableError, render_flowchart, service_status,
                         validate_flowchart)
from hutch.media.providers.base import VERIFICATION_TAG
from hutch.outputblocks import parse_blocks
from hutch.safety import PolicyEngine
from hutch.store import Store
from hutch.tools.base import ToolContext
from hutch.tools.media import CreateMediaTool, RenderDiagramTool


def make_png(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        blob = struct.pack(">I", len(data)) + tag + data
        return blob + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xca\xfe\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeBackend:
    """Protocol stand-in: counts every billable call so tests can PROVE a retry
    never re-submits."""

    name = "fake"

    def __init__(self, *, poll_status: str = "succeeded", poll_error: str = "",
                 cancel_result: str = "confirm", fail_submit: str = "",
                 fetch_mode: str = "bytes"):
        self.submit_calls = 0
        self.poll_calls = 0
        self.fetch_calls = 0
        self.cancel_calls = 0
        self.poll_status = poll_status
        self.poll_error = poll_error
        self.cancel_result = cancel_result
        self.fail_submit = fail_submit
        self.fetch_mode = fetch_mode      # NOT 'fetch': that name is the method

    def capabilities(self) -> dict:
        return {"backend": self.name, "kinds": ["image", "video"],
                "output_formats": {"image": ["png"], "video": ["mp4"]},
                "max_width": 1024, "max_height": 1024, "max_seconds": None,
                "editing": False, "partial_previews": False, "verified": VERIFICATION_TAG}

    def submit(self, req: dict) -> str:
        self.submit_calls += 1
        if self.fail_submit:
            raise RuntimeError(self.fail_submit)
        return f"up-{self.submit_calls:04d}"

    def poll(self, job: dict) -> dict:
        self.poll_calls += 1
        if self.poll_status == "failed":
            return {"status": "failed", "error": self.poll_error or "the backend failed"}
        return {"status": self.poll_status}

    def fetch(self, job: dict) -> bytes:
        self.fetch_calls += 1
        if self.fetch_mode == "str":
            return "https://expiring.example/one-shot-blob"   # protocol violation
        return make_png()

    def cancel(self, job: dict):
        self.cancel_calls += 1
        return {"cancelled": True, "how": "fake"} if self.cancel_result == "confirm" else None


@pytest.fixture()
def service(store: Store, config) -> MediaJobService:
    return MediaJobService(store, MediaStorage(config))


RUN, CONV, KEY = "run-media-1", "conv-media-1", "key-media-1"


# ----------------------------------------------------------------- state machine


def test_submit_persists_submitting_then_records_upstream_and_runs(service):
    backend = FakeBackend()
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="a lighthouse", idempotency_key=KEY, backend_hint="fake")
    assert backend.submit_calls == 1
    assert row["status"] == "running" and row["upstream_job_id"] == "up-0001"
    assert service_status(row) == "running"
    stored = service.store.get_media_job(row["id"])
    assert stored["upstream_job_id"] == "up-0001", "the upstream id is recorded immediately"
    assert stored["requested"]["prompt"] == "a lighthouse"


def test_submit_failure_marks_failed_without_a_charge_claim(service):
    backend = FakeBackend(fail_submit="provider 500")
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY + "-f", backend_hint="fake")
    assert row["status"] == "failed" and service_status(row) == "failed"
    assert "upstream submit failed" in row["error"]
    assert "no provider charge should exist" in row["cost_note"]
    assert row["upstream_job_id"] is None


def test_duplicate_key_same_request_returns_the_existing_job_without_rebilling(service):
    backend = FakeBackend(poll_status="failed", poll_error="nope")
    service.backends["fake"] = backend
    first = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                           prompt="same", idempotency_key=KEY, backend_hint="fake")
    service.poll(first["id"], backend)
    assert service.store.get_media_job(first["id"])["status"] == "failed"
    # The retried submit returns the existing job, the backend is NOT called again.
    again = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                           prompt="same", idempotency_key=KEY, backend_hint="fake")
    assert again["id"] == first["id"]
    assert backend.submit_calls == 1, "a retried submit must never re-bill"


def test_duplicate_key_with_a_different_request_is_refused_loudly(service):
    service.backends["fake"] = FakeBackend()
    service.submit(run_id=RUN, conversation_id=CONV, kind="image", prompt="one",
                   idempotency_key=KEY, backend_hint="fake")
    with pytest.raises(MediaJobError, match="different"):
        service.submit(run_id=RUN, conversation_id=CONV, kind="image", prompt="two",
                       idempotency_key=KEY, backend_hint="fake")


def test_poll_records_upstream_terminal_states_honestly(service):
    backend = FakeBackend(poll_status="failed", poll_error="safety filter")
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    row = service.poll(row["id"], backend)
    assert row["status"] == "failed" and "safety filter" in row["error"]
    backend2 = FakeBackend(poll_status="cancelled")
    service.backends["fake"] = backend2
    row2 = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                          prompt="y", idempotency_key=KEY + "-c", backend_hint="fake")
    row2 = service.poll(row2["id"], backend2)
    assert row2["status"] == "cancelled"


def test_submit_validates_the_request(service):
    service.backends["fake"] = FakeBackend()
    for kwargs in ({"kind": "memecom", "prompt": "x"},
                   {"kind": "image", "prompt": ""},
                   {"kind": "image", "prompt": "x", "width": 4}):
        with pytest.raises(MediaJobError):
            service.submit(run_id=RUN, conversation_id=CONV, idempotency_key=KEY + str(kwargs),
                           backend_hint="fake", **kwargs)


def test_no_capable_backend_is_honest_absence(service):
    with pytest.raises(MediaUnavailableError, match="no configured backend"):
        service.submit(run_id=RUN, conversation_id=CONV, kind="video", prompt="x",
                       idempotency_key=KEY, backend_hint=None)


# ----------------------------------------------------------------- finalize


def test_finalize_validates_stores_and_builds_the_contract_payload(service):
    backend = FakeBackend()
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="chart", idempotency_key=KEY, backend_hint="fake")
    payload, final = service.finalize(row["id"], alt_text="A generated chart.")
    assert final["status"] == "succeeded" and final["result"]["media_id"] == payload["media_id"]
    assert payload["kind"] == "image" and payload["generated_by"] == "provider"
    assert payload["backend"] == "fake" and payload["mime"] == "image/png"
    assert payload["width"] == 4 and payload["height"] == 4
    # The stored payload must satisfy the block contract's own media payload model.
    from hutch.outputblocks import MediaPayload
    MediaPayload.model_validate(payload)
    data, manifest = service.media_store.read_version(payload["media_id"], 1)
    assert data == make_png() and manifest["sha256"] == payload["sha256"]
    assert "cannot verify" in final["cost_note"], "cost uncertainty is reported"


def test_finalize_never_stores_a_url_as_the_result(service):
    backend = FakeBackend(fetch_mode="str")
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    final = service.finalize(row["id"], alt_text="x")
    row = service.store.get_media_job(row["id"])
    assert row["status"] == "failed"
    assert "protocol violation" in row["error"] and "never a result" in row["error"]


def test_finalize_refuses_a_kind_mismatch_instead_of_storing_incoherence(service):
    backend = FakeBackend()          # fetch returns a PNG
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="video",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    service.finalize(row["id"], alt_text="x")
    row = service.store.get_media_job(row["id"])
    assert row["status"] == "failed" and "mismatch" in row["error"]


def test_finalize_requires_readable_alt_text(service):
    service.backends["fake"] = FakeBackend()
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    with pytest.raises(MediaJobError, match="alt_text"):
        service.finalize(row["id"], alt_text="   ")


# ----------------------------------------------------------------- cancel


def test_cancel_confirmed_is_cancelled(service):
    service.backends["fake"] = FakeBackend(cancel_result="confirm")
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    row = service.cancel(row["id"], wait_seconds=0.1)
    assert row["status"] == "cancelled" and service_status(row) == "cancelled"
    assert row["result"]["cancelled_by"] == "request"


def test_cancel_unconfirmed_is_never_silently_cancelled(service):
    backend = FakeBackend(cancel_result="refuse", poll_status="running")
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    row = service.cancel(row["id"], wait_seconds=0.2)
    assert service_status(row) == "cancel_unconfirmed"
    assert row["status"] != "cancelled", "an unconfirmed cancel is never recorded as cancelled"
    assert row["status"] == "failed"      # the honest store-side terminal choice
    assert row["error"].startswith("cancel_unconfirmed:")
    assert "may still be running and billing" in row["error"]
    assert "NOT recorded as cancelled" in row["cost_note"]


def test_cancel_loses_the_race_to_a_completed_job(service):
    backend = FakeBackend(cancel_result="refuse", poll_status="succeeded")
    service.backends["fake"] = backend
    row = service.submit(run_id=RUN, conversation_id=CONV, kind="image",
                         prompt="x", idempotency_key=KEY, backend_hint="fake")
    row = service.cancel(row["id"], wait_seconds=0.2)
    assert row["status"] == "succeeded"
    assert row["result"]["bytes"] == "not_fetched", \
        "a job that finished mid-cancel has no fetched bytes"
    assert "before the cancellation took effect" in row["cost_note"]


# ----------------------------------------------------------------- reconcile


def test_reconcile_marks_orphans_honestly(store: Store, config):
    # Jobs left behind by a previous process: a fresh service instance owns none of them.
    stale_backend = FakeBackend()
    service = MediaJobService(store, MediaStorage(config), backends={"fake": stale_backend})
    q = store.create_media_job(run_id="run-o", conversation_id="c", kind="image",
                               backend="fake", idempotency_key="o-queued",
                               requested={"kind": "image", "prompt": "x"})
    r_cancel = store.create_media_job(run_id="run-o", conversation_id="c", kind="image",
                                      backend="fake", idempotency_key="o-cancel",
                                      requested={"kind": "image", "prompt": "x"})
    store.record_upstream_job(r_cancel["id"], "up-cancel")
    store.transition_media_job(r_cancel["id"], "running")
    r_success = store.create_media_job(run_id="run-o", conversation_id="c", kind="image",
                                       backend="fake", idempotency_key="o-success",
                                       requested={"kind": "image", "prompt": "x"})
    store.record_upstream_job(r_success["id"], "up-success")
    store.transition_media_job(r_success["id"], "running")
    r_nobackend = store.create_media_job(run_id="run-o", conversation_id="c", kind="image",
                                         backend="ghost", idempotency_key="o-ghost",
                                         requested={"kind": "image", "prompt": "x"})
    store.record_upstream_job(r_nobackend["id"], "up-ghost")
    store.transition_media_job(r_nobackend["id"], "running")

    class MixedBackend(FakeBackend):
        def poll(self, job):
            if job["upstream_job_id"] == "up-cancel":
                return {"status": "cancelled"}
            if job["upstream_job_id"] == "up-success":
                return {"status": "succeeded"}
            return {"status": "running"}

    summary = service.reconcile(run_ids=["run-o"], backends={"fake": MixedBackend()})
    assert summary["examined"] == 4 and summary["skipped_active"] == 0
    queued = store.get_media_job(q["id"])
    assert queued["status"] == "failed"
    assert queued["error"].startswith("orphaned_submitting:")
    assert "may have started and may be billable" in queued["cost_note"]
    cancelled = store.get_media_job(r_cancel["id"])
    assert cancelled["status"] == "cancelled"
    succeeded = store.get_media_job(r_success["id"])
    assert succeeded["status"] == "succeeded"
    assert succeeded["result"]["bytes"] == "not_fetched", \
        "an unfetched upstream success never pretends to hold media"
    ghost = store.get_media_job(r_nobackend["id"])
    assert ghost["status"] == "failed" and ghost["error"].startswith("orphaned_running:")


def test_reconcile_skips_jobs_this_instance_is_driving(store: Store, config):
    service = MediaJobService(store, MediaStorage(config), backends={"fake": FakeBackend()})
    row = service.submit(run_id="run-live", conversation_id="c", kind="image",
                         prompt="x", idempotency_key="live-1", backend_hint="fake")
    summary = service.reconcile(run_ids=["run-live"], backends={})
    assert summary["skipped_active"] == 1
    assert store.get_media_job(row["id"])["status"] == "running"


# ----------------------------------------------------------------- record_local


def test_record_local_renders_stores_and_dedups_without_re_rendering(service):
    renders = []

    def produce():
        renders.append(1)
        svg = render_flowchart({"nodes": [{"id": "a", "label": "A"}],
                                "edges": [], "direction": "LR"})
        return (svg.encode("utf-8"),
                {"format": "svg+xml", "width": 200, "height": 80,
                 "alt_text": "A tiny flowchart with a single node."})

    requested = {"kind": "image", "diagram": "tiny", "nodes": 1, "edges": 0}
    row = service.record_local(run_id=RUN, conversation_id=CONV, kind="image",
                               requested=requested, idempotency_key="local-1",
                               produce=produce)
    assert row["status"] == "succeeded" and row["backend"] == "deterministic"
    payload = row["result"]
    assert payload["generated_by"] == "deterministic" and payload["mime"] == "image/svg+xml"
    again = service.record_local(run_id=RUN, conversation_id=CONV, kind="image",
                                 requested=requested, idempotency_key="local-1",
                                 produce=produce)
    assert again["id"] == row["id"] and len(renders) == 1, "identical retry does not re-render"


def test_record_local_failure_marks_failed_with_the_renderer_error(service):
    def produce():
        raise ValueError("layout blew up")
    row = service.record_local(run_id=RUN, conversation_id=CONV, kind="image",
                               requested={"kind": "image"}, idempotency_key="local-bad",
                               produce=produce)
    assert row["status"] == "failed" and "layout blew up" in row["error"]


# ----------------------------------------------------------------- tools


def _make_ctx(store: Store, config, tmp_path, *, gate):
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    from hutch.approvals import ApprovalGate
    bot = Bot(name=f"media-bot-{abs(hash(tmp_path)) % 100000}", model="mock/demo",
              tools=["render_diagram", "create_media"], approval_mode=ApprovalMode.auto)
    if not store.get_bot(bot.name):
        store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="test", status=RunStatus.running)
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    if gate is None:
        gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda ev: None,
                            poll_seconds=0.01)
    return ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate,
                       config=config, workspace=workspace)


class FakeGate:
    """Records gate decisions; auto-allows, so tests prove the tool ASKED, not
    that a human answered."""

    def __init__(self):
        self.calls = []
        self.last_authorization = {"tool": "media", "source": "test"}

    def decide(self, tool, action, detail, decision=None, **kwargs):
        self.calls.append({"tool": tool, "action": action, "decision": decision,
                           "kwargs": kwargs})


def test_render_diagram_tool_stores_media_and_presents_valid_blocks(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=None)
    result = RenderDiagramTool().run(
        {"title": "Ship it", "direction": "LR",
         "nodes": [{"id": "build", "label": "Build", "group": "ci"},
                   {"id": "test", "label": "Test", "group": "ci"},
                   {"id": "ship", "label": "Ship"}],
         "edges": [{"from": "build", "to": "test", "label": "green"},
                   {"from": "test", "to": "ship"},
                   {"from": "test", "to": "build", "label": "on failure"}]},
        ctx)
    assert result.ok, result.output
    blocks = result.data["blocks"]
    assert [b["kind"] for b in blocks] == ["media", "flowchart"]
    parsed, errors = parse_blocks(blocks)
    assert not errors, errors
    media_payload = parsed[0]["payload"]
    assert media_payload["generated_by"] == "deterministic"
    assert media_payload["backend"] == "deterministic"
    job = store.get_media_job(result.data["job_id"])
    assert job["status"] == "succeeded" and job["backend"] == "deterministic"
    data, manifest = MediaStorage(config).read_version(media_payload["media_id"], 1)
    assert b"<svg" in data and manifest["sha256"] == media_payload["sha256"]
    assert "cyclic" not in result.output
    assert ctx.run.id in blocks[0]["provenance"]["run_id"]


def test_render_diagram_refuses_invalid_graphs_and_keeps_the_source(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=None)
    payload = {"title": "Broken", "nodes": [{"id": "a", "label": "A"}],
               "edges": [{"from": "a", "to": "ghost"}]}
    result = RenderDiagramTool().run(dict(payload), ctx)
    assert not result.ok
    assert "dangling" in result.output or "does not match any declared node" in result.output
    assert "'ghost'" in result.output
    assert "Source:" in result.output, "the caller's structure is preserved, never lost"
    assert result.data == {}


def test_create_media_animation_is_deterministic_and_free(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=None)
    tool = CreateMediaTool()
    result = tool.run({"kind": "animation", "prompt": "the water cycle",
                       "frames": [{"label": "Evaporation", "duration_seconds": 1.5},
                                  {"label": "Condensation"},
                                  {"label": "Precipitation", "detail": "rain"}]}, ctx)
    assert result.ok, result.output
    parsed, errors = parse_blocks(result.data["blocks"])
    assert not errors, errors
    payload = parsed[0]["payload"]
    assert payload["kind"] == "animation" and payload["mime"] == "image/svg+xml"
    assert payload["generated_by"] == "deterministic" and payload["duration_seconds"] == 5.5
    assert result.data["content_url"].startswith("/api/v1/media/")
    assert "nothing was billed" in result.output


def test_create_media_animation_frames_that_are_too_long_never_lose_the_source(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=None)
    frames = [{"label": f"f{i}"} for i in range(500)]
    result = CreateMediaTool().run({"kind": "animation", "prompt": "x", "frames": frames}, ctx)
    assert not result.ok and "Frames:" in result.output and "199" in result.output


def test_create_media_provider_requires_outward_approval_and_reports_uncertain_cost(
        store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=FakeGate())
    backend = FakeBackend()
    tool = CreateMediaTool(backends={"fake": backend}, poll_interval=0.0, max_polls=3)
    assert tool.effect({"kind": "image"}, ctx) == "web"
    assert tool.effect({"kind": "animation"}, ctx) == ""
    result = tool.run({"kind": "image", "prompt": "a lighthouse in fog"}, ctx)
    assert result.ok, result.output
    gate_call = ctx.gate.calls[0]
    assert gate_call["tool"] == "media"
    assert gate_call["decision"].verdict.value == "ask"
    assert gate_call["decision"].outward is True, "outward asks are never sticky (SR-4)"
    assert backend.submit_calls == 1 and backend.fetch_calls == 1
    parsed, errors = parse_blocks(result.data["blocks"])
    assert not errors, errors
    assert parsed[0]["payload"]["generated_by"] == "provider"
    assert "cannot verify the exact amount" in result.output


def test_create_media_with_no_backend_refuses_instead_of_fabricating(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=FakeGate())
    result = CreateMediaTool(backends={}, poll_interval=0.0).run(
        {"kind": "video", "prompt": "drone shot"}, ctx)
    assert not result.ok
    assert "does not substitute stock assets" in result.output
    assert ctx.gate.calls == [], "an unavailable backend is reported before any approval ask"


def test_create_media_rehearsal_never_reaches_a_provider(store, config, tmp_path):
    ctx = _make_ctx(store, config, tmp_path, gate=FakeGate())
    ctx.dry_run = True
    backend = FakeBackend()
    result = CreateMediaTool(backends={"fake": backend}, poll_interval=0.0).run(
        {"kind": "image", "prompt": "x"}, ctx)
    assert result.ok and result.data.get("simulated") is True
    assert backend.submit_calls == 0
