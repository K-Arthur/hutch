# Onboarding and getting started: research and requirements (2026-10)

Status: complete for this program (research date 2026-10-30). This document is
the requirements source for `docs/realignment/onboarding-2026-10/`. It builds on,
and does not replace, [first-run-setup-2026-10-23.md](first-run-setup-2026-10-23.md),
[complaints.md](complaints.md), [offerings-and-failures.md](offerings-and-failures.md),
[bot-setup-patterns-2026-10-09.md](bot-setup-patterns-2026-10-09.md),
[grok-bot-product-review-2026-10-09.md](grok-bot-product-review-2026-10-09.md),
[connections-setup-ux-2026-10-10.md](connections-setup-ux-2026-10-10.md) and the
earlier planning set in `docs/onboarding/` (research.md, edge-case-matrix.md,
slice briefs 01-04, marketing-changes.md).

Evidence labels: **[primary]** page or issue opened directly on 2026-10-30
(fetched over HTTP or the GitHub API); **[search]** surfaced by a web search
summary only, not opened at its origin; **[repo]** read in this checkout;
**[prior]** inherited from earlier in-repo research, not re-opened today.

## 1. Executive summary

1. The strongest competitor pattern is not a wizard. It is **verify one real
   model completion before anything else is configured**. OpenClaw's current
   onboarding "establishes inference first", detects existing access (saved
   profiles, Claude/Codex CLI login, API-key environment variables, loaded local
   models), tests only the chosen connection with a real completion, and keeps
   the previous configuration when the check fails [primary].
2. Hutch has already shipped the right skeleton (server-owned resumable setup
   record, request step, three-route chooser) but the journey currently **ends at
   a temporary bridge to the general Apps and AI page**. A user who completes the
   shipped steps has still not connected a route, created an assistant, or seen a
   result [repo].
3. The most repeated real failures in comparable products are about **false
   readiness and lost state**, not missing tutorials: configured-but-401, model
   lists that work while generation fails, credentials not persisting, headless
   OAuth that cannot complete, and false rate-limit states [primary, section 5].
4. Hutch's existing honesty rules are an advantage worth keeping: "saved" is not
   "verified", no browser-to-provider calls, keys are write-only 0600 files,
   approvals are explicit.
5. Priority order for this program: (a) per-route readiness truth, (b) a real
   connection step per route that replaces the bridge, (c) a guided
   assistant-creation step that carries the request, (d) a first real run with
   approval explained in context, (e) a short, state-derived Getting Started
   surface for returning users, (f) a truthful desktop startup page, (g) a
   Getting Started guide and corrected marketing entry path.
6. Not adopted: product tours, mandatory checklists, a separate onboarding funnel,
   marketing analytics, fabricated trust signals, mocked demos presented as the
   product.

## 2. Research methodology

- Re-fetched the four OpenClaw pages, the Grok Bot get-started and bots pages and
  the MausBot download page over HTTP and read the rendered text [primary].
- Queried the GitHub issues API for first-run, auth and onboarding problems in
  `openclaw/openclaw`, `anomalyco/opencode`, `anthropics/claude-code`,
  `openai/codex` and `ollama/ollama`; opened eight issues individually and
  recorded date, state, product version where stated, and reaction counts.
- Ran web searches for OpenAI Dots, n8n, NN/g progressive disclosure, Ollama
  requirements and OpenCode authentication. Search summaries cite aggregator
  pages; none of these were opened at their origin and are labelled [search].
- Read the current Hutch implementation: `src/hutch/onboarding*.py`,
  `src/hutch/server/onboarding_*.py`, onboarding templates/CSS/JS,
  `src/hutch/connections.py`, `src/hutch/providers/connection.py`,
  `desktop/web/*`, `desktop/src/main.rs`, `website/index.html`, README headings.
- Limits: no live provider account was used; Reddit and Hacker News were not
  opened (not reachable through the tools used), so no claim here rests on them;
  "OpenAI Dots" documentation could not be opened at the vendor origin and is
  treated as low-confidence orientation only; issue counts are anecdotal and are
  never used as a prevalence rate.

## 3. Competitor comparison

| Product | First-run entry | Provider / model step | First task | Permissions explained | Recovery | Notes |
|---|---|---|---|---|---|---|
| OpenClaw (local, CLI/app) [primary] | `npx openclaw@latest` or installer; Quick start vs Custom setup after a one-line security pointer | Detects existing access in a fixed order, verifies one connection with a real completion, keeps prior config on failure; "Skip for now" exits without starting the gateway | Gateway opens dashboard chat | Security trust model shown first; Quick start defaults to full tool profile (explicit, but permissive) | `openclaw triage` and `doctor` (read-only diagnosis, sanitized hand-off), re-run keeps/modifies/resets | Requires Node 24+; headless/OAuth paths documented |
| Grok Bot (cloud + desktop) [primary] | Install app, browser sign-in, short intro, first Bot auto-created | No provider choice (plan-gated) | "Give it a first task" with a worked example and a five-minute document summary | Approvals and Auto Review linked before external changes; credentials never visible to the bot | Troubleshooting pages | Eligibility by paid plan is a pre-install gate; cloud computer model |
| MausBot (local desktop) [primary] | Download page with per-OS install steps and SmartScreen/Gatekeeper notes; "one bot and one provider" | Onboarding engine check installs/signs in to Claude Code or Codex, or API key/local | Copy-paste "plan your morning" task | Optional items listed (apps, computer control, voice, pairing) | Installation help, Discord, issue tracker | States required items and that provider fees apply |
| OpenAI Dots [search] | Desktop only; name the Dot | Plan-gated | "Small, bounded first task" | Approval rules chosen during setup | not verified | Low confidence; vendor origin not opened |
| Claude Code / Codex [primary issues] | Terminal login | Browser OAuth, API key alternative | Prompt in terminal | Per-action prompts | `/doctor`, manual code paste (Codex #2798 asks for headless sign-in) | See section 5 |
| Ollama [primary] | Download, `ollama` prompts, sign in for cloud or choose local | Local or cloud model choice at first prompt | `ollama launch <agent>` | n/a | n/a | Model sizes and memory are the real prerequisite |
| n8n [search] | Owner account, then canvas | Credentials vault | Assistant-built or template workflow | Activation toggle separates test from live | not verified | Useful idea: test run before activation |
| Hutch today [repo] | Dedicated `/onboarding`, SPA empty chat hand-off | Three-route chooser; ends at `/#/connections` bridge | None in onboarding | Not explained in onboarding | Setup record resume/stale/expired/damaged states | No verified-route step, no assistant step, no first-run result |

## 4. Positive patterns worth adopting

| ID | Pattern | Source | Hutch decision |
|---|---|---|---|
| P-01 | Inference first: nothing else is configured until one real completion succeeds | OpenClaw onboarding overview [primary] | Adopt as an explicit, owner-triggered "test generation" (the slice 03 contract), never a hidden call |
| P-02 | Detect before asking: reuse existing credentials/services and label them detected | OpenClaw [primary] | Adopt for detectable routes (saved connections, loopback model services, an existing OpenCode login); never read another client's cookies |
| P-03 | A failed check preserves prior config and offers retry, another provider, or skip | OpenClaw [primary] | Adopt; failed probe never mutates a working route |
| P-04 | Read-only diagnosis that can be shared without secrets | OpenClaw `triage`, Claude `/doctor` [primary] | Reuse `hutch doctor`; surface its readiness summary in the app and desktop startup page |
| P-05 | One focused job per assistant plus a concrete first task with a finish line | Grok Bot bots/get-started [primary] | Adopt in the assistant step: starter examples, carried request, no catch-all default |
| P-06 | State prerequisites and cost scope before the click | MausBot download, Ollama docs [primary] | Adopt on the website and in the local-service step (download size, memory) |
| P-07 | Approvals taught at the first approval, with credentials kept out of chat | Grok Bot approvals link [primary] | Adopt: explain approval in context on the first approval, not as a tour |
| P-08 | Optional items named as optional | MausBot download [primary] | Adopt in every step footer and the Getting Started guide |
| P-09 | Server-owned resumable setup state | Existing Hutch slice 01 [repo] | Keep; extend with connection, assistant and first-request milestones |

## 5. Reported failures and complaints

Each row was opened directly unless marked. "Still relevant" asks whether the
failure class applies to Hutch's architecture, not whether the other product has
fixed it.

| ID | Product, date | Reported problem | State at 2026-10-30 | Evidence | Still relevant to Hutch |
|---|---|---|---|---|---|
| C-01 | OpenClaw #2697, 2026-01-27 | Claude Code CLI OAuth reused during setup returns 401 "Invalid bearer token"; config files disagree on auth mode | closed 2026-02-04, 33 comments | [primary] strong for "detected credential accepted without a real call" | Yes: saved-but-unusable credential |
| C-02 | OpenClaw #32828, 2026-03-03 | False "API rate limit reached" on every model while the same keys work elsewhere | closed 2026-03-11, 56 comments | [primary] | Yes: cooldown or classifier state masquerading as provider state; per-route states must be derived from real probes |
| C-03 | OpenClaw #1818, 2026-01-25 | Onboarding wizard silently skips service install on Ubuntu 22.04 because the user systemd bus is unavailable | closed 2026-02-07, 31 comments | [primary] | Partly: environment prerequisites should be diagnosed and named, not skipped silently |
| C-04 | OpenClaw #27009, 2026-02-26 | Users blocked at onboarding because their subscription/provider is not an offered route | closed 2026-03-12, 23 comments, 25 reactions | [primary] | Yes: unlisted provider must have a labelled escape (Hutch: OpenCode or custom connection), not a dead end |
| C-05 | OpenCode #54833, 2026-10-12, v2.0.27 | Every model returns "Upstream request failed: Invalid credential" right after start | closed 2026-10-21, 23 comments | [primary] | Yes: authentication failure shown after the user believes setup is done |
| C-06 | Codex #2798, 2025-08-27 | Login needs a localhost callback; impossible from remote/headless sessions; asks for copy-paste code | closed 2026-01-11, 49 comments, 142 reactions | [primary] strong | Yes for OpenCode/OAuth routes on a remote or headless Hutch host |
| C-07 | Codex #48237, 2026-09-25 | 401 "Incorrect API key" surfaced from the first request | open, 97 comments | [primary] | Yes: first-request failure must be classified, not raw |
| C-08 | Claude Code #34229, 2026-03-14 | Account sign-up stalls at phone verification (reported by users of a plugin driving new users in) | open, 742 comments, 891 reactions | [primary] strong for external-account friction | Context only: Hutch has no account step; the lesson is to name external prerequisites before install |
| C-09 | Claude Code (search) [search] | Browser sign-in succeeds but the CLI returns to the login prompt (credential store not writable, WSL/SSH callbacks) | not verified | [search] weak | Treat as class-level hint with C-06 |
| C-10 | Prior in-repo catalog: OpenCode #38257, #7992, #9922; Jan #7658, #8594; Open WebUI #16287; chat-ui #252; Home Assistant #35696; n8n PRs #33670, #35734 | model list 200 but generation 401; OAuth success but client waits; key not pasteable or lost; first-run buttons unusable on mobile; consent modal loops; onboarding re-asks known values; empty-state inconsistency; checklist disabled later | see [onboarding/research.md](../onboarding/research.md) section 3 | [prior] | Yes, mapped in section 6 |

Not established: any industry-wide abandonment rate. The earlier benchmark
figures (checklist completion averages, regulated-finance abandonment) were
checked in `docs/onboarding/research.md` section 0.3 and are not used as
targets here.

## 6. Root causes

| Cause | Complaints | Hutch exposure today [repo] |
|---|---|---|
| RC-1 Readiness inferred from configuration or a metadata call, not a real completion | C-01, C-05, C-07, C-10 | `check_connection` returns `verified=ok` on a model-list success; the legacy SPA shows "Connected" from it. Slice 03 contract fixes the vocabulary but is not implemented |
| RC-2 One generic failure state for many causes | C-02, C-07 | The SPA readiness panel collapses three checks into setup/error; no per-route typed state |
| RC-3 Setup state not durable or not honoured on re-entry | C-10 | Fixed by slice 01 for the request/route; connection, assistant and first-run milestones are not yet recorded server-side |
| RC-4 Auth flows that assume a local browser | C-06, C-09 | OpenCode and OAuth tiles assume the dashboard browser is on the host; no stated fallback |
| RC-5 Environment prerequisites assumed or skipped silently | C-03 | `hutch doctor` exists but the app and desktop startup page do not surface its findings; startup page cannot show why it failed |
| RC-6 Dead ends for unlisted providers or plans | C-04 | Chooser offers three routes; the connection step for each does not exist yet |
| RC-7 Documentation that does not match the product | prior catalog | Website links `github.com/K-Arthur/hutch#quickstart`, but the README has no Quickstart heading (verified: headings are Setup details, Features, ...) |

## 7. Opportunities for Hutch

1. Replace the bridge with real connection steps for all three routes, each
   ending in an honest readiness state and one next action.
2. Make the first successful outcome concrete: connected route, created
   assistant, a real answer to the user's own saved request.
3. Make approvals and spend limits legible at the moment they first matter.
4. Give returning users a short, state-derived "what next" surface instead of a
   repeat of onboarding, and let established users never see onboarding.
5. Make the desktop startup page diagnose and recover, since it is the first
   screen of the desktop app.
6. Publish a Getting Started guide whose steps match the product and whose entry
   path names Linux, Python, local server and model route before the click.

## 8. Architecture implications

- The setup record (`onboarding:setup:v1` in kv) stays the single source of truth
  for the journey. Additions are defaulted fields: connection name, assistant id,
  first-request marker. Unknown fields are already ignored by older readers.
- Readiness is one pure module (`route_readiness.py`) plus a typed server-side
  probe adapter. No second classifier. The browser never calls a provider.
- "Verified" requires a generation. A metadata success yields saved-unverified.
  The slice 03 brief flags that a direct one-token probe bypasses governed-run
  accounting; this program resolves it as: the explicit probe is owner-triggered,
  one-shot, tool-free, labelled as possibly using a small amount of credit, and
  the first governed run also upgrades readiness (see DECISION.md D-03).
- Completion of onboarding is derived from facts in the store (a verified or
  successfully used route, an assistant exists, a completed run), never from a
  flag set by opening a page. Existing users are recognised by those facts and
  are never forced into onboarding.
- All new routes are owner-only (capability `None`), CSRF-checked, free of
  user-controlled redirects, and keep secrets out of HTML, logs, kv and URLs.
- Frozen files (`app.py`, `app.js`, `store.py`, `models.py`, `pages.py`,
  `connections.py`, `security.py`) may not grow; new code lives in small modules.

## 9. UX implications

- One primary action per step, in document flow; every step has a visible
  "not now" that preserves the saved request.
- Words carry state ("Saved on this machine, not tested"), never colour alone.
- Cost, download size, and privacy statements precede the action they concern.
- The first-run surface is not a tour. Teaching happens at first approval, first
  spend limit, and first failure.
- A failed step offers: retry (only when retryable), choose another route, leave
  and resume later. The written request is never lost.
- Plain-language glossary on first use of: assistant, model, provider, route,
  approval, workspace. Advanced terms (runtime, protocol) stay behind disclosure.

## 10. Accessibility considerations

- WCAG 2.2: status messages without moving focus (4.1.3); focus not obscured
  (2.4.11); target size (2.5.8, 44 px floor on coarse pointers); reflow at 320 px
  (1.4.10); text spacing (1.4.12); non-text contrast (1.4.11).
- Server-rendered forms that work without JavaScript; htmx or JS only enhance.
- One polite status region per step; polling ticks silent; error summary focused
  once; step heading focused on arrival.
- Dark theme only (product decision) with forced-colours and reduced-motion
  support; 200 percent zoom and keyboard-only passes are part of the gate.
- Phone keyboard: primary action reachable with the keyboard open; emulated by a
  scripted visual-viewport resize and documented as emulation.

## 11. Prioritized requirements

| ID | Requirement | Priority | Addresses |
|---|---|---|---|
| R-01 | Pure per-route readiness classifier and typed probe; saved-unverified vs verified; 14 provider error kinds mapped | P0 | RC-1, RC-2, C-01, C-05, C-07 |
| R-02 | Readiness panel states with one next action each; capped retry; no browser-to-provider call | P0 | RC-2, C-02 |
| R-03 | Hosted-key step: write-only field, trim and Bearer-prefix handling, 0600 storage, terms acknowledgement, recovery copy | P0 | RC-1, C-01, C-10 |
| R-04 | Replace the chooser's temporary bridge so the three routes lead to real connection steps | P0 | RC-6 |
| R-05 | Local-service step: server-side probe, down vs empty vs ready states, size and memory guidance, exact commands | P1 | C-10, P-06 |
| R-06 | OpenCode/external login step with waiting, expiry, cancel, retry and a no-local-browser fallback statement | P1 | RC-4, C-06 |
| R-07 | Guided assistant step: carried request, starter examples, editable name, route, plain permissions/workspace/spend summary, idempotent create | P0 | P-05 |
| R-08 | First request step: real run, progress, approval explained at first approval, run inspection link | P0 | P-07, C-07 |
| R-09 | State-derived Getting Started surface: dismissible, resumable, never complete by page view, hidden for established users | P1 | RC-3 |
| R-10 | Existing-user safety: detection from persisted facts, no forced onboarding, no config loss when a flag is missing | P0 | section 3.1 of the mission |
| R-11 | Desktop startup page: progress, timeout, failure reasons, quit/retry, diagnostics pointer | P1 | RC-5, C-03 |
| R-12 | Website entry path and Getting Started guide; fix dead quickstart anchor; dated availability; prerequisites before the click | P1 | RC-7 |
| R-13 | Docs updated: runtime-setup, connections, models, bot-config, safety, marketing-site, README index | P1 | RC-7 |
| R-14 | Real-world validation and opened-image visual evidence at the required viewports | P0 | gate |

## 12. Source links and evidence confidence

| Source | Used for | Confidence |
|---|---|---|
| https://docs.openclaw.ai/start/getting-started | Quick start, prerequisites, triage | High [primary] |
| https://docs.openclaw.ai/start/onboarding-overview | Inference-first, detection order, recovery | High [primary] |
| https://docs.openclaw.ai/start/wizard | Quick start/Custom lanes, Skip for now, failure handling | High [primary] |
| https://docs.openclaw.ai/start/onboarding | App onboarding, security notice | High [primary] |
| https://docs.x.ai/grok-bot/get-started | Install, sign in, first Bot, first task, approvals | High [primary] |
| https://docs.x.ai/grok-bot/bots | One job per Bot, approval boundaries | High [primary] |
| https://mausbot.com/download | Per-OS install, one provider, optional items | High [primary] |
| https://docs.ollama.com/quickstart | Local/cloud model entry | High [primary]; sizes from search are [search] |
| https://github.com/openclaw/openclaw/issues/2697, /32828, /1818, /27009 | C-01..C-04 | High for existence and dates; anecdotal for prevalence |
| https://github.com/anomalyco/opencode/issues/54833 | C-05 | High for existence; anecdotal |
| https://github.com/openai/codex/issues/2798, /48237 | C-06, C-07 | High; #2798 has 142 reactions |
| https://github.com/anthropics/claude-code/issues/34229 | C-08 | High for existence; context only |
| OpenAI Dots, n8n onboarding, NN/g progressive disclosure summaries | Orientation | Low [search] |
| `docs/onboarding/research.md` and the earlier in-repo research set | Prior catalog and standards (RFC 8252, RFC 8628, WCAG 2.2, GOV.UK patterns) | Medium [prior] |
