# Provider, authentication, runtime and multimodal platform research (2026-10)

This directory is the research and delivery record for the Hutch provider-platform expansion. It is
dated evidence, not a proposal: every claim about a provider or an integration states whether it was
read from official documentation, reproduced by Hutch, or observed live.

## Direct human constraints that govern this package

- Research before implementation; do not infer that an endpoint or SDK means a usable integration.
- Do not create demo fixtures; only real implementations are allowed. Provider breadth is expressed
  through real metadata, real authentication/readiness logic and honest status, never through fake
  accounts, seeded catalogues or synthetic screenshots.
- Never silently substitute the selected model, provider, account, runtime, endpoint or billing
  route. Never weaken local-first security, approvals, reservations or honest outcomes.
- Other agents are active in the main checkout. Implementation happens on branch
  `provider-platform` in `.worktrees/provider-platform`; the main checkout is untouched.

## Documents

| File | Contents |
|---|---|
| [00-SCOPE.md](00-SCOPE.md) | Objectives, provider inventory, boundaries, status vocabulary, exclusions |
| [01-RESEARCH-REGISTER.md](01-RESEARCH-REGISTER.md) | Dated official sources per provider (auth, API, CLI, policy) |
| [02-FAILURES-AND-COMPLAINTS.md](02-FAILURES-AND-COMPLAINTS.md) | Real failure reports, severity, reproducibility and Hutch's answer |
| [03-PROVIDER-CAPABILITY-MATRIX.md](03-PROVIDER-CAPABILITY-MATRIX.md) | Per-provider models, protocols, auth, region, billing, capabilities, status |
| [04-ARCHITECTURE-AND-ADRS.md](04-ARCHITECTURE-AND-ADRS.md) | Architecture decisions, ADR links, schemas and compatibility |
| [05-IMPLEMENTATION-PLAN.md](05-IMPLEMENTATION-PLAN.md) | Bounded slices, file ownership, verification per slice |
| [06-VALIDATION-LEDGER.md](06-VALIDATION-LEDGER.md) | Exact commands, results, screenshots and verification gaps |
| [07-ROLLOUT-AND-MIGRATION.md](07-ROLLOUT-AND-MIGRATION.md) | Compatibility, account reconnection, rollback and merge procedure |
| `drafts/` | Research fragments from the research team (primary-source input) |
| `artifacts/` | Machine-readable evidence: environment probes, test logs, captures |

## Status vocabulary (used everywhere)

| Status | Meaning |
|---|---|
| `implemented` | Hutch has a real code path for this route and it passes focused tests |
| `live-verified` | A real provider account exercised the route; date and account class are recorded |
| `implemented-unverified` | Real code path exists; no live account has been exercised |
| `documented` | Only documented (official source read); no Hutch code path |
| `experimental` | Implemented but gated or explicitly not production-ready |
| `blocked` | Legitimate integration is impossible now (no credential, no publisher registration, policy) |
| `retired` | The provider removed the flow; Hutch must not recreate it |
| `deferred` | In the requested inventory but outside this delivery slice |

A mocked or recorded HTTP test never upgrades a status. Capability levels are separate and are
recorded as `documented`, `advertised`, `observed` or `live-verified` with a source and date.
