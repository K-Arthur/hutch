# Hutch research: media generation, Python workspace, and typed output widgets

- Date accessed for every source below: **2026-10-11**, unless a different date is stated.
- Method: live web fetches of official docs/repos/issue pages + web search. No installs, no servers, no logins.
- Evidence labels: **documented** (official docs/source), **reported** (issue/community/third-party measurement), **reasoned** (our inference; flagged inline).
- This file is research only; no Hutch code was changed.

---

## 1. OpenAI image generation API (current state)

Sources (fetched 2026-10-11):
- https://developers.openai.com/api/docs/guides/image-generation (live docs, no version string)
- https://developers.openai.com/api/reference/resources/images/generation-streaming-events (live docs)
- https://developers.openai.com/api/docs/deprecations (live docs)
- https://developers.openai.com/api/docs/pricing (live docs)
- https://developers.openai.com/api/docs/guides/video-generation (retained historical page)

Findings (documented unless noted):
- Current image models are **`gpt-image-2.5-sunburst`** (editing precision) and **`gpt-image-2.5-flare`** (fast everyday generation). The `gpt-image-1` family is not the headline model anymore.
- Two entry points: **Image API** (`POST /v1/images/generations`, `POST /v1/images/edits`, multipart with `image[]` and optional `mask`) and the **Responses API** image-generation tool (multi-turn editing, File IDs, `previous_response_id`, `action: auto|generate|edit`).
- Streaming partial images: `stream: true` + `partial_images: 0–3`; events `image_generation.partial_image` (fields: `b64_json`, `partial_image_index` 0-based, `size`, `quality`, `output_format` png|webp|jpeg, `background`) and `image_generation.completed` (final b64 + `usage` token counts). Responses API equivalent: `response.image_generation_call.partial_image` / `response.completed`.
- Deprecations: `gpt-image-1` is scheduled for shutdown **2026-10-23** (12 days from now), replaced by `gpt-image-2.5-sunburst`/`flare`; `gpt-image-1.5`, `gpt-image-1-mini`, `chatgpt-image-latest` shut down 2026-12-01. `gpt-image-2` appears in the Batch price table only (availability per main guide unclear — see Open questions).
- Costs are **token-based**. Standard (non-batch) prices: `gpt-image-2.5-sunburst`/`flare` image input $8.00 / cached $2.00 / output $30.00 per 1M tokens; text input $5.00, cached $1.25. Batch is half: image $4.00/$1.00/$15.00, text $2.50/$0.625.
- Rate limits: docs state limits can be RPM, RPD, TPM, TPD, **IPM (images per minute)** for image models; the concrete per-tier numbers live behind the account/settings page and were not publicly verifiable.
- **Sora 2 / Videos API shutdown confirmed**: "The Sora 2 models and Videos API were shut down on September 24, 2026 and are no longer available. No one-to-one replacement API is available." The guide is retained for historical reference. (documented)

Hutch applicability / recommendation:
- Media widget gets progressive previews for free: map `partial_image_index` onto a revision counter and render each partial; treat `completed` + `usage` as the cost/telemetry record.
- Recommended mechanism: Image API with `stream:true, partial_images:1–2` for generate/edit; Responses API only where multi-turn conversational refinement is the product surface.
- Rejected alternative: OpenAI for **video** — the Videos API is dead with no replacement; use Gemini video (section 2).

## 2. Google Gemini image + video entry points

Sources (fetched 2026-10-11):
- https://ai.google.dev/gemini-api/docs/image-generation (Nano Banana; live docs)
- https://ai.google.dev/gemini-api/docs/video (page footer: "Last updated 2026-06-30 UTC")
- https://ai.google.dev/gemini-api/docs/veo (live docs)

Findings (documented):
- Image: Nano Banana models — `gemini-nano-banana-2.1` (primary workhorse), `gemini-3.1-flash-lite-image`, `gemini-3.1-flash-image` (previous gen), `gemini-3-pro-image` (premium), `gemini-2.5-flash-image` (legacy). Entry point is the **Interactions API** (`POST /v1beta/interactions`), with `interaction.output_image` convenience property; multi-turn via `previous_interaction_id`.
- Output control: `response_format {type: "image", mime_type: image/png|image/jpeg, aspect_ratio, image_size}` at 1K/2K/4K (3.1 Flash Image also 512px; Flash Lite 1K only). All generated images carry a **SynthID watermark**. Up to 14 reference images (mix of object/character/style references).
- Partial previews: the image page documents a "thinking" phase that generates interim **"thought images" (visible in the backend but not charged)** but does **not** document a public partial-image streaming API. Treat partials as OpenAI-only for now.
- Video entry points: **Gemini Omni Flash** (recommended default: text/image/audio/video inputs, multi-turn conversational video editing) and **Veo 3.1** (`veo-3.1-generate-preview`; native audio, scene extension, last-frame control, legacy pipelines). Veo flow is async: `generate_videos` → poll `operation.done` → `operations.get` → download `generated_videos[0]` → `files.download` to `.mp4`. No partial-frame preview is documented; progress is operation polling.
- The video landing page states Omni Flash is the default and Veo 3.1 is for specific capabilities (scene extension, last-frame control, legacy integration).

Hutch applicability / recommendation:
- If a Google credential is present, use Veo/Omni as the **only** first-class video route post-Sora; model video widgets as async job + polling, not streaming.
- Nano Banana is a viable alternate image provider, but its response shape (Interactions API) and watermarking differ from OpenAI; keep providers behind one Hutch media interface.
- Rejected alternative: assuming partial image previews from Gemini (not documented) and assuming Sora (dead).

## 3. ComfyUI server routes and event semantics

Sources (fetched 2026-10-11):
- https://docs.comfy.org/development/comfyui-server/comms_routes (live docs)
- https://docs.comfy.org/development/comfyui-server/comms_messages (live docs)
- https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/server.py (master at fetch time, 1,569 lines; exact commit not pinned)

Findings:
- HTTP: `POST /prompt` validates and queues, returning `prompt_id` + queue `number`; `GET /prompt`; `GET /history[/{prompt_id}]`; `GET /queue` + `POST /queue` (clear pending/running); `POST /interrupt`; `GET /view`; `POST /upload/image`; `GET /object_info`; `GET /ws`. (documented)
- WebSocket messages (documented): `status` (`exec_info.queue_remaining`), `execution_start`, `execution_cached`, `executing` (`node`, `prompt_id`), `executed` (`node`, `prompt_id`, `output`), `progress` (`node`, `prompt_id`, `value`, `max`), `execution_error`, `execution_interrupted`, `execution_success`. Key trap: `executed` fires **only when a node returns a UI payload**, not on every node completion.
- `clientId` semantics (documented directly in `server.py` source): `/ws` reads query param **`clientId`** (note casing); if absent the server assigns `uuid4().hex`. Sockets are stored per `sid`; reconnecting with the same `clientId` evicts the old socket and, if that client was executing, the server re-sends the current `executing` state. `POST /prompt` accepts a JSON `client_id` which is stored in `extra_data["client_id"]`; `PromptServer.send_sync(event, data, sid=None)` can target one client.
- Preview correlation: preview/progress payloads carry `node` + `prompt_id`; the initiating client is identified by `client_id`. Node IDs are **not** unique across sessions/workspaces — the same node id in two tabs cross-updates previews (ComfyUI #6888 → ComfyUI_frontend #2660, section 4).
- Identities needed to avoid cross-session preview mixups: per-run **clientId** (`/ws?clientId=<uuid>`) + per-run **prompt_id** + a run registry that drops any event whose `prompt_id` it does not own. One WebSocket carries one sid, so concurrent runs need one socket per run (or serialize).

Recommendation: one WS per Hutch ComfyUI run with a fresh `clientId`; submit the prompt with the same `client_id`; scope every event by `prompt_id`; reconcile final outputs via `GET /history/{prompt_id}` rather than trusting `executed` alone; `POST /interrupt` for cancel.
Rejected alternative: keying previews by node id or filename (proven-broken identity per #6888); sharing one WS across parallel runs (sid collisions silently evict sockets).

## 4. Issue status: ComfyUI #6888, open-webui #27399 / #14823, newer artifact reports

Fetched 2026-10-11:
- https://github.com/Comfy-Org/ComfyUI/issues/6888 — **closed as duplicate** (2025-02-21) of https://github.com/Comfy-Org/ComfyUI_frontend/issues/2660 ("Nodes affect nodes in different open workspaces").
- `ComfyUI_frontend#2660` — **still open** (label: verified bug; parent tracker #3377 Tab-Graph-Prompt State Sync Issues). Three commits referencing it landed **2026-03-28** ("fix: filter WS messages by workflow tab to prevent cross-tab state leak", e.g. `eae437c`). So the mechanism (node-id-keyed UI updates within one frontend) is still a live concern; no issue closure yet.
- https://github.com/open-webui/open-webui/issues/27399 — artifacts panel force-reopened on every streamed token, couldn't be closed mid-generation; stale previous artifact shown. Opened 2026-07-24, confirmed; PR #27400; **closed completed 2026-07-26 "Addressed in dev."** Fix approach: gate auto-open on the message `done` prop and open once per completed code-fence block (once-per-block id registry).
- https://github.com/open-webui/open-webui/issues/14823 — Code Interpreter code "becomes malformed after execution" (pyodide and Jupyter modes). Fix commit `21d616f`; **closed completed 2025-06-26**.
- Newer related reports (web search over GitHub, 2026-10-11):
  - #27772 (2026-07-31) — sidebar hover preview containing an artifact code block closed the Chat Controls pane of the open chat; root cause: `ContentRenderer` auto-open writing global stores from a read-only preview; fixed via PR #27773; closed.
  - #22889 (2026-03-20) — artifact sidebar fails to auto-show when tab was backgrounded; suspected `requestAnimationFrame` throttling; fixed via PR #22910; closed.
  - #23232 (2026-03-30) — opening an artifacts preview in tab A auto-expanded Controls in tab B (shared `showControls` state); search index shows **state: open** with PRs #23259/#23261 proposed (sessionStorage). Treat as still relevant; not re-verified beyond the search snippet.
- Mechanism takeaway (reproduced from issue write-ups): completion-gated auto-open, stable per-block IDs, per-session (not global) UI state, and never let read-only previews mutate run state.

## 5. Mermaid security configuration

Sources (fetched 2026-10-11): https://mermaid.js.org/config/schema-docs/config.html (Mermaid **12.1.0**), mermaid docs/usage (repo), mermaid issue #7695, Bundlephobia.

Findings (documented):
- `securityLevel` (required; default `"strict"`): `strict` = HTML encoded, clicks disabled; `antiscript` = HTML allowed, scripts stripped, clicks enabled; `loose` = everything allowed; `sandbox` = all rendering inside a sandboxed iframe, no JavaScript, interactive features degraded (docs historically label sandbox "still in beta").
- `maxTextSize` default **50000**; `maxEdges` default **500** (minimum 0); `secure` default array `["secure","securityLevel","startOnLoad","maxTextSize","suppressErrorRendering","maxEdges"]` prevents per-diagram directives from overriding site security; `suppressErrorRendering`; `dompurifyConfig` passthrough; `htmlLabels` root-level; `layout` default `elk` per schema page.
- Sanitization: in non-sandbox/non-loose modes mermaid sanitizes SVG via DOMPurify (per Mermaid's advanced-rendering docs).
- CSP: mermaid emits **inline styles** in SVG, so `style-src` needs `'unsafe-inline'` (reported by multiple adopters' fix commits). `mermaid.render()` returns an SVG **string** intended for `innerHTML`, which violates `require-trusted-types-for 'script'`; mermaid issue **#7695 (opened 2026-04-29, open)** confirms there is no supported Trusted-Types-safe path yet (proposed `svgElement` return is not shipped as of this check).
- Bundle size: Bundlephobia reports mermaid 12.1.0 at ~710 KB min / ~173 KB gzip, 23 dependencies (third-party measurement, npm registry metadata today).

Recommendation: lazy-load mermaid only when a flowchart widget renders; `mermaid.initialize({ securityLevel: 'strict', maxTextSize: 10000, maxEdges: 200, htmlLabels: false, suppressErrorRendering: true })`; never let diagram source set `securityLevel` (the `secure` list does this if you always initialize); for untrusted/LLM-authored diagrams, additionally render inside Hutch's own sandboxed iframe with **no** `allow-scripts`. Offline: mermaid is fully client-side; a bundled copy inside a `srcdoc` iframe needs no network — **reasoned** from the architecture, not stated verbatim in the schema page.
Rejected alternative: `loose`/`antiscript` for LLM output; server-side mermaid-cli rendering (adds a Chromium/Puppeteer dependency to a local-first app and imports a second trust boundary).

## 6. Chart rendering options (bundled offline, strict CSP, fixed schema)

Measurements fetched 2026-10-11: Bundlephobia for minified+gzip, npm registry for license/version. Bundlephobia is third-party; treat sizes as **reported**.

| Library | Version | License | Min / gzip (Bundlephobia) | Output | CSP eval use | Keyboard a11y | 2000-pt series |
|---|---|---|---|---|---|---|---|
| Chart.js | 4.5.1 | MIT | 200.8 KB / 68.4 KB | Canvas | none documented (**reasoned**) | None built-in; docs require `role`/`aria-label`/fallback content (documented) | Native; decimation plugin documented (not needed at 2k) |
| uPlot | 1.6.32 | MIT | 50.8 KB / 21.9 KB | Canvas | none documented (**reasoned**) | None built-in (README "non-features"; **reasoned**) | Designed for 100k+ pts (README: 166,650 pts in 25 ms) |
| Vega-Lite + vega-embed | 6.5.0 / 7.3.0 | BSD-3-Clause | 280.9 / 89.9 KB + 59.8 / 21.1 KB (plus vega core) | SVG or Canvas | **Needs `unsafe-eval` by default**; documented CSP-compliant interpreter available | ARIA generated by default (`aria: true`, SVG only; mark `description` → `aria-label`) documented; marks not tab-focusable by default | Canvas renderer for perf; Canvas loses ARIA |
| Observable Plot | 0.6.17 | ISC | 384.5 KB / 128.0 KB | SVG only | none documented (**reasoned**) | `ariaLabel`/`ariaDescription`/`ariaHidden`; mark groups auto-labelled (documented) | Per-mark SVG DOM grows with n (**reasoned**); 2k manageable, not its scale target |

Network: all four can be bundled locally and need no runtime network when bundled (Vega documented local import; the others are plain packages — **reasoned** from packaging model).

Recommendation for Hutch (`line/bar/scatter/area, ≤8 series, ≤2000 points`, strict CSP, local): **Chart.js** as the single bundled renderer — MIT, ~68 KB gzip, first-class line/bar/scatter/area, no eval path, 2000 points is trivial; pair every chart with a generated accessible data table (canvas gets `role="img"` + `aria-label` per its docs). Fallback: **hand-rolled SVG** for the simplest widgets (zero deps, focusable data points, full keyboard support, but we own axes/legend/tooltip work and per-point DOM cost).
Rejected alternatives: Vega-Lite/vega-embed for v1 (default `Function` constructor requires `unsafe-eval`; adding `vega-interpreter` + three packages is too much for a fixed schema); Observable Plot as primary (heaviest bundle, SVG-only; fine as a later "advanced" renderer); uPlot as primary (excellent at scale but narrow type coverage and zero a11y; keep it in mind if streaming >100k points becomes real).

## 7. Jupyter messaging semantics a custom kernel host must replicate

Source: https://jupyter-client.readthedocs.io/en/stable/messaging.html (live "stable"; protocol spec **5.5**; fetched 2026-10-11).

Documented semantics worth copying (even though Hutch will not use ZMQ):
- Every message: `header{msg_id, session, username, date, msg_type, version, subshell_id?}`, `parent_header` (a copy of the request header — replies MUST have one), `metadata`, `content`, `buffers`. Clients route output to the originating widget via `parent_header`/`msg_id`.
- Kernel status: `busy` immediately on request start, `idle` after all associated IOPub traffic; all outputs for a request arrive between its busy/idle pair. Busy/idle apply to every request, not just execute (since 5.0).
- Execution: `execute_request{code, silent, store_history, user_expressions, allow_stdin, stop_on_error}` → `execute_reply{status: ok|error|aborted, execution_count}` (execution_count present on every status). `execute_input{code, execution_count}` broadcasts; `execute_result{execution_count, data, metadata}` = displayhook result; `stream{name: stdout|stderr, text}`; `display_data{data, metadata, transient}`; `error{ename, evalue, traceback}` (note: error omits `status`/`execution_count`). One monotonic counter for all history-storing executes; `silent=True` forces no history and no IOPub output.
- Rich display updates: `transient.display_id` names a display; `update_display_data` with the same `display_id` replaces all matching outputs (frontend-defined semantics). `clear_output{wait}` clears the output area; `wait=true` defers clearing to the next output.
- Control channel: `interrupt_request`/`interrupt_reply` (only when kernelspec `interrupt_mode: message`), `shutdown_request{restart}`, `kernel_info` (5.5). Heartbeat = plain echo bytes for liveness.
- `kernel_info_request/reply`: `protocol_version`, `implementation(+version)`, `language_info`, `banner`, `help_links`, `supported_features` (5.5; `debugger` deprecated).
- Compatibility rule: kernels MUST implement execute + kernel_info + busy/idle; everything else optional. `stdin` requests only if `allow_stdin` was true.

Minimal subset for a non-Jupyter host that owns both ends (recommended), and the failure mode of skipping each:
1. request/reply with `id` + echo; skip → outputs land in the wrong widget once two runs interleave.
2. `busy`/`idle` bracketing; skip → UI cannot know when a run's output is complete (streams look never-ending).
3. `kernel_info` handshake; skip → client cannot detect protocol/version mismatch or display capabilities.
4. `execute_reply` with monotonic `execution_count`; skip → broken In[n]/Out[n] receipts and audit ordering.
5. Distinguish `stream` vs `display_data` vs `execute_result`; skip → charts/tables get rendered as raw text or appended wrong.
6. `display_id` + update semantics; skip → progress bars/partial images append new rows instead of updating.
7. `clear_output(wait)`; skip → animation/progress widgets leave stale output.
8. `error` with traceback; skip → failures look like empty successes.
9. "interrupt" request + ack; skip → long code cannot be cancelled (see section 10 for signal pitfalls).
10. `shutdown`/heartbeat; skip → orphaned Python processes.

Recommendation: implement exactly this subset over Hutch's JSON-lines stdio protocol (not ZMQ), keeping Jupyter naming/semantics for familiarity. Rejected alternative: embedding a real Jupyter/`jupyter_client` kernel for the bwrap workspace — drags in ZMQ sockets, tokens/origin checks, and a second network surface for functionality a stdio driver covers.

## 8. Jupyter server security notes worth citing for a local broker

Source: https://jupyter-server.readthedocs.io/en/latest/operators/security.html (live; fetched 2026-10-11).

Findings (documented):
- Token auth is **on by default**; token via `Authorization: token ...`, URL param, or login field; disabling auth (`token=""`, `password=""`) is explicitly NOT RECOMMENDED unless enforced elsewhere.
- AuthN (IdentityProvider) and AuthZ (Authorizer) are separate; the `execute` permission wraps kernel/terminal websockets and "generally means arbitrary code execution... equivalent to having all other permissions."
- Transport encryption: since 2.20, optional CurveZMQ for kernel sockets; default `disabled`; `auto` only for kernelspecs declaring `metadata.supported_encryption: ["curve"]`.
- Notebook trust model: trust is a local signature DB (`nbsignatures.db`); "The central question of trust is 'Did the current user do this?'" Untrusted HTML is sanitized, untrusted JS never runs, markdown cells never trusted, outputs from the current user's own execution trusted. Trust updates only on save; nbconvert pages get `sandbox allow-scripts` CSP by default.

Why notebook trust ≠ Hutch trust: a notebook signature only proves *this user on this machine* ran/saved that file. LLM-authored code, downloaded notebooks, or any second client is outside that trust circle. Hutch must therefore:
- bind the workspace broker to loopback only and use a per-session random token (Jupyter's own pattern);
- check `Origin`/CSRF on any localhost HTTP surface (Jupyter's identity model assumes cookie/origin handling);
- treat the Python execute channel as root-equivalent and gate it per-run with explicit user action — never auto-run because a file "is trusted".
Rejected alternative: reusing a "trusted document" flag to auto-execute LLM code.

## 9. Pyodide web worker constraints

Source: https://pyodide.org/en/stable/usage/webworker.html (docs banner **Version 314.0.7**; fetched 2026-10-11).

Findings (documented on that page):
- Pyodide **requires a module-type worker** (`pyodide.asm.mjs` is an ES module); classic workers with `importScripts()` are not supported.
- A worker runs "in a separate global context": it **cannot directly manipulate the DOM**, and globals cannot be shared with the main thread — context must be passed in the message payload.
- Recommended pattern: unique message `id` per request; `loadPyodide()` once; `loadPackagesFromImports(python)` before running; `runPythonAsync(python, {globals})` built from the passed context; post `{result | error, id}` back.
- Package loading: `loadPackagesFromImports` fetches/loads the packages needed by the script (so package availability mirrors the configured pyodide distribution; the page does not document FS persistence or network requirements — see Open questions).
- What cannot work in a worker: DOM access, blocking dialogs, any main-thread-only API; rendering must be sent back as data and drawn on the main thread.

Hutch applicability: Pyodide is the browser-only/secondary path; the native bwrap workspace (section 10) is primary. If used: module worker + id-correlated messages + structured-clone results (CSV rows, chart specs), never attempt DOM or persistent FS assumptions.
Rejected alternative: running Pyodide on the main thread (self-documented UI-blocking) — jank on every analysis run.

## 10. Supervised Python REPL inside bwrap with a JSON-line protocol

Sources (fetched 2026-10-11): bwrap man page https://manpages.debian.org/trixie/bubblewrap/bwrap.1.en.html (published 2026-08-26), https://github.com/Beforerr/repld, https://github.com/soliplex/bubble-sandbox, https://github.com/Aitherium/awrepl, https://github.com/v1kko/repl-session, awrepl README, bwrap README/containers.

Prior art found:
- **repld** — persistent, stateful REPL kernel for agents over a plain-text protocol, daemon + sessions, `interrupt`/`close`/`sessions` commands; intentionally avoids rich MIME output. (reported, repo checked)
- **bubble-sandbox** — bwrap driver for disposable Python exec: ro-bind venv/system libs, tmpfs /tmp, `--unshare-user`, `--unshare-pid`, `--unshare-net`, `--new-session`, `--die-with-parent`, auto-deleted workspace. (reported, repo checked)
- **awrepl** — persistent Python subprocess worker, **JSON over pipes**, per-session namespace, timeouts + output truncation; explicitly NOT a sandbox; notes heavy/C-extension code may be uninterruptible. (reported, repo checked)
- **Beforerr/repl-session** — pexpect + prompt-regex approach to driving arbitrary REPLs; notes Python 3.13 REPL color/ANSI churn. (reported)
- **bwrap native JSON-lines lifecycle**: `--json-status-fd` writes one JSON object per line — `child-pid` when the sandbox starts, `exit-code` when it exits (shell encoding; 128+n if signaled); readers must ignore unknown members. `--unshare-pid` gives a trivial pid1 that reaps children; `--new-session` protects against TIOCSTI (CVE-2017-5226); `--die-with-parent` kills the sandbox with its parent. (documented)

Pitfalls for a supervised `bwrap python` + JSON-lines REPL (**documented** where cited, otherwise engineering judgment):
- **Buffering**: Python block-buffers stdout when it is a pipe; a driver must flush after every protocol write (or run `python -u` / `PYTHONUNBUFFERED=1`), or replies stall. (judgment; consistent with repld/awrepl designs)
- **Framing**: exactly one JSON object per line; cap line length and reject non-JSON lines; do not allow code to write raw bytes to the protocol stream — redirect user stdout/stderr through the driver. (judgment)
- **stdin EOF semantics**: EOF on the host→worker pipe is shutdown, not an empty eval; worker exits, host reaps the exit-code line. Distinguish "worker exited" from "request timed out". (judgment)
- **Signals/process groups**: SIGINT sent to a raw child may be swallowed by Python's REPL/signal handling; interrupt the **process group** (start the session, then signal the group) or use an in-band interrupt that raises in the worker; awrepl notes some native loops remain uninterruptible. bwrap `--unshare-pid` means the sandbox has its own pid namespace — identify the sandbox child via `child-pid` and signal knowing namespace boundaries. (partly documented)
- **Orphaned children**: always `--die-with-parent`; reap with `wait()`; parse `exit-code` to distinguish crash vs clean exit. (documented)
- **Avoid prompt parsing**: don't scrape `>>>` (ANSI and Python-version churn; repl-session's config shows the pain). Ship a tiny driver that `compile()`/`exec()`s each request, captures `stdout/stderr` and the last-expression value, and emits structured JSON. (judgment, supported by repld/awrepl)
- **Resource isolation**: `--unshare-net` (loopback only), ro-binds for interpreter/venv, writable tmpfs workspace only, and optionally seccomp; bubble-sandbox is a concrete recipe. (documented)

Recommended mechanism: one long-lived sandboxed worker per Hutch analysis session; host spawns `bwrap` with ro-binds + `--unshare-net` + `--die-with-parent` + `--json-status-fd`; worker reads `{id, type:"exec", code}` lines, replies `{id, type:"result|stream|error", ...}`; host watchdog combines request ids, heartbeat, ack-based interrupt, and exit-code correlation.
Rejected alternative: pexpect/PTY prompt scraping (fragile across Python versions and ANSI output); also rejected: launching bwrap per execution (loses namespace state — the whole point of an analysis session).

---

## Open questions / blocked checks

- **OpenAI per-tier rate limits**: the public rate-limits guide names RPM/RPD/TPM/TPD/IPM but the per-tier numbers were not publicly accessible without an account; only the metric names are verified.
- **`gpt-image-2` status**: appears in the pricing/batch table but not in the current guide's model list; availability and deprecation status unresolved.
- **Gemini partial image previews**: not documented publicly; "thought images" are explicitly backend-only/unbilled. Gemini video previews: only operation polling found.
- **Veo output/resolution details**: the landing page + quickstart confirmed `.mp4` download and preview-tagged model ids; full resolution/format matrix and any partial-render preview were not verified today.
- **Mermaid in a sandboxed iframe with no network**: reasoned from its client-side architecture; not stated verbatim in the config schema page. The Trusted Types gap (#7695) remains open.
- **Chart CSP eval use for Chart.js/uPlot/Plot**: absence of `Function`-based expression languages was reasoned, not found stated in their docs; Vega's `unsafe-eval` requirement is documented.
- **Observable Plot large-dataset guidance** and **Pyodide FS persistence/package network requirements**: not verified from official docs this pass.
- **ComfyUI_frontend #2660**: still open; the 2026-03-28 WS-filtering commits may or may not cover same-clientId multi-run cases. Not reproduced locally.
- **GitHub issue states** (e.g. open-webui #23232 "open") come from the search index today and could lag; only #6888, #27399, #14823, #2660 were fetched directly.
- The ComfyUI `server.py` fetch followed `master` without pinning a commit; line references are from the 1,569-line file retrieved today.
