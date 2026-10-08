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
  containment mode. These repairs do not finish browser account authority or sandboxed egress.
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
| [715: lost peer continuation after approval](https://github.com/CopilotKit/OpenBot/issues/715), closed | Persist parent/child lineage, destination, budget and continuation before waiting; an approval after restart must resume the authorized destination once. Hutch delegation is unavailable until this scenario passes. |
| [716: advertised group tools refused at runtime](https://github.com/CopilotKit/OpenBot/issues/716), closed | Capabilities presented to the model must agree with actual lineage/permission checks. A depth-limited child must receive a clear restriction, rather than a tool advertised as usable that always fails. Hutch has not implemented delegation. |
| [753: model and effort controls](https://github.com/CopilotKit/OpenBot/issues/753), open | Expose the bot default, one-message override and actual run model distinctly. Hutch's existing composer journey verifies the override does not edit the default; provider-specific effort controls require verified capability metadata. |
| [736: ChatGPT plan harness](https://github.com/CopilotKit/OpenBot/issues/736), open | Preserve supported subscription authentication and request contracts; do not turn an OAuth token into an arbitrary API credential. Hutch Sign in with ChatGPT remains unavailable under the documented preview/eligibility boundary, and external harnesses remain disabled until permission brokering is verified. |
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
These browser tests use fixtures, not a live signed-in account. Live browser egress and
handoff, reviewed memory, delegation and subscription authentication remain open release gates.

The extra-mount scenario reproduced a Hutch defect: read-only mounts under `/tmp` were
installed before the private `/tmp` mount and became invisible. Mounts now follow their parent
mounts, preserve read-only mode under real bubblewrap execution, and reject credential
descendants or grants covering the writable workspace. `tests/test_sandbox.py` exercises that
boundary; `tests/test_tools.py` verifies independent equal-content memory and scoped forgetting.

Navigation evidence is in `navigation.md` and `navigation-visual-validation.md`. This review
does not claim a reduction in missed approvals, faster real-user completion, or comparative
security. No customer telemetry or controlled usability study supports those claims.
