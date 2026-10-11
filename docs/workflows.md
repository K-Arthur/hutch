# Dynamic workflows

A **workflow** is a saved, reviewable plan that Hutch can execute step by step: discover
inputs, branch on what it finds, hand bounded pieces of work to a model or a tool, check the
result against real evidence, and publish what it produced. It is *not* a routine (a routine
decides **when** saved work is invoked), not a skill (a skill teaches a method to a model),
and not an MCP server (which exposes operations). The workflow engine owns execution state.

Workflows are optional. New assistants start in **Suggest**; schema v57 preserves the former
Off behavior for existing assistants whose saved record did not contain a mode, and schema v58
adds archived amendment history. When the
current chat model is selector-qualified for its exact execution profile, Suggest can return
a compact route card during the ordinary model/tool turn. Simple requests do not get a separate
classifier call, and Suggest never starts work. Auto can start only an activated saved definition
inside the Bot's explicit workflow and budget limits; consequential actions still need their own
approval.

Workflows are in private preview. The owner can start a reviewed saved workflow from Studio,
the API or CLI. Chat recommendations and Auto saved-workflow launch now use an exact-profile
selector gate, but neither Qwen3 local profile tested in the bounded campaign qualified, so those
paths are blocked for the tested checkpoints. Auto does not start a newly generated plan, and
scheduled routine links are not connected. The public website describes these limits; it does
not imply a public download or a currently qualified local selector.

## What a workflow is

A plan is data, not code. It declares:

* **inputs** with types, bounds and defaults;
* an **envelope** - which tools, models and skills the plan may use, and whether it must
  stay on local models;
* a **budget** - node instances, actual provider requests, reported/reserved tokens, wall clock,
  fan-out and repair rounds;
* **nodes** connected by explicit references, and the **outputs** worth publishing.

Node kinds: deterministic transforms (`transform`), governed tool calls (`tool`), model
steps (`agent`), bounded fan-out (`map`/`expand`), branches (`branch`), bounded loops
(`repeat`), joins with an explicit policy (`join`), verification (`verify`), durable
questions (`ask`) and artifact publication (`publish`).

Because a plan is data it can be validated, diffed, saved, exported, replayed and reviewed.
Hutch never executes generated code: there is no script sandbox to escape.

## Modes: off, suggest, auto

| Mode | What Hutch may do |
|---|---|
| `off` | Hutch does not recommend or automatically start a workflow; you can still run a saved workflow yourself |
| `suggest` | an exact-profile qualified selector may describe a candidate route and its bounds in the conversation; starting it stays your action |
| `auto` | an exact-profile qualified selector may start a matching activated saved workflow inside the scope you preauthorized in Bot settings |

Set the policy per Bot; saving it starts nothing:

```bash
hutch workflow mode research-bot --mode suggest
hutch workflow mode research-bot --mode auto --allow-definition weekly-report \
    --max-nodes 40 --max-model-calls 5 --max-tokens 64000 \
    --max-wall-seconds 900 --max-fanout 8
```

`auto` needs an explicit scope: which saved definitions it may start and the maximum nodes,
actual model requests, tokens, wall clock and fan-out. Anything outside that scope is refused
with the reason. New plans default to at most 40 node instances, 12 requests, 64,000 tokens,
900 seconds, fan-out 8 and two repair rounds. The envelope defaults to two logical workers;
local inference still sends one request at a time.
Consequential actions inside a run still use their own approval boundaries - permission to
choose a method is never permission to spend, access or mutate.

Auto scope names only existing activated definitions and has explicit limits for nodes, actual
model requests, tokens, wall time and fan-out. A chat launch is idempotent and rechecks the
conversation mode, exact selector profile, saved definition, role assignments and scope at the
point of admission. Required inputs must validate before work is admitted. Role checks and the current Bot's tools,
integrations and data boundaries are checked again at admission. A conversation-level override
is an additional, narrower choice; setting Auto for one chat cannot create or widen the Bot-level
scope. The local-owner-only API is
`GET/POST /api/v1/workflows/conversations/{conversation_id}/policy`; mutations carry an
`Idempotency-Key` and `expected_revision`. `inherit` uses the Bot setting, and stale revisions
are rejected. Paired phones do not receive planning, policy, probe, amendment or launch controls.

**Status:** the policy, recommendation rules, revisioned per-conversation override, chat route
tool, and idempotent Auto launch for scoped saved definitions are implemented. The runtime offers
the tool only when the active model passes the exact-profile selector gate; unqualified models do
not receive it. Scripted runtime/API regressions and the Studio review-card browser test pass.
Both local Qwen3 profiles tested on 2026-10-11 failed selector qualification, so live chat routing
is blocked for those checkpoints. Chat Auto for newly generated plans remains unsupported; changing
a conversation policy starts nothing.

## Running a saved workflow

```bash
hutch workflow list                                   # saved methods (inert until run)
hutch workflow show weekly-report                      # the plan and its bounded structure
hutch workflow validate plan.json --bot research-bot   # compile + authority check, runs nothing
hutch workflow run weekly-report --bot research-bot --input week=2026-W41
hutch workflow status wrun_…                           # instance, nodes, pending questions
hutch workflow stop wrun_…                             # durable stop; no continuation starts
hutch workflow answer wq_… "yes"                       # answer one pending question by its id
```

Running a saved workflow makes **no planning call**: the plan is fixed, and every model step
must already have a qualified role binding.

## Authoring

Write a plan as JSON and save it:

```bash
hutch workflow validate my-plan.json --bot research-bot
hutch workflow save my-plan.json --name my-plan --note "reviewed 2026-10-11"
hutch workflow submit my-plan.json --bot research-bot   # validate + save + run, and wait
hutch workflow export my-plan --out reviewed-plan.json # review the exact committed plan
```

A model may draft a plan only when its route is qualified for the **author** role (probed
evidence on that exact route revision), and only through the `draft_workflow` tool, which
validates and explains but never starts anything. A person then reviews and runs it.

Importing a definition starts it **inactive**; running it and scheduling it are separate
actions, and saving never grants a schedule or wider permissions.

## Roles and qualification

A model is not "workflow-capable" in general. Each role is qualified separately, per exact
route revision and execution profile, with its own evidence. The profile distinguishes the
serving backend/version, checkpoint digest where available, quantization, chat template,
tokenizer, protocol/parser, effective context, decoding settings and reported modalities.
It contains no credential or resource-readiness state. For Ollama, `/api/tags` and `/api/show`
provide the installed digest and model metadata; missing identity fields are reported as
incomplete instead of guessed. These fields now participate in compiler identity, so changing
one cannot silently reuse a plan compiled for another execution setup. Qualification records
are bound to that exact profile. A passing author or selector probe applies only to the same
backend build, checkpoint, quantization, template, tokenizer, protocol/parser, context, decoding
settings and modalities. A profile change blocks the role until it has new held-out evidence.

| Role | Qualification |
|---|---|
| selector | matches an eligible saved method or abstains (probed evidence) |
| author / replanner | produces valid bounded plans across held-out scenarios (probed evidence) |
| bounded worker | performs its particular step with validated output; a text-only model can still be a no-tools worker |
| verifier | checks a criterion with independent evidence; a same-route reviewer is advisory only |
| deterministic executor | application-owned; needs no model at all |

Evidence states are `documented`, `advertised`, `probed`, `observed`, `limited`,
`unsupported`, `stale` and `unknown`. A **negative** state blocks the capability; unknown or
advertised states are allowed with a recorded caveat. Authoring and selection require probed
evidence and cannot be unlocked by an operator acknowledgement.

```bash
hutch workflow qualify research-bot --assess --role worker
hutch workflow qualify research-bot --role worker --reason "local extraction only"
hutch workflow qualify research-bot --revoke --role worker
```

The built-in probe runner is deliberately narrow: it uses four harmless, held-out JSON cases
for each role, only against a loopback Ollama 0.40.3 endpoint and an installed Q4_K_M checkpoint
with a complete identity profile. It uses 4,096 context, the normal local 2,048-token turn cap,
streaming with thinking disabled, and verifies after every response that exactly one model is
resident with no VRAM use. It checks current memory headroom before each request and does not
start a load when the candidate no longer fits. Each request stores the measured RAM,
resident-model bytes, fit estimate and effective context before and after inference; these
snapshots describe this machine at that moment and are not a general hardware guarantee. It
sends no tools, user data, or hosted fallback. Its durable campaign ledger caps all runs together at 80 requests, 60,000
estimated/reported tokens and two hours;
an uncertain dispatch keeps its reservation and blocks another probe until reconciled. A
timeout or incomplete sample is inconclusive and never grants authority. A complete failed
suite records negative evidence for that exact profile.

```bash
hutch workflow qualify local-planner --probe --role author
hutch workflow qualify local-planner --probe --role selector --campaign dynamic-workflows-initial
hutch workflow qualify local-planner --assess --role author
```

The probe command and `POST /api/v1/workflows/qualifications/probe` are local-owner operations.
After a passing probe, authoring/selection is available only to turns that report the exact
same execution-profile fingerprint. For the initial probe profile, configure the Bot's model
context to 4,096; the default local output cap is 2,048 tokens. No acknowledgement creates
author or selector qualification. These initial probe limits do not qualify other settings.

## Verification

`verify` nodes need at least one **independent** check: a JSON schema over a value, an
artifact read-back that re-hashes the recorded bytes, a fixed-argv command with an expected
exit code, or a person's answer to a durable question. A model review (`agent_review`) is
advisory by construction: it can fail a result or send it to repair, never certify it.

`on_fail` is explicit: `stop`, `continue` (recording the result as unverified), or `repair`
with a bounded number of rounds. A repair policy identifies the earlier node value to replace
with `adopt`; that node must be in the same scope and referenced by a verification check. For
backward compatibility, a plan can omit `adopt` only when its checks identify exactly one prior
node. Ambiguous plans are rejected before admission.

Each repair worker must return one JSON object shaped like `{"replacement": ...}`. Hutch validates
that closed output contract, adopts the complete replacement value, and reruns the independent
checks in a new durable verification round. Reusing a completed child after recovery does not
dispatch it again, and its saved replacement is applied again before a recheck. A replacement equal
to the current value fails with a no-progress reason; repair rounds and model requests stay inside
the original root budget. This execution path is covered with a scripted local route, but repair
quality from a live model has not been verified.

## Joins and output status

`all_required` fails when a named result failed or was skipped. `all_settled` waits until
its named earlier nodes settle, keeps successful values in `items`, and lists failed,
skipped and missing targets separately. `complete` means every target produced a value;
`accepted` reports whether the optional `require` threshold was met. A failed node is
allowed to pass through only when an `all_settled` join names it; unrelated failures still
fail the workflow. This interpreter currently visits ordinary nodes sequentially.

`first_success` is rejected during compilation. It promises the first acceptable completion
and requires canceling and draining work that lost the race; selecting the first successful
node after sequential execution would make a weaker promise. That policy remains unsupported
until the scheduler can provide those guarantees.

The terminal workflow result keeps node-state `counts` separate from `output_outcomes`.
Declared top-level outputs are grouped as `verified`, `partial`, `skipped`, `failed`, or
`uncertain`. A direct independent check of the output can establish `verified`; checking only
a nested field does not certify the whole output. Incomplete maps and joins remain `partial`
even when a schema check passes. Outcome groups identify durable node records; their values
remain in those records, so large artifacts are not duplicated into the summary.

## Bounds, waiting and stopping

* Budgets are root-level: node instances, provider requests, tokens, wall clock, fan-out and
  repairs. The request counter is charged at the durable provider-dispatch boundary, so each
  retry, uncached local context self-check and child step consumes the same allowance. Reported
  tokens replace an estimate after settlement; unresolved requests keep their estimate held.
  A request that never crossed the dispatch boundary releases its reservation. A fan-out over
  its bound fails loudly.
* Every wait expires. A question has its own id, answer and deadline; an unanswered
  question is never treated as consent.
* Workflow model steps are ordinary Hutch runs: same approval gate, same receipts, same
  artifacts, same transcripts. They run in a workflow lane, so a workflow can progress while
  you keep chatting with the same Bot, and one workflow per Bot runs at a time.
* Model steps use fresh private workspaces; delivery happens by publishing artifacts, never
  by writing into the Bot's shared workspace.
* `stop` is durable: it cancels the owned work and prevents any continuation.

When a workflow needs a person or a child step, Hutch commits the pending question and the
workflow's waiting status together, then parks the orchestration attempt and releases its run
slot. The workflow remains visible as waiting, not successful. An answer or settled child lets
the supervisor admit a fresh attempt; settled node records are reused.
Stopping a parked workflow cancels its pending questions and owned child work, and it remains
visible until cleanup is verified.
Stopping while a model step is active also cancels the step run. The process-executor
regression verifies that both the step and orchestration attempt settle as stopped, and that
their owned process records are closed before the workflow becomes terminal.
The scripted local model-server test and recorded source hashes are listed in the
[A1 workflow acceptance evidence](realignment/dynamic-workflows.md#a1).

Effect receipts use a stable workflow revision/site/instance/slot identity. If a process
crashes after an effect is recorded but before its node settles, Hutch reuses the stored result
without dispatching the effect again. If the receipt is uncertain, Hutch blocks retry until
the action is reconciled; an operator's “not applied” finding is required before another
attempt can run.

## What is not implemented yet

* **Local author/selector probes are implemented, but the tested checkpoints are blocked.**
  On 2026-10-11, the bounded held-out campaign tested Qwen3 1.7B and 4B Q4_K_M on CPU at
  4,096 context. Both exact profiles failed at least one required author and selector case;
  neither model can author or select production workflows. See the retained negative evidence
  in [`qualification-campaign-2026-10-11.json`](realignment/artifacts/dynamic-workflows/qualification-campaign-2026-10-11.json).
* **Studio now has a workflow card for the selected conversation.** It separates planned
  structure from discovered instances, labels completed versus verified work, lists pending
  questions by durable ID, accepts an answer for that question, starts a saved workflow after
  you choose it, and sends a revision-checked Stop. The conversation options menu stores a
  revisioned Off/Suggest/Auto override; Auto is unavailable until the assistant has an
  activated definition and explicit limits. These controls do not run a planner or start work
  when you change policy.
* **Chat routing is implemented behind an exact-profile selector gate.** During the ordinary
  chat model/tool turn, an eligible selector can return a review-only suggestion or start a
  matching activated saved workflow under Auto. The two local Qwen3 profiles tested failed
  selector qualification, so neither receives the selector. Auto does not create a new plan;
  a qualified selector profile has not been verified locally.
* **Paired-phone workflow supervision is implemented as a redacted monitor/review view.** A
  paired session with `monitor` can list workflow runs and inspect planned steps plus
  question-backed or recorded instance statuses. It does not receive workflow inputs,
  results, artifacts, usage ledgers, or expansion keys. A session with `review` can see each
  pending durable question ID and answer that question, or request Stop against the current
  revision; both mutations carry the paired session's CSRF token and an idempotency key.
  Planning, workflow launch, probes, policy changes, and amendments remain local-owner-only.
  Monitor-only sessions do not load review data or show review controls. Browser evidence at
  390 and 320 CSS pixels and the route authorization/redaction regressions are recorded in
  [`artifacts/workflow-studio/phone/`](realignment/artifacts/workflow-studio/phone/).
* No MCP facade (Hutch has no MCP plane), no code facade, and no automatic downloads or
  model substitution.
* **No scheduling of workflows yet.** A routine decides *when* saved work runs; wiring a
  routine to a saved workflow is a separate, explicit act that is not implemented, so a
  workflow cannot currently run unattended on a schedule.
* **Amendment preview and a constrained adoption API exist.** The local-owner API
  `POST /api/v1/workflows/runs/{id}/amendments/preview` takes an expected immutable revision,
  the current attempt ID as an opaque generation token, a candidate plan and optional new input
  snapshot. It returns a field/site diff, current authority verdicts, budget limits, quiescence
  facts, and per-instance reuse or invalidation reasons without saving a revision or mutating
  the run. Its `eligible` flag covers authority and budget checks only; the preview separately reports
  whether the attempt released its owner lease and whether its owned child/process tree is quiet. Reuse is limited to settled pure transforms
  when inputs, capability envelope, node semantics and dependencies remain unchanged, and every
  upstream result is also safe to reuse. Tool, model, verification, publication, question and
  control/container results are invalidated because binding/evidence or nested-output provenance
  is not yet sufficient to prove reuse. A preview also refuses a wider root budget.
  `POST /api/v1/workflows/runs/{id}/amendments/adopt` requires an idempotency key and the same
  revision/generation compare. It only adopts a parked run after child work and owned processes
  have settled. Active children are never killed by adoption. Pending human questions require the
  explicit `cancel_pending_questions` choice; old question IDs and result records are archived
  before continuation. The old owner is fenced by the new revision, and any subsequent ask gets a
  fresh identity. `GET /api/v1/workflows/runs/{id}/amendments` lists adoption history and
  `GET /api/v1/workflows/runs/{id}/amendments/{history_id}` exposes the archived graph/results.
  The owner-local Studio card offers a declarative plan/input editor, read-only preview with
  authority, budget, quiescence, diff and reuse sections, and an explicit adoption action. It
  requires a pending-question cancellation checkbox when relevant, and falls back to the composer
  for focus while the new revision is running. Live-run draining and safe reuse beyond pure
  transforms remain unavailable. Terminal-run amendment adoption is intentionally unsupported:
  the API returns 409 and leaves the terminal result intact; start a new run from the saved definition.
