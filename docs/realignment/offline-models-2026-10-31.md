# Offline and local model ecosystem — 2026-10-31

Status: phases A, B, C and E done and verified (see section 6); phase D open. Baseline and research recorded below from a live host with a real
Ollama runtime and two real installed models. Nothing in this document is inferred from
fixtures; every measurement names the command that produced it.

Baseline host and runtime are recorded in §1. Research register is §2. Deficiencies found
by live testing are §3. Implementation phases and their acceptance evidence are §4 onward.

---

## 1. Live baseline

Recorded 2026-10-31 on the development host, with `hutch` at `main` (18 modified,
8 untracked files from an unrelated concurrent task; none touched by this work).

### 1.1 Hardware

| Fact | Value | Source |
|---|---|---|
| CPU | AMD Ryzen 3 5300U, 4 cores / 8 threads | `lscpu` |
| RAM | 22 GiB total, 8.9 GiB available at probe time | `free -h` |
| GPU | AMD Lucienne (Radeon integrated, `RADV RENOIR`), no dedicated VRAM | `lspci`, Ollama startup log |
| Disk free | 40 GiB on `/` | `df -h` |

`hutch.hardware.probe()` classifies this as `cpu` accelerator, 7.6 GiB usable budget,
"medium" tier — correct, and the note it prints ("integrated GPU sharing system RAM;
models run on the CPU unless the runtime has Vulkan/ROCm support for it") is accurate.

### 1.2 Runtime

No local runtime was installed on this host before this work. Installed for testing,
user-locally, with models confined to `~/.hutch-tmp/localmodels/models`:

- Ollama `0.40.13`, Linux amd64 bundle (`ollama-linux-amd64.tar.zst`), sha256 of each
  model blob verified by `ollama pull` itself.
- Server started with `OLLAMA_MODELS=<scratch>` on `127.0.0.1:11434`.

Two facts from the Ollama 0.40.13 startup log matter for this document:

```
level=INFO source=runner.go:405 msg="dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1"
    id=0 library=Vulkan compute=0.0 name=Vulkan0 description="AMD Radeon Graphics (RADV RENOIR)"
level=INFO source=routes.go:2586 msg="vram-based default context" total_vram="0 B" default_num_ctx=4096
```

The runtime *detects* the integrated GPU through Vulkan and then discards it unless
`OLLAMA_IGPU_ENABLE=1` is set. Separately, because `total_vram` is zero, Ollama's
default context is **4096 tokens** — the documented trap that silently truncates a
system prompt from the front.

### 1.3 Models installed

| Model | Params | Quant | Size on disk | Native max context | Capabilities (`/api/show`) |
|---|---|---|---|---|---|
| `qwen3:4b` | 4.0B | Q4_K_M | 2.5 GB | 262,144 | `completion`, `tools`, `thinking` |
| `qwen2.5-coder:1.5b` | 1.5B | Q4_K_M | 986 MB | 32,768 | `completion`, `tools` |

`qwen3:4b` architecture numbers read from `/api/show` (`model_info`):

```
attention.head_count     32
attention.head_count_kv   8
attention.key_length    128
attention.value_length  128
block_count              36
context_length       262144
```

That gives a KV cache of `2 x 36 x 8 x 128 x 2 bytes = 147,456 bytes/token` (144 KiB).
Hutch's `fit.kv_bytes_per_token()` derives exactly this, so `hutch models list` reports:

```
qwen3:4b  4.0B Q4_K_M  max context 262144
  @16k: fits (gets 16,384)    @32k: tight (gets 32,768)    self-check: not run
```

The arithmetic is right: 32k tokens of KV alone is 4.5 GiB, against a 7.6 GiB budget
that already holds 2.5 GB of weights.

### 1.4 Residency and acceleration, measured

While a run was live, `/api/ps` returned:

```json
{"name": "qwen3:4b", "size": 5113412320, "size_vram": 0,
 "context_length": 16384, "runner": "llamacpp"}
```

So: the model really is resident, really has a 16,384-token window (Hutch's request was
applied — it is not the 4096 default), and `size_vram: 0` proves **all of it is on the
CPU**. Hutch does not currently read either field, so it cannot tell a user which of the
two is true.

Measured generation throughput on this host, from Ollama's own slot timing:

```
prompt processing, n_tokens = 1024, progress = 0.09, t =  54.00 s / 18.96 tokens per second
prompt processing, n_tokens = 2048, progress = 0.18, t = 127.25 s / 16.09 tokens per second
```

**~16-19 tokens/second of prompt processing.** This single number drives most of the
first-run experience problems in §3.

### 1.5 Strict Offline capability on this host

```
$ python -c "from hutch.sandbox import offline_egress_status; print(offline_egress_status(refresh=True).ok)"
True
```

The bubblewrap network/PID-namespace and Unix-socket broker probe passes here.
ADR-0009 is candid that a live local model has never been driven through this path —
only a fixture request. That gap is what §4 Phase D closes.

---

## 2. Research register

Sources consulted for the design decisions below. Dates are the access date.

| # | Source | Fact taken | Bearing on Hutch |
|---|---|---|---|
| R1 | https://docs.ollama.com/context-length (2026-10-31) | Default context is vram-derived: `<24 GiB VRAM -> 4k`, `24-48 -> 32k`, `>=48 -> 256k`; agents should use `>=64000`; `ollama ps` shows `PROCESSOR` and `CONTEXT` | Confirms the 4k trap Hutch's `num_ctx` discipline exists to defeat. `PROCESSOR` is the honest acceleration signal Hutch should surface |
| R2 | https://docs.ollama.com/api/ps (2026-10-31) | `/api/ps` exposes `size`, `size_vram`, `context_length`, `expires_at`, `digest` | Hutch reads none of these. `context_length` is the *actual* applied window; `size_vram` is the *actual* GPU/CPU split |
| R3 | https://docs.ollama.com/api/errors (2026-10-31) | Errors are `{"error": ...}`; mid-stream errors arrive as an ndjson object with status already 200 | Hutch's `_chat_stream` already handles a mid-stream `error` key. Correct |
| R4 | https://docs.ollama.com/capabilities/tool-calling (2026-10-31) | Native `tools` array; parallel tool calls; streaming requires accumulating `thinking`, `content` and `tool_calls` across chunks; `tool_name` on the tool result message | Hutch's `_fold` accumulates all three and `to_ollama_messages` sends `tool_name`. Correct |
| R5 | https://docs.ollama.com/capabilities/vision (2026-10-31) | Images travel as a per-message base64 `images` array | Hutch's `to_ollama_messages` converts `image_url` data URIs to this. Correct |
| R6 | https://docs.ollama.com/api/pull (2026-10-31) | `POST /api/pull` with `{model, stream, insecure}`, returns ndjson status events ending in `success` | The capability Hutch is missing entirely (§3.1) |
| R7 | https://docs.ollama.com/api/delete (2026-10-31) | `DELETE /api/delete` with `{model}` | Removal is a user-controlled operation Hutch does not offer |
| R8 | github.com/openclaw/openclaw#4028 (2026-10-31) | Ollama's `/v1` shim ignores `OLLAMA_NUM_CTX` and the model's own window, truncating a 10.5k prompt to 4,096 and cutting the system prompt | Independent confirmation that Hutch's "native API only, always send `num_ctx`" rule is the right call |
| R9 | r/LocalLLM, "Ollama's default 4096 context silently truncates your prompt, and it keeps the TAIL" (2026-10-31) | Truncation removes the *front*, so the system prompt is the first casualty | Hutch's `prompt_truncated` detection plus the needle self-check address exactly this |
| R10 | github.com/ollama/ollama#14493 (2026-10-31) | Tool calling "completely non-functional" on a specific model family; repetition penalties silently ignored; model acknowledges tools then emits malformed output | Model-specific, not universal. Argues for measured per-model qualification (Hutch's `reliability.py`), never name-based claims |
| R11 | r/LocalLLaMA, "LM Studio's parser silently breaks Qwen3.5 tool calling and reasoning" (2026-10-31) | A parser can put the tool call inside the reasoning block, where the client never sees it; models then "loop forever" | Reasoning/content separation is a real integration defect class, not a model defect. Hutch keeps `thinking` and `content` separate in `ChatResult` |
| R12 | r/LocalLLaMA, "My agent kept randomly stopping mid-task" (2026-10-31) | Same mechanism: tool call fully formed inside the reasoning block, parser returns nothing | Reinforces R11 |
| R13 | r/LocalLLaMA, "Are you guys actually using local tool calling" (2026-10-31) | Local tool calling is viable on current mid-size models, not a novelty | Local agent work is worth supporting properly rather than disclaiming |

### 2.1 Complaint triage — what Hutch can and cannot fix

Each observed complaint class, classified per §4 of the brief:

| Complaint | Class | Hutch response |
|---|---|---|
| Prompt silently truncated at 4k | integration / protocol | **Already addressed.** Native API only, `num_ctx` always sent, post-hoc truncation detection, needle self-check |
| Slow first response / cold start | hardware | **Measurable, not removable.** Report load time and measured throughput; do not block for minutes without saying so (§3.2) |
| Tool call swallowed inside reasoning | integration / protocol | **Partly addressed.** Separate `thinking` from `content`; qualification records whether calls were recoverable |
| Model advertises tools, fails in practice | model-specific | **Cannot be fixed, can be measured.** Per-model qualification bound to digest + template + quant + window (`reliability.py`) |
| Integrated GPU silently ignored | hardware / runtime | **Not Hutch's to fix** (it is `OLLAMA_IGPU_ENABLE`), but Hutch must not claim GPU acceleration it cannot evidence (§3.3) |
| "Install the model" means leaving the app | frontend usability | **Fully fixable.** §3.1 |
| Offline needs internet unexpectedly | configuration | **Partly addressed**; the remaining server-side hole is disclosed in §5 |

---

## 3. Deficiencies found by live testing

These are ordered by what actually blocks or misleads a user, established by running the
real product against the real runtime above — not by reading the code alone.

### 3.1 Hutch cannot install, or remove, a local model

There is no model-installation path anywhere in the product. Every surface that notices a
missing model prints a shell command for the user to copy elsewhere:

- `hutch models list` → `ollama pull qwen3:4b` (as dim hint text)
- `hutch doctor` → fix text `ollama pull <tag>`
- `modelview.build_models_view` → `install_hint=f"ollama pull {tag}"` in every preset
- `providers/ollama.py` on a 404 → `install it with \`ollama pull {model}\``
- Models page → suggests models with an install command and no control
- `runtime/builtin.py` on a missing route → `ollama pull <model>`

So a person who has Hutch open, and no models, must leave Hutch, find a terminal, run a
command, and come back. Ollama's `/api/pull` (R6) exposes this as a streaming HTTP call
with progress, cancellation and digest verification; Hutch simply does not use it.
Removal (`/api/delete`, R7) is likewise absent.

This is the largest single gap between Hutch and every competing local-model surface
(Ollama's own app, LM Studio, Open WebUI, Jan all install models in-app).

### 3.2 The first run blocks for ~12 minutes on CPU-only hardware with no time estimate

`Bot.selfcheck` defaults to `True` (`models.py:434`). On the first run against a given
model build + window, `runtime/builtin.py` runs `context.run_selfcheck`, which builds a
prompt of `min(0.8 * num_ctx, 12_000)` tokens — 12,000 tokens at a 16k window — and asks
the model to recall a code word from the top.

Measured on this host with `qwen3:4b` at a 16,384-token window:

```
slot   operator(): id 0 | task 0 | new prompt, n_ctx_slot = 16384, n_keep = 4, task.n_tokens = 11288
slot print_timing: id 0 | task 0 | prompt processing, n_tokens = 1024, progress = 0.09, t =  54.00 s
slot print_timing: id 0 | task 0 | prompt processing, n_tokens = 2048, progress = 0.18, t = 127.25 s
```

At ~16-19 tokens/s of prompt processing, 11,288 tokens is **~10-12 minutes of prompt
processing** before a single token of the answer is generated. The self-check is a good
idea — it is the only thing that proves the window was really applied — but it is sized
as though prompt processing were free. On a hosted model it is; on CPU-only hardware it
is the single most expensive thing Hutch does.

The user sees one log line and no estimate. This is the "slow first response" complaint
(R10, §2.1) in its most acute form, and Hutch causes it.

### 3.3 Hutch cannot evidence the acceleration or the applied window it reports

`/api/ps` returns `context_length` (the window actually in effect) and `size_vram` (how
much is on the GPU). `OllamaProvider.show()` reads `size_bytes` from `/api/tags` or
`/api/ps` but discards both fields, and `ModelMeta` has nowhere to put them.

Consequence: Hutch can say "fits, 16k context" (a prediction from arithmetic) but cannot
say "*running* at 16k, entirely on the CPU, 5.1 GB resident" (a measurement). The brief
asks for exactly this distinction — "Distinguish estimates from measurements" — and the
data is one field away.

It also cannot detect the case where the runtime applied a *different* window than
requested, which is the failure mode ADR-0009 and R8/R9 are all about.

### 3.4 The Vision preset tells the user something untrue

`src/hutch/data/presets.json` describes the Vision preset as "...but Hutch chat cannot
attach or send images yet."

That is false in the current tree. Chat accepts `image_attachment_ids`
(`server/app.py`), validates them (`providers/attachments.validate_image_rows`), refuses
routes without image support (`image_route_refusal`), and `providers/ollama.py`
`to_ollama_messages` converts them to Ollama's native base64 `images` array, which R5
confirms is the correct wire shape. The runtime re-verifies per model and records what
was actually transmitted.

A user reading the Models page is told a working feature does not exist, and a user
looking for it is told to go elsewhere. This is a documentation defect with product
consequences, not a cosmetic one.

### 3.5 Strict Offline has never been driven with a live model

ADR-0009 states plainly: "no live local model or backend provenance was verified... a
fake Ollama health request completed through the broker inside the isolated worker. This
is fixture evidence, not a live local model or provider check."

The host probe passes (§1.5). The missing evidence is a real model answering a real
prompt through the broker inside the namespace. That is a runnable experiment, not a
design question, and §4 Phase D runs it.

---

## 4. Implementation plan

Ordered so that each phase produces evidence the next one depends on. Scope is
deliberately narrower than the brief's full list: this document claims only what it can
evidence.

### Phase A — Model installation and removal (Ollama-native)

Add a bounded, cancellable model-install service over `/api/pull`, and removal over
`/api/delete`. One module, provider-specific, reusing the existing provider and offline
plumbing. Surfaces: CLI, API, Models page. No uniform cross-runtime abstraction — LM
Studio and llama.cpp do not have an equivalent registry and pretending they do would be
the "artificial uniform download mechanism" the brief warns against.

Acceptance: install a real model through Hutch, watch real progress, verify `/api/tags`
grows by exactly that model, cancel a second install mid-flight, and remove a model.

### Phase B — Measured residency and window

Carry `context_length`, `size_vram` and `expires_at` from `/api/ps` into the model view.
Report the applied window against the requested one, and the CPU/GPU split. Distinguish
measured from estimated everywhere it is shown.

Acceptance: `/models` and `hutch models list` state the applied window and that the
model is running on CPU, matching `/api/ps` exactly.

### Phase C — Self-check cost awareness

Size the self-check from measured throughput instead of a fixed 12k, and tell the user
what it will cost before it runs. Never remove the check — it is the only proof the
window works.

Acceptance: on this host the first run reports an estimated self-check duration, and the
self-check completes in bounded time.

### Phase D — Strict Offline with a live model

Drive a real prompt through the broker inside the isolated worker and record what
happens. Document the server-side limitation that remains.

Acceptance: a governed tool run completes with the model served from loopback under
network isolation, with the worker's egress genuinely blocked.

### Phase E — Documentation and marketing truth

Correct the stale Vision claim, document installation, and state the offline boundary
exactly as far as the process boundary substantiates it.

---

## 5. The offline claim, stated exactly

This is the distinction the brief calls fundamental, and it is worth writing down before
any code claims otherwise.

| Layer | What Hutch enforces | What it does not |
|---|---|---|
| **Worker egress** | Under `inference_mode=offline`, the worker runs in a fresh bubblewrap network + PID namespace with no host interfaces. Its only model path is a per-run Unix socket; the supervisor-side broker fixes the destination to the validated loopback origin and never accepts an address from the worker. Hosted fallbacks, overrides and escalation are refused before dispatch; web/browser tools are removed; provider, proxy and custom-endpoint environment variables are scrubbed | — |
| **Model server** | Nothing yet. ADR-0035 records the owner's decision that Hutch will manage the process in its own network namespace; it is not implemented. | A separately running `ollama serve` is an ordinary host process. It may proxy requests, check for updates, or download blobs. Loopback addressing does not prove it stays local. |
| **Runtime updates / telemetry** | Nothing in Hutch starts an update check or sends telemetry | Ollama has its own release cadence and network behavior |

Therefore Hutch may say: *"this run's worker could not reach the network, and its model
route went only to your loopback address."* It may not say: *"your model server was
air-gapped"* or *"nothing left this machine."* The first is enforced by namespaces and a
socket broker; the second is a property of a process Hutch does not own.

Closing that gap properly means Hutch managing an independently isolated model process. The
owner selected that option on 2026-11-06; ADR-0035 records the decision, its constraints and
the implementation plan. It is not implemented, so the weaker claim above remains the only
one Hutch may make. The Phase 6 evidence in section 9 establishes the worker boundary, not
the managed process.

---

## 6. Evidence log

Appended as phases complete. Every row is a command that was actually run on the host in
§1.

| Phase | What shipped | How it was checked |
|---|---|---|
| A: install and remove | `providers/model_install.py` (validated names, at most two concurrent installs, bounded job list, cancel keeps verified blobs), `hutch models install` and `remove`, and install, cancel and remove on the Models page (`/api/models/install`, `/api/models/remove`). The size is on the button before the click; a running download shows a Cancel control; the empty state links to the section | `tests/test_model_install.py` (provider and installer against a fake runtime that speaks the ndjson captured from Ollama 0.40.13), `tests/test_model_install_api.py` (9: CSRF refused, install to done, bad names, remove, unknown job), `tests/e2e/test_model_install.py` (2: the real page installs and cancels). **A review found that every install request raised `NameError` (`require_csrf` was never defined), which no earlier test called; it is fixed and now covered.** Not yet run: a real multi-gigabyte pull through the page against the live Ollama in section 1 |
| B: measured residency | `ModelMeta.applied_context`, `vram_bytes`, `resident_bytes` from `/api/ps`; `hutch models list` prints "now loaded: loaded at N tokens, X GiB resident, entirely on the CPU" only when the runtime reports it, and unknown is never rendered as zero | `tests/test_models_layer.py`; the live figures in section 1.4 were the source |
| (found in testing) leaked reasoning | A thinking model (qwen3) with `think: false` returned its whole reasoning inside the answer, ending in a literal `</think>`; the chat path now separates it only when the marker has real text after it and no thinking was reported | `tests/test_model_install.py` (the split function), recorded in section 3 |
| (found in testing) stuck queue | A killed supervisor left process rows open, so every later run of that assistant sat in `pending` forever. `recovery.release_settled_process_rows` closes a row only when every recorded pid is dead | `tests/test_engine_loop.py` (both directions: a dead row is settled and the next run proceeds; a live descendant keeps its slot) |
| E: truth | The Vision preset no longer says chat cannot send images | the preset text |

| C: self-check cost | `selfcheck_plan.py`: the recall probe is sized from measured prompt throughput to fit a 120 s budget (never below 1,024 tokens, never above the old 12,000), the estimate and the reason it was shortened are logged before it runs, and a shortened pass says how far it verified. The speed of every real probe is remembered per model. The runtime's own report of the applied window is checked after the probe and fails the check if smaller than requested. The check is never skipped | `tests/test_selfcheck_plan.py` (10: plan sizing with and without a measurement, GPU keeps the full probe, a fast machine keeps it, the estimate wording, a smaller applied window fails, the report is read after the probe, throughput is remembered even when the probe fails), plus the 500+ existing tests that run through the self-check. **Live, `qwen3:4b` on this CPU-only host (Ollama 0.40.13, 16,384-token window):** the first run announced "a 1,440-token probe (shortened from 12,000 to fit; throughput 12 tokens/s assumed for this hardware), about 2.0 minutes", passed ("recalled the code word ... verified to 1,440 tokens ... the runtime reports a 16,384-token window in effect"), remembered 17.11 tokens/s, and the whole first run finished in about 3 minutes, against more than 7 minutes for the old probe alone |

**A bug the live run found that no fixture had.** The first version read the applied window before the probe and failed a healthy
setup ("applied a 4,096-token window, not the 16,384 requested"): Hutch preloads a model without a window and Ollama then reports its
own default until a request arrives at the target window. Reading it after the probe is correct, and `test_the_runtimes_report_is_read_after_the_probe_not_before`
reproduces the sequence.

What C does not claim: a probe of 1,440 tokens proves the window is applied and the model recalls from the top of that prompt; it
does not prove recall at 12,000 tokens on a slow machine, and the result text says so. A person who wants the full probe can
use `hutch doctor --deep`, which runs the unshortened check on request.

Closed: **D** by the Phase 6 live evidence in section 9 (Ollama 0.40.13 and llama.cpp
b12144, a governed tool-and-image turn through the broker, and the airplane test). Model
server isolation is now the accepted ADR-0035 decision, not yet implemented; the claim
stays at the worker boundary until it ships.

---

## 7. Phase 4 (2026-11): getting a model

Phase 4 closes the Phase A open item ("a real multi-gigabyte pull through the page") and
the install gaps recorded in `docs/realignment/offline-models-2026-11/`. Decisions and
the full dated ledger are in `02-PROGRESS.md`; the boundary is ADR-0031.

- **Name grammar (G1).** The lowercase regex is replaced by the runtime's grammar
  (`model_names.py`): mixed case, registry hosts and ports, namespace/model/tag, and the
  real `hf.co/<user>/<repo>:<quant>` forms. A live table built from Ollama's
  `types/model/name.go` and Hugging Face's page is in `tests/test_model_names.py`.
- **Preflight and the page (G6).** The real plan for `qwen2.5-coder:3b` reported a
  2,040,109,465-byte catalog size, 75,594,895,360 bytes free on
  `~/.hutch-tmp/localmodels/models` (from `OLLAMA_MODELS`), "fits" at 16,384 tokens, and
  "download time unknown" because no transfer had been measured. The page required
  **Confirm download**; the server re-ran the plan. A real 1.9 GiB pull through Chromium
  was cancelled at 44,076,255 bytes and resumed from 46,717,902 bytes (not zero), then
  finished in 106.3 s with `success` and the model in `/api/tags`. A page reload and a
  second tab both reattached to the same running job. A second real pull (`qwen3:1.7b`)
  repeated cancel/resume for the four-width visual states.
- **Failure states.** A real pull into a 300 MiB tmpfs failed at 309,451,728 of
  1,929,903,008 bytes with `write ...-partial: no space left on device`; a real pull with
  no external route failed with `dial tcp ...: connect: network is unreachable`. Both are
  classified (`disk_full` / `network`), carry one action, and redact credential-shaped
  text.
- **Local import.** The retained qwen3-4b GGUF imported with its SHA-256 compared against
  the runtime's existing blob (no duplicate upload) in 7.22 s; the runtime returned the
  Apache license and tools/thinking capabilities, and removing the imported model left
  `qwen3:4b` intact. A 1.93 GB vision GGUF that was not in the store uploaded through
  `POST /api/blobs` in 4.246 s, created the model, and its blob was removed with the test
  model; the source file's hash was unchanged.
- **Not run.** A gated Hugging Face pull (no token or gated repo), LM Studio's native
  download through Hutch (deliberately guided: no cancel or catalog API), and vLLM/SGLang
  install (not installed). The visible import form and the full state matrix are Phase 7.
- **Not claimed.** Hutch can say this pull's bytes went to the local runtime; it cannot
  say the runtime was air-gapped. Resume depends on the runtime keeping its parts.

---

## 8. Phase 5 (2026-11): vision, tools and reasoning on real local models

Phase 5 closes the multimodal and tool-reliability gaps for the three runtimes on this
host. Dated evidence and the not-run list are in
`docs/realignment/offline-models-2026-11/02-PROGRESS.md`; raw benches and captures are in
`docs/research/2026-11-offline-models/evidence/phase5/`.

- **Vision capability is read, not guessed.** Ollama uses `/api/show.capabilities`;
  llama.cpp uses `/props.modalities.vision` and the model's input modalities; LM Studio
  uses `/api/v1/models.capabilities.vision`. Before this phase Hutch refused every
  llama.cpp and LM Studio vision model because its OpenAI-compatible provider only knew the
  official OpenAI table. A shared resolver now asks the runtime.
- **A real image path.** A 640 px cat photo and a Playwright capture of `/models` went
  through the real app on llama.cpp b12144 (Qwen2.5-VL-3B Q4_K_M + Q8_0 projector) and LM
  Studio 0.0.27-1 (qwen2.5-vl). Answers were content-dependent (`Cat`, `"Models"`,
  `image 1` for two images), and the run's media record showed `transmitted: 1`. A text
  model was refused before sending. Ollama moondream described the cat through the native
  provider; the app refuses that 2,048-token model as below the 4,096-token agent floor.
- **Image cost is bounded.** Planning and compaction count an image as 800 tokens, never
  as its base64 payload. The first live run exposed the old compaction estimate turning a
  121 KB JPEG into about 52,000 fake tokens; the shared `content_tokens` estimator now
  keeps the run at ~2,500 tokens and the image fits.
- **LM Studio media types are honest.** 0.0.27-1 accepts PNG/JPEG data URIs and rejects a
  WebP data URI. Hutch refuses WebP on that route with the reason before sending; it does
  not rewrite the file.
- **Tool causes are measurable.** `hutch models bench --provider ...` now runs against
  llama.cpp and LM Studio. Sixteen model/runtime pairs were measured; the same coder model
  scored 6/15 on Ollama, 1/15 on llama.cpp and 3/15 on LM Studio. The bench names
  `call_in_content` (a complete call left as text), `reasoning_only`, `missing_id`,
  `parse_error` and the rest instead of calling every failure "prose".
- **Current-model comparison (owner-approved beyond the original budget).** Qwen3.5 0.8B/2B/4B
  and Gemma 4 e2b were pulled and measured beside the 2025 baseline. All four passed 15/15
  isolated probes on Ollama; Qwen3.5 2B also passed 15/15 on llama.cpp, while Gemma 4 e2b
  passed 11/15 there and 12/15 on LM Studio (reasoning-only). The full-app image comparison
  separated them: Gemma 4 e2b 3/3, Qwen3.5 4B 2/3, Qwen3.5 2B 1/3, Qwen3.5 0.8B 0/3. Gemma 4
  e2b is the current full-multimodal winner on this host; Qwen3.5 2B Q4 is the lightweight
  tool choice; the old qwen3:0.6b remains the fastest tiny tool model. The catalog and presets
  now carry the measured rows.
- **Reasoning budget is a state.** A real Ollama qwen3:4b turn with `think: true` and 32
  output tokens returned `done_reason: length`, empty content and 147 characters of
  thinking; Hutch's note says the output limit was reached while reasoning and gives the
  fix. llama.cpp qwen3-4b at the default budget generated at ~3.9 tokens/s and did not
  finish four probes in ten minutes; no third-trial result is claimed.
- **Ollama GGUF import is not a vision path.** Importing the Qwen2.5-VL GGUF produced
  `capabilities: ["completion"]` and no projector. Pull a vision model instead.
- **Not run.** Audio/speech on any runtime, GPU vision, Gemma 4 e4b/12b/26b, Qwen3.5 122B,
  Qwen3-VL specifically, and full-app text-only runs for the current models. The old
  Qwen2.5-VL template has no tool section, so its image-plus-tool probe used a disclosed
  local merge; the current Gemma 4 and Qwen3.5 2B templates support vision and tools
  together. Phase D was closed by Phase 6 (section 9); an air-gapped model server is the
  accepted ADR-0035 decision, not yet implemented.

---

## 9. Phase 6 (2026-11): Strict Offline with a live model

Phase 6 closed phase D and recorded the owner's boundary choice. Research and design are in
`docs/research/2026-11-offline-models/07-PHASE6-OFFLINE.md` and `08-PHASE6-DESIGN.md`; the
dated ledger is `02-PROGRESS.md`.

### What was run

- **Real Ollama 0.40.13, Gemma 4 e2b, real cat photo, governed `write_file` and `shell`.**
  The Strict Offline worker answered "cat" and the byte count "3" in 97.7 s; the workspace
  file held `cat`; the shell ran `wc -c`; the worker's `/proc/<pid>/net` showed a different
  network namespace from the supervisor with only `lo` and no route.
- **Real llama.cpp b12144, Gemma 4 e2b plus projector, `--offline`, `--parallel 1`,
  8192 applied.** The same image and tools succeeded in 190.9 s; `context_limit` was 8192,
  read through the per-run broker. The first attempt was refused because the local adapter
  probed `/props` over direct TCP from inside the isolated worker; the adapter now uses the
  broker.
- **Airplane test.** The same Ollama turn with the app, Ollama and the worker inside one
  `unshare -rn` namespace (only `lo` up, no route) succeeded in 138.3 s. An external
  `connect()` from that namespace returned `101` (network unreachable).
- **Tool egress.** The model ran a shell command that called
  `socket.connect_ex(("1.1.1.1", 53))`; the tool result was `connect_ex 101`, and the run
  continued.
- **Large streamed response.** A forced 1,200-token NDJSON generation crossed the broker as
  1,202 chunks and 131,695 bytes, ending with `done_reason: length` and `eval_count: 1200`.
- **Cancellation.** A running generation stopped in 0.304 s; the worker exited with code
  -15; the status timeline was `running, cancelling, stopped`.
- **Broker loss.** Before the first model call the run failed with "Strict Offline model
  broker is missing; no direct network fallback is allowed". After a successful call, the
  classifier now names the Strict Offline bridge and stops; it no longer tells the user to
  start a runtime that is still running.
- **Request limit.** A 64 MiB+1 `Content-Length` to the real run broker returned HTTP 413
  (`model request exceeds the broker's 64 MiB limit`) before any upstream request.
- **Runner kill.** A real `SIGKILL` of the Gemma runner mid-generation was classified as a
  local runtime stop; Hutch reloaded once (8.65 s) and the run completed. A kill during the
  pre-run self-check had been reported as `context`; `selfcheck_error` now maps the captured
  "unexpected EOF" text to a runtime failure, with a unit regression.
- **Server restart.** A real `SIGKILL` and restart of Ollama produced the broker's 502; the
  classifier reloaded once. The restarted server had not re-listed the model yet, so the
  reload failed with "model ... is no longer installed"; the run stopped with both causes
  and no silent fallback.

### What changed

- `src/hutch/sandbox.py`: a host with only loopback is now testable; the probe still proves
  the worker cannot reach the host's loopback listener.
- `src/hutch/providers/local/probe.py`: local runtime introspection (`/health`, `/props`,
  `/slots`, `/v1/models`) uses the per-run broker inside an Offline worker.
- `src/hutch/providers/ollama.py` and `providers/openai_compat.py`: the broker canonicalizes
  the HTTP client without rewriting `provider.base_url`, so the reviewed-route check no
  longer fails a healthy local route.
- `src/hutch/runtime/outcomes.py`: a distinct Strict Offline bridge failure, a reload for
  the broker's 502, and a runtime-failure classification for an interrupted self-check.

### Boundary

The owner chose the Hutch-managed isolated model process on 2026-11-06. ADR-0035 records
the decision, its constraints and the implementation plan; it is not implemented. The exact
claim today is the worker boundary in section 5: the run's worker could not reach the
network, and its model route went only to loopback. The stronger sentence waits for the
dated managed-process test.

### Not run

LM Studio under the Offline worker (its adapter shares the OpenAI-compatible broker path
proven on llama.cpp), vLLM/SGLang, macOS and Windows, GPU inference, and the managed model
process itself (not built).
