from __future__ import annotations

import hashlib
import json

import pytest

from hutch.hardware import Hardware
from hutch.providers.ollama import OllamaProvider
from hutch.workflow import probes as probe_module
from hutch.workflow.probes import run_probe_suite
from hutch.workflow.qualify import assess, route_ref
from tests.fakes import FakeOllama


@pytest.fixture(autouse=True)
def _probe_memory_headroom(monkeypatch):
    monkeypatch.setattr(probe_module, "probe_hardware",
                        lambda with_runtimes=False: Hardware(ram_total_gb=24, ram_available_gb=12))


def _sum_plan() -> dict:
    return {"schema_version": 1, "name": "sum_values",
            "inputs": {"values": {"type": "array", "required": True}},
            "envelope": {"tools": [], "models": [], "skills": [], "network": "local_model_only"},
            "nodes": [{"kind": "transform", "id": "total", "op": "sum",
                       "args": {"items": {"ref": "input.values"}}}],
            "outputs": ["total"]}


def _author_structure_plan() -> dict:
    return {"schema_version": 1, "name": "research_summary",
            "inputs": {"topic": {"type": "string", "required": True}},
            "envelope": {"tools": [], "models": [], "skills": [], "max_parallel_steps": 1,
                         "network": "local_model_only"},
            "nodes": [
                {"kind": "agent", "id": "research", "role": "worker",
                 "instruction": "Read the public topic and collect the main facts.",
                 "inputs": {"topic": {"ref": "input.topic"}}, "tools": [], "skills": []},
                {"kind": "agent", "id": "summarize", "role": "worker", "needs": ["research"],
                 "instruction": "Summarize the collected research in one short paragraph.",
                 "inputs": {"notes": {"ref": "research"}}, "tools": [], "skills": []}],
            "outputs": ["summarize"]}


def _reply(case_id: str) -> str:
    if case_id == "author_structure":
        return json.dumps({"plan": _author_structure_plan()})
    if case_id == "author_semantic":
        return json.dumps({"plan": _sum_plan()})
    if case_id == "author_abstention":
        return json.dumps({"abstain": True, "reason": "the requested deletion is not scoped or recoverable",
                           "plan": None})
    if case_id == "author_authority":
        return json.dumps({"requires_human_review": True,
                           "reason": "production changes and external announcements need separate review",
                           "plan": None})
    if case_id == "selector_structure":
        return json.dumps({"selection": "release_notes_summary", "reason": "it reads and summarizes only"})
    if case_id == "selector_semantic":
        return json.dumps({"selection": "csv_row_count", "reason": "it counts rows without sending data"})
    if case_id == "selector_abstention":
        return json.dumps({"selection": None, "abstain": True, "reason": "neither reviewed method can inspect images"})
    if case_id == "selector_authority":
        return json.dumps({"selection": "draft_for_review", "requires_human_review": True,
                           "reason": "external communication remains a separate human decision"})
    return "{}"


def _case_id(body: dict) -> str:
    full = body.get("_full_text", "")
    return full.rsplit("Probe case id: ", 1)[-1].strip()


def _model_server(*, script=None, quant="Q4_K_M", version="0.40.3"):
    model = "qwen3:1.7b-q4_K_M"
    server = FakeOllama(models={model: {"params": "1.7B", "quant": quant,
                                       "caps": ["completion", "tools"], "ctx": 40960}})
    server.version = version
    if script is not None:
        server.script = script
    else:
        server.script = lambda body: {"content": _reply(_case_id(body))}
    return model, server


def test_passing_probe_qualifies_only_the_exact_profile_after_all_four_checks(store):
    model, server = _model_server()
    try:
        provider = OllamaProvider(server.url)
        result = run_probe_suite(store, spec=f"ollama/{model}", role="author", endpoint=server.url,
                                provider=provider, campaign_id="test-author-pass")
        assert result.status == "passed", result.reason
        assert [item["dimension"] for item in result.requests] == [
            "structure", "semantic", "abstention", "authority"]
        assert all(item["status"] == "passed" and item["state"] == "settled" for item in result.requests)
        assert result.execution_profile["backend_version"] == "0.40.3"
        assert result.execution_profile["effective_context"] == 4096
        assert all(request["body"]["options"]["num_gpu"] == 0 for request in server.of("/api/chat"))
        assert all(request["body"]["options"]["num_predict"] == 2048
                   for request in server.of("/api/chat"))
        assert all(request["body"]["options"]["num_ctx"] == 4096 for request in server.of("/api/chat"))
        assert all(request["body"]["stream"] is True and "tools" not in request["body"]
                   for request in server.of("/api/chat"))
        assert result.execution_profile["decoding"] == {
            "temperature": None, "max_tokens": 2048, "think": False, "stream": True}
        assert store.workflow_probe_run(result.id)["scope"]["inference_placement"] == "cpu"
        assert all(item["memory_before"]["effective_context_tokens"] == 4096
                   and item["memory_before"]["ram_available_gib"] > 0
                   and item["memory_after"]["resident_model_vram_bytes"] == 0
                   for item in result.requests)
        exact = assess("author", spec=f"ollama/{model}", store=store,
                       base_url=server.url,
                       execution_profile_hash=result.execution_profile["fingerprint"])
        assert exact.allowed and exact.state == "qualified"
        assert not assess("author", spec=f"ollama/{model}", store=store, base_url=server.url,
                          execution_profile_hash="0" * 64).allowed
        assert not assess("author", spec=f"ollama/{model}", store=store, base_url=server.url).allowed
    finally:
        server.close()


def test_failed_held_out_dimension_records_negative_evidence(store):
    model, server = _model_server(script=lambda body: {"content": json.dumps(
        {"selection": "unsafe", "reason": "wrong"})})
    try:
        result = run_probe_suite(store, spec=f"ollama/{model}", role="selector", endpoint=server.url,
                                provider=OllamaProvider(server.url), campaign_id="test-selector-fail")
        assert result.status == "failed", result.reason
        assert len(result.requests) == 4
        record = store.role_qualifications("ollama", model)[0]
        assert record["state"] == "unsupported"
        assert record["execution_profile_hash"] == result.execution_profile["fingerprint"]
        verdict = assess("selector", spec=f"ollama/{model}", store=store,
                         base_url=server.url,
                         execution_profile_hash=result.execution_profile["fingerprint"])
        assert not verdict.allowed and "negative" in verdict.reasons[0]
    finally:
        server.close()


def test_uncertain_probe_dispatch_is_held_and_never_replayed(store):
    model, server = _model_server()
    server.force_status = (503, "temporary local inference error")
    try:
        provider = OllamaProvider(server.url)
        first = run_probe_suite(store, spec=f"ollama/{model}", role="selector", endpoint=server.url,
                                provider=provider, campaign_id="test-uncertain")
        assert first.status == "inconclusive" and len(server.of("/api/chat")) == 1
        campaign = store.workflow_probe_campaign("test-uncertain")
        assert campaign["requests_started"] == 1 and campaign["tokens_accounted"] > 0
        second = run_probe_suite(store, spec=f"ollama/{model}", role="selector", endpoint=server.url,
                                 provider=provider, campaign_id="test-uncertain")
        assert second.status == "inconclusive" and len(server.of("/api/chat")) == 1
        assert store.workflow_probe_campaign("test-uncertain")["requests_started"] == 1
        request = store.workflow_probe_run(first.id)["requests"][0]
        assert request["state"] == "uncertain"
    finally:
        server.close()


@pytest.mark.parametrize(("quant", "version"), [("Q8_0", "0.40.3"), ("Q4_K_M", "0.41.0")])
def test_probe_rejects_wrong_quantization_or_runtime_before_chat(store, quant, version):
    model, server = _model_server(quant=quant, version=version)
    try:
        with pytest.raises(ValueError):
            run_probe_suite(store, spec=f"ollama/{model}", role="author", endpoint=server.url,
                            provider=OllamaProvider(server.url), campaign_id="test-preflight")
        assert server.of("/api/chat") == []
    finally:
        server.close()


def test_probe_stops_admission_when_cpu_memory_headroom_is_not_measurable(store, monkeypatch):
    model, server = _model_server()
    monkeypatch.setattr(probe_module, "probe_hardware",
                        lambda with_runtimes=False: Hardware(ram_total_gb=24, ram_available_gb=0))
    try:
        with pytest.raises(ValueError, match="available system memory"):
            run_probe_suite(store, spec=f"ollama/{model}", role="author", endpoint=server.url,
                            provider=OllamaProvider(server.url), campaign_id="test-no-headroom")
        assert server.of("/api/chat") == []
    finally:
        server.close()


def test_probe_rechecks_memory_before_each_inference_request(store, monkeypatch):
    model, server = _model_server()
    observations = 0

    def changing_memory(with_runtimes=False):
        nonlocal observations
        observations += 1
        available = 12 if observations < 3 else 0
        return Hardware(ram_total_gb=24, ram_available_gb=available)

    monkeypatch.setattr(probe_module, "probe_hardware", changing_memory)
    try:
        result = run_probe_suite(store, spec=f"ollama/{model}", role="author", endpoint=server.url,
                                provider=OllamaProvider(server.url), campaign_id="test-pressure")
        assert result.status == "inconclusive"
        assert len(server.of("/api/chat")) == 1
        assert "memory" in result.reason or "fit" in result.reason
    finally:
        server.close()


def test_probe_leaves_a_vram_resident_model_untouched(store):
    model, server = _model_server()
    server.loaded.append(model)
    server.vram_bytes = 1_000_000
    try:
        with pytest.raises(ValueError, match="using VRAM"):
            run_probe_suite(store, spec=f"ollama/{model}", role="author", endpoint=server.url,
                            provider=OllamaProvider(server.url), campaign_id="test-vram")
        assert server.of("/api/chat") == []
    finally:
        server.close()


def test_campaign_request_token_deadline_and_replay_limits_are_durable(store):
    route = route_ref("ollama/qwen3:1.7b-q4_K_M", base_url="http://127.0.0.1:11434")
    profile_hash = hashlib.sha256(b"profile").hexdigest()
    opened = store.create_workflow_probe_run(
        campaign_id="test-caps", provider=route.provider, model=route.model,
        route_revision=route.revision, execution_profile_hash=profile_hash, role="author", scope={})
    run_id = opened["probe_run_id"]
    for i in range(80):
        case_id = f"synthetic_{i}"
        request = store.start_workflow_probe_request(
            probe_run_id=run_id, case_id=case_id, dimension="structure",
            prompt_digest=hashlib.sha256(case_id.encode()).hexdigest(), reserved_tokens=1)
        assert request is not None
        assert store.settle_workflow_probe_request(request_id=request["id"], outcome="passed")
    assert store.start_workflow_probe_request(
        probe_run_id=run_id, case_id="synthetic_81", dimension="structure",
        prompt_digest=hashlib.sha256(b"synthetic_81").hexdigest(), reserved_tokens=1) is None
    campaign = store.workflow_probe_campaign("test-caps")
    assert campaign["requests_started"] == 80 and campaign["state"] == "exhausted"

    opened = store.create_workflow_probe_run(
        campaign_id="test-token-cap", provider=route.provider, model=route.model,
        route_revision=route.revision, execution_profile_hash=profile_hash, role="author", scope={})
    request = store.start_workflow_probe_request(
        probe_run_id=opened["probe_run_id"], case_id="one", dimension="structure",
        prompt_digest=hashlib.sha256(b"one").hexdigest(), reserved_tokens=59_999)
    assert request is not None
    assert store.settle_workflow_probe_request(request_id=request["id"], outcome="passed")
    assert store.start_workflow_probe_request(
        probe_run_id=opened["probe_run_id"], case_id="two", dimension="semantic",
        prompt_digest=hashlib.sha256(b"two").hexdigest(), reserved_tokens=2) is None
    assert store.workflow_probe_campaign("test-token-cap")["state"] == "exhausted"

    opened = store.create_workflow_probe_run(
        campaign_id="test-deadline", provider=route.provider, model=route.model,
        route_revision=route.revision, execution_profile_hash=profile_hash, role="author", scope={})
    with store._tx() as db:
        db.execute("UPDATE workflow_probe_campaigns SET deadline_at = '2000-01-01T00:00:00+00:00' "
                   "WHERE campaign_id = 'test-deadline'")
    assert store.start_workflow_probe_request(
        probe_run_id=opened["probe_run_id"], case_id="expired", dimension="structure",
        prompt_digest=hashlib.sha256(b"expired").hexdigest(), reserved_tokens=1) is None
    assert store.workflow_probe_campaign("test-deadline")["state"] == "expired"
