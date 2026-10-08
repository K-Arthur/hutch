# Contracts shared with the frontend workstream

The frontend is a separate workstream (another session owns `server/static/*` and `server/pages.py`). Nothing here is built
by editing those files. This page is the agreement about what the server will provide, so the two can proceed in parallel.
It is a living document: a contract is marked **landed** only when the server tests for it pass on this branch.

## 1. Run status values and labels (landed with slice S2)

`status` is the stored value; show the **label**, not the value. `stopped` keeps its name for compatibility.

| status | label | terminal | needs a person | notes |
|---|---|---|---|---|
| `pending` | Queued | no | no | |
| `loading_model` | Loading the model | no | no | |
| `running` | Working | no | no | |
| `waiting_approval` | Waiting for you | no | **yes** | an approval request is attached |
| `waiting_human` | Needs you | no | **yes** | login / CAPTCHA / MFA; `reason` and `handoff` describe how |
| `waiting_resources` | Waiting for a free slot or quota | no | no | `reason` says which |
| `recovering` | Recovering | no | no | owner lost; recovery deciding |
| `cancelling` | Stopping | no | no | stay visible until `stopped`; never show "stopped" early |
| `succeeded` | Done | yes | no | `verified` is `true`, `false` or `null` |
| `failed` | Failed | yes | no | `exit_reason` explains |
| `stopped` | Cancelled | yes | no | |
| `outcome_unknown` | Needs review | yes | **yes** | an action may or may not have happened; list `unknown_actions` |
| `skipped` | Skipped | yes | no | scheduled occurrence deliberately not run |

A client that does not know a status must render its label from `GET /api/v1/status-labels` (landing with S8) and treat it as non-terminal.

## 2. Authority split

* **Server owns:** status, approval resolution, receipts, permissions, usage, who holds control of a browser/terminal.
* **Browser owns:** drafts, focus, scroll, view filters.
* An optimistic UI may show "sending"; it must never show a tool as executed or a run as done before the server says so.

## 3. Cursors, idempotency, pagination (landing with S8)

* Event streams: SSE, `id:` is the per-stream cursor, `Last-Event-ID` resumes, the server replays from the database. A gap returns the authoritative state.
* Commands (submit, approve, deny, cancel, resume) accept `Idempotency-Key`; replaying one returns the original outcome.
* Lists: `limit` (max 200) and `after`; never an unbounded response.

## 4. Frontend acceptance items taken from the evidence ledger

| From | Requirement |
|---|---|
| C2 (Open WebUI #30055) | A pending approval or handoff must be visible on **every** view and mode, including full-screen overlays, with a visible count. |
| C3 (Open WebUI #31656) | On phones, closing a menu must not move focus into a text field (no keyboard pop-up). |
| A1, A3 | A person can open the live session and take over; the UI says who holds control. |
| ADR-0003 | `cancelling` and `outcome_unknown` are first-class and explained in plain language. |
