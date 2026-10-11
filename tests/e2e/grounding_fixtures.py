"""Shared browser fixtures and seed data for the grounded-evidence journeys.

Kept out of ``conftest.py`` so the documents/skills journeys keep their own fixtures and
only the grounding tests pay for these.
"""

from __future__ import annotations

import hashlib
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.config import hutchConfig  # noqa: E402
from hutch.models import Bot, Event, EventType, Run, RunStatus  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.store import Store  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = None
        errors = []
        for engine in (p.chromium, p.firefox):
            try:
                b = engine.launch()
                break
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if b is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app, tmp_path / "state"
    server.should_exit = True
    t.join(timeout=10)


def seed_grounded_run(state_dir) -> str:
    """One succeeded run with a stored investigation: two feeds (one mirrored), a media
    frame, and a scoped 'insufficient evidence' answer revision."""
    from PIL import Image
    config = hutchConfig(state_dir=state_dir)
    store = Store(config)
    try:
        bot = Bot(name="grounding-e2e", model="mock/demo", tools=[])
        if not store.get_bot(bot.name):
            store.create_bot(bot)
        bot = store.get_bot(bot.name)
        run = store.create_run(Run(bot_id=bot.id, prompt="Did the Kestrel bridge reopen after the storm?"))
        claimed = store.claim_run(run.id, "e2e-seed", 300)
        run = claimed or store.get_run(run.id)
        store.transition_run(run.id, RunStatus.running, fence=run.fence)
        inv = store.create_investigation(run_id=run.id, bot_id=bot.id,
                                         question="Did the Kestrel bridge reopen after the storm?",
                                         reference_instant="2026-10-11T19:30:00+00:00",
                                         user_timezone="America/Vancouver", horizon_hours=24)
        inv_id = inv["id"]
        store.record_query_attempts(inv_id, [
            {"adapter": "feeds", "lane": "feeds", "state": "ok", "retained": 2, "returned": 3,
             "dropped_out_of_range": 1, "latency_ms": 412.0, "freshness": "polled"},
            {"adapter": "bluesky", "lane": "social", "state": "blocked", "http_status": 403,
             "detail": "HTTP 403: the public AppView refused this network; no social results were observed"},
        ])
        stored = store.record_sources(inv_id, [
            {"adapter": "feeds", "lane": "feeds", "kind": "feed_item",
             "url": "https://news.example/kestrel", "canonical_url": "https://news.example/kestrel",
             "title": "Kestrel bridge reopens after storm repairs", "origin": "news.example",
             "origin_id": "https://news.example/kestrel",
             "excerpt": "Officials said the bridge reopened at noon after inspections.",
             "published": {"raw": "2026-10-11T19:05:00+00:00", "role": "publication", "method": "iso8601",
                            "precision": "second", "instant": "2026-10-11T19:05:00+00:00"},
             "retrieved_at": "2026-10-11T19:31:02+00:00", "freshness": "polled"},
            {"adapter": "feeds", "lane": "feeds", "kind": "feed_item",
             "url": "https://mirror.example/copy", "canonical_url": "https://mirror.example/copy",
             "title": "Kestrel bridge reopens (syndicated)", "origin": "mirror.example",
             "origin_id": "https://mirror.example/copy",
             "excerpt": "Officials said the bridge reopened at noon after inspections.",
             "published": {"raw": "2026-10-11T19:20:00+00:00", "role": "publication", "method": "iso8601",
                            "precision": "second", "instant": "2026-10-11T19:20:00+00:00"},
             "retrieved_at": "2026-10-11T19:31:04+00:00", "freshness": "polled"},
        ])
        primary, mirror = stored[0], stored[1]
        store.annotate_sources(inv_id, {
            primary["id"]: {"cluster": "cl_one", "independence": "independent"},
            mirror["id"]: {"cluster": "cl_one", "independence": "same_origin"},
        })
        claim = store.add_claim(inv_id, text="the Kestrel bridge reopened at noon", kind="occurrence")
        store.add_evidence_link(inv_id, claim_id=claim, source_id=primary["id"],
                                relation="reports_allegation", quote="reopened at noon")
        frame_dir = config.state_dir / "grounding" / "media" / run.id
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_path = frame_dir / "frame-0.jpg"
        Image.new("RGB", (320, 200), (30, 90, 140)).save(frame_path, "JPEG")
        frame_bytes = frame_path.read_bytes()
        media_id = store.add_media(inv_id, origin="https://news.example/kestrel.jpg",
                                   local_path=str(frame_path), kind="image", mime="image/jpeg",
                                   byte_size=len(frame_bytes),
                                   sha256=hashlib.sha256(frame_bytes).hexdigest(),
                                   c2pa_json={"state": "absent", "detail": ""},
                                   frames=[{"at_ms": 0, "path": str(frame_path),
                                            "sha256": hashlib.sha256(frame_bytes).hexdigest()}])
        store.add_observation(inv_id, kind="limitation",
                              text="inspected 1 frame at [0] ms; intervals and audio were not inspected",
                              media_id=media_id)
        store.add_observation(inv_id, kind="model_input",
                              text="1 of 1 prepared frame(s) transmitted to openai/gpt-4o-mini",
                              media_id=media_id, transmitted_json={"transmitted": 1})
        coverage = {"adapters": {"feeds": "ok", "bluesky": "blocked"},
                    "missing": [{"adapter": "bluesky", "state": "blocked", "detail": "HTTP 403"}],
                    "sample": {"raw_items": 2, "unique_items": 2, "origin_clusters": 1, "distinct_origins": 1},
                    "citations": {primary["id"]: "S1", mirror["id"]: "S2"}}
        store.update_investigation(inv_id, coverage=coverage, status="open")
        store.add_answer(inv_id, body_json={
            "kind": "evidence_brief", "text": "EVIDENCE BRIEF (fixture)",
            "assessments": {claim: {"label": "insufficient_evidence",
                                    "reasons": ["one origin cluster supports this claim; independent confirmation is not established"],
                                    "axes": {"independent_support_origins": 1}, "missing_checks": [], "coverage": {}}},
            "citations": {primary["id"]: "S1", mirror["id"]: "S2"}},
            effective_as_of="2026-10-11T19:30:00+00:00", coverage_json=coverage)
        store.append_event(Event(run_id=run.id, type=EventType.message,
                                 data={"role": "assistant", "content": "One independent report; a copy repeats it. [S1]"}))
        store.append_event(Event(run_id=run.id, type=EventType.tool_result,
                                 data={"tool": "live_search", "ok": True, "output": "2 sources", "investigation_id": inv_id}))
        store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
        return run.id
    finally:
        store.close()


def open_panel(page, base, run_id):
    problems: list[str] = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.goto(f"{base}/#/run/{run_id}?focus=evidence")
    page.wait_for_selector("[data-evidence-panel]", timeout=20_000)
    return problems
