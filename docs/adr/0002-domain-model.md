# ADR-0002: Model the product, not just execution attempts

Status: partially implemented (2026-10-07). Slice: S6. Evidence: baseline journey "continue a conversation", A2, A3.

## Context

Before schema v8, a bot's "conversation" was a list of unrelated runs. Hutch now has canonical `conversations`, `messages`, and
`conversation_runs` tables. The Studio selects and archives threads through the versioned API, displays persisted message history,
and submits follow-up runs to the same conversation. Legacy run pages remain available.

## Decision

Introduce these entities. IDs are opaque and stable; display names are labels, never keys. SQLite tables with
foreign keys on; JSON `doc` columns only for fields that are never queried.

| Entity | Purpose | Key rules |
|---|---|---|
| **Bot** | Configuration and identity (exists) | Renaming never changes `id`; `upsert_bot` no longer rewrites ids |
| **Conversation** | A thread between the operator and one bot (implemented) | A bot has many; context is never shared across conversations; archive hides it from default lists |
| **Message** | A user or assistant turn (implemented) | Ordered by conversation sequence; points at the run that produced it; canonical user/assistant history |
| **Task** (standing intent) | "Every Monday summarise X" or "finish the Q3 draft" | Separate from attempts; one task has many runs |
| **Run / Attempt** | One execution (exists) | Belongs to a conversation and optionally a task; has a fence, lease, and ordered state history |
| **ToolAction + Receipt** | An intended and a completed effect | Written *before* (intent) and *after* (receipt) the effect; basis for `outcome_unknown` |
| **Approval** | A decision on an exact action (exists, hardened) | Bound to an action hash; resolved by compare-and-swap |
| **Workspace / Artifact** | Stable per-bot workspace plus per-run scratch; versioned outputs | Artifacts record path, sha256, size, producing run; prior outputs survive follow-ups |
| **Provider Connection** | A credential reference plus endpoint (ADR-0005) | Secrets are referenced, never stored in the bot doc |
| **Model Capability** | Verified facts about a (route, model) pair | Probed or declared with provenance; unknown is not false |
| **Schedule / Occurrence** | Cron definition and each claimed fire | Occurrence row is the dedupe key (ADR-0001) |
| **Usage Ledger / Reservation** | Measured use, estimated use, and holds taken before a call | Separate columns for tokens, quota units and currency; unknown is NULL not zero |
| **Notification** | Something a person should see (approval waiting, handoff, failure) | Derived from state through the outbox (ADR-0003) |

**Target:** Hutch owns the canonical conversation even when an external runtime keeps its own session. Each runtime adapter declares
how it maps (`session_id` stored per conversation + runtime), what it can resume, and what happens on a model or runtime
switch: Hutch replays a bounded, summarised history into the new session and writes a visible system message saying so
("context carried over as a summary; tool state was not").

**Archive / delete / export** (per data class):

| Data | Archive | Delete | Export |
|---|---|---|---|
| Bot config | hides, stops schedules | cascades after a confirmation that lists what goes | YAML |
| Conversations, messages | kept, read-only | deleted with the bot or on request | JSONL |
| Runs, events, receipts | kept | deleted with their conversation; **audit rows** (approvals, receipts) are kept 90 days then purged unless exported | JSONL + hash chain |
| Memory | kept | deleted | JSON |
| Workspace, artifacts | kept | **never deleted if the workspace is the user's own folder (`workdir`)** | tar of Hutch-created files only |
| Browser profile | closed | deleted | not exported (contains credentials) |
| Credentials | n/a | removed from the keyring; connections that reference them are marked broken | never exported |

Running work is cancelled first; deleting a bot with a live run is refused until Stop completes.

## Consequences

* Schema v8 migrates every old run into its own `is_legacy` conversation, with its prompt and assistant message events. It never
  combines runs whose continuity was not recorded. Existing IDs and event chains remain unchanged.
* New v1 conversation creation, message admission, archival, and their idempotency receipts are transactional. Each admitted run
  stores a snapshot of up to 12 prior messages and 16,000 characters; only the governed builtin runtime currently consumes that
  snapshot. Pi and OpenCode stay disabled, so external-session translation is not active.
* SQLite FTS5 indexes canonical message text for explicit search. It does not index tool output, credentials, workspaces, or memory,
  and search results are not automatically injected into prompts.
* Durable facts, approval/edit workflows for bot-written memory, workspace artifacts, delegation, notification outbox, deletion,
  and export remain future work. Current archive hides a thread; it does not delete its records.
* Cost: more tables; each is small and indexed on the foreign key.
* Rollback: tables are additive; old code ignores them.
