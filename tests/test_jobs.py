"""Durable jobs: step checkpoints, restart resume, retry policy, unknown effects, and the real document pipeline."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from hutch import jobs as job_mod
from hutch import pipelines, sources
from hutch.engine import Engine
from hutch.jobs import HandlerContext, JobRunner, JobSpec, StepSpec
from hutch.models import ApprovalMode, Bot, Run, RunStatus, Task, iso, utcnow
from hutch.monitoring import SourcePump
from hutch.sources import SourceRuntime

HANDLER_CALLS: dict[str, int] = {}


def _counter(name: str) -> None:
    HANDLER_CALLS[name] = HANDLER_CALLS.get(name, 0) + 1


def _bot(store, name="job-bot") -> Bot:
    return store.create_bot(Bot(name=name, model="mock/demo", approval_mode=ApprovalMode.auto))


@pytest.fixture(autouse=True)
def _register_test_definition():
    """Tiny definitions used by the core tests; handlers count their calls."""
    job_mod.register_job(JobSpec(kind="test_two_step", revision=1, steps=(
        StepSpec("test-a", "handler"),
        StepSpec("test-b", "handler", deps=("test-a",), retries=1),
    )))
    job_mod.register_job(JobSpec(kind="test_run_step", revision=1, steps=(
        StepSpec("work", "run", retries=1),
    )))

    def handler_a(job_input, prior, context):
        _counter("a")
        return {"from_a": job_input.get("seed", "seed")}, ""

    def handler_b(job_input, prior, context):
        _counter("b")
        if HANDLER_CALLS.get("b") == 1 and job_input.get("fail_first_b"):
            return {}, "transient failure"
        return {"from_b": (prior.get("test-a") or {}).get("from_a", "?")}, ""

    job_mod.register_handler("test-a", handler_a)
    job_mod.register_handler("test-b", handler_b)
    HANDLER_CALLS.clear()
    yield
    HANDLER_CALLS.clear()


def _advance(engine, store, job_id, *, timeout=20.0):
    deadline = time.time() + timeout
    engine._is_supervisor = True
    while time.time() < deadline:
        engine.jobs.pump()
        engine.dispatch_pending()
        job = store.get_job(job_id)
        if job["status"] in ("succeeded", "failed", "blocked"):
            return job
        time.sleep(0.05)
    return store.get_job(job_id)


# ---------------------------------------------------------------- core jobs

def test_job_runs_handlers_in_order_and_checkpoints_outputs(store, config):
    bot = _bot(store)
    job, created = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="one",
                                    input={"seed": "alpha"})
    assert created is True
    engine = Engine(config, store, light=True)
    result = _advance(engine, store, job["id"])
    engine.jobs.shutdown()

    assert result["status"] == "succeeded"
    steps = {step["step_key"]: step for step in store.job_steps(job["id"])}
    assert steps["test-a"]["status"] == "succeeded" and steps["test-b"]["status"] == "succeeded"
    assert steps["test-b"]["output"]["from_b"] == "alpha", "a downstream step reads the checkpointed output"
    assert steps["test-a"]["input_hash"] and steps["test-a"]["attempt"] == 1


def test_identical_occurrence_is_never_admitted_twice(store):
    bot = _bot(store)
    first, created_first = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="same",
                                            input={"seed": "x"})
    second, created_second = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="same",
                                              input={"seed": "x"})
    assert created_first is True and created_second is False
    assert first["id"] == second["id"]
    assert len(store.list_jobs()) == 1


def test_step_attempt_is_never_started_twice(store):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="claim", input={})
    assert store.start_job_step(job["id"], "test-a", 1, input_hash="h") is True
    assert store.start_job_step(job["id"], "test-a", 1, input_hash="h") is False
    assert store.finish_job_step(job["id"], "test-a", 1, status="succeeded", output={"ok": True}) is True
    assert store.finish_job_step(job["id"], "test-a", 1, status="failed") is False, \
        "a sealed attempt is immutable"


def test_handler_failure_retries_only_within_policy(store, config):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="retry",
                              input={"fail_first_b": True})
    engine = Engine(config, store, light=True)
    result = _advance(engine, store, job["id"])
    engine.jobs.shutdown()

    assert result["status"] == "succeeded"
    attempts = [step for step in store.job_steps(job["id"]) if step["step_key"] == "test-b"]
    assert [a["attempt"] for a in attempts] == [1, 2]
    assert attempts[0]["status"] == "failed" and attempts[1]["status"] == "succeeded"


def test_restart_resumes_at_the_first_incomplete_step(store, config):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="resume", input={})
    store.start_job_step(job["id"], "test-a", 1, input_hash="h")
    store.finish_job_step(job["id"], "test-a", 1, status="succeeded", output={"from_a": "kept"})

    engine = Engine(config, store, light=True)      # a new process over the same state directory
    result = _advance(engine, store, job["id"])
    engine.jobs.shutdown()

    assert result["status"] == "succeeded"
    assert HANDLER_CALLS.get("a", 0) == 0, "a completed checkpoint is never re-executed"
    steps = {step["step_key"]: step for step in store.job_steps(job["id"])}
    assert steps["test-b"]["output"]["from_b"] == "kept"


def test_changed_definition_revision_blocks_instead_of_reinterpreting(store, config):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_two_step", occurrence_key="rev", input={},
                              definition_revision=99)
    engine = Engine(config, store, light=True)
    engine._is_supervisor = True
    engine.jobs.pump()
    engine.jobs.shutdown()

    blocked = store.get_job(job["id"])
    assert blocked["status"] == "blocked" and "definition changed" in blocked["error"]


def test_unknown_effect_run_step_blocks_and_is_never_replayed(store, config):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_run_step", occurrence_key="unknown", input={})
    run = Run(bot_id=bot.id, prompt="do it", origin="job", job_id=job["id"], job_step="work")
    task = Task(bot_id=bot.id, kind="on_demand", prompt="do it")
    store.submit_run(run, task)
    store.start_job_step(job["id"], "work", 1, input_hash="h", run_id=run.id)
    store.transition_run(run.id, RunStatus.running, fence=run.fence)
    store.transition_run(run.id, RunStatus.outcome_unknown, fence=run.fence)

    engine = Engine(config, store, light=True)
    engine._is_supervisor = True
    engine.jobs.pump()
    engine.jobs.pump()
    engine.jobs.shutdown()

    steps = store.job_steps(job["id"])
    assert [step["status"] for step in steps] == ["unknown"]
    blocked = store.get_job(job["id"])
    assert blocked["status"] == "blocked" and "needs review" in blocked["error"]


def test_interrupted_effect_free_run_step_retries_under_policy(store, config):
    bot = _bot(store)
    job, _ = store.create_job(bot_id=bot.id, kind="test_run_step", occurrence_key="retry-run", input={})
    first = Run(bot_id=bot.id, prompt="do it", origin="job", job_id=job["id"], job_step="work")
    store.submit_run(first, Task(bot_id=bot.id, kind="on_demand", prompt="do it"))
    store.start_job_step(job["id"], "work", 1, input_hash="h", run_id=first.id)
    store.transition_run(first.id, RunStatus.running, fence=first.fence)
    store.transition_run(first.id, RunStatus.failed, fence=first.fence, exit_reason="interrupted",
                         error="worker disappeared")

    engine = Engine(config, store, light=True)
    engine._is_supervisor = True
    engine.jobs.pump()
    engine.jobs.shutdown()

    attempts = store.job_steps(job["id"])
    assert [a["status"] for a in attempts] == ["failed"]
    assert attempts[0]["output"]["interrupted"] is True
    assert store.get_job(job["id"])["status"] in ("queued", "running"), "a policy retry is still possible"


# ------------------------------------------------------- document pipeline

def _make_text_pdf(path: Path, lines: list[str]) -> None:
    """A minimal valid one-page PDF with a real text layer (no dependency)."""
    stream = ("BT /F1 14 Tf 72 720 Td " + " ".join(f"({line}) Tj 0 -18 Td" for line in lines) + " ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> "
        b"/Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def _make_scanned_pdf(text_pdf: Path, path: Path, tmp: Path) -> bool:
    """Render the text page to an image and rebuild it as an image-only PDF (real scanned shape)."""
    import shutil as _shutil

    if not (_shutil.which("pdftoppm") and (_shutil.which("magick") or _shutil.which("convert"))):
        return False
    prefix = tmp / "render"
    code = subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", str(text_pdf), str(prefix)],
                          capture_output=True, check=False)
    if code.returncode != 0 or not prefix.with_suffix(".png").is_file():
        return False
    tool = _shutil.which("magick") or _shutil.which("convert")
    code = subprocess.run([tool, str(prefix.with_suffix(".png")), str(path)], capture_output=True, check=False)
    return code.returncode == 0 and path.is_file()


def test_document_pipeline_end_to_end_with_real_pdf_text_and_ocr(store, config, tmp_path):
    from shutil import which

    if which("pdftotext") is None or which("pdfinfo") is None:
        pytest.skip("poppler is not installed")
    bot = _bot(store, name="docs-bot")
    text_pdf = tmp_path / "invoice.pdf"
    _make_text_pdf(text_pdf, ["Invoice 42", "Total 1,240 dollars", "Due October 30 2026"])
    scanned_pdf = tmp_path / "scan.pdf"
    scanned = _make_scanned_pdf(text_pdf, scanned_pdf, tmp_path)

    paths = [str(text_pdf)] + ([str(scanned_pdf)] if scanned else [])
    if not scanned:
        pytest.skip("ImageMagick/pdftoppm unavailable: the scanned-page OCR case cannot be exercised")
    job, _ = store.create_job(bot_id=bot.id, kind="document_pipeline", occurrence_key="batch-1",
                              input={"paths": paths, "source_name": "Inbox",
                                     "summary_prompt": "Summarize the invoice."})
    engine = Engine(config, store, light=True)
    result = _advance(engine, store, job["id"], timeout=120)
    engine.jobs.shutdown()

    assert result["status"] == "succeeded", (result["error"], [s for s in store.job_steps(job["id"])])
    steps = {step["step_key"]: step for step in store.job_steps(job["id"])}
    assert steps["extract"]["output"]["documents"][0]["pages"] == 1
    assert steps["extract"]["output"]["documents"][1]["scanned_pages"] == [1]
    assert steps["ocr"]["output"]["ocr_pages"] >= 1, "the scanned page is OCR'd with real tesseract"
    assert steps["summarize"]["output"]["message"].startswith("Test scenario finished")
    receipt = steps["deliver"]["output"]["receipt"]
    assert receipt["index_generation"] and receipt["chunks"] >= 1
    artifact = Path(steps["deliver"]["output"]["artifact"])
    assert artifact.is_file() and steps["deliver"]["output"]["artifact_sha256"]

    # The published index is searchable with provenance and only exposes the active generation.
    generation = store.active_index_generation()
    assert generation and generation["generation"] == receipt["index_generation"]
    hits = store.search_index("Invoice")
    assert hits and hits[0]["doc_name"] == "invoice.pdf" and hits[0]["page"] == 1
    assert all(hit["doc_sha256"] for hit in hits)

    # A second run publishes a new generation and retires the previous one without deleting it.
    job2, _ = store.create_job(bot_id=bot.id, kind="document_pipeline", occurrence_key="batch-2",
                               input={"paths": [str(text_pdf)], "summary_prompt": "Summarize."})
    engine2 = Engine(config, store, light=True)
    result2 = _advance(engine2, store, job2["id"], timeout=120)
    engine2.jobs.shutdown()
    assert result2["status"] == "succeeded"
    assert store.active_index_generation()["generation"] > generation["generation"]
    with store._lock:
        retired = store._db.execute("SELECT COUNT(*) AS n FROM doc_index_generations WHERE status='retired'").fetchone()
    assert retired["n"] >= 1


def test_index_generation_is_not_visible_until_published(store):
    generation = store.start_index_generation({"a.pdf": "abc"})
    store.append_index_chunks(generation, [{"doc_name": "a.pdf", "doc_sha256": "abc", "page": 1,
                                            "chunk_index": 0, "extraction": "text", "content": "hidden words"}])
    assert store.search_index("hidden") == [], "a building generation is never searchable"
    store.publish_index_generation(generation, status="active")
    assert store.search_index("hidden"), "publishing makes the generation visible atomically"


def test_ocr_missing_dependency_blocks_without_losing_extraction(store, config, tmp_path, monkeypatch):
    bot = _bot(store, name="ocr-bot")
    text_pdf = tmp_path / "doc.pdf"
    _make_text_pdf(text_pdf, ["Scanned-looking content"])
    job, _ = store.create_job(bot_id=bot.id, kind="document_pipeline", occurrence_key="no-ocr",
                              input={"paths": [str(text_pdf)]})
    engine = Engine(config, store, light=True)
    engine._is_supervisor = True
    # pretend the page has no text layer and no OCR tools exist
    monkeypatch.setattr(pipelines, "MIN_TEXT_CHARS", 10_000)
    monkeypatch.setattr(pipelines, "_tool", lambda name: None if name in ("pdftoppm", "tesseract") else _real_tool(name))
    result = _advance(engine, store, job["id"], timeout=60)
    engine.jobs.shutdown()

    assert result["status"] == "blocked" and "OCR" in result["error"]
    steps = {step["step_key"]: step for step in store.job_steps(job["id"])}
    assert steps["ingest"]["status"] == "succeeded" and steps["extract"]["status"] == "succeeded", \
        "completed downloads/extraction survive a blocked OCR step"


_real_tool = pipelines._tool


def test_documents_admission_mode_creates_one_idempotent_job(store, config, tmp_path):
    bot = _bot(store, name="admit-bot")
    root = tmp_path / "watched"
    root.mkdir()
    (root / "a.pdf").write_bytes(b"pdf-bytes")
    source = store.create_event_source(
        bot_id=bot.id, kind="folder", name="Inbox", config={"path": str(root), "settle_seconds": 0},
        admission={"mode": "documents", "prompt": "Summarize the new scans.", "cooldown_seconds": 60,
                   "max_per_hour": 4})
    row = store.get_event_source(source["id"])
    outcome = sources.check_source("folder", row["config"], row["cursor"], runtime=SourceRuntime(),
                                   now=utcnow())
    store.record_source_check(source["id"], row["revision"], cursor=outcome.cursor, events=outcome.events,
                              summary=outcome.summary, interval=30)

    engine = Engine(config, store, light=True)
    pump = SourcePump(engine)
    pump._try_admit(store.get_event_source(source["id"]))
    jobs = store.list_jobs()
    assert len(jobs) == 1 and jobs[0]["kind"] == "document_pipeline"
    assert jobs[0]["input"]["paths"] == [str(root / "a.pdf")]
    assert all(event["job_id"] == jobs[0]["id"] for event in store.source_events(source["id"]))
    pump._try_admit(store.get_event_source(source["id"]))
    assert len(store.list_jobs()) == 1, "re-admission of the same batch is idempotent"
    engine.jobs.shutdown()
