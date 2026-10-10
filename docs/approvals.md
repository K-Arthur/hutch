# Reviewing and resolving approvals

An approval is a request to perform one action, such as changing a file. The server owns its status and the decision. The dashboard and chat view show the same action summary, risk, reason, and relevant arguments. Open **Review details** before deciding, especially when the request can send data outside the machine.

Decide in the conversation or open **Needs you** for requests across bots. Provider fallback
reviews include the receiving account, endpoint, billing mode, revision and scope. An approved
provider route covers calls within this run on that exact route, with usage reserved before each
attempt. Another account or a changed connection needs another review. This outward permission
cannot be remembered as an always-allow grant; a new run starts with fresh authority.

The queue at `GET /api/approvals` lists pending requests. The same resources are available at `/api/v1/actions/approvals`. `GET /api/approvals/{id}` reads one request after a conflict or a reconnect. `GET /api/approvals?status=resolved&limit=8` shows recently decided requests. A decision uses `POST /api/approvals/{id}/approve` or `/deny`; a second decision returns a conflict. Only non-outward actions with a narrow sticky permission offer **Always allow for this bot**. Outward actions still require a person each time.

The client does not remove a request as completed based on a local click alone. If another device decides first, it reads the server's result and shows that decision. Expired requests fail closed as denied. Stop does not undo effects that were already completed.

Approval CAS and reconciliation are live on both path families. The versioned approve/deny routes require `Idempotency-Key`; approve
also requires the `action_hash` returned with the approval so a revised action cannot reuse the decision. Exact retries return the
same result and changed request arguments conflict. Legacy routes remain available for the local Studio. Per-run and cross-run transcript SSE
support durable `Last-Event-ID` replay; a missing global cursor returns `snapshot_required` so the client can fetch `/api/v1/snapshot`
and resume from its event watermark. Paired phones can inspect the exact pending action and choose **Allow once** or **Deny**; they
cannot create standing permissions or change approval policy. Phone approval uses the same action hash, current-state checks,
idempotency, and compare-and-set resolution as the local API. Remote access is disabled unless explicitly enabled by the operator.
See [the phone supervision contract](realignment/contracts.md#6-phone-supervision-partial-experimental).
