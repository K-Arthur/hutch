# Reviewing and resolving approvals

An approval is a request to perform one action, such as changing a file. The server owns its status and the decision. The dashboard and chat view show the same action summary, risk, reason, and relevant arguments. Open **Review details** before deciding, especially when the request can send data outside the machine.

The queue at `GET /api/approvals` lists pending requests. `GET /api/approvals/{id}` reads one request after a conflict or a reconnect. `GET /api/approvals?status=resolved&limit=8` shows recently decided requests. A decision uses `POST /api/approvals/{id}/approve` or `/deny`; a second decision returns a conflict. Only non-outward actions with a narrow sticky permission offer **Always allow for this bot**. Outward actions still require a person each time.

The client does not remove a request as completed based on a local click alone. If another device decides first, it reads the server's result and shows that decision. Expired requests fail closed as denied. Stop does not undo effects that were already completed.

These `/api` paths are the current compatibility interface. The versioned API and durable event replay are being introduced separately; clients should not treat polling or a successful HTTP response as proof that a larger task completed.
