# ADR-0010: API contracts, event transport, and phone supervision

Status: partial implementation (2026-10-09). Slice: S8. Automated boundary tests pass; physical-device and live-network validation remain open.

## Decision

* **Contract first** (`docs/realignment/contracts.md`): Pydantic schemas cover health, status labels, conversations, messages, search
  results, and selected run/approval aliases under `/api/v1`. Conversation creation, message submission, archive, stop and approval
  resolution require an `Idempotency-Key` and persist request identity with the result. Versioned bot, run, approval, conversation
  and event lists are bounded; other command families and complete resource schemas remain open. Existing `/api/*` routes stay as
  compatibility paths.
* **Transport**: per-run and cross-run transcript SSE streams use database-backed cursors and `Last-Event-ID`. The cross-run stream
  orders transcript events by SQLite's committed event ID while preserving each run's local `seq`. Page reads detect a cursor outside
  retained history; clients fetch the bounded resource snapshot and replay transcript events from its watermark. Events are not pruned
  today. A separate schema-v11 resource outbox publishes material SQLite changes at `/api/v1/changes`
  and `/api/v1/changes/stream`, with history epochs, chained committed IDs and gap reconciliation.
  Snapshot resource state and `change_cursor` share a read transaction; UI invalidations preserve
  drafts/focus and include canonical approval decisions. See [ADR-0012](0012-resource-outbox-and-reconciliation.md).
  Connection-file changes are excluded. No interactive terminal or browser-handoff WebSocket route
  is implemented yet; those controls must use their own authenticated, sequenced contract.
* **Server owns** status, approval resolution, receipts, permissions and usage. The browser owns drafts, focus and view state. Optimistic UI
  may show "sending", never "done".
* **Remote phone supervision**: loopback remains the default. Remote mode requires the explicit `hutch serve --allow-remote` launch,
  one exact WebAuthn RP hostname/origin in `HUTCH_WEBAUTHN_RP_ID` and `HUTCH_WEBAUTHN_ORIGIN`, and a matching `HUTCH_ALLOWED_HOSTS`
  entry. Direct listeners must bind a private LAN or Tailscale IP with a trusted TLS certificate; wildcard and public binds are
  refused. A reverse proxy must be named in `HUTCH_TRUSTED_PROXIES` as exact IPs, and its HTTPS, Host, and client-address headers are
  accepted only from that socket peer. Uvicorn proxy rewriting remains disabled. No unauthenticated forwarded headers, owner token,
  or WebSocket is accepted as remote identity. The recommended initial remote path is Tailscale Serve forwarding to Hutch on
  loopback, with tailnet access rules restricted to the operator; LAN access requires a trusted HTTPS certificate.
* `hutch pairing create` issues a single-use 60-second code; `--allow-start` can add the Start capability. Code exchange creates only a
  five-minute enrollment cookie with a 16-challenge registration ceiling. Passkey registration requires user verification and exact
  RP/origin validation; successful registration creates a separately revocable credential and HttpOnly session cookie. Synced
  passkeys are accepted, so a credential is not represented as proof of one physical phone. Authenticated sessions expire after
  30 minutes idle or eight hours absolute;
  background polls and SSE do not extend idle time. Local CLI pairing management revokes credentials and all their sessions.
* The phone principal is deny-by-default. Its route inventory grants Monitor, Review, and optional Start; each Start also requires the
  local owner to opt that Bot in with `hutch bot update NAME --remote-start`. Bot pause only disables scheduled work; an explicit
  phone start remains an on-demand command when both Start gates are enabled. Paired phones cannot change bot settings, models, tools,
  provider connections, schedules, secrets, device enrollment, or computer-control settings. They can inspect bot/run status and
  transcript, decide an exact pending action once or deny, stop/resume within current event checks, and start work under the Bot's
  existing policy. Permission checks precede replay/admission, and Store rechecks remote authority before a queued run is claimed.
  Revoking a credential or disabling a Bot cancels its unclaimed remote starts; already claimed work stays visible and needs explicit
  Stop. Remote WebSockets and computer interaction remain unavailable.
* **Terminal**: governed command execution first (exists). An interactive PTY (sandboxed, bounded scrollback 1 MiB, resize, cancel, text transcript)
  is built only after the WebSocket auth above lands; **control ownership is a lease** (`agent` | `human`) so input never races; stale or replayed
  frames carry a sequence number and are dropped after reconnect.
* **Trust boundaries**: the web client and the installed executor are separate. A hosted marketing site never talks to `localhost`.
* A sleeping host cannot run anything: the UI shows queued/offline/reconnecting with the next action. A hosted remote executor is a separate,
  opt-in product and is not built here.

## Consequences

Current boundary: pairing, passkey ceremonies, database-backed sessions, route capabilities, phone supervision, and TLS/proxy checks
have local regression coverage, including a real Uvicorn HTTPS socket test. The phone UI hides private content when its session expires
or is revoked and requires explicit reconciliation before retrying an uncertain command. iOS Safari/Android Chrome, live Tailscale
Serve, LAN certificate installation/renewal, and network isolation have not been manually validated. Remote access remains disabled
unless explicitly launched and configured; keep it private. No PTY or browser-control WebSocket route, remote computer input,
production remote-support claim, or transcript-retention policy exists.

## Security references checked

* [W3C Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/) — exact origin validation, required user verification,
  backup-eligibility state, and why signature counters require different handling for single-device and multi-device credentials.
* OWASP [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
  [CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), and
  [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) cheat sheets — server-side idle/absolute
  expiry, CSRF tokens with SameSite defense in depth, and deny-by-default capabilities.
* Tailscale [Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve), [Serve](https://tailscale.com/docs/features/tailscale-serve),
  [Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel), [Funnel](https://tailscale.com/docs/features/tailscale-funnel),
  [Grants](https://tailscale.com/docs/features/access-control/grants), [ACL defaults](https://tailscale.com/docs/reference/examples/acls),
  and [HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates) — Serve is tailnet-only and subject to policy;
  Funnel is public when configured and shares an exclusive port with Serve. At review time, Tailscale's Serve page says Funnel is
  enabled by default while its Funnel feature and CLI pages say it is disabled by default. Inspect actual Serve/Funnel status and the
  effective policy; do not infer exposure from defaults. New tailnets start with an allow-all ACL policy. Tailscale HTTPS hostnames
  are published in certificate transparency logs even though Serve traffic remains tailnet-restricted. The current Tailscale
  [Serve proxy source](https://github.com/tailscale/tailscale/blob/main/ipn/ipnlocal/serve.go#L1014-L1036) sets forwarded Host/For
  headers and sets forwarded Proto when TLS terminates, and marks Funnel traffic; Hutch's trusted-proxy checks depend on these
  behaviors, reject the Funnel marker, and still require its own passkey authentication.
