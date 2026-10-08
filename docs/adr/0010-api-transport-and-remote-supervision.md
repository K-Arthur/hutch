# ADR-0010: API contracts, event transport, and phone supervision

Status: partially implemented (2026-10-07). Slice: S8. Evidence: baseline "reconnect", `security.py` WebSocket gap, A1/A3, C2.

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
* **Remote supervision**: loopback by default. An operator can explicitly enable a direct remote listener with `--allow-remote`, a TLS
  certificate and key, and configured network reachability. `hutch pairing create` prints a one-time code (60 s); exchanging it over
  HTTPS creates an HttpOnly per-device session whose hash is stored, whose sliding expiry is 30 days, and which can be listed/revoked
  from the CLI or Connections. `/pair` exchanges the code without placing it in a URL; Connections labels the active browser and can
  revoke any session. Pairing attempts are limited per source IP. Host/Origin checks and HTTP/WebSocket device-token checks run before
  remote access. No token appears in a URL or log. The responsive dashboard is experimental for remote use; physical-device/network
  checks, browser/PTY/desktop controls and tunnel handling are not complete.
* **Terminal**: governed command execution first (exists). An interactive PTY (sandboxed, bounded scrollback 1 MiB, resize, cancel, text transcript)
  is built only after the WebSocket auth above lands; **control ownership is a lease** (`agent` | `human`) so input never races; stale or replayed
  frames carry a sequence number and are dropped after reconnect.
* **Trust boundaries**: the web client and the installed executor are separate. A hosted marketing site never talks to `localhost`.
* A sleeping host cannot run anything: the UI shows queued/offline/reconnecting with the next action. A hosted remote executor is a separate,
  opt-in product and is not built here.

## Consequences

Current boundary: the local `/api/v1` surface and Studio conversation flow are partial. Some
screens use compatibility routes; approval decisions and Stop use idempotent v1 commands.
Pairing UX and revocable device sessions plus explicit direct HTTPS binding are implemented and browser-fixture-tested. Cross-run
transcript/resource replay and bounded reconciliation are implemented, but no PTY or browser-control WebSocket route, configured tunnel
support, physical-device test, event-retention policy, or production remote-support claim exists. Keep direct access private and
operator-controlled.
