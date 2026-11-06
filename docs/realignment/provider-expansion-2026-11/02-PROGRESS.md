# Progress: provider expansion (2026-11)

Update at every checkpoint. Keep entries short and factual.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | done 2026-11-06 | Phase 0 commit | none this phase; re-read 2026-10-31 Xiaomi evidence | - |
| 1 Route resolution | not started | | | |
| 2 Credential lifecycle | not started | | | |
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

## Review findings log

- 2026-11-06, Phase 0, baseline test hashed lifecycle state (`archived`) as preset content; fixed
  by excluding it after proving content equality.
- 2026-11-06, Phase 0, `server/templates/providers.html:18` hardcodes obsolete live evidence and
  mislabels documented/blocked routes as implemented-unverified; queued for Phase 1.
- 2026-11-06, Phase 0, light and dark captures are identical because the theme is fixed; recorded
  as G16, not a capture failure.

## Open items and deferred

- Kimi Coding needs its own identity/template (G2); Qwen has no working route (G3); Claude CLI
  delegate and Codex native runtime are absent (G4, G5); Antigravity decision needed (G6).
- Z.AI Coding Plan eligibility for Hutch and OpenCode Go unattended use need vendor confirmation
  before those routes leave documented/experimental.
- Out-of-scope providers are listed at the end of `00-GAP-AUDIT.md`.
