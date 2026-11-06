# Progress: provider expansion (2026-11)

Update at every checkpoint. Keep entries short and factual.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | done 2026-11-06 | Phase 0 commit | none this phase; re-read 2026-10-31 Xiaomi evidence | - |
| 1 Route resolution | done 2026-11-06 | 9f0fa4ed | none this phase; no provider call | - |
| 2 Credential lifecycle | done 2026-11-06 | Phase 2 commit | fixture lifecycle; no provider call | - |
| 3 Flagship providers | not started | | | |
| 4 Hosted and gateways | not started | | | |
| 5 Local and custom | not started | | | |
| 6 Media, speech, search | not started | | | |
| 7 Frontend | not started | | | |
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

## Phase 0 outputs (2026-11-06)

- Baseline: `npm run check:agent` passed; 26 focused provider/media test files ran (433 passed, 1
  failed). The failure was `test_catalog.py::test_the_presets_came_out_of_code_unchanged`: `Bot`
  gained `archived`, which the digest hashed. Recomputing with the pre-change field set reproduced
  every recorded digest, so preset content is unchanged. Fixed by excluding `archived` from the
  digest (test-only).
- `docs/research/2026-11-provider-expansion/00-GAP-AUDIT.md`: baseline, G1-G18 cross-cutting
  findings, missing identities, all 62 catalogue rows, ordered backlog.
- `docs/research/2026-11-provider-expansion/01-FAILURE-MINING.md`: auth, routing, retry, tool,
  local-engine and media failures classified fixable/mitigable/vendor-side, with test ideas.
- Visual capture: `docs/realignment/capture_provider_pages.py` captured Providers, Models and
  first-run at 360/768/1280/1920 in light and dark; 24/24 with 0 console errors, 0 failed requests,
  0 px overflow. Artifacts under
  `docs/realignment/artifacts/provider-expansion-2026-11/phase0/` (`results.json`).
- Real stack: isolated `HUTCH_STATE_DIR` + `hutch init` + `hutch serve --port 18890`; no provider
  call was made.

## Phase 1 outputs (2026-11-06)

- `9fffa9ab` Providers banner is derived from `LIVE_VERIFIED_EVIDENCE` grouped by route/date plus
  catalogue status counts. The old hardcoded sentence (which omitted Xiaomi and mislabeled
  documented/blocked entries) is gone.
- `d7f53448` `providers/routing.py` resolves `(provider, account, account_source, billing, model,
  runtime, protocol, endpoint, status)` from local facts, labels ambient keys, withholds them from
  non-official hosts, and refuses to pick between accounts. Exposed at
  `/api/v1/provider-resolution`. `resolve_chain` flags a subscription-to-metered hop.
- `36673256` schema version 91 writes the implicit `openai-compatible/` prefix into saved `model`,
  `fallbacks`, `escalation.to` and `task_routes`. Behavior, billing and order are unchanged;
  already explicit routes are untouched. Migration module keeps frozen `store.py` at its cap.
- `9f0fa4ed` `SpendGuard` refuses a fallback or escalation from a subscription primary to
  per-token/credits before the call.
- `docs/research/2026-11-provider-expansion/02-ROUTE-RESOLUTION.md` records the research, design,
  real-stack output and limits.
- Design docs updated in the same series: `docs/provider-platform.md` (resolver and billing
  boundary), `docs/models.md` (resolution API and refusal rules),
  `docs/realignment/provider-compatibility.md` (resolution subsection), and ADR-0028.
  `docs/runtime-setup.md` is unchanged because this phase did not change runtime behavior.

## Phase 2 outputs (2026-11-06)

- `chatgpt_status.py` projects a saved account into `active`, `expired`, `revoked` or `missing`
  with `can_refresh` and the expiry; `chatgpt_auth.accounts()` shrank to use it.
- `AccountProfile` carries `credential_state` and `credential_expires_at`. Readiness maps `expired`
  to `authentication_expired` and `revoked` to `needs_authentication`; `/providers` and
  `/legacy/connections` show the state instead of a green "missing" chip.
- `ConnectionBook.has_key` for a ChatGPT account requires an active credential; expired/revoked
  accounts no longer trigger model discovery.
- Single-flight is proven with two real processes contending for one rotating token; a failed
  refresh leaves the stored access and refresh tokens unchanged.
- A remote dashboard states that the ChatGPT loopback callback cannot complete there and points to
  an API key or the official CLI; no undocumented device-code client was added. OpenCode keeps its
  own official OAuth/device flow.
- `docs/research/2026-11-provider-expansion/03-CREDENTIAL-LIFECYCLE.md`, ADR-0029, and updates to
  `provider-platform.md`, `models.md`, `runtime-setup.md`, `connections.md`.
- Real UI observation: three synthetic ChatGPT accounts (active, expired, revoked) on an isolated
  server; API states matched; 32/32 captures clean at four widths in light and dark.

## UI correction pass (2026-11-06, after Phase 2)

- Root cause: the server templates used `.list-row`, `.plain-list` and `.card-actions`,
  but those classes were only defined in `style.css`, which these pages do not load. Rows
  had no alignment primitive, so content and actions stacked wherever the browser put them.
- Inline form buttons were 32px beside 44px fields: `.hutch-actions .btn` already used the
  routine height, but `.hutch-inline` did not. Inline actions are now 40px (44px at phone
  width), and the page header actions are 40px rather than 32px.
- The Connections "Add a connection" gallery was 37 cards each with an always-visible
  primary Add button. It is now one form with a template select, optional custom endpoint
  fields, and a collapsed template reference. The page is 4,219px tall at 1280 (was 7,658).
- Provider account actions now share a trailing edge: label input, Rename and Remove local
  key in one row on desktop; on phones the input and Rename share a row and Remove aligns
  to the same right edge.
- The disabled ChatGPT sign-in action is a ghost button, not a green primary; mobile page
  actions are equal-width full-row buttons.
- Validation: 32/32 captures at 360/768/1280/1920 in light and dark, 0 console errors, 0
  failed requests, 0 px overflow; keyboard order for the add form is template, name, base
  URL, key variable, Add, template reference, each with a 2px focus outline; 54 focused
  tests passed. Baseline browser failures (assistant settings tabs, first-run readiness,
  phone pairing confirm) reproduce at HEAD without these changes and are not caused here.

## Owner inputs (batch, answered 2026-11-06)

- Provisioned credentials: OpenAI, Anthropic, Google Gemini. Every other paid route is
  "blocked: no credential" for live purposes.
- Spend cap: discuss per phase; ask before the first paid call with route, model and token cap.
- Dependency approvals: both granted for Phase 4 (AWS SigV4 for Bedrock, Azure/Foundry auth). No
  dependency was added in Phase 0.

## Decisions log

- 2026-11-06: Phase 0 preset-digest fix excludes `archived`; content equality was proven against
  the pre-change `Bot` field set, so this is not a status change.
- 2026-11-06: Anthropic subscription OAuth stays out of Hutch. Only the official unmodified Claude
  Code CLI may be delegated to, with the user's own sign-in; no token import or proxy.
- 2026-11-06: Gemini CLI OAuth stays blocked (Google calls third-party use a terms violation).
  Google replaced Gemini CLI with Antigravity CLI on 2026-06-18; treat the `coding_cli` service
  claim as stale and decide in Phase 3c.
- 2026-11-06: The workspace is dark-only by product decision. The "light and dark" visual gate is
  scoped to the marketing site until a light theme is approved in Phase 7.
- 2026-11-06: Providers page live-evidence sentence is generated from evidence and statuses in
  Phase 1, not hand-maintained (G1).
- 2026-11-06: Route resolution never chooses an account when two or more could pay. An ambient key
  is labeled and never breaks the tie (D2, D3).
- 2026-11-06: A fallback or escalation from a subscription primary to per-token/credits is refused
  until the metered route is made primary. That configuration is the explicit consent (D4).
- 2026-11-06: Saved route specs are normalized to the provider prefix the runtime already used.
  The migration is additive in meaning: no spec, billing relationship or fallback order changes
  (D5, schema 91).
- 2026-11-06: A saved OAuth account has an explicit state (active, expired, revoked, missing). A
  refresh token is enough for active; expired/revoked accounts are not keys. A failed refresh keeps
  the stored credential (ADR-0029).
- 2026-11-06: ChatGPT sign-in stays loopback-only. Remote/headless hosts get an honest boundary and
  the API-key/official-CLI alternative; no undocumented device-code client is added. OpenCode owns
  its official OAuth/device flow.
- 2026-11-06: Revocation is reported as confirmed or unconfirmed; clearing local tokens is not the
  same act as provider-side revocation.

## Review findings log

- 2026-11-06, Phase 0, baseline test hashed lifecycle state (`archived`) as preset content; fixed
  by excluding it after proving content equality.
- 2026-11-06, Phase 0, `server/templates/providers.html:18` hardcodes obsolete live evidence and
  mislabels documented/blocked routes as implemented-unverified; queued for Phase 1.
- 2026-11-06, Phase 0, light and dark captures are identical because the theme is fixed; recorded
  as G16, not a capture failure.
- 2026-11-06, Phase 1, the first resolver draft imported the runtime registry at module load,
  creating a routing -> runtime -> builtin -> ladder -> routing cycle; the import is now lazy.
- 2026-11-06, Phase 1, `store.py` is frozen at its line cap, so the migration lives in
  `route_spec_schema.py` and is appended without growing the file.
- 2026-11-06, Phase 1, the surface test asserted the obsolete hardcoded banner; it now asserts the
  derived routes and status counts.
- 2026-11-06, Phase 1, the main design docs and ADR were not updated with the code in the first
  pass; corrected in the same series with ADR-0028 and the three design-doc updates.
- 2026-11-06, Phase 2, the real populated-state capture exposed a 500: a partial ChatGPT account
  record raised `KeyError` during model discovery. Fixed by requiring an active credential in
  `has_key` and reporting an incomplete record as a model-list error.
- 2026-11-06, Phase 2, `has_key` treated an expired ChatGPT access token as usable because it only
  checked plan scope; corrected to require an active credential.
- 2026-11-06, Phase 2, design docs initially lagged the code again; corrected in this series with
  ADR-0029 and four doc updates.

## Open items and deferred

- Kimi Coding needs its own identity/template (G2); Qwen has no working route (G3); Claude CLI
  delegate and Codex native runtime are absent (G4, G5); Antigravity decision needed (G6).
- Z.AI Coding Plan eligibility for Hutch and OpenCode Go unattended use need vendor confirmation
  before those routes leave documented/experimental.
- Out-of-scope providers are listed at the end of `00-GAP-AUDIT.md`.
- Phase 1 API only: the dashboard picker does not yet show the resolved tuple before the first send
  (Phase 7). The resolver is read-only and not persisted per run.
- Billing-crossing refusal covers subscription-to-metered only; a local/free primary falling back to
  a hosted route keeps the existing first-hosted approval path.
- Account identity is still the spec prefix; a separate Bot account field would change how saved
  routes are interpreted and is deferred.
- Phase 2 used synthetic account records: no live OpenAI SIWC sign-in, refresh or revocation was
  exercised. The route is eligibility-gated; live OAuth is deferred to Phase 3a with owner approval.
- Remote/WSL loopback sign-in is documented as unavailable, not implemented. OpenCode's official
  device/OAuth flow was not exercised interactively in this environment.
