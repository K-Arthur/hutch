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

## The Models page (`/models`)

The "everything" view behind the switcher: runtimes and connections with state and fix, installed models marked
**fits / tight / won't fit** at 16k and 32k context, what each task preset resolves to on this machine (with the
install command when it is missing), measured swap costs, and the hosted price table.

`hutch models list` and `hutch models presets` print the same data in the terminal.

Fit is **arithmetic, not a benchmark**: weights plus KV cache against the memory budget, using the runtime's own
architecture numbers once a model is installed and catalog estimates before. It does not predict speed.

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
This is a profile of one model on one machine, not a leaderboard score. It has been exercised only against scripted
models; run it on your own installed models to get real numbers.

## Tool calling modes and compatibility

Every Bot's tools are compiled into one per-run plan before the first model call, and the
plan is recorded in the transcript (`tool_protocol` entries with catalog/plan hashes and
field-level diagnostics). The default is **auto**: Hutch uses the provider's own tool
protocol exactly as before and never silently switches modes.

| Mode | What it means |
|---|---|
| `auto` / `native` | The provider's own function-tool protocol (OpenAI Chat Completions, Anthropic Messages, Ollama native, llama.cpp/vLLM when the server has tool parsing enabled). Best-effort call shaping; every call is still validated locally. |
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
cache fit remain estimates, not an OOM guarantee. Other local protocols have queue limits but
lack validated memory admission. No real model was exercised here.

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
- **Not verified on real models.** The development machine has about 3 GiB free and no Ollama, so swap latency,
  cold-load times and context self-check results on real local models have not been measured. The pages and commands
  report "not measured" rather than showing numbers that were not.
