# Edge-case register

Cases the original request did not list. Priority: MUST = a test exists before the owning phase is done;
SHOULD = test or a recorded reason; RECORD = cannot be run on the dev host (CPU-only, Linux), so document
the behavior and mark "not run: <reason>". "Proof" is what counts as evidence: a real runtime, a real
browser, a real image. Fault injection is acceptable only where a real server cannot produce the fault
on demand. Add cases you discover; never delete one without a reason in `02-PROGRESS.md`.

## Privacy and offline honesty (Phase 1, 6)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-01 | MUST | A `-cloud` / `:cloud` model is listed by the local server and run through `localhost:11434`, but inference happens on ollama.com. Name regex can be wrong (renamed tags, copies via `ollama cp`, third-party cloud-backed tags). | Public reports of cloud models passing as local, including a project whose "local mode" still allowed one. Hutch's `data_stays_local()` ignores the model. | Real Ollama: classify from the server signal first, name second; refusal under Strict Offline; visible label elsewhere |
| EC-02 | MUST | Endpoint is not loopback: `OLLAMA_HOST` on a LAN IP, `0.0.0.0`, an mDNS `.local` name, a hostname that resolves to a public address, `*.localhost` mapped away in `/etc/hosts`, IPv6 `::1` vs `127.0.0.1`. | Host-string checks can be fooled; DNS can change between check and use. | Resolve and pin the address at connect time; test with a real second interface or hosts entry |
| EC-03 | MUST | The model server itself reaches out: Ollama update checks and registry, LM Studio catalog and auto-update, llama.cpp `-hf` downloading at server start, Hugging Face token use. | Local address does not prove local behavior. The 2026-10-31 doc section 5 records this as the boundary. | Read-only listing of what the runtime does at start (strace/ss under `unshare -n`), documented per runtime |
| EC-04 | MUST | "Airplane test": network fully down at host level, a complete bot turn with a tool call and an image. | The only test that matches what a user means by offline. | Real run inside `unshare -rn` or the bubblewrap path, evidence row |
| EC-28 | SHOULD | Switching a bot to a cloud-tagged or non-loopback model after creation, or Hutch falling back to one when the local model fails. | Silent substitution is the worst privacy failure. | Test that no fallback or override crosses the boundary without a recorded confirmation |

## Context, memory and fit (Phase 2, 3)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-05 | MUST | LM Studio / llama.cpp / vLLM window is fixed at load or launch time; Hutch cannot set it per request and currently cannot read it. | Silent front-truncation or a hard "context size exceeded" 400; LM-1 protections cover Ollama only. | Needle placed in the system prompt survives or the run refuses; applied window read from the server |
| EC-06 | MUST | Context shift / rolling-window overflow policies (llama.cpp context shift, LM Studio overflow policy such as truncate-middle or rolling window). | Drops the system prompt and tool definitions mid-run without an error. | Real server with the policy on and off; Hutch detects or refuses for agent runs |
| EC-07 | SHOULD | Fit estimate assumes f16 KV and full-attention; reality differs with KV-cache quantization, flash attention, sliding-window models, MoE active parameters, partial GPU offload. | Wrong "fits" verdicts either block good models or load ones that thrash. | Compare `fit.py` prediction to measured `/api/ps` `size` and `size_vram` on at least two real models; record error |
| EC-08 | SHOULD | Parallel slots divide the window (`--parallel N`), Ollama multiplies KV by `OLLAMA_NUM_PARALLEL`, LM Studio `parallel`. | Headline context differs from per-request context. | Read per-slot `n_ctx` from `/slots` or `/props` on a real server started with `--parallel 2` |
| EC-22 | MUST | Memory pressure: other apps, two runtimes loaded at once, swap thrash, kernel OOM-killer ends the runner mid-stream. | User sees a generic stream error; the probe's `ram_available` is a stale snapshot. | Real kill -9 of the runner; error mapped to an actionable state; probe refreshed before admission |

## Lifecycle and identity (Phase 2, 3)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-09 | MUST | Cold start: llama-server `/health` is 503 "Loading model"; LM Studio loads just-in-time on the first request; a 20 GB Ollama load takes minutes. | First-token waits are reported as timeouts or hangs. | Real cold load of the largest model that fits; state shown as loading with measured time |
| EC-10 | SHOULD | Eviction while idle or under load: keep-alive expiry, LM Studio TTL auto-evict, `OLLAMA_MAX_LOADED_MODELS`, router `--models-max`. Scheduled bots wake to a cold model. | Surprise latency and failed admission. | Real expiry with a short keep-alive; scheduled run measured cold and warm |
| EC-11 | SHOULD | Runtime upgraded or downgraded under Hutch; features gated by version (thinking, tools, structured output, native LM Studio `/api/v1`, llama.cpp router mode). | A capability profile cached for one build is wrong for the next. | Test on retained 0.40.13 and the current release; profile keyed by version |
| EC-12 | MUST | Port squatting and collisions: anything on :8080 or :8000 answering `/v1/models`; two runtimes on one GPU; Ollama and LM Studio both resident. | Mislabelled runtime; combined memory over budget. | Fingerprint by response (`/props`, `/api/version`, headers), not by port; start a decoy server on :8080 |
| EC-13 | MUST | Key-protected servers: llama-server `--api-key`, LM Studio API tokens. Discovery sends no credential and reports "not a model list". | Users conclude the runtime is broken. | Real server with a key: state `needs_key`, key via vault, sent only to its origin |
| EC-14 | SHOULD | Containers, WSL2, Flatpak/Snap and the Tauri sidecar: `localhost` is not the host. | "Cannot connect" with no hint. | Document and detect where possible; RECORD otherwise |

## Models, formats and getting them (Phase 4)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-15 | MUST | Real name forms: `hf.co/<user>/<repo>:Q4_K_M`, mixed-case quant tags, registry-host prefixes, `:latest` normalization, custom namespaces, models built from a Modelfile with their own `PARAMETER num_ctx`, template, or system prompt. | Current validator refuses six of eight real names (G1). A Modelfile template can silently break tools. | Names scraped from the live Ollama library and Hugging Face; one Modelfile-built model run for real |
| EC-20 | SHOULD | Integrity and rights: corrupt or truncated GGUF, wrong architecture, gated Hugging Face repo needing a token, license text, model swapped behind a mutable tag. | Bad downloads look like model bugs. | Digest recorded at install and compared at run; gated-repo flow without a token in a URL |
| EC-23 | MUST | Disk: no preflight (G6); server model directory is on another drive (`OLLAMA_MODELS`, HF cache, LM Studio folder); disk full mid-pull; partial blobs; double-counted size on remove. | The pull fails at 90 percent, minutes later, with a raw error. | Real small loopback filesystem filled mid-pull; cancel and resume |
| EC-25 | SHOULD | Recommendation drift: hard-coded tags removed or renamed upstream; license or size changed; model too large for the box recommended anyway. | First-run recommendation is the first impression. | Check every recommended tag against the live registry in a test that is allowed to be network-dependent and says so |

## Multimodal, tools and reasoning (Phase 5)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-16 | MUST | Vision: llama.cpp needs the projector (`--mmproj`/`-hf` auto) or images fail while the model lists fine; LM Studio `capabilities.vision`; Ollama `capabilities`. Image tokens count against the window; high-resolution or many images overflow it; non-vision model must be refused before sending. | Wrong answers that look like model weakness; overflow. | Real photo, screenshot, multi-image and oversized image on real local VLMs; the answer must depend on image content |
| EC-17 | MUST | Tool calling defects that are integration, not model: llama.cpp needs a working template (`--jinja`/`--chat-template-file`), invalid or missing tool-call ids echoed back (reported in 2026), tool call emitted inside the reasoning block, string versus object arguments, parallel calls, big tool catalogs on small windows. | The agent "stops randomly"; users blame the model. | Bench on three real models per runtime; failure causes counted; repair path tests built from real captured output |
| EC-18 | SHOULD | Reasoning models spend the output budget on thinking and return an empty answer; `finish_reason=length`. | Looks like a hang or an empty reply. | Real thinking model with a small `max_tokens` |
| EC-19 | MUST | Embeddings, memory or search silently hitting a hosted endpoint for an offline assistant. | Breaks the offline claim from a side door. | Run an offline assistant under `unshare -n` through memory, search and skill flows; any egress attempt fails the test |
| EC-26 | SHOULD | One GPU or CPU, many bots: scheduled and interactive runs queue behind each other; a background run starves chat. | Local concurrency is 1, not N. | Two real concurrent runs; queue position and wait time shown |
| EC-27 | SHOULD | Audio: runtimes that accept audio input or run local STT/TTS; which seam in `providers/transcription.py` applies. | Easy to over-claim. | Record what each runtime does today; implement only native paths |

## Hardware and platform (record, then test what is possible)

| ID | Pri | Case | Why it bites | Proof |
|---|---|---|---|---|
| EC-21 | RECORD | Integrated GPU dropped by Ollama unless `OLLAMA_IGPU_ENABLE=1` (seen on the dev host); ROCm unsupported-card overrides; CUDA driver mismatch falling back to CPU silently; Apple unified-memory wired limit; Windows. | Users think the GPU is in use; speed is a tenth of expected. | Dev host: the integrated-GPU case is real, test the message. Others: "not run: no hardware" |
| EC-24 | RECORD | Laptop on battery or asleep during a long local run; thermal throttling; scheduled local runs at wake. | Long CPU generations are interrupted or crawl. | Document; test sleep/resume only if the host allows it safely |

## Frontend states (Phase 7)

Every panel and flow must render, and be keyboard operable and announced, in: runtime down, starting,
loading model, ready, key required, window too small, installing, install cancelled, install failed
(disk, network, name), cloud-tagged, non-loopback, upgrade needed, empty, and reloaded mid-install.
Prove each state with the real server and a real runtime put into that state, then view the screenshots.
