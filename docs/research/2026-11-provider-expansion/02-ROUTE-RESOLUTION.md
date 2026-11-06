# 02 - Phase 1 design: explicit route resolution and status truth (2026-11)

Date: 2026-11-06. Phase 1 of `docs/realignment/provider-expansion-2026-11/`. Research first, then
the design, then the code and the real-stack evidence. This file extends `01-FAILURE-MINING.md`;
it does not repeat it.

## Research questions

1. Which route decisions must be refused rather than guessed when more than one account could pay?
2. How do current clients label ambient keys, fallbacks and model substitution?
3. What must a saved-route migration preserve?

## Findings that drove the design

| Question | Finding | Source |
|---|---|---|
| Account choice | A provider prefix does not name an account. Any automatic pick would decide who pays, and the failure is invisible until the bill. Refuse and name the candidates. | Existing Hutch readiness rule; Phase 0 G1/G15. |
| Ambient keys | A process-wide key can silently take over from the chosen subscription or account. Label the source and send ambient keys only to the official host. | [claude-code #12352](https://github.com/anthropics/claude-code/issues/12352); community billing guides (2026). |
| Silent substitution | Gateway and fallback routing can serve a different model without the caller knowing. A substitution must be configured, recorded and never cross who pays. | [OpenRouter model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks); [tragenx benchmark](https://tragenx.com/blog/openrouter-s-auto-routing-can-quietly-swap-how-your-model-behaves/). |
| Billing crossing | A subscription allowance falling back to a per-token model changes the payer. That is a spend decision, not an availability decision. | Master prompt rule; Phase 0 G4/G9. |
| Saved routes | `parse_spec` already treats a bare model name as `openai-compatible/<model>`. The saved document was less explicit than the runtime. Writing the prefix changes no behavior. | `providers/registry.py:parse_spec`; ADR-0026 compatibility section. |

All sources accessed 2026-11-06.

## Decisions

- **D1 - One tuple.** `providers/routing.py` returns `(spec, provider, account, account_source,
  billing, model, runtime, runtime_status, protocol, endpoint, status)`. Status comes from the
  existing readiness vocabulary; the resolver adds the tuple and never invents a new state.
- **D2 - No account guessing.** A spec that names a provider while two or more named accounts map
  to that provider resolves to `needs_configuration` with `account=""` and the candidates listed.
  An ambient key does not break the tie.
- **D3 - Ambient keys are labeled and scoped.** A usable ambient key resolves the account as
  `ambient environment (OPENAI_API_KEY)`; a key aimed at a non-official endpoint is withheld and
  reported as `needs_authentication`. No credential value is returned.
- **D4 - Substitution is visible and never crosses billing.** The resolver always reports
  `substituted=False`. A fallback or escalation from a subscription primary to per-token/credits is
  refused in `SpendGuard` before the call; configuration (making the metered route primary) is the
  explicit approval. The runtime's existing switch log already records `from_model`, `to_model`,
  `reason` and `hosted` for each hop.
- **D5 - Saved routes become explicit, not different.** Migration 91 writes the implicit
  `openai-compatible/` prefix into `model`, `fallbacks`, `escalation.to` and `task_routes`. It is
  idempotent and leaves already explicit specs byte-identical.

## What changed

| Commit | Change |
|---|---|
| `9fffa9ab` | Providers banner derived from live evidence and catalogue status counts; the hardcoded sentence is gone. |
| `d7f53448` | `providers/routing.py`, `/api/v1/provider-resolution`, ambient labeling, ambiguity refusal, billing-crossing flag. |
| `36673256` | `route_spec_schema.migrate`, wired as schema version 91 without growing frozen `store.py`. |
| `9f0fa4ed` | `SpendGuard` refuses a subscription-to-metered fallback before the call. |

## Real-stack evidence (2026-11-06)

Isolated state, two OpenAI accounts (`openai-personal`, `openai-work`) with no stored keys, and
`OPENAI_API_KEY` set to a non-secret placeholder in the server environment. Server:
`hutch serve --port 18891`; no provider request was made.

```
GET /api/v1/provider-resolution?spec=openai/gpt-4o
  account: ""            account_source: "not chosen: 2 named account(s)"
  billing: "unknown"     status: "needs_configuration"   substituted: false

GET /api/v1/provider-resolution?spec=openai-personal/gpt-4o
  account: "openai-personal"  account_source: "named connection"
  billing: "per_token"        status: "capability_unverified"  substituted: false

GET /api/v1/provider-resolution?spec=openai-work/gpt-4o
  account: "openai-work"      status: "capability_unverified"
```

The ambient key neither selected an account nor overrode the named account. The populated
Providers page was captured at 360/768/1280/1920 in light and dark:
`docs/realignment/artifacts/provider-expansion-2026-11/phase1/`. 24/24 captures: 0 console errors,
0 failed requests, 0 px horizontal overflow. The banner now names every live route and date:
DeepSeek 2026-10-30, OpenCode/DeepSeek 2026-10-30, Xiaomi text/tools/streaming/ASR/TTS 2026-10-31,
plus the actual catalogue status counts (3 implemented, 35 implemented-unverified, 1 experimental,
20 documented, 2 blocked, 1 deferred).

## Validation

| Check | Result |
|---|---|
| `tests/test_route_resolution.py` + surfaces/routes/readiness | 41 passed |
| `tests/test_migration.py` | 43 passed |
| resolution + authority + routes + builtin runtime | 119 passed |
| `npm run check:agent` | run after the docs update; see the progress ledger |
| Visual | 24 captures clean; the banner adds no focusable element, so keyboard traversal is unchanged. |

## Limits and deferred

- The dashboard route picker does not yet show this tuple before the first send; the API is the
  Phase 1 surface and Phase 7 builds the picker.
- Billing-crossing refusal covers subscription-to-metered only. A local/free primary falling back
  to a hosted route still uses the existing first-hosted approval path.
- The resolver is read-only and not persisted per run; the migration only makes saved specs
  explicit. A per-run route snapshot can reuse this tuple later without a second resolver.
- Account identity still comes from the spec prefix; there is no separate account field on a Bot.
  Changing that would alter how saved routes are interpreted, so it is deferred.
- No OAuth, token refresh or credential value is touched in this phase; that is Phase 2.

## Next

Phase 2 - credential and OAuth lifecycle: single-flight refresh, failed-login-never-deletes,
device-code and loopback flows, expired/revoked states, contending real processes.
