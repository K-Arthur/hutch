"""Model installation, measured residency, and reasoning separation.

These are regression tests, not acceptance evidence. The behaviour they cover was
established against a real Ollama 0.40.13 runtime with real installed models (qwen3:4b,
qwen2.5-coder:1.5b) and recorded in docs/realignment/offline-models-2026-10-31.md; what
they protect is the exact shapes observed there, so a change that regresses them fails
here instead of silently shipping.

The fake below mirrors the wire shapes captured from that runtime:
`/api/pull` emitting per-blob ndjson with `total`/`completed` and ending in `success`,
`/api/ps` carrying `context_length` and `size_vram`, and a thinking-capable model
returning its reasoning inside `content` when the runtime declines to separate it.
"""

from __future__ import annotations

import threading
import time

import pytest

from hutch.providers.base import ModelMeta, ProviderError
from hutch.providers.model_install import (
    MAX_CONCURRENT_INSTALLS, ModelInstaller, _same_model, validate_model_name,
)
from hutch.providers.ollama import OllamaProvider
from hutch.providers.ollama_extras import split_leaked_reasoning as _split_leaked_reasoning
from tests.fakes import FakeOllama


@pytest.fixture()
def fake():
    server = FakeOllama(models={"fake:4b": {}})   # starts its own loopback server on construction
    try:
        yield server
    finally:
        server.close()


def provider_for(server) -> OllamaProvider:
    return OllamaProvider(server.url)


def wait_done(job, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and job.state in ("starting", "running"):
        time.sleep(0.01)
    return job


# ------------------------------------------------------------------ model names

@pytest.mark.parametrize("raw,expected", [
    ("qwen3:4b", "qwen3:4b"),
    ("qwen3", "qwen3:latest"),                 # a bare name is the `latest` tag
    ("library/qwen3:4b", "qwen3:4b"),          # `library/` is the default namespace
    ("qwen2.5-coder:1.5b", "qwen2.5-coder:1.5b"),
])
def test_valid_model_names_are_normalized(raw, expected):
    assert validate_model_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "../evil", "a b", "model;rm -rf /", "x" * 200,
                                 "model:tag:extra", "host/ns/model/tag"])
def test_invalid_model_names_are_refused_before_any_request(raw):
    with pytest.raises(ValueError):
        validate_model_name(raw)


def test_namespace_and_tag_semantics():
    assert _same_model("qwen3", "qwen3:latest")
    assert _same_model("library/qwen3:4b", "qwen3:4b")   # `library/` is the default namespace
    assert _same_model("Qwen3:4B", "qwen3:4b")           # the runtime compares case-insensitively
    assert not _same_model("qwen3:4b", "qwen3:latest")   # different tags are different models
    assert not _same_model("ns/qwen3:4b", "qwen3:4b")    # a non-default namespace is distinct


# ------------------------------------------------------------------ installation

def test_install_downloads_then_confirms_against_the_runtime(fake):
    installer = ModelInstaller(provider_for(fake))
    assert "new:1b" not in installer.installed()

    job = wait_done(installer.start("new:1b"))

    assert job.state == "done", job.error
    assert job.percent == 100.0
    # Success is confirmed from /api/tags, not assumed from the stream ending.
    assert "new:1b" in installer.installed()


def test_install_reports_progress_from_the_runtimes_own_counters(fake):
    fake.pull_total = 800_000
    fake.pull_events = 4
    fake.pull_delay = 0.05
    installer = ModelInstaller(provider_for(fake))
    job = installer.start("slower:7b")
    seen = set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and job.state in ("starting", "running"):
        if job.total:
            seen.add(job.completed)
        time.sleep(0.01)
    wait_done(job)
    assert job.state == "done", job.error
    assert len(seen) > 1, "progress should advance through several byte counts"
    assert max(seen) <= job.total


def test_install_refuses_a_model_that_is_already_present(fake):
    installer = ModelInstaller(provider_for(fake))
    with pytest.raises(ProviderError) as excinfo:
        installer.start("fake:4b")
    assert "already installed" in str(excinfo.value)


def test_install_refuses_a_duplicate_while_one_is_running(fake):
    fake.pull_delay = 0.05
    fake.pull_events = 20
    installer = ModelInstaller(provider_for(fake))
    job = installer.start("dup:1b")
    with pytest.raises(ProviderError) as excinfo:
        installer.start("library/dup:1b")     # same model, different spelling
    assert "already being installed" in str(excinfo.value)
    installer.cancel(job.id)
    wait_done(job)


def test_install_bounds_concurrent_downloads(fake):
    fake.pull_delay = 0.05
    fake.pull_events = 40
    installer = ModelInstaller(provider_for(fake))
    jobs = [installer.start(f"bulk{i}:1b") for i in range(MAX_CONCURRENT_INSTALLS)]
    with pytest.raises(ProviderError) as excinfo:
        installer.start("onemore:1b")
    assert "already running" in str(excinfo.value)
    for job in jobs:
        installer.cancel(job.id)
        wait_done(job)


def test_cancel_stops_the_download_and_leaves_the_model_absent(fake):
    fake.pull_delay = 0.05
    fake.pull_events = 200
    installer = ModelInstaller(provider_for(fake))
    job = installer.start("partial:3b")
    time.sleep(0.05)
    assert installer.cancel(job.id)
    wait_done(job)
    assert job.state == "cancelled"
    assert "partial:3b" not in installer.installed()
    # Nothing is left running: the model can be offered again immediately.
    again = installer.start("partial:3b")
    installer.cancel(again.id)
    wait_done(again)


def test_a_stream_that_ends_without_success_is_a_failure(fake):
    """The runtime saying `success` is necessary; a truncated stream must not read as done."""
    installer = ModelInstaller(provider_for(fake))

    def truncated_pull(model, **_kwargs):
        yield {"status": "pulling manifest"}
        yield {"status": "pulling abc", "digest": "sha256:abc", "total": 100, "completed": 100}

    fake_provider = provider_for(fake)
    fake_provider.pull_events = truncated_pull
    job = wait_done(ModelInstaller(fake_provider).start("truncated:1b"))
    assert job.state == "failed"
    assert "before the runtime reported success" in job.error


def test_success_without_the_model_in_the_registry_is_a_failure(fake):
    """A runtime that says `success` but does not list the model must not be reported as installed."""
    fake_provider = provider_for(fake)

    def lying_pull(model, **_kwargs):
        yield {"status": "success"}

    fake_provider.pull_events = lying_pull
    job = wait_done(ModelInstaller(fake_provider).start("ghost:1b"))
    assert job.state == "failed"
    assert "does not list the model" in job.error


def test_an_error_event_fails_the_job(fake):
    fake_provider = provider_for(fake)

    def failing_pull(model, **_kwargs):
        yield {"status": "pulling manifest"}
        yield {"error": "no space left on device"}

    fake_provider.pull_events = failing_pull
    job = wait_done(ModelInstaller(fake_provider).start("toobig:70b"))
    assert job.state == "failed"
    assert "no space left" in job.error


def test_remove_deletes_from_the_runtime(fake):
    installer = ModelInstaller(provider_for(fake))
    assert "fake:4b" in installer.installed()
    assert installer.remove("fake:4b") == "fake:4b"
    assert "fake:4b" not in installer.installed()


def test_remove_refuses_while_that_model_is_installing(fake):
    fake.pull_delay = 0.05
    fake.pull_events = 40
    installer = ModelInstaller(provider_for(fake))
    job = installer.start("busy:1b")
    with pytest.raises(ProviderError):
        installer.remove("busy:1b")
    installer.cancel(job.id)
    wait_done(job)


def test_remove_of_a_missing_model_is_reported_as_missing(fake):
    installer = ModelInstaller(provider_for(fake))
    with pytest.raises(ProviderError) as excinfo:
        installer.remove("never:existed")
    assert excinfo.value.kind == "model_missing"


def test_installed_reflects_the_runtime_not_the_job_registry(fake):
    """The registry is not the source of truth: a job list can be lost, the runtime cannot."""
    installer = ModelInstaller(provider_for(fake))
    wait_done(installer.start("durable:1b"))
    fresh = ModelInstaller(provider_for(fake))     # a new process, as after a restart
    assert fresh.jobs() == []
    assert "durable:1b" in fresh.installed()


# ------------------------------------------------------------------ residency

def test_residency_reports_the_window_actually_applied(fake):
    """`/api/ps` carries the window in effect; it need not be the one that was asked for."""
    fake.models["fake:4b"]["applied_ctx"] = 4096
    provider = provider_for(fake)
    provider.preload("fake:4b")

    meta = provider.show("fake:4b")

    assert meta is not None
    assert meta.applied_context == 4096
    assert meta.vram_bytes == 0          # measured: entirely on the CPU
    assert not meta.wants_gpu


def test_residency_is_unknown_rather_than_zero_for_an_unloaded_model(fake):
    provider = provider_for(fake)
    meta = provider.show("fake:4b")      # never preloaded
    assert meta is not None
    assert meta.applied_context is None
    assert meta.vram_bytes is None


def test_residency_distinguishes_a_gpu_resident_model(fake):
    fake.vram_bytes = 4_000_000_000
    provider = provider_for(fake)
    provider.preload("fake:4b")
    meta = provider.show("fake:4b")
    assert meta is not None and meta.wants_gpu


def test_a_measurement_without_arithmetic_still_reads_as_loaded():
    from hutch.modelview import residency_note
    note = residency_note(ModelMeta(name="m", applied_context=16384, resident_bytes=5_000_000_000, vram_bytes=0))
    assert "16,384" in note
    assert "CPU" in note
    assert residency_note(ModelMeta(name="m")) == ""


# ------------------------------------------------------------------ reasoning

def test_real_leaked_reasoning_is_moved_out_of_the_answer():
    """The exact shape captured from Ollama 0.40.13 + qwen3:4b with think:false."""
    leaked = ("Hmm, the user asked to reply with exactly three words.\n\n"
              "Okay: local model works\n</think>\n\nlocal model works")
    content, thinking = _split_leaked_reasoning(leaked, "")
    assert content == "local model works"
    assert "</think>" not in content
    assert "exactly three words" in thinking


def test_already_separated_thinking_is_untouched():
    content, thinking = _split_leaked_reasoning("the answer", "the reasoning")
    assert (content, thinking) == ("the answer", "the reasoning")


def test_content_without_a_marker_is_untouched():
    assert _split_leaked_reasoning("plain answer", "") == ("plain answer", "")


def test_a_marker_with_nothing_after_it_is_left_alone():
    """No guess: without real text after the marker, the shape is ambiguous."""
    assert _split_leaked_reasoning("reasoning only</think>", "") == ("reasoning only</think>", "")


def test_split_happens_at_the_last_marker():
    content, thinking = _split_leaked_reasoning("a</think>b</think>final", "")
    assert content == "final"
    assert thinking.count("</think>") == 2


def test_fold_applies_the_repair_to_a_reply(fake):
    fake.script = lambda body: {"content": "working</think>done"}
    provider = provider_for(fake)
    from hutch.providers.base import ChatRequest
    result = provider.chat(ChatRequest(model="fake:4b", messages=[{"role": "user", "content": "hi"}],
                                       num_ctx=4096))
    assert result.content == "done"
    assert "</think>" not in result.content
