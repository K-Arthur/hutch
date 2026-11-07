# Models: switching, fit, slots, prices and `hutch doctor`

## Switching models in the chat

The Studio composer has a model control beside message options. Every model wears a **vendor mark** (bundled OpenAI and
Anthropic artwork, a monogram of the model family otherwise) with a small badge that distinguishes a listed local route from a
hosted route; the mark is decorative, and the control's full accessible name identifies the model and selection scope.
Its menu opens on **Quick picks** once there is something to pick from: the bot's own model first (marked *default*), the one
in use (with a check), and the last four routes you chose for this assistant (kept in this browser, per assistant). Then come
the remaining usable models grouped by where they run, then **All models**. The first nine rows have number keys (1-9, shown
as key hints on pointer devices), `/` opens the searchable list, and **Choose a model** in the command palette (Ctrl or
Cmd K) opens the menu from anywhere on a chat page. Each entry has one line of secondary text that says something true on
this machine:

| Entry | Secondary line |
|---|---|
| installed local model | `fits, 16k context` or `tight fit, 7k context` (the context the bot will really get) |
| hosted model | `$4 in / $20 out per 1M tokens`, or `needs ANTHROPIC_API_KEY` |
| connection model | `flat-rate plan` / `pay per token`, or what is missing (key, acknowledged terms) |
| OpenRouter model | provider-reported catalog price and name when listed; the model's own usage and tool behavior still need verification |

**All models** opens a searchable dialog with everything, grouped, with the search field focused on pointer devices. A
**Recent** group comes first, **All / Ready now / On this machine / Hosted** filters narrow the list, and the up and down
arrows choose while Enter uses the choice without leaving the search field. Models that cannot be used are shown with the
reason and the fix (`the weights alone are 40 GiB against 3.5 GiB usable`, `set ANTHROPIC_API_KEY where hutch
starts`) instead of being hidden. Anything that sends the chat off the machine carries a **leaves this machine** tag.
The dialog says explicitly that the choice applies to the next message. **Selected route and details** shows the exact
route and catalog/estimate qualifications; **Enter a model ID** opens the advanced field for models that are not listed.
Small positive estimates are not rounded to `$0.00`. Catalog refresh failures retain the previous choices and display
an error. These choices are revalidated when sending; selecting a model never dispatches inference.

OpenRouter is available as a first-party connection. Opening the composer model picker fetches its 40 most-popular
text models; typing at least two characters searches OpenRouter's catalog and returns matching entries. The chat
page itself does not contact OpenRouter to refresh that list. Catalog search also works when the OpenRouter connection
has a custom name. Catalog pricing and context size are reported values,
not guarantees of upstream availability. Separately, before admission to a paid OpenRouter route, Hutch reads the
public model-endpoint metadata and uses a five-minute quote; the response is capped at 1 MB, 512 endpoints and 64
pricing overrides per endpoint, and compressed responses are rejected. Strict USD ceilings refuse when fresh
metadata or a context/tool-qualified endpoint is unavailable. Strict reservation uses each eligible endpoint's entire
published input capacity (the smaller of its context and any explicit prompt limit), plus the requested output,
including declared higher-price tiers and possible cache-write cost; the highest whole-endpoint cost is held.
This deliberately reserves more than a short prompt estimate and can refuse a request despite its likely low cost.
Reported usage settles that hold after completion. When no strict ceiling applies, a labeled stale
quote or reviewed Settings > Prices row may be used. This estimate is not a provider-enforced billing cap. OpenRouter
requests ask for `usage.include=true` and retain the reported `usage.cost`. If that route omits a valid
billed charge, Hutch stops before tools or another model request and keeps the quoted amount held for
reconciliation. A reported zero is valid; missing, boolean, negative and nonfinite charges are not zero. A model
listing does not establish tool-call compatibility; verify task behavior with a normal governed run.

OpenAI API and other OpenAI-compatible connections discover model IDs from
their own authenticated `/models` endpoint when the model picker requests
discovery; Anthropic uses its paginated Models API. The catalog response and
short-lived cache are not a bundled inventory, and a catalog outage does not
remove an already configured route. Provider model IDs, prices, and capabilities
change independently of Hutch releases. A successful list request proves only
that Hutch could read the catalog, not that a selected model can complete a
task or call tools. OpenRouter can route within its own service according to
its fallback configuration; Hutch reports the response model for usage and
receipt records. See the [provider setup and compatibility review](connections.md#connect-a-model-provider-in-one-step).

Rules worth knowing:

- **Local model routes keep tools online.** A bot configured with `inference_mode=local` hides hosted choices and blocks hosted message overrides, fallbacks and escalation. Known Ollama cloud-tagged names are refused, but a local model server may still proxy traffic and network tools keep their own egress rules. Select **Hybrid** to allow hosted routes.
- **Offline is a separate, host-gated experiment.** On Linux, Settings/API/CLI offer it only after a fresh bubblewrap network/PID-namespace probe blocks TCP to both loopback and a host interface, verifies the isolated PID view, and confirms a Unix socket remains reachable. Each worker runs in fresh namespaces with a credential-free environment; saved connection definitions and key files are hidden by read-only empty mounts while Hutch's shared SQLite run state remains available. Its only model egress is a private per-run Unix socket brokered by Hutch to the configured numeric loopback endpoint; browser and web-fetch tools are omitted, and shell requires strict containment. systemd scopes provide resource caps only. Check `/api/v1/capabilities` for the current host result. Hutch cannot constrain networking inside the separate model-server process, so a local Ollama/LM Studio/vLLM service may still proxy or download data. A label, tag or loopback URL alone is not proof that model execution itself stayed local. If host verification fails, mode changes and run starts are refused.

- **One message, or explicitly save it.** A different route selected in the composer is a one-message override for the
  current conversation. The route is stored on that run as `model_override` and the chip returns to the Bot default after the
  message is accepted; if sending fails, the unsent selection stays available for retry. The pending override is remembered
  only for that conversation in this browser. The Bot's saved model and scheduled runs remain unchanged. Choose **Save as Bot
  default** in the same model menu to update the Bot settings explicitly; later chats and scheduled runs then use that route.
- **Choose a task role for one message.** In Bot → Model & connection, configure exact `provider/model` routes for banter,
  classification, extraction, summarization, synthesis/research, code analysis, or verification. In the composer menu,
  select the role for the next message; Hutch validates and runs that explicit route through normal fit, consent and budget
  checks. A model-pick override takes precedence for that message. The role selection is recorded on the run and clears
  after an accepted send. Unmapped roles use the Bot model. Automatic classification is not enabled because a classifier
  would itself require a priced, reserved, approved call; route quality has not been evaluated on Hutch tasks.
- **Three routing decisions stay distinct.** Task roles choose a route before generation, fallbacks respond to availability
  failures, and escalation follows repeated quality failures. A refusal, denied action, budget stop or invalid route cannot
  be bypassed by another role or quality ladder.
- **In Hybrid, a hosted pick is your explicit consent for that message.** The "ask before the first hosted call" rule exists
  to stop a *local-first bot* drifting off your machine on its own; it does not fire when you picked the hosted model
  yourself. Local-route mode refuses hosted choices. Estimate-based limits and exact response-usage recording still apply; provider billing can differ from Hutch's estimates.
- **The runtime still protects you.** The override goes through the normal run path, so a model that cannot fit this
  machine is refused before it loads, and the run says so.
- **The server re-validates on send.** Unknown provider, missing key and an unacknowledged connection are refused with the exact
  fix. Bots saved with legacy `pi` or `opencode` runtime values create a visible failed run with an `unsupported` reason; those
  runtimes are disabled before an external process starts.

API: `GET /api/bots/<name>/models` returns `{default, models:[{spec,label,group,state,note,fix,default,hosted,detail}]}` without contacting provider catalogs. The picker explicitly calls `GET /api/bots/<name>/models?discover=1`; an optional `q` filters the OpenRouter catalog. `PATCH /api/bots/<name>` accepts a `task_routes` object keyed by one of the seven task roles. `POST /api/v1/conversations/<id>/messages` accepts an optional `task_role` plus the existing optional `model`; the explicitly selected `model` takes precedence, and unavailable task routes are refused rather than silently replaced. `POST /api/bots/<name>/estimate` accepts the current draft, selected route, skills and rehearsal setting in its JSON body, then estimates the bounded recent conversation context and selected reply/specialist reference without putting the draft in the URL. Its token and cost figures remain estimates and can change before admission. `POST /api/bots/<name>/run` keeps its existing optional `"model": "provider/model"` override (409 = usable once set up, 422 = malformed or unknown).

## Workspace defaults for new Bots

Preferences can store a workspace model route and inference mode for **new Bot drafts**. The setting is available in Studio
under Preferences → **Model defaults for new Bots**, and through `GET`/`PUT /api/v1/preferences/model-defaults`. A route is
validated before it is saved; Strict Offline also requires the local host check and a verified local route. Leave the model
blank to have each new Bot choose its own route. Saving an empty route clears the model default.

These preferences seed creation only. If the model route is blank, a new Bot still inherits the selected routing mode after the
user chooses a usable route. They do not edit existing Bot settings, current conversations, scheduled tasks or runs.
When setup begins from a chat Bot with a configured route, that route is shown as an editable suggestion ahead of the workspace
default; the user can change it before saving. Explicit choices in the setup request take precedence. The ordinary Bot settings
remain the saved per-Bot default. The composer offers a one-message override, then returns to the saved route; a separate
**Save as Bot default** action changes future chats and schedules. Coordinator and specialist Bot routing is not yet implemented.

## Per-Bot task focus

The advanced Bot setup flow and each Bot's **Model & connection** settings expose an optional task focus: Router, Research,
Extraction, Coding, Planner, or Vision. A focus is saved on the Bot and tunes the built-in local runtime's requested context
window and model-residency behavior. The standard profile keeps the existing default. Focus selection never chooses or installs a
model, changes a provider route, enables tools, or starts a run, and does not verify that the chosen model supports the task.
Keep choosing the model route separately; the Models page and
`hutch models presets` show which local candidates fit this machine and whether they are installed.

`GET /api/v1/task-presets` returns the configured profiles. Bot create/update accepts a `preset` ID; an empty value clears it,
and an unknown or removed ID is rejected rather than silently falling back.

## Workflow model-role compatibility

The model catalog does not label a checkpoint "workflow-capable." Hutch checks each workflow
role independently. Author and selector authority require a complete, passing held-out probe
record for the exact serving backend/version, checkpoint digest, quantization, template and
tokenizer hashes, protocol/parser, effective context, decoding settings and reported modalities.
Changing any of those inputs makes the old probe inapplicable. A failure is negative evidence;
an incomplete profile or timeout is inconclusive. Worker and verifier evidence remains scoped to
the recorded task and route, and a same-route verifier cannot certify its producer.

The initial disposable probe path accepts only a loopback Ollama 0.40.3 Q4_K_M candidate. It
uses a 4,096-token context and the local runtime's default 2,048-token output cap, sends no tools
or user data, and checks that each response used one CPU-resident model. The campaign ledger
caps aggregate usage at 80 requests, 60,000 estimated/reported tokens and two hours. Probe
execution is local-owner-only; no hosted fallback occurs. Passing a probe qualifies only the
matching profile, not every setting for that model. Models without role evidence remain usable
for supported direct chat or isolated evaluation, subject to ordinary route and resource gates.
See [dynamic workflow role qualification](workflows.md#roles-and-qualification) for commands
and the scope limits.

The versioned provider compatibility matrix is available at `GET /api/v1/compatibility` and in
[provider compatibility](realignment/provider-compatibility.md). It records Hutch's request mapping and evidence for each
route. The route state describes the common protocol contract, not whether a particular live model can reliably use tools;
the current model-list check does not verify that capability.

## Getting and importing a local model (2026-11)

Installing is an explicit, runtime-native operation, not a side effect of choosing a
model. The Models page's **Install** button first asks the server for a preflight and
shows it before anything is downloaded: the catalog size (or "unknown"), free space on
the runtime's own model directory, the 16k fit verdict, and a measured-rate ETA when a
previous transfer supplied one. **Confirm download** is the only action that starts a
pull; the server re-runs the same plan, so a client cannot skip the check. An insufficient
known size is refused with the free and needed numbers; an unknown size or an unreadable
directory is a warning, never a fabricated zero.

The name grammar is the runtime's own rather than a lowercase slug: `model`,
`namespace/model`, `host/namespace/model`, optional `:tag`, and the real
`hf.co/<user>/<repo>:<quant>` forms (a quant tag or a full GGUF filename, case-preserved).
Model equality is case-insensitive. Cloud tags remain a data-sharing choice and are
refused without an explicit confirmation.

A running Ollama pull can be cancelled. The runtime keeps completely downloaded chunks
until the pull resumes or the Ollama server restarts; pressing Install again resumes when
it kept them, and some transfer paths restart a blob from zero instead. Hutch reports the
bytes this attempt received, not a synthesized percentage. `OLLAMA_NOPRUNE=1` is the
runtime's own switch for keeping parts across a restart. A page reload reattaches to a
running job; a Hutch restart loses the job record and the page says to press Install again.
Two clicks or two tabs share one job.

A local GGUF can be imported through the runtime's own blob and create APIs
(`POST /api/models/import`; the visible form is Phase 7). Hutch checks the GGUF header,
hashes the file, asks the runtime whether the blob exists, uploads only when it does not,
creates the model from the original filename and digest, and confirms it in the runtime's
list. The runtime verifies the digest again. An expected checksum is compared before any
upload, split shards are refused with the merge hint, and a license is shown from the
request, a sidecar file, or the runtime's own report — a missing license is shown as
missing.

LM Studio (`lms get`), llama.cpp (`llama-server -hf`) and vLLM/SGLang are guided paths
rather than Hutch jobs: their native downloads happen outside the runtime's request API
or lack the cancel/catalog operations the job model needs. The exact commands, cache
locations and token rules are in [runtime setup](runtime-setup.md#getting-a-local-model-2026-11).
The dated evidence, including a real 1.9 GiB pull cancelled and resumed through the page,
is in `docs/realignment/offline-models-2026-11/02-PROGRESS.md`.

## The Models page (`/models`)

The "everything" view behind the switcher: runtimes and connections with state and fix, installed models marked
**fits / tight / won't fit** at 16k and 32k context, what each task preset resolves to on this machine (with the
install command when it is missing), measured swap costs, and the hosted price table.

`hutch models list` and `hutch models presets` print the same data in the terminal.

Fit is **arithmetic, not a benchmark**: weights plus KV cache against the memory budget, using the runtime's own
architecture numbers once a model is installed and catalog estimates before. It does not predict speed.

### Where a connection's model list comes from (2026-10-31)

Every one of the 25 hosted OpenAI-compatible connections added on 2026-10-31 is listed by asking its own
`/models` endpoint, authenticated with that connection's key. Two consequences are worth knowing before
blaming the picker:

- **The list is the provider's, not Hutch's.** If a connection lists no models, the provider did not return
  any for that key. Hutch makes no model up and greys nothing in silently.
- **The list can live somewhere other than the chat URL.** OpenCode Go serves chat under
  `.../inference/go/openai/v1` but publishes its catalogue under `.../inference/go/v1`; before that was
  modelled, a valid key appeared to return `404`. A connection may therefore carry `models_base_url`
  ([`connections.md`](connections.md)), which you normally never set by hand - templates do.

A returned list still proves nothing about the models in it. It is a claim by the provider that the id
exists for your key, not that the model takes tools, images, a given context length, or your budget.

**A list can also prove nothing about the key (2026-11-06).** Hugging Face, Kilo, Novita, NVIDIA, Ollama Cloud,
Synthetic and Venice return their model list for any key, including a made-up one (measured with a placeholder
value, no account). For those, **Test** on the Models page and `hutch connections test` list the models and say
the key was *not verified*; they no longer say "verified" or "authenticated". Microsoft Foundry and Qianfan have no
list to read, and Bedrock's runtime endpoint has none either, so those checks only prove a key is present. A normal
bot request is the check that exercises the key, and it runs through the usual approvals and usage limits.

## Measuring tool reliability: `hutch models bench`

"Supports tools" on a model card does not tell you whether a model forms a valid call, gets argument types right,
picks the right tool among several, stops when it should, and uses what the tool returned. `hutch models bench
<model>` measures that on your machine:

| Probe | Passes when the model... |
|---|---|
| Forms a valid tool call | makes exactly one `read_file` call with the right file and schema-valid arguments |
| Gets argument types right | sends `quantity` as an integer and `urgent` as a boolean (`3`, `true`; not `"3"`, `"true"`) |
| Picks the right tool among five | chooses `list_files` for "list the files in reports" |
| Does not call a tool it does not need | answers "2 + 2" directly, without a tool call |
| Uses what a tool returned | answers from a tool result it was given instead of calling again |
| Recalls the start of a long prompt | repeats a code word placed at the top of a long prompt, at the measured window |

Each probe runs `--trials` times (default 3) at low temperature so a flaky model shows as flaky. Two numbers per probe:
**passed** (after Hutch's safe argument repair, which is what a bot will experience) and **unaided** (what the model
did right on its own). The verdict is *reliable*, *works, leaning on argument repair*, *unreliable* or *inconclusive*
(more than half the calls failed at the runtime, which says nothing about the model).

Profiles are keyed by model, quantisation, runtime, chat-template hash, file digest and window, so a changed file or
template is a different profile (the Models page flags "changed since measured") instead of a stale number.
`hutch doctor` warns when a bot with tools runs on a model measured unreliable, and notes models never measured.
This is a profile of one model on one machine, not a leaderboard score.

`--provider llamacpp|lmstudio --base-url <url>` runs the same probes against a local runtime's
OpenAI-compatible endpoint. The **causes** column names each failure instead of leaving it as prose:
`no_call`, `empty_answer`, `reasoning_only`, `call_in_content`, `missing_id`, `duplicate_id`,
`parallel_calls`, `parse_error`, `wrong_tool`, `unexpected_call`, `schema`, `type_repair`,
`ignored_result`, `wrong_answer`, `call_failed`. A complete call left as text is a template or parser
failure, not a model weakness, and it is counted separately.

Measured on this CPU-only host on 2026-11-06 (3 trials per probe, no recall probe; output files in
`docs/research/2026-11-offline-models/evidence/phase5/`). The first table is the retained 2025-era
baseline; the second is the November 2026 comparison, pulled after the owner approved exceeding the
original download budget. Both remain evidence: the old numbers are not replaced.

| Runtime | Model | Tool probes | Verdict | Main causes |
|---|---|---|---|---|
| Ollama 0.40.13 | qwen3:0.6b | 15/15 | reliable | none; 43.5 tokens/s |
| Ollama 0.40.13 | qwen2.5-coder:1.5b | 6/15 | unreliable | `no_call` 9; form, argument types and tool choice 0/3 |
| Ollama 0.40.13 | qwen3:4b | 13/15 | unreliable | argument types 1/3 (`no_call` 2); 7.6 tokens/s |
| llama.cpp b12144 | qwen3-0.6b | 15/15 | reliable | none |
| llama.cpp b12144 | qwen2.5-coder:1.5b | 1/15 | unreliable | `no_call`, `wrong_answer`, `ignored_result` |
| llama.cpp b12144 | qwen2.5-coder-3b | 0/15 | unreliable | `call_in_content` 15: the body was a complete call, `tool_calls` was null |
| LM Studio 0.0.27-1 | qwen3-0.6b | 15/15 | reliable | none |
| LM Studio 0.0.27-1 | qwen2.5-coder-1.5b | 3/15 | unreliable | `no_call` 9, `wrong_answer` 3 |
| LM Studio 0.0.27-1 | qwen2.5-vl | 6/15 | unreliable | `no_call` 9; not trained for tool use |

The same model can land in different places per runtime: qwen2.5-coder:1.5b scored 6/15 through
Ollama, 1/15 through llama-server and 3/15 through LM Studio. That is the reason this bench exists.
A thinking model can also spend the whole output budget before a call: llama.cpp + qwen3-4b generated
at about 3.9 tokens/s and did not finish four probes in ten minutes with the default reasoning budget;
`--reasoning-budget 0` exists for this. No third trial result is claimed for that case.

The current-model comparison, same host and commands:

| Runtime | Model | Tool probes | Verdict | Notes |
|---|---|---|---|---|
| Ollama 0.40.13 | qwen3.5:0.8b | 15/15 | reliable | 12.7 tokens/s, Q8_0, 1.3 GB |
| Ollama 0.40.13 | qwen3.5:2b-q4_K_M | 15/15 | reliable | 13.6 tokens/s, 1.9 GB |
| Ollama 0.40.13 | qwen3.5:4b-q4_K_M | 15/15 | reliable | 4.8 tokens/s, 3.3 GB |
| Ollama 0.40.13 | gemma4:e2b | 15/15 | reliable | 9.8 tokens/s, 4.6 GB; vision and audio |
| llama.cpp b12144 | qwen3.5-2b | 15/15 | reliable | stock template has vision and tools |
| llama.cpp b12144 | gemma4-e2b | 11/15 | unreliable | tool choice 0/3, 3 calls left as text |
| LM Studio 0.0.27-1 | gemma4-e2b | 12/15 | unreliable | argument types 0/3, 3 reasoning-only turns |

All current models pass the isolated tool probes on Ollama; the same file behaves differently on the
other two runtimes. The bench is not the whole story: it sends five short probes, not Hutch's full
system prompt. A separate full-app image comparison on Ollama (8,192-token preset, real cat photo,
real Playwright screenshot, two-image message) produced:

| Model | Cat | Screenshot | Two images | Full-app result |
|---|---|---|---|---|
| gemma4:e2b | `cat` | `Models` / `Route readiness` | `Image 1` | 3/3 correct |
| qwen3.5:4b-q4_K_M | `Cat` | `Models` | repeated the question | 2/3 |
| qwen3.5:2b-q4_K_M | ginger tabby | repeated the question | repeated the question | 1/3 |
| qwen3.5:0.8b | repeated the question | repeated the question | refused at the 4K window | 0/3 (8K not run) |
| qwen2.5-vl (old baseline) | `Cat` | `"Models"` | `image 1` | 3/3, but 73-188 s per run |

That gap is the practical selection rule. **Gemma 4 e2b is the current full-multimodal winner on this
host**: 15/15 isolated tools on Ollama, 3/3 full-app images, a stock vision-plus-tool template on
llama.cpp, and working vision on LM Studio. **Qwen3.5 2B Q4 is the lightweight tool winner** (15/15,
13.6 tokens/s, 1.9 GB) for routing and extraction, but 1/3 in the full multimodal prompt. Qwen3.5 4B
is slower and less accurate in the full app than Gemma 4 e2b. Qwen3.5 0.8B is an isolated-probe model,
not a full-agent model. The old qwen3:0.6b is still the fastest tiny tool model (43.5 tokens/s) but is
2025-era; qwen2.5-coder remains unsuitable for tool calling at every size measured.

## Vision and image input (2026-11-06)

Images are message content, never a silent text substitute. A route must state that it accepts images
before one is sent: Ollama reports `vision` in `/api/show` capabilities; llama.cpp reports
`modalities.vision` and input modalities in `/props` (a server started without `--mmproj` reports text
only); LM Studio reports `capabilities.vision` in `/api/v1/models`. A model without vision is refused
with words before the request; an image whose stored digest, MIME or size does not verify is refused
too.

Image cost is counted as a bounded per-image block (800 tokens) by both planning and compaction. It is
never the base64 payload: a 1.5 MB image would otherwise look like about 500,000 text tokens and block
a run that fits. The estimate is conservative, not a promise. Measured prompt tokens are 741 for a
640 px cat photo through Ollama moondream, 562 through llama.cpp Qwen2.5-VL, and 592 for two images
(the second a small icon). A large, detailed image can cost more, so the normal window check still
applies.

Real results recorded on 2026-11-06 with the retained Qwen2.5-VL/moondream2 baseline and the current
Gemma 4 e2b comparison:

| Runtime and model | Input | Answer | Measured |
|---|---|---|---|
| llama.cpp b12144, Qwen2.5-VL-3B Q4_K_M + Q8_0 mmproj | real 640 px cat photo | `Cat` | 562 prompt tokens |
| llama.cpp, same | real Playwright capture of `/models` | `"Models"` | answer depends on the heading |
| llama.cpp, same | cat plus the screenshot in one message | `image 1` | 592 prompt tokens |
| llama.cpp, same | WebP cat photo | cat description | WebP is accepted on this route |
| llama.cpp, same, merged tool template | cat plus a `describe_scene` tool | `describe_scene(animal="cat", colour="orange")` | 729 prompt tokens, 42.9 s |
| Ollama 0.40.13, moondream 1.8b Q3_K_S | real 640 px cat photo | ginger cat description | 741 prompt tokens, 4.0 s |
| LM Studio 0.0.27-1, qwen2.5-vl | real Playwright capture of `/models` | describes the Models section | 35.6 s for the whole app run |
| Ollama 0.40.13, gemma4:e2b | cat, screenshot, two images (whole app) | `cat`, `Models` / `Route readiness`, `Image 1` | 3/3 correct; 56-96 s per run |
| llama.cpp b12144, gemma4-e2b + mmproj | cat plus a `describe_scene` tool | `describe_scene(animal="cat", color="orange")` | 267 prompt tokens; stock template |
| LM Studio 0.0.27-1, gemma4-e2b | cat, screenshot | `Cat`, `Models` | vision true after the projector is named correctly; WebP still rejected |

The whole-app path (composer upload, admission, wire conversion, real answer, transmission record)
was exercised on real images through llama.cpp, LM Studio and Ollama. The old moondream model is
refused by the app at 2,048 tokens (below the 4,096-token agent floor), which is a window state, not a
vision failure. The current Gemma 4 e2b passed the whole-app image comparison 3/3 on Ollama.

Limits found in the same pass:

- **Ollama cannot import a separate projector.** Importing the Qwen2.5-VL GGUF with a Modelfile
  produced `capabilities: ["completion"]` and no projector; `/api/show` is the confirmation. To use
  vision on Ollama, pull a vision model (for example `moondream`), do not import a text GGUF.
- **A vision model's embedded template may have no tools.** Qwen2.5-VL's template reported
  `supports_tools: false`. The image-plus-tool result for that model used `--chat-template-file` with
  a local merge of llama.cpp's Qwen2.5 tool template and the model's own vision loop. That is a test
  configuration, not a vendor-shipped file, and Hutch does not modify a launch automatically. The
  current Gemma 4 e2b and Qwen3.5 2B templates report vision and tools together, so the stock
  template produced a clean `describe_scene` call.
- **LM Studio 0.0.27-1 rejects a WebP data URI** in `image_url` with "'url' field must be a base64
  encoded image"; PNG and JPEG are accepted. Hutch refuses WebP on that route before sending and does
  not rewrite the user's file type.
- **LM Studio pairs a projector only by filename.** Gemma 4 e2b was listed with `vision: false` until
  its projector was renamed to `mmproj-<model>.gguf` and the server restarted; before that LM Studio
  treated the projector as a separate CLIP model. This is a setup requirement, not a model capability.
- **Audio and speech are deferred.** Ollama exposes `/v1/audio/speech` (Phonon, WAV/PCM, 4,096
  characters), llama.cpp accepts `input_audio` with a compatible model, and LM Studio has no
  documented audio input. No audio or speech model was retained, and no Hutch audio path was
  exercised, so none is claimed.
- **Embeddings are not called for a local assistant.** LM Studio exposes `/v1/embeddings`, but no
  Hutch chat, memory or search path requests a hosted embedding; `synthesis/model.py` uses the chat
  route. The airplane test that proves the whole turn has no egress is Phase 6.

## Tool calling modes and compatibility

Every Bot's tools are compiled into one per-run plan before the first model call, and the
plan is recorded in the transcript (`tool_protocol` entries with catalog/plan hashes and
field-level diagnostics). The default is **auto**: Hutch uses the provider's own tool
protocol exactly as before and never silently switches modes.

| Mode | What it means |
|---|---|
| `auto` / `native` | The provider's own function-tool protocol (OpenAI Chat Completions, Anthropic Messages, Gemini generateContent `functionDeclarations`, Ollama native, llama.cpp/vLLM when the server has tool parsing enabled). Best-effort call shaping; every call is still validated locally. |
| `constrained` | The backend generates one JSON object from a versioned `hutch-action-v1` envelope, attached through the backend's own schema control (Ollama `format`; OpenAI-compatible `response_format`). Best for a route whose native parser mangles calls. Refused when the route has no verified schema control. |
| `prompt` | The same envelope is requested in the prompt and parsed strictly, whole-message. Best-effort and off by default: choose it explicitly for a model that cannot follow a native or constrained path. |
| `disabled` | No tools are offered to the model for this run. |

Practical guidance:

- Malformed calls, invented tool names, or a model that writes tool-shaped JSON into ordinary
  content are all rejected, logged, and (for malformed calls) answered with one precise repair
  prompt - nothing executable is invented from broken output.
- If a local model repeatedly fails native tool calling, open the Bot's settings, check
  **Tool compatibility** (below), and try `constrained` when the button is available. If the
  endpoint rejects the schema control, the run fails with that reason instead of downgrading.
- `prompt` mode is best-effort generation with local validation. It is not grammar-enforced;
  quoted or example JSON is never executed.
- Route evidence comes from documentation and from your own governed runs. `advertised` is not
  `verified`, and a single successful call is not a model guarantee.

## Tool compatibility diagnostics

`GET /api/v1/tool-compatibility?ref=<Bot>` (and the **Tool compatibility** section in Bot
settings) reports, without making a model request: the exact route profile (provider,
endpoint class, model, build/template fingerprint when known), which strategies are
available and why, the validator engine in use, and any recorded observations from governed
runs. Unknown components stay unknown. The section explains missing prerequisites rather
than saving settings that would be silently ignored.

## Local inference admission

One Hutch local-inference call may hold capacity at a time, with eight waiting calls across
processes sharing the state directory. The same model has no concurrency exemption. Native
Ollama startup, loading and self-check also hold capacity. A full queue refuses the next caller
with an actionable error. A queued call records its position, can be stopped, and does not
reserve provider usage before admission. Kernel locks release on process death; ticket files
retain no authority after their owner exits. Do not remove or replace `state/inference/*.lock`
while Hutch is running.

Capacity is held per model call, then released before tools, approvals or human waits. Each
later turn re-enters the FIFO queue. The dispatcher prefers already resident models and gives
older runs priority after fifteen minutes, but that preference grants no inference capacity.
The retired `HUTCH_MODEL_SLOTS` setting cannot widen this limit. Hosted calls bypass
this local admission queue. It does not control unrelated clients or prove that an external
server has stopped working after a Hutch process dies.

Native Ollama fit checks use current measured RAM/GPU headroom before generation, including
after an approval wait. Unknown free GPU memory fails closed; measured zero is never replaced
with total capacity. A model's reported resident allocation is credited against the physical
free-memory snapshot, capped by totals; multi-GPU placement is not inferred. Footprint and KV
cache fit remain estimates, not an OOM guarantee. Other local protocols have queue limits; their
window admission is now measured (ADR-0030), while Ollama remains the only runtime with validated
resident-memory admission. llama.cpp b12144 and LM Studio 0.0.27-1 were exercised on 2026-11-06.

Fixed-window runtimes are read, not assumed (ADR-0030). llama.cpp reports its per-request window
in `/slots[].n_ctx`; with `-c 8192 --parallel 2` that is 4096, not 8192. LM Studio reports
`loaded_instances[].config.context_length`, which can be far below `max_context_length`; a cold
model is loaded with a fitted window and the applied value is read back from `load_config`.
Hutch refuses an over-long prompt before sending and lets compaction run first where enabled. A
key-protected server answers 401/403: the Models page and discovery say `needs_key`, and a key
stored on a connection is sent only to that connection's exact loopback origin. vLLM and SGLang
put `max_model_len` on every `/v1/models` entry (their `ModelCard`, checked 2026-11-06); Hutch reads
it as the applied window only when `owned_by` names the server, and says unknown for any other
OpenAI-compatible server. No vLLM or SGLang was installed to run live, so that path is
implemented-unverified (ADR-0034). Live evidence: llama.cpp b12144 and LM Studio 0.0.27-1, 2026-11-06, in
`docs/realignment/offline-models-2026-11/02-PROGRESS.md`.

### Loading, sleeping and eviction (2026-11-06)

A runtime that is loading is a state, not a failure. llama.cpp answers `/health` with 503
"Loading model" and serves `/v1/models` before it is ready; Hutch waits on `/health`, shows
`loading_model` for the run, and records the measured wait. Measured on 2026-11-06: a cold
Ollama qwen3:4b load took 4.8 s; llama.cpp b12144 took 3.6 s from the first 503 to the applied
4,096-token slot; an LM Studio reload after an explicit unload took 2.9 s at 8,192 tokens.

Fixed-window routes are re-read before every model call. If the model was evicted (LM Studio
TTL or auto-evict, an explicit unload, a router eviction, `OLLAMA_MAX_LOADED_MODELS`) Hutch
reloads it once with a visible loading state. A runtime that stops mid-turn is classified as a
restart: with no output delivered Hutch reloads and retries once; if text was already produced,
that text is kept and marked incomplete and the turn stops with the cause. A real kill -9 of the
Ollama runner mid-stream produced `llama-server process has terminated: signal: killed`; the run
showed `loading_model`, reloaded, and finished successfully. A killed llama-server was classified
and recovered once it answered again.

A sleeping llama.cpp model (`/props.is_sleeping`) is reported as reloadable, not down, and the
first request wakes it. Hutch cannot know a runtime's TTL or eviction policy ahead of time, so it
reads the model state instead of assuming the previous turn's model is still resident.

Runtime versions are recorded and gated (Ollama tools 0.3.0, structured outputs 0.5.0, thinking
0.9.0, measured window 0.10.0; LM Studio tools 0.3.6, TTL 0.3.9, native API/tokens 0.4.0).
`hutch doctor` and the Models page say "upgrade X to Y for Z" when a used feature is newer than
the running build. llama.cpp publishes no feature matrix, so Hutch records its build string and
gates on the fields it actually returns, never a guessed build floor. An unknown version produces
no advice.

### Local runtimes on the Models page (2026-11-06)

The page shows one card per detected local runtime with its reported version, state
(`ready`, `loading`, `needs_key`, `down`, `unknown`), loaded models, applied window and
per-slot count, and the single next action. Values the runtime reports are labelled
measured; fit and window estimates are labelled predicted; a value it did not report is
shown as unknown. Discovery fingerprints the response rather than trusting a port: llama.cpp
on 9931 and a decoy on 8080 are distinguished by `/props` and `/v1/models`; a 401/403 is
`needs_key`, and a 503 on `/v1/models` is `loading` when `/health` confirms it.

Configured routes are grouped by where inference happens: "On this machine", "On your
network", "Cloud via local runtime" and "Hosted", each with a privacy sentence. A renamed
cloud copy (`my-local-copy`) is grouped by the `/api/tags.remote_host` signal, not its name.
A saved route whose runtime is down shows `cannot run` with the reason in words.

### Data-sharing confirmation (EC-28, 2026-11-06)

Changing an existing assistant's saved route, or using a one-message override, on a
cloud-tagged, non-loopback or hosted route requires a per-assistant confirmation. The
dialog names the assistant, the exact route and what moves; the server records a digest
bound to the route and scope, and the save or send consumes it once, so switching back asks
again. A local loopback route needs none. Creation from a hosted starter route keeps the
starter-route notice. Code: `route_sharing.py` and `server/model_sharing_api.py`; tests:
`tests/test_route_sharing.py` and `tests/e2e/test_model_sharing.py`.

Run details separate recorded inference admission waits from model/tool time and Hutch overhead.
Step timing covers recorded steps; startup admission waits are included in the run's `queue_ms`
total. Interrupted waits that never acquire capacity are not included in that admitted-wait total.

`hutch models swap-test <model-a> <model-b>` measures what alternating a pair really costs: cold load of A, load of B
on top, load of A again, and whether the runtime actually evicted A. It unloads and reloads your models and generates
no tokens, so run it when the machine is idle. Results appear on the Models page. *Until you run it, the page says
"not measured": Hutch does not guess swap cost.*

## What a run may cost, before it starts

Every bot page, `hutch bot estimate <bot> [--model X]` and `GET /api/bots/<name>/estimate` show Hutch's **price estimate**:
the prompt-size estimate is multiplied by the configured step count and per-turn output limit. This is an admission signal,
not a guarantee of the provider's final bill. Provider tokenization, price changes, and unreported usage can differ. Before
each hosted call Hutch atomically reserves the same kind of estimate against the run, bot, and configured provider account;
responses with reported usage settle measured tokens and cost. An unresolved request stays held until an operator checks the
provider record and reconciles it. A configured cost limit refuses the next call when Hutch's estimate would cross it; it
cannot guarantee that an outside provider never bills more than the limit. Use the provider's own spending controls for a
separate external ceiling. A local model says "no per-token cost", a flat-rate plan says that calls still count against its
declared allowance, and a hosted model with no price row is refused while a currency limit is set.

In **Apps & AI → Model accounts → Spending limits**, set optional USD warning, approval and stop thresholds
for a billing account shared by multiple model connections. Choose **Each local day** or **Across all days**;
the latter includes the account's entire retained ledger in this Hutch profile, across Bots and tasks. The preview
shows recorded spending plus unresolved holds for the selected period. Blank removes a band; a zero stop permits
only requests with a known zero quote. Existing per-run, per-Bot and legacy daily limits still apply independently.
Saving from an outdated form is refused: reload the current limits before editing again. These controls govern
Hutch's estimates, not your provider balance or activity in other applications. They do not establish that a
native third-party runtime has reserved a maximum for every auxiliary call.

## Usage

`/usage` answers "where did the money and the allowance go": measured spend and tokens by **local calendar day** (the same day the
daily limits use), by model and by bot; today against each bot's measured use plus held reservations; each plan's allowance meter; the
share of prompt tokens served from cache; and a log of every time a run **fell back** (the model was unavailable),
**escalated** (it was not up to the job) or **stopped at a plan allowance**, newest first. Local models read "free
(local)" and flat plans read "flat plan" instead of a misleading `$0.00`.

## Hosted prices

`prices.json` rows carry a source and a **verified** date; rows over 90 days old are flagged. Correct a row on the
Models page and the new number is used immediately: it is written to `<state dir>/prices.json`, stamped today, and
**Reset** restores the bundled row. Local models cannot have a price row. A hosted model with no row **cannot run
while a Hutch currency limit is set**: Hutch refuses rather than guess. Even a priced route uses an estimate, not a guarantee
of the provider's final bill.

## `hutch doctor`

```bash
hutch doctor              # every check, each problem with its fix
hutch doctor --deep       # also run each local bot's context self-check (uses CPU/GPU, no money)
hutch doctor --online     # authenticate connections (spends no tokens)
hutch doctor --json
```

Checks: Python version; database integrity, WAL and schema version; state-directory and key-file permissions;
runs orphaned by a dead process; the `hutch.service` user unit; each runtime (a stopped runtime is a failure only
when a bot depends on it); each local bot's model fit and the context it will actually get; connection keys and
terms; hosted bots with no Hutch currency estimate limit; auto-approval combined with a shell. Exit status is non-zero only for a
**FAIL**; warnings do not fail it, so it can gate a script.

Per-runtime health (also on the Models page): each call's outcome is recorded; two consecutive failures mark a runtime
*degraded*, four mark it *down*, and a success clears it. One runtime's failures never change another's state.

## What is and is not verified

- Verified by kernel-lock process tests and scripted servers: bounded FIFO admission, crash release,
  human-wait release, cancellation before reservation, fresh-memory refusal, fit arithmetic, ordering, swap measurement logic,
  override validation, the fit guard on an overridden run, price edits, doctor and health, and the switcher in a
  real browser (desktop and phone width).
- **Verified on real local models (2026-11-06).** Ollama 0.40.13, llama.cpp b12144 and LM Studio
  0.0.27-1 ran on this CPU-only host. Measured: cold loads, per-slot windows, tool reliability on
  sixteen model/runtime pairs (the retained 2025 baseline and the current Qwen3.5/Gemma 4 set),
  vision on real images, and the whole-app image path. The evidence and the not-run list are in
  `docs/realignment/offline-models-2026-11/02-PROGRESS.md`; the raw benches are in
  `docs/research/2026-11-offline-models/evidence/phase5/`.
- **Strict Offline (2026-11-06).** The worker boundary is live-verified on Ollama 0.40.13 and
  llama.cpp b12144: a governed tool-and-image turn through the per-run broker, the airplane test
  inside `unshare -rn`, shell egress returning `connect_ex 101`, a 1,200-token stream, cancellation,
  a runner kill and a server restart. The model server itself was user-run and is not isolated;
  ADR-0035 records the owner's managed-process decision, which is not implemented. The exact claim
  is in `docs/realignment/offline-models-2026-10-31.md` section 5 and section 9.
- **Not verified.** GPU inference, CUDA/ROCm/Metal, a 4 GB-class cold load, an older runtime's
  upgrade path, GPU OOM, LM Studio API-token mode from the CLI, vLLM/SGLang serving, audio/speech
  (including Gemma 4's audio capability), a gated Hugging Face pull, a Hutch-managed isolated model
  server (ADR-0035, not implemented), LM Studio through the Offline worker, Gemma 4 e4b/12b/26b,
  Qwen3.5 122B, Qwen3-VL specifically, and full-app text-only runs for the current models. The
  pages and commands report "not measured" rather than showing numbers that were not.

## Route readiness and provider evidence (2026-10-30)

The Models page now shows an explicit readiness state for every configured route. States are computed
from local configuration only: available, needs authentication, authentication expired, revoked
account, capability unverified, endpoint unavailable, needs configuration, blocked by policy, and
similar. Capability unverified is not a failure; it means no dated evidence exists for that exact
route and model in this build. A provider catalogue link opens the account, capability and runtime
overview. See provider-platform.md and ADR-0029.

A spec of `provider/model` names a provider, not an account. When the provider has a configured account,
the readiness panel says which account exists and shows a resolving spec such as
`google-gemini/gemini-3.8-flash` instead of claiming no connection exists; it never picks an account for
you, because that choice decides who pays. The same applies when an ambient key and a named account are
both present: the detail names the key variable and asks you to choose.

`GET /api/v1/provider-resolution?spec=provider/model&runtime=builtin` returns the explicit tuple Hutch
would use: provider, account and account source (named connection, ambient variable, local service or
none), billing relationship, model, runtime, protocol, endpoint and readiness state. It reads local
configuration only. A named account is reached by naming it (`account/model`); a provider prefix with
two matching accounts returns `needs_configuration` instead of choosing. A fallback or escalation from a
subscription primary to a per-token model is refused before the call; making the metered route primary is
the explicit decision. See ADR-0028.

### Twenty-five hosted routes, no live inference (2026-10-31)

The Models page and the switcher can now list models for 25 more providers, because each has a real
connection template whose endpoint answered a credential-free request. Read the readiness label, not the
presence of a name: those routes are `implemented-unverified`, which the page renders as
"route only, untested - Hutch can reach this service, but no live account has run a request through it".

No capability, price or context claim is made for any model behind them until a dated, authenticated run
exists for that exact route and model. The only routes with that evidence are the DeepSeek text route and
the managed OpenCode runtime with a DeepSeek model, both 2026-10-30.

