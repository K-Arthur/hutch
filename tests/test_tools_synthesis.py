"""Synthesis tool tests: ingestion, manifest registration, script validation, render flow."""

from __future__ import annotations

import uuid

import pytest

from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run
from hutch.safety import PolicyEngine
from hutch.synthesis.model import new_id
from hutch.synthesis.tts import TTSAudio, wrap_pcm
from hutch.tools.base import ToolContext
from hutch.tools.synthesis import (
    IngestSourceTool,
    RegisterManifestTool,
    RegisterScriptTool,
    RenderAudioOverviewTool,
)


def _ctx(tmp_path, store, config, *, approval_mode=ApprovalMode.auto) -> ToolContext:
    bot = store.create_bot(Bot(name=f"syn-{uuid.uuid4().hex[:6]}", model="mock/demo",
                               tools=["synthesis"], approval_mode=approval_mode))
    run = store.create_run(Run(bot_id=bot.id, prompt="x"))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    policy = PolicyEngine()
    gate = ApprovalGate(store, bot, run, policy, emit=lambda _e: None)
    return ToolContext(bot=bot, run=run, store=store, policy=policy, gate=gate,
                       config=config, workspace=ws)


def _thread_posts():
    return [
        {"post_id": "p1", "author_id": "A", "author": "Ada", "text": "Four lessons on caching. 1/4"},
        {"post_id": "p2", "author_id": "A", "author": "Ada", "text": "2/4 Locality matters.",
         "reply_to": "p1"},
        {"post_id": "p3", "author_id": "A", "author": "Ada", "text": "3/4 TTLs are blunt.",
         "reply_to": "p2"},
        {"post_id": "p4", "author_id": "A", "author": "Ada", "text": "",
         "reply_to": "p3", "accessible": False, "unavailable_reason": "deleted"},
        {"post_id": "p5", "author_id": "A", "author": "Ada", "text": "4/4 Measure first.",
         "reply_to": "p4"},
        {"post_id": "pb", "author_id": "B", "author": "Bob", "text": "Nice thread!", "reply_to": "p2"},
    ]


def _manifest_payload(source_id: str, span_id: str, claim_id: str, *, quantity: str = "12%",
                      output_id: str = "") -> dict:
    claims = [{
        "id": claim_id, "text": f"The hit rate rose {quantity}.", "kind": "measurement",
        "spans": [span_id],
        "quantities": [{"value": float(quantity.rstrip("%")), "unit": "%",
                        "as_reported": f"hit rate rose {quantity}"}],
    }]
    outputs = []
    if output_id:
        outputs.append({"id": output_id, "kind": "audio_overview", "version": 1,
                        "status": "validated", "depends_on_claim_ids": [claim_id]})
    return {
        "id": "syn_" + "a" * 16,
        "sources": [{"id": source_id, "kind": "thread", "identity": "https://social.example/t/1",
                     "content_sha256": "c" * 64,
                     "coverage": {"state": "complete", "expected_units": 4, "accessible_units": 4}}],
        "spans": [{"id": span_id, "source_id": source_id, "source_revision": 1, "container": "post",
                   "locator": {"post_id": "p2"}, "quote": "hit rate rose 12%", "quote_kind": "quoted"}],
        "claims": claims,
        "coverage_summary": "4 of 4 accessible",
        "audience": "engineers",
        "language": "en",
        "outputs": outputs,
    }


def test_ingest_thread_tool_reports_coverage_and_registers_source(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    result = IngestSourceTool().run(
        {"kind": "thread", "identity": "https://social.example/t/1", "expected_count": 4,
         "posts": _thread_posts()}, ctx)
    assert result.ok
    assert "deleted" in result.output and "accessible" in result.output
    # Ada has 4 accessible posts and one deleted: 4 of 4 expected accessible with a gap recorded
    assert result.data["ordered_post_ids"] == ["p1", "p2", "p3", "p5"]
    stored = store.get_synthesis_source("https://social.example/t/1")
    assert stored["revision"] == 1 and stored["kind"] == "thread"
    assert stored["doc"]["coverage"]["gaps"], "the deleted post is an explicit gap"


def test_ingest_paper_tool_from_workspace(tmp_path, store, config):
    from tests.test_synthesis_ingest import _pdf

    ctx = _ctx(tmp_path, store, config)
    pdf = ctx.workspace / "paper.pdf"
    pdf.write_bytes(_pdf([["Abstract", "We test things.", "1 Introduction", "Body text."]]))
    result = IngestSourceTool().run(
        {"kind": "paper", "path": "paper.pdf", "title": "A paper"}, ctx)
    assert result.ok and result.data["kind"] == "paper"
    assert any(s["title"] == "Introduction" for s in result.data["sections"])

    escape = IngestSourceTool().run({"kind": "paper", "path": "../outside.pdf"}, ctx)
    assert not escape.ok and "workspace" in escape.output

    from pypdf import PdfWriter
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret")
    buffer = BytesIO()
    writer.write(buffer)
    (ctx.workspace / "locked.pdf").write_bytes(buffer.getvalue())
    locked = IngestSourceTool().run({"kind": "paper", "path": "locked.pdf"}, ctx)
    assert not locked.ok and "encrypted" in locked.output


def test_register_manifest_registers_sources_and_marks_stale_on_change(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    span_id, claim_id, output_id = new_id("spn"), new_id("cl"), new_id("out")
    payload = _manifest_payload("src_proposed", span_id, claim_id, output_id=output_id)
    first = RegisterManifestTool().run({"manifest": payload}, ctx)
    assert first.ok, first.output
    assert first.data["revision"] == 1 and first.data["stale_output_ids"] == []
    stored = store.get_synthesis_manifest("syn_" + "a" * 16)
    assert stored["revision"] == 1
    # the span now points at the registry's source id, not the model's proposal
    registry_source = store.get_synthesis_source("https://social.example/t/1")
    assert stored["doc"]["spans"][0]["source_id"] == registry_source["id"]
    assert registry_source["doc"]["id"] == registry_source["id"]

    changed = _manifest_payload("src_proposed", span_id, claim_id, quantity="21%")
    second = RegisterManifestTool().run({"manifest": changed}, ctx)
    assert second.ok, second.output
    assert second.data["revision"] == 2
    assert claim_id in second.data["changed_claim_ids"]
    assert output_id in second.data["stale_output_ids"]
    newest = store.get_synthesis_manifest("syn_" + "a" * 16)
    assert newest["revision"] == 2
    assert newest["doc"]["claims"][0]["quantities"][0]["as_reported"] == "hit rate rose 21%"
    old = store.get_synthesis_manifest_revision("syn_" + "a" * 16, 1)
    assert old["doc"]["outputs"][0]["status"] == "stale"

    bad = _manifest_payload("src_proposed", new_id("spn"), claim_id)
    bad["claims"][0]["spans"] = [new_id("spn")]  # cites a span that is not defined
    rejected = RegisterManifestTool().run({"manifest": bad}, ctx)
    assert not rejected.ok and "valid" in rejected.output


def test_register_script_validates_and_stores(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    span_id, claim_id = new_id("spn"), new_id("cl")
    assert RegisterManifestTool().run(
        {"manifest": _manifest_payload("src_proposed", span_id, claim_id)}, ctx).ok
    good = {"chapters": [{"title": "Findings", "utterances": [
        {"speaker": "guide", "text": "The hit rate rose 12%.", "claim_ids": [claim_id]},
        {"speaker": "probe", "kind": "question", "text": "What is the caveat?"},
        {"speaker": "guide", "kind": "answer", "text": "It is one measurement."},
    ]}]}
    result = RegisterScriptTool().run(
        {"manifest_id": "syn_" + "a" * 16, "script": good}, ctx)
    assert result.ok, result.output
    assert result.data["segments"] >= 1
    row = store.get_synthesis_artifact(result.data["script_artifact_id"])
    assert row["kind"] == "script" and row["status"] == "validated"

    invented = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "guide", "text": "The hit rate rose 43%.", "claim_ids": [claim_id]}]}]}
    rejected = RegisterScriptTool().run(
        {"manifest_id": "syn_" + "a" * 16, "script": invented}, ctx)
    assert not rejected.ok and "43" in rejected.output

    directed = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "guide", "text": "<reading dramatically> The hit rate rose 12%.",
         "claim_ids": [claim_id]}]}]}
    assert not RegisterScriptTool().run(
        {"manifest_id": "syn_" + "a" * 16, "script": directed}, ctx).ok


class _FakeGeminiEngine:
    """A local stand-in that returns real WAV bytes; no provider is contacted."""

    name = "gemini"
    model = "gemini-3.8-flash-tts"

    def capabilities(self):
        from hutch.synthesis.tts import TTSCapabilities
        return TTSCapabilities(multi_speaker=True, max_chars_per_request=4000,
                               formats=("AUDIO_L16",))

    def synthesize(self, turns, *, voices, language):
        chars = sum(len(t.text) for t in turns)
        seconds = max(1.5, chars / 12.0)
        return TTSAudio(data=b"\x00\x10" * int(24_000 * seconds), container="pcm",
                        sample_rate=24_000)


def test_render_audio_overview_requires_a_key_then_produces_artifacts(
        tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    span_id, claim_id = new_id("spn"), new_id("cl")
    RegisterManifestTool().run({"manifest": _manifest_payload("src_proposed", span_id, claim_id)}, ctx)
    script_result = RegisterScriptTool().run(
        {"manifest_id": "syn_" + "a" * 16,
         "script": {"chapters": [{"title": "Findings", "utterances": [
             {"speaker": "guide", "text": "The hit rate rose 12%.", "claim_ids": [claim_id]},
             {"speaker": "probe", "kind": "question", "text": "What is the caveat?"},
             {"speaker": "guide", "kind": "answer", "text": "It is one measurement."},
         ]}]}}, ctx)
    assert script_result.ok, script_result.output

    monkeypatch.setattr("hutch.tools.synthesis.tts_engines", lambda cfg: [])
    no_key = RenderAudioOverviewTool().run(
        {"manifest_id": "syn_" + "a" * 16,
         "script_artifact_id": script_result.data["script_artifact_id"]}, ctx)
    assert not no_key.ok and "GEMINI_API_KEY" in no_key.output

    monkeypatch.setattr("hutch.tools.synthesis.tts_engines", lambda cfg: [_FakeGeminiEngine()])
    monkeypatch.setattr(ctx.gate, "decide", lambda *a, **k: None)  # approval itself is tested elsewhere
    rendered = RenderAudioOverviewTool().run(
        {"manifest_id": "syn_" + "a" * 16,
         "script_artifact_id": script_result.data["script_artifact_id"]}, ctx)
    assert rendered.ok, rendered.output
    audio = store.get_synthesis_artifact(rendered.data["audio_artifact_id"])
    assert audio["kind"] == "audio_overview" and audio["status"] == "validated"
    transcript = store.get_synthesis_artifact(rendered.data["transcript_artifact_id"])
    assert transcript["kind"] == "transcript"
    assert rendered.data["duration_ms"] > 0

    again = RenderAudioOverviewTool().run(
        {"manifest_id": "syn_" + "a" * 16,
         "script_artifact_id": script_result.data["script_artifact_id"]}, ctx)
    assert again.ok and "reused" in again.output
    assert again.data["sha256"] == rendered.data["sha256"]
