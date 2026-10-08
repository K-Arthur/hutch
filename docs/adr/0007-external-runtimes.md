# ADR-0007: External runtime safety boundary

Status: accepted safety boundary; execution disabled (updated 2026-10-08). Slice: S5. Evidence: baseline lead 7, B4-B6, D10-D11 and current adapter review. Published protocols: [OpenCode CLI](https://opencode.ai/docs/cli/), [OpenCode server](https://opencode.ai/docs/server/) and [Pi RPC](https://pi.dev/docs/latest/rpc).

## Decision

External harnesses must never use blanket approval (`--auto`) or a shared background service. Process ownership, permission decisions, provider routing, bounded budgets, session mapping and sandbox policy must all be verified before execution is enabled.

The previous OpenCode adapter violated that boundary by hard-coding `--auto`, ignoring the bot model and instructions, inheriting environment credentials, and reading stdout synchronously while leaving stderr undrained. The previous Pi adapter used a request shape that does not match its published RPC contract and could not observe completion or safely drain both pipes.

**Current behavior: disabled.** Both adapters return an actionable `unsupported` failure before process creation. Offline protocol helpers now test Pi JSONL framing, command correlation, streaming, settled completion and abort framing, plus OpenCode SSE framing, permission-request identity and one-time/reject decision mapping. These helpers are not execution adapters and do not drain child pipes. Hutch has no verified end-to-end permission broker or external-runtime budget reservation. Pi's RPC protocol documents no per-action approval hook; its restricted CLI mode is assessed below. The installed OpenCode 2.0.24 server describes its API as experimental and its SSE stream as volatile: events can be lost on overflow or disconnect. That stream cannot currently uphold Hutch's durable action and receipt contract. Its permission API accepts `always`; Hutch must never emit that decision. The shell sandbox does not yet wrap these harnesses, and it has no scoped egress broker for online model traffic. `sandbox=off` does not override these constraints.

### Restricted-mode reassessment (2026-10-08)

Pi's current CLI reference offers a plausible text-only boundary: `--no-tools` disables built-in, extension, custom and MCP tools, and `--no-extensions`, `--no-mcp` and `--no-session` can further reduce ambient behavior. This is useful evidence for a future restricted capability profile, but it does not route model requests through Hutch's `ConnectionBook`/`SpendGuard`, establish an enforceable pre-call usage reservation, or provide Hutch's durable conversation mapping. Hutch has not verified a Pi binary against this protocol in the current environment. We therefore keep Pi unavailable even in text-only mode until provider traffic and usage are governed by Hutch and a real child-process integration is tested. Sources: [Pi RPC](https://pi.dev/docs/latest/rpc) and [Pi CLI](https://pi.dev/docs/latest/cli), checked 2026-10-08.

OpenCode's current permissions documentation describes `allow`, `ask` and `deny`, and the server exposes message/session endpoints that could support later recovery work. That does not override the installed v2.0.24 contract test: its event stream can lose records, and no implementation yet proves that a restarted client can reconstruct every action and receipt before continuing. We also have not connected its permission endpoint to Hutch's immutable approval arguments and once-only decisions. Sources: [OpenCode permissions](https://docs.opencode.ai/docs/permissions/) and [OpenCode server API](https://opencode.ai/docs/server/), checked 2026-10-08.

Re-enabling requires process-level tests with bounded stdout and stderr drainers, installed-version contract checks, process-group cancellation with verified identity, explicit model/instruction/session propagation, a visibly restricted capability set, no ambient credentials, brokered permissions with no persistent grant, budget reservations, recoverable event/history reconciliation across disconnects, and truthful UI/docs. Any enablement must require the actual containment and usage controls, not just a version fixture. No external runtime is currently a supported executor.

## Consequences

There is no unsafe opt-in. Once all gates above pass, enablement should be a reviewed feature flag with a separate explicit approval and spend policy. Until then the unavailable state must be visible in runtime selection and `hutch doctor`.
