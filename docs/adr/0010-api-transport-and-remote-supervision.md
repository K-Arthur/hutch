# ADR-0010: API contracts, event transport, and phone supervision

Status: partially implemented (2026-10-07). Slice: S8. Evidence: baseline "reconnect", `security.py` WebSocket gap, A1/A3, C2.

## Decision

* **Contract first** (`docs/realignment/contracts.md`): typed Pydantic schemas now cover health, status labels, conversations, messages,
  search results, and selected run/approval aliases under `/api/v1`. Conversation creation, message submission, and archive commands
  require an `Idempotency-Key`, persist the request hash and result in the same transaction, and return 409 if a key is reused with
  different arguments. Conversation messages and lists are bounded and cursor-paginated. Other command families, global ordered
  cursors, retention-gap snapshots, and full schemas remain to be implemented. Existing `/api/*` routes stay as compatibility paths.
* **Transport**: legacy per-run SSE supports `Last-Event-ID`; the versioned per-run alias is available. Durable global replay for
  conversations and all resources is not implemented. The interactive terminal and browser-handoff input use a **separate WebSocket**, authenticated per message and gated by the
  same middleware (the current middleware passes non-HTTP scopes through - fixed).
* **Server owns** status, approval resolution, receipts, permissions and usage. The browser owns drafts, focus and view state. Optimistic UI
  may show "sending", never "done".
* **Remote supervision**: loopback by default. Pairing = a one-time code shown on the host terminal/UI (60 s, single use) exchanged for a
  per-device token (hash stored, revocable, 30-day sliding expiry, listed in the UI). Requirements before off-loopback binding is allowed:
  token auth, TLS (or an explicit `--insecure-lan` acknowledgement printed every start), Host/Origin validation, CSRF on cookie sessions,
  per-IP and per-device brute-force limits, WebSocket auth. Hutch will not bind a LAN/Internet address without all of these.
* **Terminal**: governed command execution first (exists). An interactive PTY (sandboxed, bounded scrollback 1 MiB, resize, cancel, text transcript)
  is built only after the WebSocket auth above lands; **control ownership is a lease** (`agent` | `human`) so input never races; stale or replayed
  frames carry a sequence number and are dropped after reconnect.
* **Trust boundaries**: the web client and the installed executor are separate. A hosted marketing site never talks to `localhost`.
* A sleeping host cannot run anything: the UI shows queued/offline/reconnecting with the next action. A hosted remote executor is a separate,
  opt-in product and is not built here.

## Consequences

Current boundary: the local `/api/v1` surface and Studio conversation flow are partial; approvals, stops and other existing screens
still use compatibility routes. Pairing, device sessions, PTY WebSocket, global replay and remote binding controls are not implemented. The current service remains
loopback-only; there is no `--allow-remote` option or pairing flow to enable.
