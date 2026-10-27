# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People who want a personal assistant to keep useful work moving, with optional specialist
assistants for separate kinds of work. The everyday path should work for someone who does not
know provider, runtime, or executor terminology. People who want to tune models, tools, memory,
budgets, or workspaces can open those controls when they need them. Desktop and phone are both
first-class reading and supervision surfaces; remote phone features remain experimental and
physical-device validation is not available in this preview.

## Product Purpose

Hutch is a local-first personal-assistant app in preview. Its source repository is public;
no desktop installer release has been published yet. A person starts with a conversation, can turn an existing request into
a task-specific assistant without repeating it, and stays in control when a task needs a decision.
The app can keep work and its history on a computer the person controls while connecting to a
chosen local or hosted model. Advanced configuration is available on purpose, not imposed on the
first screen. Usage limits use measured or estimated data and do not guarantee a provider invoice.
Success means ordinary tasks feel approachable and every action, connection, and status remains
honest and reviewable.

## Positioning

Hutch runs its control state on the person's computer and uses the local or hosted models and
connected apps they choose. The product begins with a familiar conversation and explains model,
account, privacy, and permission choices in plain language where they matter. People can inspect
task history, adjust assistant behavior, and review consequential actions. Technical routes,
resource limits, permissions, and provider-side billing details remain available in contextual
advanced controls. Provider-side controls remain necessary for a guaranteed external spending
limit.

## Operating Context

- `hutch serve` on 127.0.0.1; CSRF/DNS-rebinding middleware; tokens never in URLs or logs.
- Runs stream over SSE with `Last-Event-ID` gap-free resume from SQLite (server is the
  source of truth); events are paginated by per-run `seq`.
- Bots have model, tools, schedule (cron + IANA tz + catch-up), memory, sticky allows,
  estimate-based usage limits, and a per-bot workspace folder.
- Product runs require a configured real model route. Deterministic execution scenarios live
  under test support only and are excluded from packaged builds; there is no product demo runtime
  or seeded demo command.
- CLI (`hutch …`) and server-rendered pages coexist; retired pages redirect into the SPA.

## Capabilities and Constraints

- Authoritative HTTP surface today (`/api/*`): bots CRUD + patch (model, approval mode,
  workdir, pause, schedule, memory delete, sticky-allow revoke), run submit/stop/resume,
  run events + stream + verify, approvals list/get/decide with server-authoritative
  resolution and cross-device conflict handling, overview/usage/health, bot models +
  estimate, connections (currently server-rendered forms; JSON surface is a small additive
  dependency for the SPA views).
- Durable conversations/messages, archive and idempotent command receipts are implemented on
  the integrated realignment branch. Studio uses `/api/v1/conversations`; legacy runs remain
  separate imported threads. Connection JSON APIs support the shared settings surface.
- The workspace roster pin preference persists with each Bot and does not change its
  runtime or authority. See the [roster and mascot review](docs/research/bot-roster-and-mascot-review-2026-10-09.md).
- Chat is the daily workspace: familiar conversations, one compact assistant list, one Apps & AI
  destination, inline approvals and a clear Needs you view. The main assistant stays first;
  owners can pin frequent assistants without hiding active work. More contains Activity,
  Scheduled work, Work history, and Manage assistants. The larger assistant manager appears
  at ten assistants with search/state filters; ten is a product heuristic, not a research-proven threshold.
- Frontend stack constraint: zero build step, zero external assets (fonts/CDNs),
  vanilla ES + hash-routed SPA at `/`; Jinja2+HTMX server pages for the remainder.
  Restructuring inside those files is allowed; introducing a framework or bundler is not.
- The marketing site (`website/`) is a separate surface with a shared token source. Its claims
  must match the actual support matrix and disclose that source and downloads are private.

## Brand Commitments

The main-branch design system in [`DESIGN.md`](DESIGN.md) is the visual source of truth.
Hutch should feel like a capable personal assistant for everyday users: familiar chat,
recognizable app marks, a simple 2D identity in the product, and concise, task-focused
screens. Put model, permission, workspace, and execution details in contextual settings
for people who choose to tune them. Keep the original, more detailed 3D mascot for marketing.
Use the shared graphite surfaces, emerald actions, azure focus, semantic status colors,
system-sans prose, and rounded geometry documented in `DESIGN.md`. Icons clarify actions
and destinations; service marks always sit beside their names. Motion stays short, useful,
state-linked, and respectful of reduced-motion and forced-colors settings.
- Accessibility: WCAG 2.2 AA target everywhere; 24×24 AA minimum with Hutch's 44×44
  touch comfort target; visible focus independent of glow.

## Evidence on Hand

- `docs/design-system.md` (token values, complaint traceability), `docs/research/`
  (verified reference map: Grok Bot design article + changelog, Open WebUI #31656 closed,
  #30055 and #27187 open — focus restoration, hidden pending input, eager history transfer),
  `docs/performance.md` baselines, Playwright e2e in `tests/e2e/`.
- Before/after captures in `/tmp/opencode/shots/` — the "after" set was rejected by the
  user as amateurish and ugly. The incumbent skin is anti-reference for this work.
- No real customer data or live provider keys are used for visual QA. Use the isolated test
  server and clearly labelled synthetic lifecycle fixtures only for states that are difficult
  to hold naturally; marketing captures must come from the actual empty first-run product.

## Quality Gates (user-set, 2026-10-07)

- Aesthetic score ≥ 90/100 and functionality score ≥ 95/100 (overall = the lower), each
  with written evidence; every screen judged on opened screenshots, desktop and phone,
  not on code inspection. Screenshot creation alone is not validation.

## Product Principles

1. Truthful state beats a confident look: every badge, count, and receipt comes from server
   evidence; unknown says unknown.
2. Governance is the loudest thing on screen: approvals, spend, risk, and waiting reasons
   never hide behind chrome or color.
3. Conversation is the workspace; operations views (runs, transcripts, health) are
   supporting tools, not the homepage.
4. Quiet chrome, dense evidence: decoration must communicate structure or state, or it is
   deleted.
5. Phone is a supervisor's device, not a shrunken desktop.

## Accessibility & Inclusion

WCAG 2.2 Level AA across all applicable A/AA criteria; keyboard-complete core journeys;
scoped status announcements (never whole-app live regions); reduced-motion and forced-colors
modes; drafts and focus survive dialogs, navigation, and reconnects. Automated checks are a
floor, not a claim of conformance; manual keyboard passes are recorded with what was and
was not tested.
