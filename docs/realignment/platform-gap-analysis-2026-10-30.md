# From preview to a real platform: what Hutch is missing (2026-10-30)

Status: analysis and plan, written at the end of the release-readiness run after the owner said the app is
"not yet a real functioning platform" and that demo-looking behaviour (model picker, "Working" labels,
presets) still shows on the front end. Everything under "Verified in this tree" was read or run in this
repository. Everything about other projects is labelled **primary** (their own docs or README, fetched
2026-10-30), **secondary** (third-party write-ups) or **unverified** (directory listings). Nothing here claims a
live-model result.

## 1. What the owner described

1. One orchestrator, named by the person at onboarding, that can create other assistants, or the person creates
   them manually.
2. Ready-made presets are fine but belong in an agent store (as in Grok Bot), not shipped as built-ins.
3. No demos and no fixtures anywhere in the product.

## 2. Verified in this tree

### 2.1 Demo-looking or fixture-derived items still in the product

| Item | Where | Why it reads as demo | State after this run |
|---|---|---|---|
| An assistant stuck on "Working" | roster label is "any run in a live status" (`app.js` `rosterStatus`, `store.active_runs_by_bot`) | rows that nothing owns (no pid, no lease) were never recovered, so they showed Working forever; leftover starter assistants look exactly like this | **Fixed** (`1683156e`): the supervisor and `hutch doctor` recover live rows that nothing owns after a 5-minute grace. Not seen on a real state directory (off limits); the owner should run `hutch runs`, restart `hutch serve`, and expect old rows to become failed-interrupted |
| An assistant on the retired `mock/` route looks healthy | roster "Idle", composer chip "demo", picker lists it as default | the engine refuses the route only when a message is sent | **Fixed** (`2b8cad03`): server `route_problem`; roster says "Needs a model route", chip says "Choose a model" |
| Eight built-in assistant presets | `src/hutch/templates.py` (`personal-assistant`, `day-planner`, `inbox-followups`, `research-decisions`, `project-coordinator`, `meeting-followthrough`, `document-workbench`, `data-brief`), offered in assistant setup ("Choose a starting point") and the "Create a helper from an example" gallery | shipped as code constants, shown as if they were the product | **Open**: needs a catalog (section 5, B) |
| Canned prompt cards | `app.js` "Plan my week", "Draft a message", "Create a helper from an example"; first-run "Plan my week / Catch up on email / Organize a project" | invented activity the person did not ask for | **Open**: remove or generate from the person's connected apps |
| Leftover `mock` handling | `app.js` workspace-default guard, "Retired mock" runtime label; picker `LOCAL_RUNTIMES` includes `mock`; `RuntimeKind.mock` | the runtime was removed but its ghosts remain | **Partly removed**; the rest needs a data migration (C1) |
| Starter assistants from older versions | audit finding S8 | rows in long-lived state directories | **Open**: needs a "repair or remove" flow, not a silent rewrite |
| Test runtime | `tests/support/runtime.py` (patches `engine.get_runtime` and `modelchoices`) | fixtures belong in tests, and the product selector is deliberately not test-aware | Verified not shipped: the wheel is `src/hutch` only |

### 2.2 The orchestrator already exists, but it is not the product's centre

- `workspace_settings.coordinator_bot_id` stores **one named workspace coordinator**; `GET/PUT /api/v1/workspace/coordinator`
  exist; the Tasks page shows work the coordinator handed to specialists.
- The coordinator's specialist roster **starts empty**; only assistants an owner adds in coordinator settings can
  receive assignments (README, "Multiple named bots").
- Onboarding creates a generic assistant. **Nothing in first run designates it the coordinator**; that is a
  separate settings action. The person is never asked "what do you want to call your main assistant?" as the
  product's first decision.
- The coordinator **cannot create assistants**. "Make an assistant from this request" is person-initiated and
  reviewable. `delegate_task` is a narrow, opt-in, Strict-Offline-only preview (`docs/realignment/delegation.md`).
- The roster lists every assistant as an equal row, so the sidebar looks like a bot gallery, not one assistant with helpers.

### 2.3 What is genuinely good and should be kept

Approvals bound to one exact action; reviewed, scoped memory; schedules with catch-up; spend reservations and a
workflow currency ceiling; reviewed, hash-trusted Agent Skills (`hutch skills install` is inert until
`trust`); governed whole-assistant deletion; local-first state; a read-only setup check and doctor.

## 3. What other projects do

### OpenClaw (primary: [docs.openclaw.ai/concepts/multi-agent](https://docs.openclaw.ai/concepts/multi-agent))

- With no configuration there is **one agent, `main`**. More agents are added deliberately:
  `openclaw agents add <name> [--role --workspace --model --bind]`, a "New agent" button in the sidebar
  (Settings, Agents), or config entries.
- Each agent has its **own workspace** (`AGENTS.md`, `SOUL.md`, `USER.md`), **own sessions**
  (`<agentDir>/openclaw-agent.sqlite`), **own auth profiles**, and a skills allowlist. The workspace is a default working
  directory, **not a hard sandbox** unless sandboxing is enabled.
- A **team preset** (`openclaw agents team create`) creates coordinator, researcher, writer and reviewer. The coordinator
  has `subagents.allowAgents` and `delegationMode: "prefer"` (prompt guidance, not a scheduler); specialists cannot
  delegate further. Role instructions require **human approval for external sends, publication, purchases, deletion
  and production changes**, and **agent-created agents also need operator approval**.
- The wizard offers "one agent or a team"; the docs describe **no onboarding step that names the agent**. Naming is explicit in `agents add`.
- ClawHub, its skills marketplace, has been reported (secondary) to host malicious skills, so vetting matters.

### Hermes Agent (primary overview, thin: [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/docs/user-guide/features/overview); detail secondary)

- `hermes setup` (and `--portal`) configures model and tools. `SOUL.md` is the agent's identity and the first part of
  the system prompt; personalities switch per session.
- `delegate_task` starts **child agents with isolated context, restricted toolsets and their own terminal**; **3
  concurrent by default** (primary). Secondary sources add a 50-iteration default budget per child and parent aggregation.
- **Bounded, curated memory** in `MEMORY.md` and `USER.md` (primary); session recall over SQLite FTS5 (secondary).
- Skills follow the **agentskills.io** standard with progressive disclosure (primary). A skills hub with sources
  (official repo, skills.sh, well-known URLs, GitHub, ClawHub, LobeHub), **browse, search, install, audit, publish and a
  security scan**, and automatic skill creation after complex tasks are described by secondary sources only.

### Cloudroom (primary: [github.com/davidondrej/cloudroom-core](https://github.com/davidondrej/cloudroom-core))

- Apache-2.0 desktop app plus a Rust runtime that runs **existing coding agents** (Claude Code, Codex, Pi, OpenCode,
  Hermes, Cursor, Devin) rather than being an assistant itself. It describes no coordinator.
- **Every cloud thread gets its own sandbox and its own Git branch**; agents run as a **separate Linux user without
  admin rights**; the API needs a secret token and listens on localhost; Mac access has four levels
  (Off, Read-only, Ask first, Full); history persists on disk; "Teleport" moves a thread between machines.
- It states that agents run **without approval prompts**, which is the opposite of Hutch's stance. Linux x64 is labelled alpha, Windows beta.

### Grok Bot alternatives (unverified directory listings)

OpenClaw, Rakazo (a sidebar roster of role-named bots), OpenMausBot (each bot with its own model, instructions,
working folder, apps and computer environment), Hermes and LobeHub (agent teams with a community sharing layer)
are what the directories list. I could not confirm their behaviour beyond those descriptions.

### What this adds up to

1. **One default agent first**; more agents are an explicit, named act. Nobody leads with a gallery of presets.
2. **Agent-created agents need the operator's approval** (OpenClaw). That is Hutch's model already; it just does not exist yet.
3. **Per-agent isolation** is a checklist: workspace, persona, sessions, credentials, skills, budget. Cloudroom adds
   **a sandbox and a branch per task**.
4. **Presets are a catalog with provenance**, and installing from a catalog is inert until reviewed. Hutch already
   built that trust model for skills.
5. Memory is **bounded and curated**, which Hutch's reviewed memory already is.

## 4. Target model for Hutch

- **Your assistant.** Onboarding's first decision is its name (editable later). It is created as the workspace
  coordinator. It is the only assistant that exists until the person or it proposes another.
- **Specialists** are created (a) manually: blank, or from a catalog entry, with a visible diff of what they can do; or
  (b) as an **orchestrator proposal**: "I suggest a specialist called X with these tools, this folder, this model, this
  budget", which the person approves, edits or rejects. Nothing is created by the model alone.
- **Catalog** (the agent store): a *Catalog* destination, not part of first run. Entries have a manifest, publisher,
  version, hash and requested permissions; install is inert until reviewed and trusted, exactly like skills.
- **No fixtures in the product.** A fresh state shows one real thing (set up your assistant). Example prompts exist
  only if they come from the person's connected apps, or are removed.

## 5. Gap list

Effort: S under a day, M a few days, L a week or more. "Dep" lists blockers.

### A. Orchestrator and assistants

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| A1 | Onboarding never asks for the main assistant's name and never marks it the coordinator | First-run "Name your assistant" step; create it with `coordinator_bot_id` set in one governed transaction; rename later | M | none |
| A2 | The coordinator cannot create assistants | A reviewable **proposal** object (name, instructions, tools, folder, model, budget, schedule) the coordinator can file; approval creates the assistant through the existing governed path; every proposal and decision recorded | L | A1 |
| A3 | Specialist roster starts empty and is edited only in settings | Roster becomes the result of proposals and manual creation; show who the coordinator may delegate to and why | M | A2 |
| A4 | Roster treats all assistants as equals | Main assistant pinned and visually distinct; specialists grouped beneath; Assistants manager only from ten (existing rule) | S | A1 |
| A5 | No persistent identity or user-profile files | Per-assistant identity (a `SOUL.md`-equivalent: tone, boundaries) and a person profile (`USER.md`-equivalent), bounded and reviewable; reuse the persona profile that exists | M | A1 |
| A6 | Delegation is a Strict-Offline-only preview | Make delegation work on ordinary routes behind the same approval and capability snapshot; budgets and concurrency limits per child (Hermes defaults 3 concurrent) | L | A2 |

### B. Catalog (agent store)

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| B1 | Eight presets are Python constants | Move them to a **catalog file** shipped as data with a manifest; show them under *Catalog*, never in first run | M | B2 |
| B2 | No assistant manifest format | Versioned manifest: name, description, instructions, tools, connections required, permissions requested, model needs, schedule default, publisher, hash | M | none |
| B3 | No import or export of an assistant | Export an assistant (no memory or secrets) as a package; import is inert until reviewed. A skill-ZIP importer already exists at tag `archive/agent-connections-2026-10-11` and is the starting point | M | B2 |
| B4 | No sources or trust model for catalogs | Local folder and Git/URL sources first; hash pinning; permission diff before enable; reuse the skills review and trust code | M | B2 |
| B5 | No publishing | Out of scope until B1 to B4 hold; design for signing, not hosting | L | B4 |
| B6 | No scanning of third-party packages | Static checks for requested tools and egress before review (Hermes describes a scan; OpenClaw's marketplace shows the cost of skipping it) | M | B4 |
| B7 | No versions or updates | Pin versions; update shows a diff and requires re-trust | M | B4 |
| B8 | No Catalog destination | One nav row, search, entry detail with permissions, install inert, review | M | B1 |

### C. Remove the demo and fixture remnants

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| C1 | Assistants that still use `mock/` or have no model | A "repair or remove" flow listed in Assistants and `hutch doctor`: choose a real route, or remove with the governed deletion; never rewrite silently | M | none |
| C2 | Canned prompt cards and first-run example buttons | Remove, or derive from connected apps with a visible source | S | none |
| C3 | `mock` ghosts: `RuntimeKind.mock`, `LOCAL_RUNTIMES`, "Retired mock", workspace-default guard | Remove once C1 has run; keep a migration that fails loudly on an unknown runtime | S | C1 |
| C4 | The "no demo surfaces" guard covers only `static/` | Extend to: no `mock` token in `src/` outside an allowlisted migration, no seeded assistants, no sample content in templates | S | none |
| C5 | Python API error text still says "bot" | Line-neutral rewrite of user-visible API strings; extend the vocabulary audit to Python | M | none |

### D. Execution is real, not just wired

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| D1 | No end-to-end first request on a real route has been run | Run the first request on the free OpenCode route and on a local Ollama model; record transcripts and cost; fail the release if it does not complete | M | none |
| D2 | A run is not isolated per task | A private workspace per run exists; add a **branch per task** for folder workspaces (Cloudroom) and a separate OS user for the executor where available | L | none |
| D3 | An interrupted run shows "Failed" | A distinct "Interrupted" chip driven by `exit_reason` | S | none |
| D4 | Background service is optional and invisible after install | Surface service health in the header; offer repair | S | none |

### E. Platform completeness

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| E1 | Install is a source checkout | `pipx`/`uv tool` install from a published wheel; PyPI name `hutch` returned 404 on 2026-10-30 (owner to reserve) | M | owner |
| E2 | No import from another agent | `hutch import hermes\|openclaw`: read persona, skills and memory with a preview (Hermes' README offers to import from other agents' directories, per `start-state-audit-2026-10-30.md`) | M | B2 |
| E3 | One messaging channel | Telegram exists; add the next channel only with the same pairing and approval boundary | L | none |
| E4 | No signed desktop builds, Linux only | Owner action: signing, notarization, macOS and Windows executors | L | owner |
| E5 | No hosted or shared catalog | Only after B5; the product stays local-first | L | B5 |

### F. Front-end production grade (from this run)

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| F1 | Server pages and the app still have different header chrome (C5 in the product spine) | One header contract: work status, global stop while running, title in the header | M | none |
| F2 | Per-page empty, loading, error-with-retry and permission states are uneven; no skeletons | A shared state kit; one polite live region; verified per page | L | none |
| F3 | No seeded-state browser pass | A populated, non-marketing state in the isolated artifact root for every destination at three widths | M | none |
| F4 | 19 `test_browser.py` failures predate this run (touch targets 40 vs 44, workflow studio, passkey) | Triage each: fix the control or the test | L | none |
| F5 | No screen-reader or axe pass | Automated axe plus a recorded manual pass | M | none |
| F6 | The History status filter and the Activity tabs share one fill; the phone header wraps while the stop control shows | Quieter active state for tabs; compact stop control | S | none |

## 6. Suggested order

1. **Honesty first** (C1 to C4, D3, F1): finish removing the demo remnants and make state truthful. Acceptance: a
   scan of `src/` finds no `mock` outside one migration; a fresh state and a legacy state both read truthfully.
2. **Orchestrator-first onboarding** (A1, A4, A5): name step, coordinator set, roster hierarchy. Acceptance: first
   run ends with one named assistant that is the coordinator; no presets appear.
3. **Catalog v1, local only** (B1 to B4, B8): presets leave the code, entries are inert until reviewed. Acceptance:
   removing the catalog file removes every preset; an install shows its permission diff.
4. **Proposals and delegation** (A2, A3, A6): the coordinator proposes, the person approves. Acceptance: no assistant
   exists that a person did not approve; every proposal is in the audit trail.
5. **Real-route proof** (D1, D2) before any release wording changes.
6. **Distribution** (E1, E2, E4) is the owner's.

## 7. What was and was not done in this run toward this

Done and committed: the "Working forever" root cause, the dead-demo-route signal, the removal of redundant `mock/`
filters and a vendor-specific example in the picker, one vocabulary, one title format, the Activity merge, a shared
shell, first-run setup check and service offer, the Models detected-service panel, the form-POST fix, packaging
(sdist 267 MB to 8.3 MB). **Not done:** the orchestrator onboarding, proposals, the catalog, the migration for
existing demo assistants, per-page state kit, and any live-model run. Those are the work in sections 5 and 6.

## Sources

- OpenClaw multi-agent concepts (primary): <https://docs.openclaw.ai/concepts/multi-agent>
- Hermes Agent features overview (primary, thin): <https://hermes-agent.nousresearch.com/docs/user-guide/features/overview>
- Cloudroom core README (primary): <https://github.com/davidondrej/cloudroom-core>
- OpenClaw multi-agent write-ups (secondary): <https://clawdocs.org/guides/multi-agent>, <https://dev.to/hex_agent/building-a-team-of-ai-agents-with-openclaw-149p>
- Hermes architecture and hub write-ups (secondary): <https://www.datacamp.com/tutorial/hermes-agent>, <https://github.com/spinningideas/resources/wiki/AI-Agent-Tools-Hermes-Agent>
- Grok Bot alternatives (unverified directories): <https://openalternative.co/alternatives/grok-bot>, <https://www.bitdoze.com/md/best-open-source-grok-bot-alternatives.md>
- Earlier comparison in this repository: `docs/realignment/start-state-audit-2026-10-30.md`
