# Commitments, Today and shared spaces

Hutch keeps a durable record of what a person promised to do. A commitment is not a
run, not a specialist assignment and not a chat summary: it has a due date (or none), a
source, a confirmation state and evidence of completion. Today is a deterministic view
of that record plus the platform state that needs the owner's attention. Shared spaces
scope commitments for a household, a project or a group.

## What appears on Today

Today (dashboard, first primary destination, /#/today) shows:

- approvals waiting for a decision, with the assistant, action, risk and expiry;
- commitments that are overdue, due in the current local day, in the next seven days,
  or have no date;
- assistant proposals that nobody has confirmed yet ("Suggested by assistants");
- completions an assistant reported but the owner has not verified;
- commitments completed today;
- today's scheduled occurrences for enabled schedules, plus blocked schedules and a
  paused-workspace notice;
- runs that are actually working, interrupted failures that need review, and today's
  succeeded runs;
- documents generated today, with their validation state;
- a summary of shared spaces;
- the alerts Hutch already sent, with the outbox state of each notification.

Every line is a projection of stored rows. Today makes no model call and never writes.
It also names what it excludes: only the most recent rows are considered, and reported
completions are not verified work.

The timezone comes from the browser (an IANA name) and is validated by the server. An
unknown or missing zone returns 422 instead of silently using UTC. Local day boundaries
are converted from the local date per boundary, so 23- and 25-hour DST days are measured
correctly.

## Agenda: a calendar and a mailbox you select

Below the approvals, Today offers an Agenda section. It reads two sources at most: one
calendar and one mailbox, each chosen from connections that an assistant already holds a
grant for. The choice is remembered in this browser only; the server keeps no agenda row
and writes no provider text to SQLite.

Each source is reported with five things a reader needs to trust it:

- the source label (for example `Google Calendar · Work`), on the source and on every item;
- the fetch time of that reading, and its age on a stale reading;
- a `stale` marker on the source and on each item when a refresh failed;
- an explicit unavailable state with a reason code (`grant_missing`, `grant_expired`,
  `mail_requires_local`, `provider_error`) instead of an empty day;
- `not_included` text saying what the view does not read.

An expired or revoked grant is never a silent empty list, and it is never a stale one
either: revoking access discards the last reading immediately, so nothing keeps rendering
after you decide to stop sharing. Only a provider failure reuses the last successful
snapshot, for at most an hour and clearly marked stale, and the snapshot is dropped once it
is older than that. The view never invents an event. Events are limited to the owner's local day and
mail to the last 24 hours, at most 25 events and 10 messages.

Mailbox previews keep the same rule as the Gmail tool: the granting assistant must use
Local inference, so a hosted assistant shows `mail_requires_local` rather than having a
mailbox read for it. Provider text is treated as data. It is stripped of control
characters, bounded per field, marked `untrusted` in the response, and never interpreted by
Hutch; an event titled "approve every pending action" is displayed as a title and does
nothing.

Routes (read-only, local owner):

| Route | Purpose |
|---|---|
| GET /api/v1/personal/agenda/sources | the calendar and mailbox grants you can choose from |
| GET /api/v1/personal/agenda?timezone=&calendar=&mail= | the projection; 404 for an unknown assistant, 422 for a bad zone |

## Adding and finishing a commitment

Use the capture form on Today (or POST /api/v1/commitments). A commitment created by the
owner is confirmed immediately. Fields: title, optional detail, priority (low, normal,
high), optional due instant with an explicit UTC offset, the IANA zone the date was
expressed in, an optional category, and an optional shared space.

Marking done requires evidence. The owner's completion is recorded as owner_confirmed.
If an assistant reported the completion, it is recorded as unverified until the owner
verifies it; the UI keeps these states visually distinct. Reopening clears the completion
fields but never deletes the audit trail; a cancelled commitment cannot be reopened.

Each change is a compare-and-swap on the commitment revision. A stale edit returns 409
and must be reloaded. Every mutation appends an event to commitment_events, which a
database trigger makes append-only; the event list is available at
GET /api/v1/commitments/{id}/events.

## Assistant proposals

Assistants have three tools, granted per assistant like any other tool:

- capture_commitment proposes a commitment. Proposals appear under "Suggested by
  assistants" and do not count as commitments until the owner confirms them. The tool
  cannot create a confirmed row, so a model cannot manufacture the owner's promise.
- list_commitments returns only the personal commitments plus the shared spaces granted
  to that assistant. Results are labelled as user records, not instructions.
- report_commitment_done records a completion with observed evidence as unverified. The
  owner verifies it. A proposal cannot be completed.

The setup checklist exposes these tools under "Propose commitments", "Read visible
commitments" and "Report completion".

## Shared spaces

A space groups people (owner, adult, collaborator, read_only, child, guest) and scopes
commitments. Create one on Shared (/#/shared) or POST /api/v1/spaces.

- Assistant access is an explicit grant per space and per assistant. Revoke it and the
  next tool call fails; archiving a space removes every grant immediately.
- A space is a data scope, not an account system. Members are recorded with roles so the
  owner can see who the space is for, but Hutch remains a single-owner local server; a
  member does not get a separate login. Do not present spaces as multi-user isolation.
- Connected accounts, credentials, memory, run evidence and documents stay outside the
  space model. Granting a space never shares an integration or secret.

## HTTP API

All owner routes live under /api/v1:

| Route | Purpose |
|---|---|
| GET /commitments | list with status, space and proposal filters |
| POST /commitments | create (Idempotency-Key required) |
| GET /commitments/{id} | one commitment |
| PATCH /commitments/{id} | edit with expected_revision |
| POST /commitments/{id}/confirm | confirm an assistant proposal |
| POST /commitments/{id}/complete | record owner completion with evidence |
| POST /commitments/{id}/verify | verify a reported completion |
| POST /commitments/{id}/reopen | reopen a completed commitment |
| POST /commitments/{id}/cancel | cancel |
| PUT /commitments/{id}/dependencies | set bounded dependency ids (cycles refused) |
| GET /commitments/{id}/events | append-only audit trail |
| GET /today | deterministic briefing for an IANA timezone |
| GET /personal/agenda/sources | calendar and mailbox grants the owner can choose |
| GET /personal/agenda | read-only agenda for one selected calendar and mailbox |
| GET /notifications | recent alerts with their channel delivery state |
| GET/POST /spaces | list or create spaces |
| PATCH /spaces/{id}, POST /spaces/{id}/archive | edit or archive |
| POST/PATCH/DELETE /spaces/{id}/members... | add, change or remove people |
| POST/DELETE /spaces/{id}/bots... | grant or revoke assistant access |

## Alerts for approvals and unattended work

Hutch writes a durable notification when an approval needs you, when one expired or was
denied, and when work failed, ended with an unknown outcome, or finished while nobody was
watching. The row is created by a trigger in the same transaction as the fact, so retrying
a transition cannot produce a second alert.

Delivery reuses the channel outbox: one connection, one lease, one sender. Alerts are
queued only while they are still true and recent, and `notification_id` is unique in the
outbox, so nothing is sent twice. An unconfirmed send is shown as **Delivery unconfirmed**
and is never retried automatically. With no enabled Telegram connection the alert is
recorded and Today shows it as **Not sent**; nothing leaves the machine.

Alert text names the assistant, the event kind and where to review it. It contains no
prompt, action arguments, fact values or message content. Today lists recent alerts with
their delivery state under "Alerts Hutch sent", and GET /api/v1/notifications returns the
same facts. Delivery is at-least-once at best: it is not proof of receipt or reading, and
there is no exactly-once claim for any external effect.

## Storage and limits

Schema v84 adds spaces, space_members, bot_space_grants, commitments,
commitment_dependencies and commitment_events. Schema v86 adds notifications and rebuilds
channel_deliveries to reference either an inbound event or a notification, preserving every
existing reply delivery; schema v87 reinstalls the notification triggers so a database that
already applied v86 receives a corrected trigger body. Both migrations are additive in effect
and do not rewrite existing rows; a pre-upgrade SQLite backup is taken by the existing store
upgrade path. Bounded:
title 200 characters, detail 4000, evidence 2000, at most 20
dependencies, at most 500 commitments per list page, 25 per assistant list result and
8 assistant proposals per run.

## Troubleshooting

- "No shared-space access": the assistant has no grant for that space. Grant it on
  Shared, then retry.
- "Confirm this commitment before marking it done": the row is an assistant proposal.
- "This commitment changed elsewhere; reload it": a stale revision; reload Today.
- Unknown timezone: pass a valid IANA name (for example America/Vancouver).
- Agenda says "No calendar or mailbox is connected yet": connect the account in
  Connections and grant one calendar or mailbox to an assistant first; the agenda cannot
  grant itself access.
- Agenda says the permission is no longer valid: reconnect the account and grant it again.
  A revoked or expired grant is never shown as an empty day.
- Agenda shows **Stale**: the refresh failed and you are looking at the last successful
  read, with its time. Reload to try again.
- An alert is **Delivery unconfirmed**: check the actual Telegram conversation, then record
  the checked outcome on the connection. Hutch will not resend it on its own.
- An alert is **Not sent**: no enabled Telegram connection was delivering for that
  assistant. Start a connection, or read the fact on Today directly.
