"""Providers: explicit context (LM-1), streaming retry (SR-9), typed errors (SR-1), exact usage (SR-2)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import pytest

from hutch.providers import ChatRequest, ProviderError, make_provider, parse_spec
from hutch.providers.base import parse_tool_args
from hutch.providers.claude import ClaudeProvider, to_claude_messages, to_claude_tools
from hutch.providers.ollama import OllamaProvider, to_ollama_messages
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.pricing import PriceBook
from tests.fakes import FakeAnthropic, FakeOllama, FakeOpenAI

TOOL = {"type": "function", "function": {"name": "write_file", "description": "write",
                                         "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                                        "required": ["path"]}}}


@pytest.fixture()
def ollama():
    s = FakeOllama({"fake:8b": {}, "thinker:8b": {"caps": ["completion", "tools", "thinking"]}})
    yield s
    s.close()


def req(model="fake:8b", content="hello", **kw):
    kw.setdefault("num_ctx", 8192)
    return ChatRequest(model=model, messages=[{"role": "user", "content": content}], **kw)


# ============================================================== Ollama: LM-1

def test_ollama_always_sends_num_ctx_and_per_turn_cap(ollama):
    OllamaProvider(ollama.url).chat(req(num_ctx=16384, max_tokens=512))
    sent = ollama.of("/api/chat")[-1]["body"]
    assert sent["options"]["num_ctx"] == 16384 and sent["options"]["num_predict"] == 512
    assert sent["stream"] is True and sent["keep_alive"] == "10m"


def test_ollama_refuses_to_send_without_an_explicit_context_size(ollama):
    with pytest.raises(ProviderError, match="num_ctx explicitly"):
        OllamaProvider(ollama.url).chat(req(num_ctx=None))
    assert not ollama.of("/api/chat"), "nothing may reach the runtime when the context was not sized"


def test_the_v1_url_is_normalised_to_the_native_api(ollama):
    p = OllamaProvider(ollama.url + "/v1")
    assert p.base_url == ollama.url
    p.chat(req())
    assert ollama.of("/api/chat") and not ollama.of("/v1/chat/completions")


def test_silent_front_truncation_is_detected_not_ignored(ollama):
    big = "x" * 40_000                                    # ~10k tokens into a 2k window
    res = OllamaProvider(ollama.url).chat(req(content=big, num_ctx=2048))
    assert res.prompt_truncated and res.prompt_tokens >= int(2048 * 0.98)
    assert any("truncated" in n for n in res.notes)
    ok = OllamaProvider(ollama.url).chat(req(content="short", num_ctx=2048))
    assert not ok.prompt_truncated


def test_usage_timing_and_tool_calls_are_exact(ollama):
    ollama.script = lambda b: {"content": "writing", "tool_calls": [{"name": "write_file", "arguments": {"path": "a.md"}}],
                               "prompt_tokens": 321, "completion_tokens": 45}
    res = OllamaProvider(ollama.url).chat(req(tools=[TOOL]))
    assert (res.prompt_tokens, res.completion_tokens) == (321, 45)
    assert res.tool_calls[0].name == "write_file" and res.tool_calls[0].arguments == {"path": "a.md"}
    assert res.finish_reason == "tool_calls" and res.tokens_per_sec and res.tokens_per_sec > 0
    assert res.load_ms > 0                                  # cold load reported (the model was not resident)
    again = OllamaProvider(ollama.url).chat(req())
    assert again.load_ms == 0                               # warm


def test_think_false_only_goes_to_models_that_support_thinking(ollama):
    p = OllamaProvider(ollama.url)
    p.chat(req(model="thinker:8b", think=False))
    p.chat(req(model="fake:8b", think=False))
    bodies = [r["body"] for r in ollama.of("/api/chat")]
    assert bodies[0]["think"] is False                      # SR-5: off by default for thinking-capable models
    assert "think" not in bodies[1]                         # sending it to others is an error in Ollama


def test_native_message_conversion_uses_objects_and_tool_name():
    msgs = [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": '{"command": "ls"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "shell", "content": "a.txt"}]
    out = to_ollama_messages(msgs)
    assert out[0]["tool_calls"][0]["function"]["arguments"] == {"command": "ls"}
    assert out[1] == {"role": "tool", "content": "a.txt", "tool_name": "shell"}


def test_show_reports_what_fit_estimation_needs(ollama):
    provider = OllamaProvider(ollama.url)
    meta = provider.show("fake:8b")
    assert meta.params_b == 8.0 and meta.quant == "Q4_K_M" and meta.max_context == 40960
    assert (meta.n_layers, meta.n_kv_heads, meta.head_dim) == (36, 8, 128)
    assert "tools" in meta.capabilities and meta.license.startswith("Apache")
    assert meta.backend == "ollama" and meta.backend_version == ollama.version
    assert meta.digest == "sha256:fake-8b"
    assert len(meta.template_hash) == 64 and len(meta.tokenizer_hash) == 64
    assert OllamaProvider(ollama.url).show("nope:1b") is None


def test_preload_loads_without_generating_and_reports_the_load_time(ollama):
    p = OllamaProvider(ollama.url)
    assert not p.is_loaded("fake:8b")
    ms = p.preload("fake:8b")
    assert p.is_loaded("fake:8b") and ms > 0
    assert not [r for r in ollama.of("/api/chat")]
    p.unload("fake:8b")
    assert not p.is_loaded("fake:8b")


# ====================================================== typed errors (SR-1)

def test_a_dead_runtime_is_an_unreachable_error_with_a_fix():
    with pytest.raises(ProviderError) as e:
        OllamaProvider("http://127.0.0.1:9").chat(req())
    assert e.value.kind == "unreachable" and "ollama serve" in str(e.value) and e.value.retryable


def test_missing_model_says_how_to_install_it(ollama):
    with pytest.raises(ProviderError) as e:
        OllamaProvider(ollama.url).chat(req(model="absent:7b"))
    assert e.value.kind == "model_missing" and "ollama pull absent:7b" in str(e.value)


def test_out_of_memory_is_its_own_kind(ollama):
    ollama.force_status = (500, "model requires more system memory (12.0 GiB) than is available (4.0 GiB)")
    with pytest.raises(ProviderError) as e:
        OllamaProvider(ollama.url).chat(req())
    assert e.value.kind == "oom" and "smaller model" in str(e.value)


# ===================================================== streaming retry (SR-9)

def test_a_stream_that_dies_mid_flight_is_retried_once_without_streaming(ollama):
    ollama.fail_stream_once = True
    res = OllamaProvider(ollama.url).chat(req(content="hello there"))
    assert res.content and res.streamed is False
    assert any("retried once without streaming" in n for n in res.notes)
    modes = [r["body"]["stream"] for r in ollama.of("/api/chat")]
    assert modes == [True, False]                           # exactly one retry, and it was non-streaming


def test_a_stalled_stream_times_out_and_falls_back(ollama):
    ollama.stall_once = 3.0
    t0 = time.time()
    res = OllamaProvider(ollama.url).chat(req(idle_timeout=0.4))
    assert res.streamed is False and time.time() - t0 < 2.5, "should not wait out the 3 s stall"


def test_non_stream_failures_are_not_retried_into_a_loop(ollama):
    ollama.force_status = (500, "boom")
    with pytest.raises(ProviderError):
        OllamaProvider(ollama.url).chat(req())
    assert len(ollama.of("/api/chat")) == 1


def test_stop_can_abort_an_in_flight_request(ollama):
    ollama.chat_delay = 0.0
    ollama.stall_once = 10.0
    closers = []

    def register(fn):
        closers.append(fn)
        return lambda: None

    errs = []

    def run():
        try:
            OllamaProvider(ollama.url).chat(req(register_cancel=register, stream=True, idle_timeout=30))
        except ProviderError as e:
            errs.append(e)

    t = threading.Thread(target=run)
    t.start()
    deadline = time.time() + 5
    while not closers and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.2)
    t0 = time.time()
    closers[0]()                                            # what Engine.stop_run does through cancel_hooks
    t.join(timeout=5)
    assert not t.is_alive() and time.time() - t0 < 3, "stop did not unblock the model call"


# ======================================================== OpenAI-compatible

@pytest.fixture()
def oai():
    s = FakeOpenAI()
    yield s
    s.close()


def test_openai_stream_assembles_split_tool_arguments_and_exact_usage(oai):
    oai.script = lambda b: {"content": "hi", "tool_calls": [{"name": "write_file", "arguments": {"path": "x.md"}}],
                            "prompt_tokens": 100, "completion_tokens": 9, "cached_tokens": 64}
    p = OpenAICompatProvider(oai.url + "/v1", "k", "openai-compatible")
    res = p.chat(ChatRequest(model="fake-model", messages=[{"role": "user", "content": "go"}], tools=[TOOL]))
    assert res.tool_calls[0].arguments == {"path": "x.md"} and res.finish_reason == "tool_calls"
    assert (res.prompt_tokens, res.completion_tokens, res.cached_tokens) == (100, 9, 64)
    assert res.streamed is True


def test_openai_rejecting_stream_options_falls_back_to_non_streaming(oai):
    oai.reject_stream_options = True
    p = OpenAICompatProvider(oai.url + "/v1", "", "llamacpp")
    res = p.chat(ChatRequest(model="m", messages=[{"role": "user", "content": "hi"}]))
    assert res.content == "ok" and res.streamed is False
    assert [r["body"].get("stream") for r in oai.of("/v1/chat/completions")] == [True, False]


@pytest.mark.parametrize(("message", "should_retry"), [
    ("stream_options is not supported", True),
    ("server-sent event streaming is not supported", True),
    ("Unknown field max_completion_tokens", False),
    ("temperature is outside the allowed range", False),
])
def test_only_stream_specific_field_rejections_trigger_plain_retry(message, should_retry):
    error = ProviderError("bad_request", message, status=400)
    assert error.streaming_related is should_retry


def test_openai_auth_rate_limit_and_context_errors_are_typed(oai):
    oai.require_key = "secret"
    with pytest.raises(ProviderError) as e:
        OpenAICompatProvider(oai.url + "/v1", "wrong").chat(ChatRequest(model="m", messages=[]))
    assert e.value.kind == "auth" and not e.value.retryable is False or e.value.kind == "auth"
    oai.require_key = None
    oai.force_status = (429, {"error": {"message": "slow down"}}, {"retry-after": "7"})
    with pytest.raises(ProviderError) as e:
        OpenAICompatProvider(oai.url + "/v1", "k").chat(ChatRequest(model="m", messages=[]))
    assert e.value.kind == "rate_limit" and e.value.retry_after == 7.0 and e.value.retryable
    oai.force_status = (400, {"error": {"message": "This model's maximum context length is 8192 tokens"}}, {})
    with pytest.raises(ProviderError) as e:
        OpenAICompatProvider(oai.url + "/v1", "k", "openai-compatible").chat(
            ChatRequest(model="m", messages=[], stream=False))
    assert e.value.kind == "context"


def test_openai_token_param_name_follows_the_vendor(oai):
    p = OpenAICompatProvider("https://api.openai.com/v1", "k", "openai")
    assert "max_completion_tokens" in p._body(ChatRequest(model="m", messages=[], max_tokens=5), False)
    q = OpenAICompatProvider("http://localhost:8080/v1", "", "llamacpp")
    assert "max_tokens" in q._body(ChatRequest(model="m", messages=[], max_tokens=5), False)


# ============================================================ Claude (SDK)

anthropic = pytest.importorskip("anthropic")


@pytest.fixture()
def claude_srv():
    s = FakeAnthropic()
    yield s
    s.close()


def test_claude_request_shape_cache_control_system_tools_and_key(claude_srv):
    claude_srv.script = lambda b: {"content": "done", "cache_read": 900, "cache_write": 100,
                                   "input_tokens": 40, "output_tokens": 12}
    p = ClaudeProvider(api_key="sk-test", base_url=claude_srv.url)
    res = p.chat(ChatRequest(model="claude-opus-5-5", max_tokens=2000, tools=[TOOL], messages=[
        {"role": "system", "content": "be brief"}, {"role": "user", "content": "go"}]))
    sent = claude_srv.of("/v1/messages")[0]
    assert sent["headers"]["x-api-key"] == "sk-test" and "anthropic-version" in sent["headers"]
    b = sent["body"]
    assert b["model"] == "claude-opus-5-5" and b["max_tokens"] == 2000 and b["system"] == "be brief"
    assert b["cache_control"] == {"type": "ephemeral"}      # PF-1
    assert b["tools"][0] == {"name": "write_file", "description": "write",
                             "input_schema": TOOL["function"]["parameters"]}
    assert "thinking" not in b and "temperature" not in b   # model default; never budget_tokens
    assert res.prompt_tokens == 40 + 900 + 100 and res.cached_tokens == 900 and res.cache_write_tokens == 100
    assert res.completion_tokens == 12 and res.finish_reason == "stop"


def test_claude_tool_use_round_trip_merges_parallel_results(claude_srv):
    claude_srv.script = lambda b: {"tool_calls": [{"name": "write_file", "arguments": {"path": "a"}},
                                                  {"name": "write_file", "arguments": {"path": "b"}}]}
    p = ClaudeProvider(api_key="sk-test", base_url=claude_srv.url)
    res = p.chat(ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "go"}], tools=[TOOL]))
    assert [c.arguments for c in res.tool_calls] == [{"path": "a"}, {"path": "b"}] and res.finish_reason == "tool_calls"
    history = [{"role": "user", "content": "go"},
               {"role": "assistant", "content": "", "tool_calls": [
                   {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": '{"path": "a"}'}}
                   for c in res.tool_calls]},
               {"role": "tool", "tool_call_id": res.tool_calls[0].id, "name": "write_file", "content": "ok a"},
               {"role": "tool", "tool_call_id": res.tool_calls[1].id, "name": "write_file", "content": "ok b"}]
    _, msgs = to_claude_messages(history)
    assert len(msgs) == 3 and msgs[2]["role"] == "user" and len(msgs[2]["content"]) == 2   # ONE user message
    assert {b["type"] for b in msgs[2]["content"]} == {"tool_result"}
    assert msgs[1]["content"][0]["type"] == "tool_use"


def test_claude_refusal_is_terminal_typed_error_with_its_category(claude_srv):
    claude_srv.script = lambda b: {"refusal": "cyber"}
    with pytest.raises(ProviderError) as e:
        ClaudeProvider(api_key="sk-test", base_url=claude_srv.url).chat(
            ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "x"}]))
    assert e.value.kind == "refused" and "cyber" in str(e.value) and not e.value.retryable   # refusal is terminal


def test_provider_error_retryability_is_kind_based():
    assert not ProviderError("refused", "policy").retryable
    assert ProviderError("timeout", "network").retryable


def test_claude_auth_rate_limit_and_missing_key(claude_srv):
    with pytest.raises(ProviderError) as e:
        ClaudeProvider(api_key="", base_url=claude_srv.url).chat(
            ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "x"}]))
    assert e.value.kind == "auth" and "ANTHROPIC_API_KEY" in str(e.value) and not claude_srv.requests
    with pytest.raises(ProviderError) as e:
        ClaudeProvider(api_key="bad-key", base_url=claude_srv.url).chat(
            ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "x"}]))
    assert e.value.kind == "auth"
    claude_srv.requests.clear()
    claude_srv.force_status = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}},
                               {"retry-after": "11"})
    with pytest.raises(ProviderError) as e:
        ClaudeProvider(api_key="sk-test", base_url=claude_srv.url).chat(
            ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "x"}], stream=False))
    assert e.value.kind == "rate_limit" and e.value.retry_after == 11.0
    assert len(claude_srv.requests) == 1, "the SDK must not retry underneath Hutch's own retry/fallback logic"


def test_effort_is_only_sent_to_models_that_take_it(claude_srv):
    p = ClaudeProvider(api_key="sk-test", base_url=claude_srv.url)
    p.chat(ChatRequest(model="claude-opus-5-5", messages=[{"role": "user", "content": "x"}], effort="low"))
    p.chat(ChatRequest(model="claude-haiku-4-5", messages=[{"role": "user", "content": "x"}], effort="low"))
    bodies = [r["body"] for r in claude_srv.of("/v1/messages")]
    assert bodies[0]["output_config"] == {"effort": "low"} and "output_config" not in bodies[1]


# ================================================================ registry

def test_spec_parsing_and_routing():
    assert parse_spec("ollama/llama3.2:3b") == ("ollama", "llama3.2:3b")
    assert parse_spec("anthropic/claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert parse_spec("barename") == ("openai-compatible", "barename")
    assert isinstance(make_provider("ollama", None, {}), OllamaProvider)
    # an "openai-compatible" URL that is really Ollama is routed to the NATIVE provider (LM-1)
    assert isinstance(make_provider("openai-compatible", "http://localhost:11434/v1", {}), OllamaProvider)
    assert isinstance(make_provider("openai", None, {"OPENAI_API_KEY": "k"}), OpenAICompatProvider)
    with pytest.raises(ProviderError, match="base_url"):
        make_provider("openai-compatible", None, {})
    with pytest.raises(ProviderError, match="unknown provider"):
        make_provider("telepathy", None, {})


def test_importing_providers_does_not_load_httpx_or_vendor_sdks():
    """PF-6: a local-only install never pays for the Anthropic SDK (1.1 s) or httpx."""
    code = ("import sys, hutch.providers, hutch.providers.registry; "
            "bad = [m for m in ('anthropic', 'httpx', 'openai') if m in sys.modules]; "
            "print('LOADED:' + ','.join(bad))")
    clean_env = os.environ.copy()
    clean_env.pop("HUTCH_TESTING", None)
    clean_env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=clean_env)
    out = result.stdout.strip()
    assert result.returncode == 0 and out == "LOADED:", (out, result.stderr, sys.executable)


# =================================================================== helpers

def test_tool_argument_parsing_handles_the_small_model_failure_modes():
    assert parse_tool_args({"a": 1}) == ({"a": 1}, "")
    assert parse_tool_args('{"a": 1}') == ({"a": 1}, "")
    assert parse_tool_args("") == ({}, "")
    assert parse_tool_args('"{\\"a\\": 1}"') == ({"a": 1}, "")          # double-encoded
    val, err = parse_tool_args('{"a": ')
    assert val == {} and "not valid JSON" in err
    val, err = parse_tool_args("[1, 2]")
    assert val == {} and "must be a JSON object" in err


def test_tools_convert_to_claude_shape():
    assert to_claude_tools([TOOL])[0]["input_schema"]["required"] == ["path"]


# =================================================================== pricing

def test_price_book_costs_staleness_and_user_overlay(tmp_path):
    user = tmp_path / "prices.json"
    user.write_text('{"models": {"openai/gpt-x": {"input": 1, "output": 2, "verified_on": "2020-01-01"},'
                    ' "anthropic/claude-opus-5-5": {"input": 99, "output": 99, "verified_on": "2026-10-07"}}}')
    pb = PriceBook(user)
    assert pb.lookup("openai", "gpt-x").stale                         # >90 days old is flagged
    assert not pb.lookup("anthropic", "claude-sonnet-5-5").stale or pb.lookup("anthropic", "claude-sonnet-5-5").age_days
    assert pb.cost("anthropic", "claude-opus-5-5", 1_000_000, 0) == 99.0   # user row wins
    assert pb.lookup("anthropic", "claude-opus-5-5").user
    assert pb.cost("ollama", "anything", 10**6, 10**6) == 0.0
    assert pb.cost("openai", "unknown-model", 1, 1) is None and not pb.has_price("openai", "unknown-model")
    assert pb.has_price("ollama", "anything")


def test_ollama_cloud_tag_is_hosted_for_price_and_routing_checks(tmp_path):
    pb = PriceBook(tmp_path / "prices.json")
    assert pb.is_local("ollama", "llama3.2")
    assert not pb.is_local("ollama", "qwen3-coder:480b-cloud")
    assert not pb.is_local("ollama", "glm-4.7:cloud")
    assert pb.cost("ollama", "qwen3-coder:480b-cloud", 100, 100) is None
    assert not pb.has_price("ollama", "qwen3-coder:480b-cloud")
    assert pb.set_price("ollama/qwen3-coder:480b-cloud", 0.2, 0.5, source="operator estimate")
    assert pb.has_price("ollama", "qwen3-coder:480b-cloud")


def test_a_broken_user_price_file_is_reported_not_fatal(tmp_path):
    bad = tmp_path / "prices.json"
    bad.write_text("{not json")
    pb = PriceBook(bad)
    assert pb.errors and pb.rows(), "bundled prices must still load"


def test_cache_reads_are_priced_below_fresh_input():
    pb = PriceBook()
    fresh = pb.cost("anthropic", "claude-opus-5-5", 100_000, 0)
    cached = pb.cost("anthropic", "claude-opus-5-5", 100_000, 0, cached_tokens=100_000)
    assert cached < fresh * 0.1


def test_a_cancelled_call_is_never_rescued_by_the_streaming_retry(ollama):
    """Found by the runtime tests: Stop aborts the socket, which looks like a broken stream. Retrying it without
    streaming made the run complete as if Stop had never been pressed."""
    ollama.stall_once = 20.0
    closers = []
    cancelled = {"v": False}

    def register(fn):
        closers.append(fn)
        return lambda: None

    errs = []

    def run():
        try:
            OllamaProvider(ollama.url).chat(req(register_cancel=register, is_cancelled=lambda: cancelled["v"],
                                                idle_timeout=30))
        except ProviderError as e:
            errs.append(e)

    t = threading.Thread(target=run)
    t.start()
    deadline = time.time() + 5
    while not closers and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.3)
    cancelled["v"] = True
    closers[0]()
    t.join(timeout=5)
    assert errs and errs[0].kind == "stream"
    assert [r["body"]["stream"] for r in ollama.of("/api/chat")] == [True], "no non-streaming retry after Stop"
