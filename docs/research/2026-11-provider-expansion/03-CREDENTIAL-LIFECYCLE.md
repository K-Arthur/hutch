# 03 - Phase 2 design: credential and OAuth lifecycle (2026-11)

Date: 2026-11-06. Phase 2 of `docs/realignment/provider-expansion-2026-11/`. Research first, then
the design and the real evidence. This extends `01-FAILURE-MINING.md`.

## Research questions

1. What must never be lost when a refresh or a reauthorization fails?
2. How does a rotating refresh token stay single-use across real processes?
3. Which sign-in flows are officially supported, and which cannot work headless or remotely?
4. How should an expired or revoked credential be shown without a fake connected badge?

## Findings

| Question | Finding | Source |
|---|---|---|
| Rotating refresh | Providers rotate refresh tokens on use. Two concurrent spenders can invalidate the grant; the loser must reuse the first result, not post its own refresh. | claude-code [#27933](https://github.com/anthropics/claude-code/issues/27933), [#43392](https://github.com/anthropics/claude-code/issues/43392), [#25609](https://github.com/anthropics/claude-code/issues/25609); codex app-server #10332. |
| Failed login | A failed sign-in or refresh must not delete a working credential. The prior package recorded a client that did. | codex #46430 (ANECDOTE, prior package). |
| Ambient keys | A process-wide key can silently replace the chosen account and change the payer. Connection-scoped credentials and an explicit source are required. | claude-code [#12352](https://github.com/anthropics/claude-code/issues/12352). |
| Loopback sign-in | OpenAI's Sign in with ChatGPT open-source flow is a local PKCE/OIDC callback. The preview documents its limits; it does not document a device-code flow for this client. | [SIWC overview](https://developers.openai.com/siwc/token-sharing-open-source), [preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations). |
| Device code | Codex CLI supports device-code sign-in for headless hosts, but that is the official CLI's own flow. Hutch delegates to the official CLI rather than reimplementing its client. | Codex auth writeups (2026); [Codex app-server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server). |
| Third-party OAuth | Anthropic and Google prohibit third-party reuse of subscription OAuth. Only the unmodified official CLI may hold that sign-in. | [Anthropic legal](https://code.claude.com/docs/en/legal-and-compliance); [Gemini CLI terms](https://geminicli.com/docs/resources/tos-privacy/). |
| Revocation | Provider revocation is a separate act from clearing local tokens. A failed revocation request is "unconfirmed", not "revoked". | OpenAI revocation endpoint in the SIWC discovery document; Hutch's existing disconnect wording. |

All sources accessed 2026-11-06.

## Decisions

- **D1 - Credential state is explicit.** `chatgpt_status.account_row` projects a saved account into
  `active`, `expired`, `revoked` or `missing`. `AccountProfile` carries that state and its expiry;
  readiness maps `expired` to `authentication_expired` and `revoked` to `needs_authentication`.
- **D2 - A refresh credential is enough for active.** An account with a refresh token is active even
  when its access token is past expiry, because Hutch can refresh it. An access token inside the
  60-second skew with no refresh token is expired, not active.
- **D3 - A failed refresh changes nothing.** The auth store writes only after a complete, validated
  response. A failed refresh leaves the access and refresh tokens exactly as they were.
- **D4 - Single-flight is per account and cross-process.** The existing exclusive file lock is held
  across the refresh request; the second process re-reads the account after the lock and reuses the
  rotated token. A real-process test proves one provider refresh for two contenders.
- **D5 - The loopback boundary is stated, not bypassed.** ChatGPT sign-in works only when the
  browser can reach the Hutch host's `127.0.0.1` callback. A remote dashboard shows that boundary
  and offers the API-key or official-CLI path. Hutch does not implement an undocumented device-code
  client for SIWC.
- **D6 - OpenCode keeps its own sign-in.** OpenCode's OAuth/device flow runs through its official
  server API and CLI; Hutch only reuses an API key on explicit request. No OpenCode OAuth token is
  imported into Hutch.
- **D7 - Revocation wording matches what happened.** The UI distinguishes "expired", "revoked",
  "not connected", "identity only" and "plan use authorized"; disconnect reports remote revocation
  as confirmed or unconfirmed.

## What changed

| Commit | Change |
|---|---|
| (this phase) | `chatgpt_status.py` projection; `AccountProfile.credential_state`; readiness mapping; provider-page JSON fields. |
| (this phase) | Connections page and provider readiness show active/expired/revoked; `has_key` requires an active ChatGPT credential. |
| (this phase) | Real-process refresh contention test; failed-refresh preservation test; remote loopback notice. |
| (this phase) | A malformed account record no longer turns model discovery into a 500; it reports an incomplete record. |

## Real-stack evidence (2026-11-06)

Isolated state with three ChatGPT accounts (active with a refresh token, expired access with no
refresh, revoked) and three connections. Server on `127.0.0.1:18892`; no provider call was made.

```
GET /api/v1/provider-accounts
  chatgpt-active  | ready   | active  | available
  chatgpt-expired | expired | expired | authentication_expired
  chatgpt-revoked | revoked | revoked | needs_authentication
```

The Providers page renders "authentication expired" and "needs authentication"; the Connections
page renders "connected", "expired - sign in again" and "revoked - sign in again". Captures at
360/768/1280/1920 in light and dark:
`docs/realignment/artifacts/provider-expansion-2026-11/phase2/`. 32/32: 0 console errors, 0 failed
requests, 0 px overflow. The first run exposed a real defect: a partial account record raised
`KeyError` during model discovery and returned HTTP 500. Fixed by requiring an active credential in
`has_key` and reporting incomplete records as a model-list error.

## Validation

| Check | Result |
|---|---|
| chatgpt_status, refresh processes, auth, concurrency, provider accounts/readiness/surfaces | 56 passed |
| connections plus provider suites after the fix | 97 passed |
| Visual | 32 captures clean after the fix |
| Real processes | one refresh for two contenders; both received `access-2`; stored refresh became `refresh-2` |
| Failed refresh | stored `access-1` / `refresh-1` unchanged |

## Limits and deferred

- No live OpenAI account was exercised: the SIWC route is eligibility-gated and the owner's
  credentials were not used for an OAuth flow. The lifecycle is fixture-tested; status is not a
  live-eligibility claim.
- Remote/WSL loopback sign-in is documented as unavailable, not implemented. A device-code client
  for SIWC is not documented and stays out.
- OpenCode's device/OAuth flow was not exercised interactively; Hutch's reuse path is tested, and
  the flow remains owned by the installed official server/CLI.
- Revocation was tested against a scripted endpoint. A real confirmed revocation needs a live
  account and is deferred to the Phase 3 OpenAI work if the owner approves it.

## Next

Phase 3a - OpenAI (API, Sign in with ChatGPT, native Codex runtime), with the owner's credential and
a spend/eligibility check before any paid call.
