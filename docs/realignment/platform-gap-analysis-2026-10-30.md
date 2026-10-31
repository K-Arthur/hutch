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

### Grok Bot (primary, supplied by the owner: [get-started](https://docs.x.ai/grok-bot/get-started), [bots](https://docs.x.ai/grok-bot/bots), [shared bots](https://docs.x.ai/grok-bot/shared-bots)) and OpenClaw onboarding ([overview](https://docs.openclaw.ai/start/onboarding-overview))

- **First run.** Grok Bot **creates your first Bot, named "Grok Bot", and opens a chat with it**; the page describes **no
  naming, role or first-message wizard**. You rename it later by clicking its name above the chat, and you give it
  **one primary job in your first message** and ask it to remember how it should work. If you have no primary Bot the
  app shows "Introducing your primary Bot": create one or choose an existing one.
- **What a Bot is.** A durable teammate with a name, a job, its **own conversation and its own memory** (preferences,
  rules, a dated work log). Personal Bots have **no description field or settings page**: the job and boundaries are
  defined in chat and kept in memory. Secrets belong in a Vault, not in memory.
- **Three ways to get more Bots.** (1) By hand: the **+** button or Ctrl/Cmd+N, name it, Create. (2) **By an existing
  Bot**: your Bots "can suggest or create a focused Bot when a job needs a long-lived owner", and the docs advise asking
  before creating several. (3) **From templates**: Connect apps, Bot templates, Import Bot; templates are made by other
  users, there is no store, and a public template link exposes the Bot's identity, description, skills and routines, so
  the docs tell you to strip API keys, internal URLs and customer data first.
- **Primary Bot and roster.** The primary Bot is your main contact and coordinates the others, including in group
  chats where a coordinator assigns work. "Start with the smallest useful roster and add a Bot only for a stable
  specialist role." **A shared Bot cannot be your primary Bot.** Facts about you reach your other Bots; each Bot's
  working memory does not.
- **Sharing is not copying.** A *shared Bot* is the same Bot for everyone (roles: Collaborator, Manager); a *template*
  gives each person their own copy. Each person's chat is private. A Bot **asks before using a teammate's personal
  account** (Allow once, Always allow, Skip) and a connected account only ever acts for the person being answered.
- **Hide versus delete.** "Hide from sidebar" keeps history, memory and routines running; deleting erases the profile,
  conversations, memory, routines and attachments and cannot be undone. **Duplicate** copies the Bot but not its
  history, memory or attachments.
- **OpenClaw onboarding** (`openclaw onboard`: Quick start or Custom) is built around **verified inference**: it
  detects AI access you already have, or walks you through a sign-in or key, then **runs a real completion on the
  chosen model, and nothing else is configured until that passes**. Only then does it set up the workspace, the
  gateway service (a systemd user service on Linux), channels and agents. `openclaw setup` repairs the non-inference
  parts. This page documents no naming step; naming is explicit in `openclaw agents add`.

Rakazo, OpenMausBot and LobeHub stay unverified directory listings.

### Marketplaces (primary pages supplied by the owner, fetched 2026-10-30; each page is partial, and gaps are stated)

- **Grok Bot marketplace** ([x.ai/bot/marketplace](https://x.ai/bot/marketplace)). Category tabs (All, From Grok Bot Team,
  Engineering, Sales, Marketing, Design, Personal, Recruiting and People, Product, Operations), a featured row, and per-category
  previews with "View all". A listing is a name, "by <publisher>", a paragraph and an **Add** button that opens the bot's
  own page. The page shows **no search, install counts, ratings, requested permissions, or publisher verification**, and does
  not say what Add does. Safety claims inside descriptions ("nothing sends without your yes") are self-reported.
- **ClawStore** ([docs.useclawstore.com](https://docs.useclawstore.com/), introduction only). "npm for AI agents":
  `clawstore publish`, `clawstore install @scope/name`. The install flow shown **resolves dependencies, prompts for the
  secrets it needs, populates a per-agent workspace, installs a required plugin at a stated version, registers the agent
  with a model, and asks `Proceed? [Y/n]` before changing anything.** Versions are explicit (0.3.1); "Updates and Rollback",
  "Trust and Safety", "Auth and Ownership" and "Agent Package Format" are linked but were not part of the page.
- **OpenClaw Skills store** ([openclaw-skills.store](https://openclaw-skills.store/)). 200+ skills in 10 categories; a listing
  shows name, description, **version** and **price or Free before install**. CLI: `install`, `update`, `uninstall`, `list`,
  `skills search`; the sample output includes **"Verifying signature..."**. Publishing: a Node.js or Python SDK, then "submit
  for community review"; review is said to check for malicious code, unstable dependencies and privacy violations. It does
  **not** describe per-skill permissions, scan results, sandboxing, reporting or takedown.
- **Claw Store** ([claw-store.net](https://www.claw-store.net/)). A paid marketplace of *agents*: category, a Featured/New
  badge, price, star rating and review count; a seller application with a stated 48-hour manual review ("API compliance,
  documentation quality, code safety"); an 80% seller share with weekly payouts. Install, versioning and refunds are not
  described, and its headline numbers are unverifiable marketing.

What they share, and what Hutch should do differently:

1. **Nobody shows what a listing is allowed to do before you install it.** Hutch's listing shows the tools in plain words,
   whether it needs a folder, its approval mode, the commands it denies, the connections it needs, its publisher and its
   content hash. That is a differentiator, not a nicety.
2. **A preview-and-confirm install** (ClawStore's `Proceed? [Y/n]`) is the right shape: show what will be created
   (assistant, folder, tools, connections needing keys, model) and change nothing until the person confirms. Hutch's setup
   review page already is that step.
3. **Signature and hash verification** is claimed by one store and defined by none. Start with content hashes pinned in the
   index; add publisher signatures when there is key infrastructure to hold.
4. **A first-party section** ("From Grok Bot Team") separates what the product ships from what others publish. Hutch's
   equivalent is `publisher: Hutch`, shown as its own section.
5. **Reporting, takedown and a revocation list are undocumented everywhere.** Hutch needs a local denylist of hashes a
   source can revoke, and a report link on every entry.
6. **Paid listings and seller payouts are out of scope** for a local-first, non-commercial release; that is a deliberate
   non-goal, not a gap.
7. **A marketplace can be a static, signed index**, not a service: an `index.json` of entries (id, version, hash, URL,
   publisher, signature) hosted anywhere, fetched only from a source the person added, and never automatically.

### What this adds up to

1. **One default agent first**; more agents are an explicit, named act. Nobody leads with a gallery of presets.
2. **Agent-created agents need the operator's approval** (OpenClaw). That is Hutch's model already; it just does not exist yet.
3. **Per-agent isolation** is a checklist: workspace, persona, sessions, credentials, skills, budget. Cloudroom adds
   **a sandbox and a branch per task**.
4. **Presets are a catalog with provenance**, and installing from a catalog is inert until reviewed. Hutch already
   built that trust model for skills.
5. Memory is **bounded and curated**, which Hutch's reviewed memory already is.
6. **Verify the model before anything else** (OpenClaw): onboarding is not finished until a real completion works.
7. **The first assistant is created for the person, named later, and defined by its first message** (Grok Bot); a
   name field is welcome, a wizard is not. Guidance for that first message (outcome, sources, constraints, what to hand
   back, when to stop and ask) is better than invented example prompts.
8. **Three creation paths, one approval rule**: by hand, from a template that becomes the person's own copy, or proposed
   by an existing assistant who is told to ask before creating several. Grok Bot leaves the last unreviewed; Hutch
   should not.
9. **Share a template, never a live bot** for a local-first single-owner product. Live shared bots with roles are a
   team feature and a non-goal here; templates need a sanitising checklist before export.

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
| A7 | First run detects an AI service but never proves it works | **Verified first completion** before the first assistant is created: one tiny, consented, costed completion on the chosen route; on failure show the provider's error and the fix; nothing else is configured until it passes (OpenClaw). Reuses the first-run readiness panel | M | none |
| A8 | The first request has no guidance now that invented prompts are gone | Help text under the field: the outcome, where to look, what to avoid, what to hand back, when to stop and ask (Grok Bot's guidance), as copy and not prompt buttons | S | none |
| A9 | The coordinator can become any assistant, including a catalog copy of unknown provenance | Constraint: the main assistant is a local assistant the person created or reviewed; catalog entries are copies the person owns (Grok Bot's "a shared Bot cannot be primary") | S | A1 |
| A6 | Delegation is a Strict-Offline-only preview | Make delegation work on ordinary routes behind the same approval and capability snapshot; budgets and concurrency limits per child (Hermes defaults 3 concurrent) | L | A2 |

### B. Catalog (agent store)

| ID | Missing or wrong | Real implementation | Effort | Dep |
|---|---|---|---|---|
| B1 | Eight presets are Python constants | Move them to a **catalog file** shipped as data with a manifest; show them under *Catalog*, never in first run | M | B2 |
| B2 | No assistant manifest format | Versioned manifest: name, description, instructions, tools, connections required, permissions requested, model needs, schedule default, publisher, hash | M | none |
| B3 | No import or export of an assistant | Export an assistant as a template (no memory, history, attachments or secrets, matching Duplicate); a **sanitising checklist before export** (keys, internal URLs, customer data: Grok Bot's warning); import is inert until reviewed, and the result is the person's own copy. Skill-ZIP importer at tag `archive/agent-connections-2026-10-11` is the starting point | M | B2 |
| B4 | No sources or trust model for catalogs | Local folder and Git/URL sources first; hash pinning; permission diff before enable; reuse the skills review and trust code | M | B2 |
| B5 | No publishing | Out of scope until B1 to B4 hold; design for signing, not hosting | L | B4 |
| B6 | No scanning of third-party packages | Static checks for requested tools and egress before review (Hermes describes a scan; OpenClaw's marketplace shows the cost of skipping it) | M | B4 |
| B7 | No versions or updates | Pin versions; update shows a diff and requires re-trust | M | B4 |
| B9 | No marketplace beyond the bundled files | **Sources**: a bundled first-party index plus sources the person adds by URL; each is a static `index.json` of entries (id, version, hash, manifest URL, publisher, optional signature). Fetching is explicit, per source, shows what the source can see, and never runs in the background. Listings show category, version, publisher, requested permissions and hash before install; a **Proceed** step lists everything that will be created and changes nothing until confirmed (ClawStore) | L | B4 |
| B10 | No reporting, revocation or scanning story | A local **revocation list** of hashes a source can withdraw, a report link on every entry, and a static scan of requested tools, egress and command rules before review (the stores describe review but publish no scan result) | M | B9 |
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
