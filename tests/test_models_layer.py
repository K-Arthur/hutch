"""Hardware probe (LM-4), fit (LM-5), presets (LM-7), context planning/self-check (LM-1/2/3)."""

from __future__ import annotations

import pytest

from hutch.context import check_prompt, estimate_tokens, plan_context, prompt_tokens, run_selfcheck
from hutch.fit import estimate_fit, kv_bytes_per_token, weights_gib
from hutch.hardware import GIB, Hardware, Gpu, Readers, probe
from hutch.presets import catalog_meta, load_presets, resolve_preset
from hutch.providers.base import ModelMeta
from hutch.providers.ollama import OllamaProvider
from tests.fakes import FakeOllama


# ---------------------------------------------------------------- canned machines

def readers(*, system="linux", machine="x86_64", files=None, cmds=None, http=None, which=(), cores=8, env=None,
            drm=()):
    files, cmds, http = files or {}, cmds or {}, http or {}
    return Readers(
        read=lambda p: files.get(p), run=lambda argv: cmds.get(" ".join(argv)),
        http_get=lambda url: next((v for k, v in http.items() if url.startswith(k)), None),
        which=lambda n: f"/usr/bin/{n}" if n in which else None, system=system, machine=machine, cpu_count=cores,
        env=env or {}, listdir=lambda p: list(drm) if p == "/sys/class/drm" else [])


def meminfo(total_gb, avail_gb):
    return {"/proc/meminfo": f"MemTotal: {int(total_gb * GIB / 1024)} kB\nMemAvailable: {int(avail_gb * GIB / 1024)} kB\n",
            "/proc/cpuinfo": "model name\t: Test CPU 9000\n"}


def test_probe_nvidia_workstation_is_a_gpu_machine():
    r = readers(files=meminfo(32, 24), which=("nvidia-smi", "ollama"),
                cmds={"nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits":
                      "NVIDIA GeForce RTX 3060, 12288, 11800\n"},
                http={"http://localhost:11434/api/version": '{"version":"0.12.3"}'})
    hw = probe(r)
    assert hw.accelerator == "gpu" and hw.gpus[0].vram_gb == 12.0
    assert 10.5 < hw.budget_gb < 11.5 and hw.tier == "medium"
    ollama = next(x for x in hw.runtimes if x.name == "ollama")
    assert ollama.reachable and ollama.version == "0.12.3" and ollama.installed


def test_probe_apple_silicon_uses_unified_memory():
    r = readers(system="darwin", machine="arm64", cmds={
        "sysctl -n hw.memsize": str(16 * GIB), "sysctl -n machdep.cpu.brand_string": "Apple M2",
        "vm_stat": "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 200000.\n"
                   "Pages inactive: 300000.\nPages speculative: 10000.\n"})
    hw = probe(r)
    assert hw.apple_silicon and hw.accelerator == "unified" and hw.ram_total_gb == 16.0
    assert 6 < hw.budget_gb <= 11.2 and hw.gpus[0].vendor == "apple"


def test_probe_cpu_only_laptop_counts_only_free_ram():
    hw = probe(readers(files=meminfo(8, 2)), with_runtimes=False)
    assert hw.accelerator == "cpu" and hw.budget_gb == pytest.approx(1.7, abs=0.05)
    assert any("CPU inference works but is slow" in n for n in hw.notes)
    assert any("free right now" in n for n in hw.notes)


def test_an_amd_apu_is_integrated_and_does_not_count_as_a_gpu():
    r = readers(files={**meminfo(22, 10), "/sys/class/drm/card0/device/vendor": "0x1002\n",
                       "/sys/class/drm/card0/device/mem_info_vram_total": str(512 * 1024 ** 2)},
                drm=("card0", "card0-eDP-1"), which=("lspci",),
                cmds={"lspci": "04:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Lucienne (rev c3)\n"})
    hw = probe(r, with_runtimes=False)
    assert hw.accelerator == "cpu" and hw.gpus[0].integrated
    assert "Lucienne" in hw.gpus[0].name
    assert any("integrated GPU" in n for n in hw.notes)


def test_runtime_detection_distinguishes_installed_from_running():
    hw = probe(readers(files=meminfo(16, 12), which=("ollama",)))      # installed, but nothing answers
    o = next(x for x in hw.runtimes if x.name == "ollama")
    assert o.installed and not o.reachable and o.detail == "installed but not running"
    assert next(x for x in hw.runtimes if x.name == "llama.cpp").detail == "not found"


# ------------------------------------------------------------------ fit (LM-5)

def hw_with(budget_gb: float) -> Hardware:
    # a GPU box whose budget is exactly budget_gb
    return Hardware(gpus=[Gpu("X", "nvidia", budget_gb / 0.92, False, budget_gb / 0.92)], ram_total_gb=64,
                    ram_available_gb=48)


def test_qwen3_8b_fits_tight_or_wont_fit_depending_on_memory():
    meta = catalog_meta("qwen3:8b")
    assert estimate_fit(meta, hw_with(24), 32768).status == "fits"
    tight = estimate_fit(meta, hw_with(8.5), 32768)
    assert tight.status == "tight" and tight.effective_ctx < 32768 and tight.effective_ctx >= 4096
    assert estimate_fit(meta, hw_with(4), 32768).status == "wont_fit"


def test_the_context_it_will_actually_get_shrinks_with_memory():
    meta = catalog_meta("qwen3:8b")
    big, small = estimate_fit(meta, hw_with(16), 40960), estimate_fit(meta, hw_with(8), 40960)
    assert big.effective_ctx > small.effective_ctx and small.effective_ctx < 40960
    assert big.effective_ctx <= meta.max_context


def test_kv_formula_matches_the_published_llama3_8b_figure():
    # Llama-3-8B: 32 layers x 8 KV heads x 128 dim -> 128 KiB per token at fp16
    meta = ModelMeta("llama3:8b", n_layers=32, n_kv_heads=8, head_dim=128, params_b=8.0, size_bytes=int(4.7 * GIB))
    per_tok, estimated = kv_bytes_per_token(meta)
    assert per_tok == 131072 and not estimated


def test_installed_numbers_beat_catalog_estimates_and_estimates_are_labelled():
    installed = ModelMeta("m", params_b=8, size_bytes=int(5 * GIB), n_layers=36, n_kv_heads=8, head_dim=128,
                          max_context=40960)
    assert not estimate_fit(installed, hw_with(24), 8192).estimated
    guess = ModelMeta("m", params_b=8)                       # nothing but a parameter count
    assert estimate_fit(guess, hw_with(24), 8192).estimated and weights_gib(guess)[1]


def test_a_model_that_cannot_hold_a_useful_window_is_wont_fit_not_tight():
    meta = catalog_meta("qwen3:14b")
    f = estimate_fit(meta, hw_with(10.5), 32768, min_ctx=16384)
    assert f.status == "wont_fit" and "needs at least" in f.reason


# --------------------------------------------------------------- presets (LM-7)

def test_all_six_task_presets_exist_with_caps_and_a_hosted_pick():
    p = load_presets()
    assert set(p) == {"router", "research", "extraction", "coding", "planner", "vision"}
    for x in p.values():
        assert x.hosted == "anthropic/claude-opus-5-5" and x.limits["max_steps"] and x.limits["max_turn_tokens"]
        assert x.want_ctx >= x.min_ctx and "tools" in x.needs


def test_resolution_scales_with_hardware_and_prefers_installed():
    p = load_presets()["research"]
    assert resolve_preset(p, hw_with(24), {}).local_model == "qwen3:14b"          # large tier
    assert resolve_preset(p, hw_with(48), {}).local_model == "qwen3:32b"          # xl tier
    r = resolve_preset(p, hw_with(24), {})
    assert not r.installed and r.install_hint == "ollama pull qwen3:14b"
    have = {"qwen3:8b": ModelMeta("qwen3:8b", params_b=8.2, size_bytes=int(5.2 * GIB), n_layers=36, n_kv_heads=8,
                                  head_dim=128, max_context=40960, capabilities=["tools"])}
    r2 = resolve_preset(p, hw_with(24), have)
    assert r2.local_model == "qwen3:8b" and r2.installed and not r2.install_hint


def test_nothing_fitting_means_hosted_only_with_the_reason_spelled_out():
    r = resolve_preset(load_presets()["research"], hw_with(1.5), {})
    assert r.local_model is None and "no local model fits" in r.reason and r.hosted.startswith("anthropic/")
    assert r.considered


def test_vision_needs_a_vision_model_and_is_hosted_only_on_small_machines():
    p = load_presets()["vision"]
    assert resolve_preset(p, hw_with(5), {}).local_model is None
    # at 24 GiB the 26B model would be squeezed below the window wanted, so the 12B that fits wins
    assert resolve_preset(p, hw_with(24), {}).local_model == "gemma4:12b"


def test_user_presets_file_overrides_the_bundled_one(tmp_path):
    f = tmp_path / "presets.json"
    f.write_text('{"hosted_default": "anthropic/claude-sonnet-5-5", "presets": {"router": {"want_ctx": 4096}}}')
    p = load_presets(f)
    assert p["router"].want_ctx == 4096 and p["router"].hosted == "anthropic/claude-sonnet-5-5"
    assert p["research"].hosted == "anthropic/claude-sonnet-5-5"


# ---------------------------------------------------- pre-run warning (LM-3)

def test_prompt_plus_tools_over_the_window_fails_with_a_fix():
    big = [{"role": "system", "content": "x" * 40_000}, {"role": "user", "content": "go"}]
    tools = [{"type": "function", "function": {"name": "t", "parameters": {"type": "object"}}}] * 8
    c = check_prompt(big, tools, effective_ctx=4096, max_turn_tokens=512)
    assert c.severity == "fail" and "cannot fit" in c.message and "fewer tools" in c.fix


def test_a_prompt_that_crowds_the_window_warns_and_a_small_one_is_ok():
    msgs = [{"role": "user", "content": "x" * 9_000}]
    assert check_prompt(msgs, [], 4096, 512).severity == "warn"
    assert check_prompt([{"role": "user", "content": "hi"}], [], 8192, 512).severity == "ok"


def test_token_estimate_is_conservative_and_counts_tools():
    assert estimate_tokens("a" * 320) == 100
    mt, tt = prompt_tokens([{"role": "user", "content": "hello"}], [{"type": "function", "function": {"name": "x"}}])
    assert mt > 0 and tt > 0


def test_plan_context_is_explicit_for_local_and_absent_for_hosted():
    hw = hw_with(24)
    local = plan_context(catalog_meta("qwen3:8b"), hw, 32768, 16384, local=True)
    assert local.num_ctx and local.num_ctx <= 32768 and not local.blocked
    assert plan_context(None, hw, 32768, 16384, local=False).num_ctx is None
    blocked = plan_context(catalog_meta("qwen3:32b"), hw_with(6), 32768, 16384, local=True)
    assert blocked.blocked


# ---------------------------------------------------- self-check (LM-2)

@pytest.fixture()
def ollama():
    def script(body):
        # a model that answers from whatever text survived truncation, like a good-but-honest long-context model
        import re
        m = re.search(r"code word for this check is ([A-Z0-9-]+)", body["_seen_text"])
        return {"content": m.group(1) if m else "I do not know."}
    s = FakeOllama({"fake:8b": {}})
    s.script = script
    yield s
    s.close()


def test_selfcheck_passes_when_the_window_is_honoured(ollama):
    res = run_selfcheck(OllamaProvider(ollama.url), "fake:8b", num_ctx=16384, size_tokens=6000, seed=1)
    assert res.ok and not res.truncated and res.prompt_tokens > 4096
    assert ollama.of("/api/chat")[-1]["body"]["options"]["num_ctx"] == 16384


def test_selfcheck_fails_loudly_when_the_runtime_silently_truncates(ollama):
    # the classic bug: window requested at 2k, prompt is ~6k -> the START (with the code word) is cut off
    res = run_selfcheck(OllamaProvider(ollama.url), "fake:8b", num_ctx=2048, size_tokens=6000, seed=2)
    # size is clamped to 90% of the window by design, so force the mismatch the way a real bug would: a server
    # that ignores our num_ctx and uses its own smaller default
    ollama.script = lambda body: {"content": "I do not know.", "prompt_tokens": 4096}
    res = run_selfcheck(OllamaProvider(ollama.url), "fake:8b", num_ctx=4096, size_tokens=3500, seed=3)
    assert not res.ok and "could NOT recall" in res.detail and res.truncated


def test_selfcheck_reports_a_dead_runtime_as_a_failure_with_its_kind():
    res = run_selfcheck(OllamaProvider("http://127.0.0.1:9"), "fake:8b", num_ctx=8192, size_tokens=1000)
    assert not res.ok and res.error_kind == "unreachable"
