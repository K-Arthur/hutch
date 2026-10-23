# ADR-0007: External runtime safety boundary

Status: accepted safety boundary; OpenCode V2 execution enabled (updated 2026-10-22), Pi disabled. Slice: S5. Evidence: baseline lead 7, B4-B6, D10-D11, the owned-server and live free-model checks, and `tests/test_runtime_opencode.py`. Published protocols: [OpenCode V2 API](https://opencode.ai/v2/api), [OpenCode V2 providers](https://opencode.ai/v2/docs/cli/providers) and [Pi RPC](https://pi.dev/docs/latest/rpc).

## Decision

External harnesses must never use blanket approval (`--auto`) or a shared background service. Process ownership, permission decisions, provider routing, bounded budgets, session mapping and sandbox policy must all be verified before execution is enabled.

The previous OpenCode adapter violated that boundary by hard-coding `--auto`, ignoring the bot model and instructions, inheriting environment credentials, and reading stdout synchronously while leaving stderr undrained. The previous Pi adapter used a request shape that does not match its published RPC contract and could not observe completion or safely drain both pipes.

**Current behavior: OpenCode enabled; Pi disabled.** OpenCode now runs through a Hutch-owned `opencode serve` process in a private profile. Hutch starts a fresh loopback server with a per-run password, never uses the shared background service, removes ambient provider credentials, and terminates the process group through the existing owned-process registry. It selects the Bot's explicit `opencode/provider/model` route and writes a per-assistant agent definition with read-only actions allowed and shell/edit/write/web actions set to `ask`.

The runtime does **not** trust the volatile SSE stream as its transcript. It reconciles durable session messages and permission requests over HTTP, so a dropped client can read the same history without inventing missing actions. Every permission prompt is passed through Hutch's `ApprovalGate`; the only affirmative reply Hutch emits is `once`, and denial is `reject`. Provider-reported tokens and cost from each completed assistant message are settled against a shared usage reservation, with a reservation covering the maximum internal turns Hutch admits. A disconnect after prompt admission marks usage uncertain and ends the run as `outcome_unknown`; it is never reported as success.

**Remaining boundary.** OpenCode executes its own tools after Hutch approves them. Those tools run with the user's operating-system authority; they are not wrapped by the built-in shell's bubblewrap sandbox. The current profile asks before `bash`/`shell`, edits, writes and web fetches, but an approved command is not OS-contained. This is stated in the setup UI and docs. Pi remains disabled because it has no per-action approval hook and cannot route provider traffic through Hutch's reservation path. Persona rewrites and answer-feedback controls remain limited to completed built-in-runtime answers.

### Restricted-mode reassessment (2026-10-08)

Pi's current CLI reference offers a plausible text-only boundary: `--no-tools` disables built-in, extension, custom and MCP tools, and `--no-extensions`, `--no-mcp` and `--no-session` can further reduce ambient behavior. This is useful evidence for a future restricted capability profile, but it does not route model requests through Hutch's `ConnectionBook`/`SpendGuard`, establish an enforceable pre-call usage reservation, or provide Hutch's durable conversation mapping. Hutch has not verified a Pi binary against this protocol in the current environment. We therefore keep Pi unavailable even in text-only mode until provider traffic and usage are governed by Hutch and a real child-process integration is tested. Sources: [Pi RPC](https://pi.dev/docs/latest/rpc) and [Pi CLI](https://pi.dev/docs/latest/cli), checked 2026-10-08.

OpenCode's current permissions documentation describes `allow`, `ask` and `deny`, and the server exposes message/session endpoints that could support later recovery work. That does not override the installed v2.0.24 contract test: its event stream can lose records, and no implementation yet proves that a restarted client can reconstruct every action and receipt before continuing. We also have not connected its permission endpoint to Hutch's immutable approval arguments and once-only decisions. Sources: [OpenCode permissions](https://docs.opencode.ai/docs/permissions/) and [OpenCode server API](https://opencode.ai/docs/server/), checked 2026-10-08.

Re-enabling requires process-level tests with bounded stdout and stderr drainers, installed-version contract checks, process-group cancellation with verified identity, explicit model/instruction/session propagation, a visibly restricted capability set, no ambient credentials, brokered permissions with no persistent grant, budget reservations, recoverable event/history reconciliation across disconnects, and truthful UI/docs. Any enablement must require the actual containment and usage controls, not just a version fixture. No external runtime is currently a supported executor.

## Consequences

There is no unsafe opt-in. Once all gates above pass, enablement should be a reviewed feature flag with a separate explicit approval and spend policy. Until then the unavailable state must be visible in runtime selection and `hutch doctor`.
