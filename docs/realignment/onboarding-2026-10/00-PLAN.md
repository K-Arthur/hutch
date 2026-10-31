# Onboarding 2026-10: plan

Scope: finish the journey that slices 01-02 started, using the briefs in
`docs/onboarding/slices/` as the contract, and add the getting-started surfaces
(desktop, docs, website). Branch `onboarding-2026-10` in an isolated worktree
because the root checkout carries another session's uncommitted work.

## Journey (server-rendered, resumable, owner-only)

1. `/onboarding` request (done, slice 01)
2. `/onboarding/ai-service` route choice (done, slice 02)
3. `/onboarding/connection` readiness shell, route form partials (slices 03-06)
4. `/onboarding/assistant` guided create (slice 07)
5. `/onboarding/first-request` real run and approval intro (slice 08)
6. Contextual Getting Started surface (state-derived, dismissible)
7. Desktop startup page, Getting Started guide, website path

## Milestones and acceptance

| M | Deliverable | Acceptance |
|---|---|---|
| M1 | Research, findings, plan, decisions | Docs committed; requirements R-01..R-14 traced |
| M2 | `route_readiness.py` + typed probe + tests | All 14 error kinds mapped; metadata never yields verified; no secret in detail |
| M3 | Hosted-key step, `connections_service.py`, bridge replaced | Key trimmed/stored 0600/never echoed; terms ack; 401/402/403/429/5xx copy; legacy JSON shape unchanged |
| M4 | Local-service and OpenCode steps | Server-side probe states; wait/cancel/retry for external login |
| M5 | Assistant + first request + Getting Started | Idempotent create; real run; surface derived from store facts |
| M6 | Desktop startup, docs, website | Dead anchor fixed; prerequisites before the click; claims match `docs/marketing-site.md` |
| M7 | Real-world run and opened visual evidence | Scenarios in RUNLOG; 8 viewports plus zoom, spacing, reduced motion, keyboard |
| M8 | Independent review and integration to main | CODE-REVIEW.md resolved; main contains commits; worktree removed |

## Constraints

400-line cap on new source files; frozen files shrink-only (`app.js`, `store.py`,
`app.py`, `models.py`, `pages.py`, `connections.py`, `security.py`); generated CSS
never edited by hand; no emoji; no secrets; no telemetry; commits are
conventional, one focused change each, no AI attribution.

## Honest status rule

Each milestone's status is recorded in CHANGES.md and HANDOFF.md as done,
partial, or not done. A step that was not exercised against a real running
server is not called validated.
