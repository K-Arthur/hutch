"""The context self-check is sized to the machine and announced first (docs/realignment/offline-models-2026-10-31.md, section 3.2).

On a CPU-only host the fixed 12,000-token recall probe cost about ten minutes of prompt processing with one log line and no estimate.
It is now shortened to fit a time budget, the estimate is stated before it runs, and the runtime's own report of the applied window
is checked first because it costs nothing. The check is never removed, and a shortened one says how far it verified.
"""

from __future__ import annotations

import json
import re
import time

import pytest

from hutch import selfcheck_plan
from hutch.providers.ollama import OllamaProvider
from hutch.selfcheck_plan import BUDGET_SECONDS, CPU_DEFAULT_TPS, FLOOR_TOKENS, plan_for, run_planned_selfcheck
from tests.fakes import FakeOllama


@pytest.fixture()
def ollama():
    def script(body):
        m = re.search(r"code word for this check is ([A-Z0-9-]+)", body["_seen_text"])
        return {"content": m.group(1) if m else "I do not know."}
    server = FakeOllama({"fake:8b": {}})
    server.script = script
    yield server
    server.close()


def test_a_machine_with_no_measurement_and_a_gpu_gets_the_full_probe_and_no_estimate(store):
    plan = plan_for(store, "fake:8b", 16384, accelerator="gpu")
    assert plan.size == plan.full == 12_000 and not plan.reduced and plan.seconds is None
    assert "minutes" not in plan.announce("fake:8b", 16384) and "16,384-token window" in plan.announce("fake:8b", 16384)


def test_a_cpu_only_machine_is_assumed_slow_until_measured_and_the_probe_is_shortened(store):
    plan = plan_for(store, "fake:8b", 16384, accelerator="cpu")
    assert plan.reduced and plan.tokens_per_second == CPU_DEFAULT_TPS and not plan.measured
    assert FLOOR_TOKENS <= plan.size <= int(CPU_DEFAULT_TPS * BUDGET_SECONDS)
    assert plan.seconds is not None and plan.seconds <= BUDGET_SECONDS + 1
    text = plan.announce("fake:8b", 16384)
    assert "shortened from 12,000" in text and "assumed for this hardware" in text and "runs once per model and window" in text


def test_a_measured_speed_replaces_the_assumption(store):
    store.kv_set("prompt_tps:fake:8b", json.dumps({"tps": 18.0, "at": time.time()}))
    plan = plan_for(store, "fake:8b", 16384, accelerator="cpu")
    assert plan.measured and plan.tokens_per_second == 18.0 and plan.size == int(18 * BUDGET_SECONDS)
    assert "measured" in plan.announce("fake:8b", 16384) and "assumed" not in plan.announce("fake:8b", 16384)


def test_a_fast_machine_that_measured_itself_keeps_the_full_probe(store):
    store.kv_set("prompt_tps:fake:8b", json.dumps({"tps": 900.0, "at": time.time()}))
    plan = plan_for(store, "fake:8b", 16384, accelerator="cpu")
    assert plan.size == plan.full and not plan.reduced and plan.seconds < 20


def test_a_small_window_is_never_planned_above_the_window(store):
    plan = plan_for(store, "fake:8b", 2048, accelerator="cpu")
    assert plan.size <= int(2048 * 0.8) and plan.size >= 256


def test_a_window_the_runtime_reports_smaller_after_the_probe_fails_the_check(store, ollama):
    ollama.models["fake:8b"]["applied_ctx"] = 4096
    ollama.loaded.append("fake:8b")
    result = run_planned_selfcheck(OllamaProvider(ollama.url), store, "fake:8b", 16384, accelerator="gpu")
    assert not result.ok and "applied a 4,096-token window, not the 16,384 requested" in result.detail and result.truncated


def test_the_runtimes_report_is_read_after_the_probe_not_before(store, ollama):
    """Found on a real Ollama: after a preload the runtime reports its own default window; only a request at the target window changes it."""
    provider = OllamaProvider(ollama.url)
    ollama.models["fake:8b"]["applied_ctx"] = 4096              # what a preload leaves behind
    ollama.loaded.append("fake:8b")

    def switches_window(request, estimated_prompt_tokens):
        ollama.models["fake:8b"]["applied_ctx"] = request.num_ctx   # the runtime reloads at the requested window on this request
        return provider.chat(request)

    assert run_planned_selfcheck(provider, store, "fake:8b", 16384, accelerator="gpu", request_runner=switches_window).ok


def test_a_shortened_probe_that_passes_says_how_far_it_verified(store, ollama):
    ollama.models["fake:8b"]["applied_ctx"] = 16384
    ollama.loaded.append("fake:8b")
    result = run_planned_selfcheck(OllamaProvider(ollama.url), store, "fake:8b", 16384, accelerator="cpu")
    assert result.ok
    assert "shortened from 12,000 to fit this machine's speed" in result.detail
    assert "the runtime reports a 16,384-token window in effect" in result.detail
    assert ollama.of("/api/chat")[-1]["body"]["options"]["num_ctx"] == 16384


def test_the_speed_of_a_real_probe_is_remembered_for_next_time(store, ollama):
    provider = OllamaProvider(ollama.url)

    def slow(request, estimated_prompt_tokens):
        time.sleep(1.15)
        return provider.chat(request)

    result = run_planned_selfcheck(provider, store, "fake:8b", 8192, accelerator="gpu", request_runner=slow)
    assert result.ok
    assert selfcheck_plan.measured_throughput(store, "fake:8b") and selfcheck_plan.measured_throughput(store, "fake:8b") > 0


def test_a_probe_that_fails_still_remembers_the_speed_and_is_not_a_pass(store, ollama):
    ollama.script = lambda body: {"content": "I do not know.", "prompt_tokens": 3000}
    provider = OllamaProvider(ollama.url)

    def slow(request, estimated_prompt_tokens):
        time.sleep(1.15)
        return provider.chat(request)

    result = run_planned_selfcheck(provider, store, "fake:8b", 4096, accelerator="gpu", request_runner=slow)
    assert not result.ok and selfcheck_plan.measured_throughput(store, "fake:8b")
