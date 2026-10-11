# Dynamic workflows

A **workflow** is a saved, reviewable plan that Hutch can execute step by step: discover
inputs, branch on what it finds, hand bounded pieces of work to a model or a tool, check the
result against real evidence, and publish what it produced. It is *not* a routine (a routine
decides **when** saved work is invoked), not a skill (a skill teaches a method to a model),
and not an MCP server (which exposes operations). The workflow engine owns execution state.

Workflows are optional and off by default. Nothing here starts on its own.

## What a workflow is

A plan is data, not code. It declares:

* **inputs** with types, bounds and defaults;
* an **envelope** - which tools, models and skills the plan may use, and whether it must
  stay on local models;
* a **budget** - node instances, model calls, wall clock, fan-out, repair rounds;
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
| `off` (default) | nothing; you can still run a saved workflow yourself |
| `suggest` | describe a candidate route and its bounds in the conversation; starting it stays your action |
| `auto` | start a workflow without a fresh confirmation, but only inside the scope you preauthorized in Bot settings |

`auto` needs an explicit scope: which saved definitions it may start and the maximum nodes,
model calls, wall clock and fan-out. Anything outside that scope is refused with the reason.
Consequential actions inside a run still use their own approval boundaries - permission to
choose a method is never permission to spend, access or mutate.

**Status:** the policy, the recommendation rules and the auto-scope check are implemented and
tested, and the *enforcement* runs on any submission that declares itself automatic. The
conversation-side wiring - a chat turn that offers a suggestion or starts an auto workflow -
is **not implemented in this revision**; today a person starts a workflow explicitly with
`hutch workflow run` or the API. Nothing can start one by accident.

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
```

A model may draft a plan only when its route is qualified for the **author** role (probed
evidence on that exact route revision), and only through the `draft_workflow` tool, which
validates and explains but never starts anything. A person then reviews and runs it.

Importing a definition starts it **inactive**; running it and scheduling it are separate
actions, and saving never grants a schedule or wider permissions.

## Roles and qualification

A model is not "workflow-capable" in general. Each role is qualified separately, per exact
route revision, with its own evidence:

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

Qualifications are keyed to the exact route identity (connection, endpoint, protocol,
template, quantization, backend). Change any of those and the old record simply stops
matching - nothing is silently re-validated.

## Verification

`verify` nodes need at least one **independent** check: a JSON schema over a value, an
artifact read-back that re-hashes the recorded bytes, a fixed-argv command with an expected
exit code, or a person's answer to a durable question. A model review (`agent_review`) is
advisory by construction: it can fail a result or send it to repair, never certify it.

`on_fail` is explicit: `stop`, `continue` (recording the result as unverified), or `repair`
with a bounded number of rounds.

## Bounds, waiting and stopping

* Budgets are root-level: node instances, model calls, wall clock, fan-out and repairs.
  Retries and children cannot reset them, and a fan-out over more items than allowed fails
  loudly instead of returning a partial view.
* Every wait expires. A question has its own id, answer and deadline; an unanswered
  question is never treated as consent.
* Workflow model steps are ordinary Hutch runs: same approval gate, same receipts, same
  artifacts, same transcripts. They run in a workflow lane, so a workflow can progress while
  you keep chatting with the same Bot, and one workflow per Bot runs at a time.
* Model steps use fresh private workspaces; delivery happens by publishing artifacts, never
  by writing into the Bot's shared workspace.
* `stop` is durable: it cancels the owned work and prevents any continuation.

## What is not implemented yet

* **No live local-model evidence.** The deterministic path (tools, transforms, verification,
  artifacts, questions) is verified end to end. Model-authored plans and planner/worker role
  splits are implemented and gated but were not exercised against a real local checkpoint on
  the development host, which has no model server installed.
* **No workflow surface in Studio yet.** The API and CLI are complete; the plan/graph view,
  mode selection and inline question cards are a later slice.
* No MCP facade (Hutch has no MCP plane), no code facade, no scheduling of workflows, and no
  automatic downloads or model substitution.
