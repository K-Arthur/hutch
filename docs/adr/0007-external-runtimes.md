# ADR-0007: OpenCode and Pi as governed, contract-tested runtimes

Status: accepted (2026-10-07). Slice: S5. Evidence: baseline lead 7, B4-B6.

## Decision

* Adapters are written against **captured contracts**, not remembered shapes. A contract test spawns the installed binary (skipped
  with an explicit reason when absent) and checks version, flags and the event schema; a recorded-fixture test exercises the parser offline. A mock test is never reported as proof of a live integration.
* **OpenCode**: `opencode run --format json --model <provider/model> --session <id> --dir <workspace>` with **`--auto` never added by default**.
  Two modes:
  1. *restricted* (default): runs inside the OS sandbox (ADR-0006) with the workspace as the only writable path and no network unless granted; OpenCode's own deny rules apply; tool permission prompts that OpenCode raises without `--auto` are answered "reject" and recorded.
  2. *brokered* (experimental, enabled only if the installed version's OpenAPI contains the permission endpoints): Hutch starts a private `opencode serve --port 0` with `OPENCODE_SERVER_PASSWORD`, forwards each permission request to the Hutch approval gate and answers through `POST /session/:id/permissions/:permissionID`, aborts with `POST /session/:id/abort`.
  The shared background service is **never used** for governed runs (`--standalone`), because work in a service Hutch does not own cannot be cancelled or contained.
* **Pi**: framing fixed to `{"type":"prompt","message":…}` with ids; completion is `agent_settled`; `--provider/--model` from the bot; cancel is `abort` then closing stdin then the kill ladder. Pi documents **no approval hook and no sandbox** (B6), so Pi runs only in `restricted` mode inside the OS sandbox and the UI says "contained, not policy-gated".
* **Model, instructions, workspace, limits, session id** are propagated explicitly; unsupported combinations (for example a Hutch-only provider route) are refused at *bot validation*, not at run time.
* If the sandbox is unavailable, external runtimes are **refused**, not run wide open, unless the operator sets `sandbox=off` on that bot, which surfaces as "uncontained" everywhere.
* Hutch's conversation is canonical. On resume the adapter passes the stored runtime session id when the runtime supports it; otherwise it replays a bounded summary (ADR-0002) and says so.

## Consequences

Rollback: previous behaviour is reachable with `runtime_args: ["--auto"]` per bot, shown as a red "auto-approve" badge. Adapters remain optional dependencies; absent binaries produce an actionable `doctor` line.
