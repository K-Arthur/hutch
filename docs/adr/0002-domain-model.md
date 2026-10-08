# ADR-0002: Model the product, not just execution attempts

Status: accepted (2026-10-07). Slice: S6 (conversations, workspaces). Evidence: baseline journey "continue a conversation", A2, A3.

## Context

Today a bot's "conversation" is a list of unrelated runs (baseline). Grok Bot and dots both treat the bot as a *durable
teammate with its own conversation* whose context develops over time (A2, A3). Hutch has Bot, Task, Run, Event,
ApprovalRequest, MemoryItem only.

## Decision

Introduce these entities. IDs are opaque and stable; display names are labels, never keys. SQLite tables with
foreign keys on; JSON `doc` columns only for fields that are never queried.

| Entity | Purpose | Key rules |
|---|---|---|
| **Bot** | Configuration and identity (exists) | Renaming never changes `id`; `upsert_bot` no longer rewrites ids |
| **Conversation** | A thread between the operator and one bot | A bot has many; context is never shared across conversations unless the user attaches it; `archived_at` |
| **Message** | A user or assistant turn, or a system notice | Owned by a conversation; points at the run that produced it; this is the canonical user-visible transcript |
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

**Hutch owns the canonical conversation** even when an external runtime keeps its own session. Each runtime adapter declares
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

* Migration: new tables; `conversations` back-filled with one conversation per bot containing its past runs, so history is preserved.
* Cost: more tables; each is small and indexed on the foreign key.
* Rollback: tables are additive; old code ignores them.
