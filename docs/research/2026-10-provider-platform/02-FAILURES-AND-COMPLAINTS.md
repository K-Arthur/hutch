# 02 - Failures and complaints

Compiled 2026-10-30 from primary reports and vendor documents. Purpose: every Hutch improvement in
this package answers a documented failure. Evidence grades are stated; a single report is never
presented as a prevalence estimate.

## Evidence rules

- Vendor-documented behaviour is stated as fact for that vendor's current docs.
- GitHub issue IDs are linked where the research verified them; issue text is treated as one report
  until independently reproduced, and its state/date matters more than its tone.
- Anecdotes from forums are not counted as evidence of a widespread problem; they motivate tests only.
- Hutch's existing recorded fixtures are not evidence that a provider works live.

## Authentication and token lifecycle

| Failure | Evidence | Severity | Hutch answer in this package |
|---|---|---|---|
| Failed login deletes the stored credential file | codex issue #46430 (GitHub, ANECDOTE) | High, destructive | Account disconnect is explicit and separate from sign-in failure; local credential removal reports exactly what happened; a failed flow must not delete a working credential. |
| Device/token exchange fails on Windows | codex issue #40839 (GitHub, ANECDOTE) | Medium, platform-specific | Account status distinguishes local configuration from live sign-in; platform-specific auth claims stay untested and documented. |
| OAuth refresh lock stalls other processes up to 60s | claude-code issue #105729 (GitHub, ANECDOTE, created 2026-10-28) | High, concurrency | Refresh must be single-flight per account and must not hold a process-wide lock; concurrency protection is a documented requirement even though Hutch's own flow differs. |
| Repeated 401 after reauthorization | claude-code issue #18225 (GitHub, ANECDOTE) | Medium | Account profiles surface needs-sign-in/expired states and never present a fake connected state. |
| Process-global ANTHROPIC_API_KEY redirects billing away from a subscription | Vendor/CLI docs (VENDOR-SECONDARY) | High, silent billing change | Connection-scoped credentials and an explicit source label; ambient keys only for official hosts. |
| Retired Qwen OAuth yields "auth succeeded but quota error" | qwen-code issues #3281 and #3382 (GitHub, ANECDOTE) | Medium, confusing recovery | Qwen Portal OAuth is recorded as retired and not implemented; a retired route fails with an explanation instead of an empty catalogue. |
| Consumer subscription bridges (Claude Max proxies) | Anthropic terms and OpenCode docs (VENDOR) | Blocking, policy | Blocked in the catalogue; no unofficial proxy is implemented. |
| GitHub Copilot subscription reuse via device OAuth | OpenCode implementation reports; no GitHub page authorizes it (UNVERIFIED) | High, policy/risk | Blocked in the catalogue; GitHub documents the Copilot SDK instead; no client impersonation. |

## Routing, billing and account attribution

| Failure | Evidence | Severity | Hutch answer in this package |
|---|---|---|---|
| BYOK gateway falls back to system credentials and bills the gateway | Vercel AI Gateway docs (VENDOR) | High, unexpected payer | Gateways are distinct catalogue identities; real returned model and routing metadata are documented as required receipts; a gateway is never described as the upstream vendor. |
| Gateway serves a different final model than requested | OpenRouter routing/fallback docs (VENDOR) | Medium, identity mismatch | The served model is recorded from the response; no silent substitution claim; the requested/actual distinction is part of the compatibility contract. |
| Alias models hide a different upstream model | LiteLLM docs (VENDOR) | Medium | Gateway alias identity is documented; capability and price claims are scoped to the gateway route, not the upstream vendor. |
| Deprecated gateway API removed | Cloudflare AI Gateway deprecation notice, 2026-10-02 (VENDOR) | Medium, future breakage | Gateway routes stay documented-only until a current contract is verified; no shipped adapter depends on the removed API. |
| Ollama OpenAI-compatible endpoint silently truncates context | Ollama context docs and openclaw issue #4028 (VENDOR + ANECDOTE) | High, silent data loss | Native Ollama route sets num_ctx explicitly; a fit/window check refuses or warns instead of truncating. |
| Router/provider failure silently changes model | Existing repo research (VENDOR/ANECDOTE mix) | High | Explicit selection; no automatic paid fallback; fallback chains are existing Hutch mechanisms with approval and reservation, not provider-side surprises. |

## Runtime, process and cancellation

| Failure | Evidence | Severity | Hutch answer |
|---|---|---|---|
| Stop does not stop spawned sub-agents | claude-code issues #95138, #73916, #98708 (GitHub, ANECDOTE) | High | Hutch owns process groups and cancellation; external runtimes are registered only with an explicit lifecycle and permission model. |
| Event stream loses events | OpenCode issue #25657 (GitHub, ANECDOTE) | Medium | Durable session history is used instead of relying on a volatile event stream; runtime registry does not treat stream delivery as durability. |
| External CLI tools bypass Hutch budgets/approvals | Repo audit (draft 04, REPO) | High | Only the built-in runtime reserves usage before provider calls; CLI runtime routes stay description-only or require an explicit future contract; no silent enabling. |
| ComfyUI has no documented built-in auth | Vendor docs (VENDOR) | High if exposed | Local-only usage; never exposed by Hutch as a public endpoint. |

## Media, async jobs and retention

| Failure | Evidence | Severity | Hutch answer |
|---|---|---|---|
| Provider shuts down a media API and the documentation lags | OpenAI Sora/Videos shutdown 2026-09-24 while the guide still describes it (VENDOR, contradictory) | High, dead route | Media matrix records retired routes; none are stubbed; adapters are not added for dead APIs. |
| Async job cannot be cancelled once running | MiniMax video docs: only queued tasks cancel (VENDOR) | Medium, paid work continues | The existing job service distinguishes cancel_unconfirmed from cancelled; no automatic replay of paid submissions. |
| Result URLs expire before retrieval | fal webhook results ~1h (shorter for large results), MiniMax async TTS URLs ~9h, xAI ephemeral URLs (VENDOR) | High if ignored | Existing media contract fetches bytes immediately and stores them; no URL is persisted as the result. |
| Moderation failures are billed as FAILED tasks | Runway docs (VENDOR) | Medium, surprising charge | Failure receipts must say whether the provider billed; uncertain outcomes stay held for reconciliation. |
| Voice cloning without explicit consent | API docs lack a consent field; Google has the strongest documented consent-recording control (VENDOR) | High, abuse | Voice cloning is not exposed; consent/abuse requirements recorded in the matrix before any implementation. |
| Music generation closed to new users | MiniMax paid music notice, 2026-08-20 (VENDOR) | Medium | Recorded as unavailable for new accounts; not advertised. |

## Hutch's own defects found during this work

| Defect | Evidence | Fix in this package |
|---|---|---|
| Compatibility matrix claims Anthropic has no model-list operation | draft 04 vs providers/claude.py list_models/probe_models | compat.json corrected; docs updated. |
| Compatibility matrix says the OpenCode executor is unavailable/never launched | draft 04 vs runtime/opencode.py governed serve process | compat.json state corrected to experimental with its real boundary. |
| Docs claim Hutch chat is text-only | provider-compatibility.md vs image-input commit dcc85e85 | docs corrected: image input is implemented and route/model gated. |
| Provider identity duplicated across six constants and two validators | draft 04 | New validated provider catalogue is the single identity source for grouping/reporting; legacy routing constants remain for compatibility and are to be consolidated incrementally. |
| Media adapters outside the usage/reservation ledger | draft 04 | Recorded as a known gap; no new unverified adapter was added. |

No claim in this document is a prevalence estimate. Open issues referenced above were located through
the GitHub API by the research team on 2026-10-30; their state can change.
