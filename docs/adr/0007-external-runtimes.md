# ADR-0007: External runtime safety boundary

Status: accepted safety boundary; OpenCode V2 execution enabled (updated 2026-10-22), run-bound memory bridge added (2026-10-24), Pi disabled. Slice: S5. Evidence: baseline lead 7, B4-B6, D10-D11, the owned-server and live free-model checks, `tests/test_runtime_opencode.py`, and `tests/test_opencode_memory_bridge.py`. Published protocols: [OpenCode V2 API](https://opencode.ai/v2/api), [OpenCode V2 providers](https://opencode.ai/v2/docs/cli/providers), [OpenCode V2 plugins](https://opencode.ai/v2/docs/build/plugins) and [Pi RPC](https://pi.dev/docs/latest/rpc).

## Decision

External harnesses must never use blanket approval (`--auto`) or a shared background service. Process ownership, permission decisions, provider routing, bounded budgets, session mapping and sandbox policy must all be verified before execution is enabled.

The previous OpenCode adapter violated that boundary by hard-coding `--auto`, ignoring the bot model and instructions, inheriting environment credentials, and reading stdout synchronously while leaving stderr undrained. The previous Pi adapter used a request shape that does not match its published RPC contract and could not observe completion or safely drain both pipes.

**Current behavior: OpenCode enabled; Pi disabled.** OpenCode now runs through a Hutch-owned `opencode serve` process in a private profile. Hutch starts a fresh loopback server with a per-run password, never uses the shared background service, removes ambient provider credentials, and terminates the process group through the existing owned-process registry. It selects the Bot's explicit `opencode/provider/model` route and writes a per-assistant agent definition with read-only actions allowed and shell/edit/write/web actions set to `ask`.

The runtime does **not** trust the volatile SSE stream as its transcript. It reconciles durable session messages and permission requests over HTTP, so a dropped client can read the same history without inventing missing actions. Every permission prompt is passed through Hutch's `ApprovalGate`; the only affirmative reply Hutch emits is `once`, and denial is `reject`. Provider-reported tokens and cost from each completed assistant message are settled against a shared usage reservation, with a reservation covering the maximum internal turns Hutch admits. A disconnect after prompt admission marks usage uncertain and ends the run as `outcome_unknown`; it is never reported as success.

**Remaining boundary.** OpenCode executes its own tools after Hutch approves them. Those tools run with the user's operating-system authority; they are not wrapped by the built-in shell's bubblewrap sandbox. The current profile asks before `bash`/`shell`, edits, writes and web fetches, but an approved command is not OS-contained. This is stated in the setup UI and docs. Pi remains disabled because it has no per-action approval hook and cannot route provider traffic through Hutch's reservation path. Persona rewrites and answer-feedback controls remain limited to completed built-in-runtime answers.

**Run-bound memory bridge (A3, implemented 2026-10-24).** OpenCode reaches Hutch's reviewed-memory operations
(`recall`/`remember`) only through a per-run authenticated bridge; an opaque session ID is never treated as
authentication. The run worker starts an abstract Unix-socket `MemoryBridge` before launching OpenCode and writes a
generated V2 plugin into the private profile whose tool executors (and whose verification RPC, which shares the exact
same call path) send `{tool, args}` over that socket — **no token, key or bearer exists anywhere in the OpenCode
environment**, because its native tools run with the user's OS authority and safe read actions could read any stored
credential. The bridge authenticates the caller with `SO_PEERCRED` (same uid) plus a PID/starttime ancestry chain that
must contain the OpenCode server process this worker recorded; the client never supplies a Bot, run, fence or
conversation — the handler derives all of them from the run the bridge was constructed for. Every call rechecks, from
SQLite: live owner fence, running status, no cancellation request, unexpired lease, current `memory_enabled`, and that
the tool is still in the Bot's reviewed list. Dispatch goes through `steps.call_tool` with fresh memory-tool objects,
so argument freezing, effect intent/receipt brackets, transcript tool events, memory-off guards and proposal-review
semantics are exactly the built-in runtime's (one enforcement path, ADR-0008). The bridge starts only when memory was
admitted at run start and is closed with the run; memory-off at start means the plugin is never written.

Trust boundary, stated honestly: any process inside the run's own OpenCode process tree can reach that run's socket
(for example through an approved shell command), but a call then gains nothing beyond the run's admitted, currently
enabled memory tools for its own conversation, because every authority field is re-derived server-side. Direct SQLite
access, a bearerless HTTP endpoint and model-selected identity remain forbidden. Verified by
`tests/test_opencode_memory_bridge.py`: process-tree authorization (direct child and grandchild accepted, parent/
unrelated caller refused, empty-trust refuse-all), cancellation/stale-fence/expired-lease refusals, live memory-off and
tool-revocation refusals, conversation scoping with exact revision plus source-update and archive/revoke flows,
receipt-backed proposals, hostile/out-of-scope request refusals with bounds, and adapter plugin wiring (plugin written
only when memory is admitted). A live installed-CLI test (OpenCode v2.1.4, no model call) loads the real plugin,
round-trips `recall`/`remember` over the authenticated socket with exact provenance, sees hostile input rejected by
the plugin's schema before the socket, and observes cancellation refuse live. Sources: [V2 plugins](https://opencode.ai/v2/docs/build/plugins),
[RPC](https://opencode.ai/v2/docs/build/plugins/rpc) and [MCP servers](https://opencode.ai/v2/docs/mcp-servers),
checked 2026-10-23/24.

Limits: the bridge is not a provider billing cap, not an OS sandbox for native tools, and grants no cross-conversation
scope. Plugin-load failure fails soft (tools absent, never half-exposed), and the RPC verification surface requires an
explicit `events: {}` map on v2.1.4. **Live free-model verification (2026-10-24, owner-authorized; evidence in the
realignment ledger):** opt-in tests (`HUTCH_LIVE_OPENCODE=1`, skipped by default) drove OpenCode Zen's free
`deepseek-v4.1-flash-free` through the real private server, plugin and bridge — model-invoked `recall` served the
reviewed fact, `remember` stayed an unreviewed proposal with a done receipt, and a toolless fresh session answered
from the provenance selection; the live run also caught the v2.1.4 `msg_` prompt-ID requirement, so the durable send
identity is now `msg_hutch_<hex>`. An independent second owner-authorized session reproduced all three legs with zero
unresolved usage reservations. One host, one free model, one observation per leg: this validates the path, not broad
tool-calling reliability or model quality.

**Conversation continuity (2026-10-23).** Both runtimes now consume the persisted admission selection rather than rebuilding a different page of history. SQLite schema v75 binds disposable native sessions to the Bot, conversation, route, workspace, agent/policy, admitted run and exact context hash, with a canonical-message high watermark. Without a verified native replace-context contract, sessions are not reused across turns: native tool output or earlier text must not silently expand a later run's bounded selection. Missing or mismatched caches rebuild; legacy JSON mapping files are no longer read or deleted. Prompt identity and `prepared`/`dispatched`/`acknowledged`/`rejected`/`uncertain` state are durable. A prior dispatch is refused before another session or usage hold is created; a missing native session cannot authorize retransmission. These records are not native tool receipts, a provider billing cap, or an authenticated Hutch memory bridge.

### Historical restricted-mode reassessment (2026-10-08; predates V2 enablement above)

Pi's current CLI reference offers a plausible text-only boundary: `--no-tools` disables built-in, extension, custom and MCP tools, and `--no-extensions`, `--no-mcp` and `--no-session` can further reduce ambient behavior. This is useful evidence for a future restricted capability profile, but it does not route model requests through Hutch's `ConnectionBook`/`SpendGuard`, establish an enforceable pre-call usage reservation, or provide Hutch's durable conversation mapping. Hutch has not verified a Pi binary against this protocol in the current environment. We therefore keep Pi unavailable even in text-only mode until provider traffic and usage are governed by Hutch and a real child-process integration is tested. Sources: [Pi RPC](https://pi.dev/docs/latest/rpc) and [Pi CLI](https://pi.dev/docs/latest/cli), checked 2026-10-08.

OpenCode's current permissions documentation describes `allow`, `ask` and `deny`, and the server exposes message/session endpoints that could support later recovery work. That does not override the installed v2.0.24 contract test: its event stream can lose records, and no implementation yet proves that a restarted client can reconstruct every action and receipt before continuing. We also have not connected its permission endpoint to Hutch's immutable approval arguments and once-only decisions. Sources: [OpenCode permissions](https://docs.opencode.ai/docs/permissions/) and [OpenCode server API](https://opencode.ai/docs/server/), checked 2026-10-08.

Re-enabling requires process-level tests with bounded stdout and stderr drainers, installed-version contract checks, process-group cancellation with verified identity, explicit model/instruction/session propagation, a visibly restricted capability set, no ambient credentials, brokered permissions with no persistent grant, budget reservations, recoverable event/history reconciliation across disconnects, and truthful UI/docs. Any enablement must require the actual containment and usage controls, not just a version fixture. No external runtime is currently a supported executor.

## Consequences

There is no unsafe opt-in. Once all gates above pass, enablement should be a reviewed feature flag with a separate explicit approval and spend policy. Until then the unavailable state must be visible in runtime selection and `hutch doctor`.
