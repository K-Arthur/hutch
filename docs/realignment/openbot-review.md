# OpenBot reference review

Reviewed 2026-10-08. Source pinned to CopilotKit/OpenBot
`59e28898238fe8510275dc02bc25cf9f4a90a77c`. The public GitHub connector and a temporary
read-only clone were used; dependencies were not installed and its services, providers,
containers and desktop integration were not run. No code was copied. Its
[README](https://github.com/CopilotKit/OpenBot/tree/59e28898238fe8510275dc02bc25cf9f4a90a77c)
describes an alpha template with a gateway and a computer per bot. Those architectural claims
are useful reference material, not live verification or a reason to replace Hutch's Python,
FastAPI and SQLite platform.

The supplied signed GitHub video failed in the native browser with “Unable to play media”
before any frame could be observed. It is not visual evidence. Its temporary authorization
URL is deliberately absent from this repository.

The product-level comparison with Grok Bot's official documentation is maintained separately in
[`../research/grok-bot-product-review-2026-10-09.md`](../research/grok-bot-product-review-2026-10-09.md).
OpenBot remains a source-code/security reference; Grok Bot is the stronger reference for the
message-first named-Bot, coordinator, and human-takeover interaction model.

## Useful patterns observed in code

- [Inline approvals](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/app/src/components/approvals/inline-approval.tsx)
  and the [inbox](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/app/src/components/approvals/inbox.tsx)
  use the same request query and decision operation. A pending decision remains outside the
  collapsed activity group. Hutch follows this authority model with one card renderer in chat
  and the Needs you drawer; server compare-and-swap and idempotency govern both.
- [Approval execution](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/server/src/approvals/execute.ts)
  resumes persisted arguments and rechecks grants. Reviewing Hutch found that file requests
  fingerprinted only the path, and browser typing only the selector. Hutch now binds the full
  write payload and reviewed file revision; browser typing binds text, URL and profile, and
  browser mutations always ask. Shell requests include effective timeout, workspace and
  containment mode. HTTP(S)/WebSocket browser destinations are pinned by a local proxy with Chromium fixture coverage; the configured
  Chromium also sends no direct WebRTC UDP to a loopback STUN fixture, while the default-browser negative control does. This does
  not finish browser account authority, OS-level browser containment, coverage for other protocols, or live public egress validation.
- The [computer gateway](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/server/src/computer/gateway.ts)
  governs actions through server state, records decisions before effects, and validates human
  gesture names at runtime. Hutch's future control routes must similarly validate capabilities
  at the executor, record authority before effects, and reject stale lease epochs. Static types
  or a UI hiding a button are insufficient.

## Reports translated into acceptance scenarios

Issue state below is the state retrieved on the review date. Each is an individual report,
not prevalence, a benchmark or proof that the present version still fails. Closed reports
are historical defects unless a pinned inspection establishes otherwise.

| Report | Evidence and Hutch acceptance scenario |
|---|---|
| [735: read-only folder grant](https://github.com/CopilotKit/OpenBot/issues/735), open | At the pinned revision, the desktop result accepts `writable`, but `HostAccessGrant` and `resolveDesktopOperation` omit it. A capability must preserve mode through storage and executor checks. Hutch's explicit extra mount must be readable but refuse write/unlink/creation; ambient mount grants must not widen authority. |
| [714: memory acknowledgement and retrieval scopes](https://github.com/CopilotKit/OpenBot/issues/714), open | Pinned `formMemory` deduplicates on owner/content while recording the forming bot. The report describes cross-bot acknowledgement followed by invisible retrieval. Use the same scope for uniqueness, access and retrieval. Hutch currently stores legacy memory per bot; test that equal keys/values stay independently accessible and deletion in one bot cannot remove another's record. Reviewed facts and shared project memory are still pending. |
| [715: lost peer continuation after approval](https://github.com/CopilotKit/OpenBot/issues/715), closed | Persist parent/child lineage, destination, budget and continuation before waiting; an approval after restart must resume the authorized destination once. Hutch's experimental same-bot flow persists lineage, destination policy, budget and approval arguments, but does not auto-replay an approved request after a parent worker dies before child admission. Verify restart leaves it visibly unresolved and requires a new explicit request. |
| [716: advertised group tools refused at runtime](https://github.com/CopilotKit/OpenBot/issues/716), closed | Capabilities presented to the model must agree with actual lineage/permission checks. Hutch advertises `delegate_task` only for opted-in bots on the Strict Offline Linux process executor; children do not receive it, and fresh human approval is always required. Verify unsupported hosts and stale/legacy rows show an actionable refusal. |
| [753: model and effort controls](https://github.com/CopilotKit/OpenBot/issues/753), open | Expose the bot default, one-message override and actual run model distinctly. Hutch's existing composer journey verifies the override does not edit the default; provider-specific effort controls require verified capability metadata. |
| [736: ChatGPT plan harness](https://github.com/CopilotKit/OpenBot/issues/736), open | Preserve the official local Sign in with ChatGPT request contract; do not turn an OAuth token into an arbitrary API credential. Hutch has an opt-in, fixture-tested Responses route, but eligibility and live authorization remain unverified; external harnesses remain disabled until permission brokering is verified. |
| [370: generated files hard to access](https://github.com/CopilotKit/OpenBot/issues/370), open | One user reports difficulty finding/downloading files generated in a channel. Hutch's acceptance check writes through `write_file`, exposes an immutable SHA-256-verified download directly in Studio chat without expanding tool details, and refuses to serve changed bytes. Files above 4 MB each or 16 MB in aggregate remain in the workspace with a visible explanation; arbitrary shell-created files are not attached. |

Pinned mode evidence:
[grant schema](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/server/src/host-access/schema.ts),
[broker](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/server/src/host-access/broker.ts).
Pinned memory evidence:
[store](https://github.com/CopilotKit/OpenBot/blob/59e28898238fe8510275dc02bc25cf9f4a90a77c/server/src/memory/store.ts).

## Verification boundary

`tests/test_file_approval.py` exercises stored full payloads, equal-length revised payloads,
changes during review, swapped file/parent symlinks, and hard-link replacement.
For issue 370, `tests/test_runtime_builtin.py`, `tests/test_api.py` and
`tests/e2e/test_browser.py::test_generated_workspace_file_is_downloadable_from_its_chat`
cover the 4 MB snapshot bound, run-local immutable copy, API listing, changed-byte rejection,
and keyboard download at desktop/tablet/phone sizes.
`tests/test_browser_profiles.py` verifies separate profiles, persisted typed contents despite
caller mutation, mandatory outward review under auto/sticky grants, and URL-change refusal.
These browser tests use fixtures, not a live signed-in account or public destination. HTTP(S)/WebSocket egress is fixture-covered;
live public destinations and other browser protocols remain open, as do remote handoff, reviewed bot-authored memory,
general-purpose delegation (including recovery continuation and artifact transfer), and subscription authentication.

The extra-mount scenario reproduced a Hutch defect: read-only mounts under `/tmp` were
installed before the private `/tmp` mount and became invisible. Mounts now follow their parent
mounts, preserve read-only mode under real bubblewrap execution, and reject credential
descendants or grants covering the writable workspace. `tests/test_sandbox.py` exercises that
boundary; `tests/test_tools.py` verifies independent equal-content memory and scoped forgetting.

Navigation evidence is in `navigation.md` and `navigation-visual-validation.md`. This review
does not claim a reduction in missed approvals, faster real-user completion, or comparative
security. No customer telemetry or controlled usability study supports those claims.

## Current profile and routine model (2026-10-09)

The upstream repository has moved well beyond the older multi-agent-canvas reference. Its current
documentation separates a coworker's `name`, `title`, and `role` in a durable profile, keeps each
channel tied to its own conversation, and routes browser and file effects through a server policy
gateway that records decisions. Its routine guide says work runs with the creator's grants and
posts the result as an ordinary message in the chosen Bot channel. These are design references;
Hutch did not run OpenBot or test an account against it. See current upstream
[coworker profiles](https://github.com/CopilotKit/OpenBot/blob/main/docs/coworkers.md),
[architecture](https://github.com/CopilotKit/OpenBot/blob/main/docs/architecture.md), and
[routine boundaries](https://github.com/CopilotKit/OpenBot/blob/main/docs/routines.md).

For Hutch's existing one-field display-name contract, the resulting UI pairs a locally generated,
friendly teammate name with its work role, keeps that purpose-based role in the chat header at
phone sizes, and labels the session as an AI Bot. Stable routing still uses the local address.
The arrangement adapts the upstream distinction between profile identity and role; it is not
evidence that a human persona improves trust or task quality. The reports above remain individual
acceptance scenarios rather than prevalence claims.
