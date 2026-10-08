# Reviewing and resolving approvals

An approval is a request to perform one action, such as changing a file. The server owns its status and the decision. The dashboard and chat view show the same action summary, risk, reason, and relevant arguments. Open **Review details** before deciding, especially when the request can send data outside the machine.

The queue at `GET /api/approvals` lists pending requests. The same resources are available at `/api/v1/actions/approvals`. `GET /api/approvals/{id}` reads one request after a conflict or a reconnect. `GET /api/approvals?status=resolved&limit=8` shows recently decided requests. A decision uses `POST /api/approvals/{id}/approve` or `/deny`; a second decision returns a conflict. Only non-outward actions with a narrow sticky permission offer **Always allow for this bot**. Outward actions still require a person each time.

The client does not remove a request as completed based on a local click alone. If another device decides first, it reads the server's result and shows that decision. Expired requests fail closed as denied. Stop does not undo effects that were already completed.

Approval CAS and reconciliation are live on both path families, but approval commands do not yet accept `Idempotency-Key`; retries should read the approval resource after a conflict. Per-run SSE supports `Last-Event-ID`. Global event replay, remote device pairing and authenticated control sessions are not available.
