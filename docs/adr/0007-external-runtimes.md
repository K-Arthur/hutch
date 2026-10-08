# ADR-0007: External runtime safety boundary

Status: accepted safety boundary; execution disabled (2026-10-07). Slice: S5. Evidence: baseline lead 7, B4-B6 and current adapter review. Published protocols: [OpenCode CLI](https://opencode.ai/docs/cli/) and [Pi RPC](https://pi.dev/docs/latest/rpc).

## Decision

External harnesses must never use blanket approval (`--auto`) or a shared background service. Process ownership, permission decisions, provider routing, bounded budgets, session mapping and sandbox policy must all be verified before execution is enabled.

The previous OpenCode adapter violated that boundary by hard-coding `--auto`, ignoring the bot model and instructions, inheriting environment credentials, and reading stdout synchronously while leaving stderr undrained. The previous Pi adapter used a request shape that does not match its published RPC contract and could not observe completion or safely drain both pipes.

**Current behavior: disabled.** Both adapters return an actionable `unsupported` failure before process creation. Hutch has no verified permission broker for either runtime and no external-runtime budget reservation. Pi's RPC protocol documents no approval hook. The shell sandbox does not wrap these harnesses, and it has no scoped egress broker for online model traffic. `sandbox=off` does not override these constraints.

Re-enabling requires fixture-based protocol tests, installed-version contract tests where available, process-group cancellation with verified identity, explicit model/instruction/session propagation, a visibly restricted capability set, no ambient credentials, budget reservations, and truthful UI/docs. No external runtime is currently a supported executor.

## Consequences

There is no unsafe opt-in. Once all gates above pass, enablement should be a reviewed feature flag with a separate explicit approval and spend policy. Until then the unavailable state must be visible in runtime selection and `hutch doctor`.
