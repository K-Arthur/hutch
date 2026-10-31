# Frontend truthfulness and platform lifecycle: owner report, root causes, correction plan

Written 2026-10-30 after the owner reviewed the **real** running app (existing state directory) and rejected
the earlier "complete" claim. Status: plan; implementation follows in slices. Nothing here deletes or
rewrites the owner's data automatically; Hutch repairs its own state through reviewed UI actions, startup
reconciliation and `hutch doctor`.

## 1. What the owner reported

1. **Activity** shows `1 working` at the top while the only "Working now" item is
   *Tidy Downloads — Stopping, 23d ago*. Nothing is actually running, and **Stop all** is offered for it.
2. **Needs you** contains *Research Briefing — Failed* with the error "The mock runtime was removed. Select
   a configured Ollama, OpenAI, Anthropic, or compatible model route." and a *Schedule check — Needs a look
   (23d ago)*. These are legacy/demo-era rows presented as live work.
3. The sidebar lists assistants the owner never created: **Design Partner, Repo Sweeper, Research Briefing,
   Tidy Downloads** — leftovers from earlier demo-era versions.
4. **Chat** for Design Partner shows a model chip labelled **"demo"**, the roster line says **Idle**, and
   the welcome still offers **"Create a helper from an example"**.
5. "The frontend doesn't do the onboarding or have a way of recognizing it on a new device."
6. "Other pages like the models page don't even make sense on how it would work with such a platform."
7. Conclusion the owner drew, and the standard for this plan: the earlier completion was verified on fresh
   scratch state and never reconciled a real, legacy installation. That was not enough.

## 2. Verified reproduction and root causes (current `main`)

A scratch-state reproduction (never the owner's state directory) is in
`.dsh/long-horizon/hutch-frontend-truth/artifacts/repro-legacy-state.json` with screenshots
`repro-legacy-chat-1440.png` and `repro-activity-now-1440.png`.

### 2.1 Truthful route status has a shape hole (R1)

`route_problem.py` flags only "no model" and a retired `mock/` route. A stored model that cannot possibly
run but is not shaped like a route — for example `demo` with no provider slash — returns `None`. The
roster then reads "Idle", the picker shows the raw last segment ("demo"), and the failure only appears when
a message is sent (`validate_override` says "'demo' is not a model spec"). Old demo-era rows can be in
exactly this state. Fix: route truth must mirror the execution validator's *shape* rules (provider/model
with non-empty parts, known runtime, retired runtimes) so no unusable assistant can read "Idle".

### 2.2 Ghost live runs can never be reconciled (R2)

Recovery considers two sets only:
- `store.expired_runs()` — live rows with `lease_expires_at IS NOT NULL` in the past;
- `store.legacy_live_runs()` — live rows with `lease_expires_at IS NULL AND fence = 0`.

A row with `lease_expires_at IS NULL AND fence > 0` (claimed by a pre-lease or crashed supervisor, never
heartbeated again) is in **neither** set. It stays live forever: it counts in `working_runs`, shows
"Stopping" in the roster and "N working" in the header, and blocks that assistant from running again. The
23-day-old row in the screenshot is consistent with this hole. Fix: a single reconciliation query for
live rows whose ownership evidence is missing or lapsed beyond a grace period (including NULL-lease rows at
any fence), plus a doctor finding; `working_runs` must count only rows with current ownership evidence.

### 2.3 Legacy/demo history is presented as live human work (R3)

`views.home_state` puts the latest failed run per assistant inside the 7-day window into `failures`,
which `needs_count` treats as "needs you". There is no legacy classification: a failure caused by a removed
demo runtime is shown like a current problem with "Open the transcript for the failing step", and its error
text is double-prefixed ("The run ended with an error: The run ended with an error: …"). Fix: classify
runs as **legacy** when the assistant's route is retired/unusable or the recorded error names a removed
runtime; keep them in History (labeled) and in the installation review, but out of "Needs you"; fix the
double prefix.

### 2.4 No installation review, onboarding continuity, or device recognition (R4)

The first-run page appears only for an empty state. A non-empty installation — especially one with
demo-era rows — has no "review this installation" step, no record of a completed review, and no
per-device "welcome back / set up this device" state. The product cannot distinguish "fresh install",
"legacy install that needs review", and "another browser/device on a known install". Fix: a small
server-side installation state machine + review surface + per-device welcome, described in §3.1.

### 2.5 The example gallery is still in the chat welcome (R5)

`welcomeHtml()` still renders the `tpl-gal` "Create a helper from an example" block and `wireWelcome()`
still fetches templates for it. The catalog destination now exists; the gallery should be removed and
replaced by a single link to Catalog.

### 2.6 Models page does not answer the platform's question (R6)

The page leads with hardware capability, then saved routes and pricing. For this product the first
question is *"which AI service can run my assistants now, and which route does each assistant use?"* — the
provider/services view, assistant routing matrix and defaults. Hardware fit and per-token pricing are
secondary and partly belong to Usage. §3.6 gives the target information architecture.

## 3. Target model

### 3.1 Installation lifecycle and onboarding

States (computed, stored in `kv` as `installation:state` once reviewed):

- **fresh** — no assistants, no usable route, first-run setup not completed → existing first-run onboarding.
- **needs_review** — assistants/runs exist but at least one installation issue is open (legacy assistant
  with retired/malformed route, ghost live run, legacy demo failure, no usable route). The app shows a
  **Review this installation** surface on first load of any session/device until it is reviewed.
- **ready** — no open issues; review recorded with the issue count and a revision.

New device/browser: if the install is `ready` and this device has not been welcomed, show a one-time
**Welcome back to this Hutch** screen with *Continue to this Hutch* and a link to pairing/settings. If the
install is `needs_review`, the review is the welcome. Device identity uses the existing session/device
machinery; no new secrets.

Review actions are the existing governed ones — choose a model route in assistant settings, remove an
assistant through whole-assistant deletion — plus "Keep, it can run now" when a route becomes usable. No
automatic deletion, no silent rewriting of assistant records, and no state-directory access by the app
beyond its normal store.

### 3.2 Assistant lifecycle (read model)

- **usable** — runnable route today.
- **needs_model** — no route, malformed route, or retired runtime; roster says "Needs a model route", the
  composer chip says "Choose a model", and the installation review lists it.
- **legacy_preview** — created by an older demo-era version (creation source/route provenance unknown or
  retired). It is surfaced in the review with provenance and a keep/removal choice; it never shows "Idle".
- **paused** — unchanged.

### 3.3 Run lifecycle

- **live** — live status *and* current ownership evidence (this supervisor's thread or a live lease with a
  heartbeat). Only these count in `working_runs`, drive "N working" and Stop all.
- **ghost** — live status with missing/lapsed ownership evidence beyond the grace period → reconciled by
  the supervisor and reported by `hutch doctor`: `cancelling`→stopped/cancelled, otherwise
  interrupted/outcome_unknown.
- **legacy** — finished run whose assistant route is retired/malformed or whose error names a removed
  runtime. Computed on read; shown in History with a label, counted in the installation review, excluded
  from "Needs you".

### 3.4 Activity information architecture

- **Now**: working runs (live with evidence) and the installation-review card when there are issues.
- **Needs you**: approvals, human waits, and failures of runnable assistants inside the current window —
  never legacy/demo failures.
- **History**: all runs, with a "Legacy" badge and one-line reason for legacy runs; scheduled checks stay
  under their own card only when their assistant can run.

### 3.5 Chat welcome

Remove the example gallery markup, wiring and CSS. The welcome keeps the real facts (approval summary,
"Can use …") and the first-request guidance, and links to Catalog for ready-made assistants. No canned
examples, no invented starter prompts.

### 3.6 Models page target information architecture

Rebuild the page top-down around the one question that matters:

1. **Can work happen now?** Service status cards: detected OpenCode profile (free models available, no
   account needed), connected providers, local runtimes — each with state, route count and one action
   ("Use this service", "Connect", "Repair").
2. **Routes available**: searchable list grouped by service with runtime tag (on this machine / leaves this
   machine), context and output limits, price note, and a "used by" assistant count.
3. **Assistant routing**: one row per assistant — default route, runtime, inference mode, fallbacks and
   escalation summary, health (usable / needs model) — with a direct action to fix.
4. **Defaults**: the workspace route used for new assistants (already implemented; give it one clear home).
5. **Secondary**: hardware capability and the token price table move under a "Hardware and prices" detail
   (and link to Usage). Connections remains the only place keys/accounts are managed; Models links there
   instead of duplicating it.

Acceptance: above the fold answers "which service is ready and which assistant uses what"; every control
maps to an existing endpoint; screenshots at 1440/900/360; no dead or decorative control.

## 4. Implementation slices

| Slice | Scope | Size | Acceptance |
|---|---|---|---|
| S1 | Route truth: mirror execution shape validation in `route_problem`; roster/chip/settings/review copy; tests for empty, `demo`, `mock/demo`, retired runtime, valid routes | S | unit + browser: no unusable assistant can read Idle; picker never shows a raw malformed label as usable |
| S2 | Ghost-run reconciliation: one query for lapsed/missing ownership evidence incl. NULL lease at any fence; supervisor + doctor; `working_runs` evidence rule; tests seeding 23d variants | M | seeded 23d cancelling ghosts become stopped/interrupted; `/api/stats.working_runs == 0`; header/Stop all absent; doctor reports before recovery |
| S3 | Installation review + lifecycle + new-device welcome; server module/API/marker; SPA review surface and routing; browser tests | M | legacy state shows review on first load; actions work; marker recorded; new device welcome once; fresh install still gets first-run |
| S4 | Remove example gallery; welcome links to Catalog; guard test | S | markup/handlers/CSS gone; test bans the phrase; e2e asserts the link |
| S5 | Legacy run classification in `home_state`/API/Activity; error-prefix fix | S | legacy failures out of Needs you, labeled in History, counted in review; no double prefix |
| S6 | Models page redesign per §3.6 | M | tests + screenshots; route/assistant semantics; no duplicate Connections controls |
| S7 | Gates: check:agent, focused unit + browser suites, docs/slice log, independent verifier | M | verifier PASS per row |

Order: S1 → S2 → S5 → S3 → S4 → S6 → S7 (S4 can land with S3). Each slice ends committed, tested and
recorded in the slice log; nothing is auto-deleted.

## 5. Non-goals and guardrails

- The product never reads or rewrites the owner's state directory outside its normal store/doctor paths;
  this work is verified on scratch state and by the owner running the updated build on their install.
- No automatic deletion of assistants, runs, memory or files. Review actions are explicit and governed.
- No new provider accounts, no paid model spend in tests; live-route checks stay on free OpenCode models
  where needed.
- No demo or fixture content may be re-added to product source; guards grow, not relax.
- Proposals/delegation (A2/A3/A6), marketplace publishing and distribution stay out of scope for this plan.

## 6. Open decisions for the owner (defaults chosen, say otherwise)

1. Legacy assistants default to **keep until reviewed**, with removal one explicit action — default keep.
2. Legacy demo-era runs stay in History with a Legacy badge; they are not deleted automatically — default keep.
3. Installation review appears once per installation after review; every new device/browser gets a one-time
   "Welcome back" screen until it is acknowledged — default yes.
4. Models page: services/routes/assistants first, hardware and prices secondary — default yes.
