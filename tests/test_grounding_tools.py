"""Store + tool integration: evidence rows, claim binding, briefs, runtime image delivery."""

from __future__ import annotations

import json

import pytest

from hutch.grounding import acquire as acquire_mod
from hutch.grounding.clock import FrozenClock
from hutch.grounding.temporal import parse_iso
from hutch.models import Bot, InferenceMode, Run, RunStatus
from hutch.tools import build_tools
from hutch.tools.base import Tool, ToolResult, _schema
from tests.test_tools import make_ctx

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")


def _fake_source(url, title, *, origin="example.com", origin_id=None, published=None):
    return acquire_mod.FoundSource(
        adapter="feeds", lane="feeds", platform="web", kind="feed_item", url=url, canonical_url=url,
        title=title, excerpt=title, origin=origin, origin_id=origin_id or url,
        retrieved_at=CLOCK.now().isoformat(), published=published)


def test_store_records_source_revisions_instead_of_second_witnesses(config, store):
    inv = store.create_investigation(question="q", reference_instant=CLOCK.now().isoformat(), run_id="run_rev")
    first = store.record_sources(inv["id"], [{"adapter": "a", "url": "https://x.example/p", "title": "v1",
                                              "origin_id": "post-1", "retrieved_at": CLOCK.now().isoformat()}])
    second = store.record_sources(inv["id"], [{"adapter": "a", "url": "https://x.example/p", "title": "v2",
                                               "origin_id": "post-1", "retrieved_at": CLOCK.now().isoformat()}])
    assert first[0]["revision"] == 1 and second[0]["revision"] == 2
    latest = store.list_sources(inv["id"])
    assert len(latest) == 1 and latest[0]["title"] == "v2"
    all_rows = store.list_sources(inv["id"], latest_only=False)
    assert len(all_rows) == 2


def test_store_bundle_carries_claims_evidence_media_and_answers(config, store):
    inv = store.create_investigation(question="did the bridge reopen?", reference_instant=CLOCK.now().isoformat())
    attempt = store.record_query_attempts(inv["id"], [{"adapter": "feeds", "state": "ok", "retained": 1}])[0]
    source = store.record_sources(inv["id"], [{"adapter": "feeds", "url": "https://x.example/a", "title": "t",
                                               "origin_id": "a", "retrieved_at": CLOCK.now().isoformat()}],
                                  attempts_by_adapter={"feeds": attempt})[0]
    claim = store.add_claim(inv["id"], text="the bridge reopened", kind="occurrence")
    store.add_evidence_link(inv["id"], claim_id=claim, source_id=source["id"], relation="supports",
                            independence="independent", quote="reopened at noon")
    media = store.add_media(inv["id"], origin="https://x.example/img.jpg", local_path="/tmp/img.jpg",
                            kind="image", mime="image/jpeg", byte_size=10, sha256="ab" * 32,
                            frames=[{"at_ms": 0, "path": "/tmp/f.jpg", "sha256": "cd" * 32}])
    store.add_observation(inv["id"], kind="model_input", text="1 frame transmitted",
                          media_id=media, transmitted_json={"route": "openai/gpt-4o-mini", "transmitted": 1})
    store.add_answer(inv["id"], body_json={"text": "answer 1"}, effective_as_of=CLOCK.now().isoformat())
    store.add_answer(inv["id"], body_json={"text": "answer 2"}, effective_as_of=CLOCK.now().isoformat())
    bundle = store.investigation_bundle(inv["id"])
    assert bundle["investigation"]["revision"] == 3      # two answers bumped the revision twice, plus creation
    assert bundle["answers"][1]["revision_of"] == bundle["answers"][0]["id"]
    assert bundle["media"][0]["frames"][0]["at_ms"] == 0
    assert bundle["evidence"][0]["relation"] == "supports"
    transmitted = json.loads(bundle["observations"][0]["transmitted_json"])
    assert transmitted["transmitted"] == 1


def test_store_stream_cursors_keep_kind_and_schema_version(config, store):
    cursor = {"adapter": "wikimedia-eventstreams", "instance": "stream.wikimedia.org",
              "kind": "structured_json", "value": [{"topic": "t", "partition": 0, "timestamp": 1}],
              "schema_version": 1}
    store.save_stream_cursor("wikimedia:recentchange", investigation_id="inv_1", cursor_json=cursor,
                             liveness_json={"state": "live"}, gap_note="")
    saved = store.get_stream_cursor("wikimedia:recentchange")
    assert saved["cursor_kind"] == "structured_json" and saved["schema_version"] == 1


def test_live_search_tool_persists_a_grounded_brief(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    ctx.clock = CLOCK
    published = parse_iso("2026-10-11T08:00:00Z", role="publication", clock=CLOCK)
    monkeypatch.setitem(acquire_mod.ADAPTERS, "feeds", lambda query, cutoff, budget, clock, cfg, stop: (
        [_fake_source("https://news.example/bridge", "Bridge reopened, officials say", published=published)],
        acquire_mod.AdapterOutcome(adapter="feeds", lane="feeds", query=query, state="ok", retained=1, returned=1)))
    for name in ("gdelt", "hn", "bluesky", "searxng"):
        monkeypatch.setitem(acquire_mod.ADAPTERS, name, lambda q, c, b, cl, cf, s, name=name: (
            [], acquire_mod.AdapterOutcome(adapter=name, lane="?", query=q, state="unavailable", detail="fixture")))
    tools = build_tools(["live_search"], ctx)
    result = tools["live_search"].run(
        {"question": "did the bridge reopen today?", "claim": "the bridge reopened at noon", "horizon_hours": 24,
         "lanes": ["feeds", "news"]}, ctx)
    assert result.ok
    assert "[S1]" in result.output and "Bridge reopened" in result.output
    assert "reports_allegation" in result.output or "S1" in result.output
    inv = store.investigation_for_run(ctx.run.id)
    assert inv is not None
    bundle = store.investigation_bundle(inv["id"])
    assert len(bundle["sources"]) == 1 and len(bundle["claims"]) == 1
    assert bundle["evidence"][0]["relation"] == "reports_allegation"
    assert bundle["answers"], "the evidence brief must be stored as an answer revision"
    answer_body = json.loads(bundle["answers"][-1]["body_json"])
    assert answer_body["assessments"] and answer_body["citations"]
    # the same item retrieved by both query formulations is one origin, never two witnesses
    assert bundle["sources"][0]["independence"] == "same_origin"
    assert bundle["sources"][0]["origin_cluster"]
    coverage = json.loads(bundle["investigation"]["coverage_json"])
    assert coverage["adapters"]["feeds"] == "ok"
    assert "missing" in coverage
    assert coverage["sample"]["unique_items"] == 1 and coverage["sample"]["raw_items"] == 2


def test_live_search_with_zero_results_says_so_without_inventing_events(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    ctx.clock = CLOCK
    for name in ("gdelt", "feeds", "hn", "bluesky", "searxng"):
        monkeypatch.setitem(acquire_mod.ADAPTERS, name, lambda q, c, b, cl, cf, s, name=name: (
            [], acquire_mod.AdapterOutcome(adapter=name, lane="?", query=q, state="zero_results")))
    tools = build_tools(["live_search"], ctx)
    result = tools["live_search"].run({"question": "anything new?", "horizon_hours": 6}, ctx)
    assert result.ok
    assert "distinct from 'nothing happened'" in result.output
    assert "Do not assert" in result.output


def test_live_search_persists_a_stream_cursor_from_the_outcome(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    ctx.clock = CLOCK

    def fake_jetstream(query, cutoff, budget, clock, cfg, stop):
        outcome = acquire_mod.AdapterOutcome(
            adapter="jetstream", lane="stream", query=query, state="zero_results", freshness="stream",
            cursor_json={"adapter": "jetstream", "instance": "js.example", "kind": "seq", "value": 99,
                         "schema_version": 2},
            liveness_json={"state": "quiet"}, gap_note="")
        return [], outcome

    monkeypatch.setitem(acquire_mod.ADAPTERS, "jetstream", fake_jetstream)
    tools = build_tools(["live_search"], ctx)
    result = tools["live_search"].run({"question": "anything from the stream?", "lanes": ["stream"]}, ctx)
    assert result.ok
    row = store.get_stream_cursor("jetstream:js.example")
    assert row is not None and json.loads(row["cursor_json"])["value"] == 99
    assert row["cursor_kind"] == "seq"


def test_inspect_media_tool_attaches_frames_and_records_observations(store, config, tmp_path):
    from PIL import Image
    ctx = make_ctx(store, config, tmp_path)
    ctx.clock = CLOCK
    shot = ctx.workspace / "screenshot.png"
    Image.new("RGB", (80, 40), (200, 10, 10)).save(shot, "PNG")
    tools = build_tools(["inspect_media"], ctx)
    result = tools["inspect_media"].run({"path": "screenshot.png", "claim": "the alert says EVACUATE"}, ctx)
    assert result.ok and result.data["media_attachments"]
    assert "no authenticity or truth verdict" in result.output
    inv = store.investigation_for_run(ctx.run.id)
    bundle = store.investigation_bundle(inv["id"])
    assert bundle["media"][0]["sha256"] == result.data["sha256"]
    assert any(o["kind"] == "transmitted" for o in bundle["observations"])


def test_inspect_media_refuses_remote_in_offline_mode(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ctx.bot = ctx.bot.model_copy(update={"inference_mode": InferenceMode.offline})
    tools = build_tools(["inspect_media"], ctx)
    result = tools["inspect_media"].run({"url": "https://example.com/a.jpg"}, ctx)
    assert not result.ok and "Strict Offline" in result.output


# ---------------------------------------------------------------- runtime delivery

def _jpeg_bytes(tmp_path):
    from PIL import Image
    path = tmp_path / "frame.jpg"
    Image.new("RGB", (24, 24), (0, 200, 0)).save(path, "JPEG")
    return path


class _MediaReturningTool(Tool):
    name = "fake_media"
    description = "test tool that returns one frame attachment"
    parameters = _schema([], {})

    def __init__(self, frame_path):
        self.frame_path = frame_path

    def run(self, args, ctx):
        return ToolResult(ok=True, output="inspected one frame", data={
            "media_attachments": [{"path": str(self.frame_path), "mime": "image/jpeg",
                                   "label": "frame at 0 ms", "timecode_ms": 0}]})


def test_runtime_transmits_frames_as_image_parts_and_records_it(store, config, tmp_path):
    from tests.fakes import FakeOpenAI, agent_script
    from tests.test_runtime_builtin import build, factory, run_it, runtime
    oai = FakeOpenAI()
    try:
        oai.script = agent_script([{"tool_calls": [{"name": "fake_media", "arguments": {}}]}, {"content": "seen"}])
        ctx, run, emitted, _ = build(store, config, tmp_path, model="openai/gpt-4o-mini", tools=())
        store.create_investigation(run_id=run.id, question="inspect", reference_instant=CLOCK.now().isoformat())
        tools = {"fake_media": _MediaReturningTool(_jpeg_bytes(tmp_path))}
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "seen"
        bodies = [r["body"] for r in oai.requests if r.get("path", "").endswith("chat/completions")]
        second = json.dumps(bodies[-1])
        assert "data:image/jpeg;base64" in second
        # what actually reached the model is recorded
        inv = store.investigation_for_run(run.id)
        bundle = store.investigation_bundle(inv["id"])
        observations = [o for o in bundle["observations"] if o["kind"] == "model_input"]
        assert observations and json.loads(observations[-1]["transmitted_json"])["transmitted"] == 1
    finally:
        oai.close()


def test_runtime_transmits_frames_to_anthropic_as_image_blocks(store, config, tmp_path):
    from tests.fakes import FakeAnthropic, agent_script
    from tests.test_runtime_builtin import build, factory, run_it, runtime
    srv = FakeAnthropic()
    try:
        def base(body):
            return {"content": "seen", "input_tokens": 10, "output_tokens": 2, "cache_read": 0, "cache_write": 0}

        def scripted(body):  # first turn asks for the tool, then answers
            if not scripted.called:
                scripted.called = True
                return {"content": "", "tool_calls": [{"name": "fake_media", "arguments": {}}],
                        "input_tokens": 10, "output_tokens": 2, "cache_read": 0, "cache_write": 0}
            return base(body)
        scripted.called = False
        srv.script = scripted
        ctx, run, _, _ = build(store, config, tmp_path, model="anthropic/claude-opus-5-5", tools=())
        tools = {"fake_media": _MediaReturningTool(_jpeg_bytes(tmp_path))}
        assert run_it(runtime(provider_factory=factory(claude=srv)), run, ctx, tools) == "seen"
        bodies = [r["body"] for r in srv.of("/v1/messages")]
        image = None
        for body in bodies:
            for message in body.get("messages", []):
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "image":
                            image = block
        assert image is not None, "the Anthropic wire request must carry an image block"
        assert image["source"]["type"] == "base64" and image["source"]["media_type"] == "image/jpeg"
        import base64
        assert base64.b64decode(image["source"]["data"]).startswith(b"\xff\xd8\xff")
    finally:
        srv.close()


def test_runtime_transmits_frames_to_ollama_as_native_images(store, config, tmp_path):
    from tests.fakes import FakeOllama, agent_script
    from tests.test_runtime_builtin import build, factory, run_it, runtime
    srv = FakeOllama({"fake:8b": {}})
    try:
        srv.script = agent_script([{"tool_calls": [{"name": "fake_media", "arguments": {}}]}, {"content": "seen"}])
        ctx, run, _, _ = build(store, config, tmp_path, model="ollama/fake:8b", tools=())
        tools = {"fake_media": _MediaReturningTool(_jpeg_bytes(tmp_path))}
        assert run_it(runtime(provider_factory=factory(ollama=srv)), run, ctx, tools) == "seen"
        chats = srv.of("/api/chat")
        carried = [m for body in chats for m in body["body"].get("messages", []) if m.get("images")]
        assert carried, "the Ollama native request must carry base64 images on a user message"
        import base64
        assert base64.b64decode(carried[-1]["images"][0]).startswith(b"\xff\xd8\xff")
    finally:
        srv.close()


def test_runtime_tells_the_model_when_a_route_cannot_receive_images(store, config, tmp_path):
    from hutch.providers.openai_compat import OpenAICompatProvider
    from tests.fakes import FakeOpenAI, agent_script
    from tests.test_runtime_builtin import build, run_it, runtime
    oai = FakeOpenAI()

    class TextOnlyProvider(OpenAICompatProvider):
        supports_media_input = False

    def factory(provider, base_url):
        if provider == "openai":
            return TextOnlyProvider(oai.url + "/v1", "k", "openai")
        raise AssertionError(provider)

    try:
        oai.script = agent_script([{"tool_calls": [{"name": "fake_media", "arguments": {}}]}, {"content": "seen"}])
        ctx, run, _, _ = build(store, config, tmp_path, model="openai/gpt-4o-mini", tools=())
        tools = {"fake_media": _MediaReturningTool(_jpeg_bytes(tmp_path))}
        assert run_it(runtime(provider_factory=factory), run, ctx, tools) == "seen"
        bodies = [r["body"] for r in oai.requests if r.get("path", "").endswith("chat/completions")]
        second = json.dumps(bodies[-1])
        assert "data:image/jpeg;base64" not in second
        assert "were NOT transmitted" in second or "NOT transmitted" in second
    finally:
        oai.close()


def test_webfetch_extracts_and_records_declared_dates(store, config, tmp_path, monkeypatch):
    from hutch.netguard import Fetched
    import hutch.tools.webfetch as wf
    ctx = make_ctx(store, config, tmp_path)
    ctx.clock = CLOCK
    html = ("<html><head><link rel='canonical' href='https://news.example/full'>"
            "<meta property='og:site_name' content='News Example'>"
            "<meta property='article:published_time' content='2026-10-10T22:00:00+00:00'>"
            "<meta property='article:modified_time' content='2026-10-11T07:30:00Z'>"
            "<script type='application/ld+json'>{\"headline\": \"Bridge reopens\"}</script>"
            "</head><body><p>Officials reopened the bridge at noon.</p></body></html>")
    monkeypatch.setattr(wf, "safe_get", lambda url, **kw: Fetched(
        status=200, reason="OK", headers={"content-type": "text/html"}, text=html, url=url,
        body=html.encode()))
    tools = build_tools(["web_fetch"], ctx)
    result = tools["web_fetch"].run({"url": "https://news.example/short"}, ctx)
    assert result.ok and "canonical: https://news.example/full" in result.output
    assert "publication: 2026-10-10T22:00:00+00:00" in result.output
    assert result.data["dates"][0]["method"] in ("meta_article_published", "jsonld_datePublished")
    inv = store.investigation_for_run(ctx.run.id)
    sources = store.list_sources(inv["id"])
    assert sources and sources[0]["canonical_url"] == "https://news.example/full"
