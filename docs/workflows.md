# Dynamic workflows

A **workflow** is a saved, reviewable plan that Hutch can execute step by step: discover
inputs, branch on what it finds, hand bounded pieces of work to a model or a tool, check the
result against real evidence, and publish what it produced. It is *not* a routine (a routine
decides **when** saved work is invoked), not a skill (a skill teaches a method to a model),
and not an MCP server (which exposes operations). The workflow engine owns execution state.

Workflows are optional. New assistants start in **Suggest**; schema v57 preserves the former
Off behavior for existing assistants whose saved record did not contain a mode. Suggest may
point out a workflow-shaped route but does not start it. Auto requires an activated saved
definition, explicit workflow and budget limits, and separate action approval where required.

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
| `suggest` | describe a candidate route and its bounds in the conversation; starting it stays your action |
| `auto` | start a workflow without a fresh confirmation, but only inside the scope you preauthorized in Bot settings |

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
model requests, tokens, wall time and fan-out. Role checks and the current Bot's tools,
integrations and data boundaries are checked again at admission. A conversation-level override
is an additional, narrower choice; setting Auto for one chat cannot create or widen the Bot-level
scope. The local-owner-only API is
`GET/POST /api/v1/workflows/conversations/{conversation_id}/policy`; mutations carry an
`Idempotency-Key` and `expected_revision`. `inherit` uses the Bot setting, and stale revisions
are rejected. Paired phones do not receive planning, policy, probe, amendment or launch controls.

**Status:** the policy, recommendation rules, revisioned per-conversation override, and explicit
Bot Auto scope checks are implemented and tested. A chat turn that offers a suggested plan or
starts a scoped Auto workflow is still **not implemented**; today a person starts one explicitly
with `hutch workflow run` or the API. Changing a conversation policy starts nothing.

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
with a bounded number of rounds.

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

When a workflow needs a person or a child step, Hutch parks the orchestration attempt durably
and releases its run slot. The workflow remains visible as waiting, not successful. An answer
or settled child lets the supervisor admit a fresh attempt; settled node records are reused.
Stopping a parked workflow cancels its pending questions and owned child work, and it remains
visible until cleanup is verified.

Effect receipts use a stable workflow revision/site/instance/slot identity. If a process
crashes after an effect is recorded but before its node settles, Hutch reuses the stored result
without dispatching the effect again. If the receipt is uncertain, Hutch blocks retry until
the action is reconciled; an operator's “not applied” finding is required before another
attempt can run.

## What is not implemented yet

* **Live local-model evidence remains candidate-specific.** The bounded probe path is
  implemented and tested against a fixture server. A checkpoint is qualified only after a
  real campaign is run and its evidence is committed; an installed model or passing fixture
  is not qualification.
* **No workflow surface in Studio yet.** The API and CLI are complete; the plan/graph view,
  mode selection and inline question cards are a later slice.
* No MCP facade (Hutch has no MCP plane), no code facade, and no automatic downloads or
  model substitution.
* **No scheduling of workflows yet.** A routine decides *when* saved work runs; wiring a
  routine to a saved workflow is a separate, explicit act that is not implemented, so a
  workflow cannot currently run unattended on a schedule.
* **No amendment of a running instance.** A crashed attempt is continued and reuses its
  settled nodes, but changing the plan of a live instance (a revision diff and adoption) is
  not implemented; edit the definition and run the new revision instead.
