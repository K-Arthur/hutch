# 07 - Rollout and migration

## Compatibility

- `connections.json`: new fields are optional and derived when absent (`provider`, `auth_method`,
  `category`, `region`). Existing connection rows load unchanged; keys stay in the same protected
  location and are never copied into the database or page.
- `compat.json`: new routes are additive; existing route ids and validation rules are unchanged.
- `providers.json` is a new bundled catalogue. A malformed or missing catalogue must fail closed for
  the provider surfaces (`/providers`, provider API) without breaking the existing model picker or
  runs. It is not persisted state, so no database migration is involved.
- Model specs (`connection/model`) are unchanged. Provider identity is used for grouping, readiness and
  documentation; it never rewrites a saved model spec.
- No new required environment variable is introduced.

## Account reconnection

- Existing named connections keep working. If a template later adds `provider`/`auth_method`, a legacy
  row derives them from the template or connection name at load time.
- Disconnecting an account keeps distinguishing local credential removal from provider-side revocation;
  provider revocation is requested only where an official revoke endpoint exists.
- OAuth/profile status is derived from local state; a missing/expired credential shows a repair state,
  never a fabricated connected state.

## Rollback / downgrade

- Revert the slice commits on `provider-platform`; because the catalogue is bundled data and the
  connection fields are optional, an older Hutch build reads the old fields and ignores the rest.
- No state migration is applied, so no down-migration is needed.
- The branch is merged only after the independent verifier passes; if main has moved, resolve by
  rebasing the slice commits onto current main and rerunning the focused suites, never by force-push.

## Merge procedure (worktree isolation)

1. Freeze the worktree: `git status` clean, all slice commits present, ledgers updated.
2. Fetch/observe main; if it moved, rebase `provider-platform` onto it and rerun checks.
3. In the main checkout, ensure no other session's uncommitted files overlap the branch's changed files
   (`git diff --name-only` on both sides). If they overlap, stop and report instead of touching their
   work.
4. `git merge --no-ff provider-platform` (or fast-forward if main is an ancestor), then rerun the named
   suites on main and verify `git status` contains no changes from our merge.
5. Record the final main commit SHA in the delivery report.

## Known operational notes

- Live verification covers only the two dated DeepSeek text routes; every other hosted route must stay
  implemented-unverified or documented and must never be relabelled live-verified from a listing or a
  single successful call.
- Local inference discovery is read-only over loopback and sends no credential. A hostile page cannot
  trigger it; the server calls it locally through the authenticated dashboard.
## Known security gap in custom endpoints

Outside Strict Offline a custom endpoint is operator-configured and keeps the existing credential scoping,
but there is no private-range allowlist or redirect/DNS pinning in the provider layer. Recorded as a
carried-over hardening gap (00-SCOPE, 04-ARCHITECTURE-AND-ADRS, docs/provider-platform.md); do not present
custom endpoints as validated against SSRF for untrusted input until that gap is closed.

## Live verification addendum (2026-10-30)

Two text routes are live-verified with owner-authorized credentials: direct DeepSeek via the built-in runtime
and managed OpenCode runtime with a DeepSeek model. Live evidence is recorded under
artifacts/live-verification/ with a summary.json consumed by the research audit. If the ephemeral test
credential is rotated or removed, the live-verified rows must be re-evaluated or downgraded; they are dated
2026-10-30 and must not be presented as a guarantee for other accounts, models or capabilities.
## Gemini route rollout (2026-10-31)

The Gemini API route is additive and needs no state migration:

- **Existing accounts and bots** keep working unchanged. No stored connection row is rewritten, no
  protocol value changes meaning, and the built-in runtime still routes every existing spec the same way.
- **Adding a Gemini account** means adding the `google-gemini` connection template: `hutch connections add
  google-gemini`, then paste a key or export `GEMINI_API_KEY`. Existing `connections.json` files without
  the template load exactly as before, because the template list is bundled rather than stored.
- **A new protocol value** (`gemini`) joins `openai-chat` and `anthropic` in the connection protocol list.
  Rows written by an older build cannot contain it, so a downgrade is safe: an older Hutch refuses a
  `gemini` protocol row with a clear "unknown protocol" error instead of misrouting it.
- **Ambient-key scoping**: `GEMINI_API_KEY` is sent only to `generativelanguage.googleapis.com`. A custom
  base URL needs its own named connection key, and a withheld key produces an explicit hint in the failure.
- **Rollback** is deleting the connection or selecting a different model; nothing else changes. A run that
  was interrupted mid-stream keeps Hutch's normal uncertain-outcome reservation because this adapter does
  not add a second accounting path.
- **Thought signatures** live only in memory. Downgrading or restarting mid-conversation is not dangerous,
  but it can produce the provider's `MISSING_THOUGHT_SIGNATURE` error on the next tool-using turn. That is
  reported to the user with the reason; it is not retried silently and never replaced by another model.

Reconnection requirements: none. A Gemini key is a long-lived API key with no refresh token, so there is
no rotation, region or refresh-window state for Hutch to track. Revoking the key in Google AI Studio takes
effect on the next request; Hutch reports the provider's 401/403 as an `auth` failure.

Verification boundary after this rollout: contract-tested, not live-verified. Do not describe the Gemini
route as working until a real key has been exercised against the live API, and record that run in the
validation ledger with a date and artifact.
