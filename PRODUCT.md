# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Developer-operators who run Hutch on their own machine: they create named bots, send them real
tasks, supervise long-running work, and decide approvals. Desktop is the primary workspace. A
responsive phone layout is part of the target experience, but remote phone supervision and
physical-device validation are not available in this preview.

## Product Purpose

Hutch is a local-first, MIT-licensed multi-bot platform in private preview; there is no public
source checkout or release today. The web app is the operator's workspace: converse with bots,
watch actual execution, review consequential actions, and manage schedules and memory. Usage
limits use measured or estimated data and do not guarantee a provider invoice. Success = an
operator trusts every state the screen shows, because each one comes from real server data.

## Positioning

One directory on your machine holds the orchestrator, memory, logs, and bots; the operator
brings their own models (local Ollama/llama.cpp/LM Studio, or OpenAI-compatible/Anthropic
connections). Governance is the product: approval gates, estimate-based usage admission,
append-only transcripts, DST-safe schedules. Provider-side controls remain necessary for a
guaranteed external spending limit. The app must make that governance legible, not decorate it.

## Operating Context

- `hutch serve` on 127.0.0.1; CSRF/DNS-rebinding middleware; tokens never in URLs or logs.
- Runs stream over SSE with `Last-Event-ID` gap-free resume from SQLite (server is the
  source of truth); events are paginated by per-run `seq`.
- Bots have model, tools, schedule (cron + IANA tz + catch-up), memory, sticky allows,
  estimate-based usage limits, and a per-bot workspace folder.
- Mock runtime (`mock/demo`) powers deterministic demos/tests; a "demo" label must always
  be visible so a mock success is never read as real.
- CLI (`hutch …`) and server-rendered pages coexist; retired pages redirect into the SPA.

## Capabilities and Constraints

- Authoritative HTTP surface today (`/api/*`): bots CRUD + patch (model, approval mode,
  workdir, pause, schedule, memory delete, sticky-allow revoke), run submit/stop/resume,
  run events + stream + verify, approvals list/get/decide with server-authoritative
  resolution and cross-device conflict handling, overview/usage/health, bot models +
  estimate, connections (currently server-rendered forms; JSON surface is a small additive
  dependency for the SPA views).
- Durable conversations/messages and idempotent command receipts exist only on the
  unmerged `realign/platform` worktree. Coordination decision (2026-10-07, reversible):
  this workstream builds against current `/api`, treats per-bot run history as the thread,
  and feature-detects `/api/v1` when it lands. No fabricated receipts, no invented
  conversation backend.
- Frontend stack constraint: zero build step, zero external assets (fonts/CDNs),
  vanilla ES + hash-routed SPA at `/`; Jinja2+HTMX server pages for the remainder.
  Restructuring inside those files is allowed; introducing a framework or bundler is not.
- The marketing site (`website/`) is a separate surface with a shared token source. Its claims
  must match the actual support matrix and disclose that source and downloads are private.

## Brand Commitments

User-pinned v2 contract (binding):
- Emerald lineage as the brand accent (`#34d399` family); `#52a8ff` is a candidate
  interaction/information color, never a second brand accent; success/warning/danger stay
  semantic state colors, paired with text and/or icon, never color alone.
- Geometry: square structural panels and data surfaces; 0px buttons/icon buttons;
  100px pill chips; named 16px exceptions only for the composer and conversation rows.
- Type: readable sans for UI/conversation, one monospace family for operational data
  (IDs, timestamps, tokens, code); tabular numerals.
- Dark, architectural, developer-focused; calm recognizable agent identity (original
  aurora-sphere character, never another product's mascot); no marketing theatrics,
  no compulsory intro, no full-screen ambient animation in the working app.
- Motion: short, functional, state-linked; honors `prefers-reduced-motion` plus an
  explicit Reduce-effects control; forced-colors fallbacks.
- Accessibility: WCAG 2.2 AA target everywhere; 24×24 AA minimum with Hutch's 44×44
  touch comfort target; visible focus independent of glow.

## Evidence on Hand

- `docs/design-system.md` (token values, complaint traceability), `docs/research/`
  (verified reference map: Grok Bot design article + changelog, Open WebUI #31656 closed,
  #30055 and #27187 open — focus restoration, hidden pending input, eager history transfer),
  `docs/performance.md` baselines, Playwright e2e in `tests/e2e/`.
- Before/after captures in `/tmp/opencode/shots/` — the "after" set was rejected by the
  user as amateurish and ugly. The incumbent skin is anti-reference for this work.
- No real customer data, no live provider keys in this repo's state; use the deterministic
  demo fixture (`hutch demo seed`) in an isolated `HUTCH_STATE_DIR` for all visual QA.

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
