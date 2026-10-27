# ADR 0023: Channel admission and delivery are separate durable boundaries

Status: accepted for the Telegram private-text preview; other transports pending.

The same assistant should be reachable from configured channels without creating
a second agent loop or allowing a chat message to impersonate owner approval.
Transport acknowledgment, model completion, tool effects and outbound delivery
are distinct outcomes and must survive a gateway restart independently.

Migration 81 adds a connection registry, bounded pending inbox, sender/assistant
conversation bindings and reply outbox. It is additive, uses the ordinary
pre-upgrade backup, and installs content-free durable change notifications.
Canonical conversation admission retains its existing idempotency, context,
run/task, model, budget, approval and receipt pipeline. A channel's recorded
revision is rechecked at admission and claim; stale or revoked work cannot start.
Only ask-mode Bots receive this preview's channel work. The native host and the
workflow interpreter remain unchanged.

Sender identity is an exact numeric allowlist and private-chat check. Every
sender/Bot pair has a separate conversation; neither automatic home-chat
selection nor a later Bot reassignment may transfer that history. Bot memory and
workspace authority remain the Bot's, disclosed before start. Channel messages
are not owner memory-learning evidence or approval decisions. Normal tool grants
and exact owner action approvals remain authoritative.

Connection save/discovery are separate from start. Explicit starts ignore older
backlog at Telegram's second timestamp precision; ordinary restart preserves the
cursor and start boundary. One leased transport owner commits updates before
their acknowledgment, and one canonical task is admitted at a time per connection.
Task admission limits and a 100-item pending cap bound work without inventing
successful processing when the queue is full.

Sending commits `sending` before crossing the network. An interrupted or ambiguous
send is `uncertain`, never an automatic retry. Only a definitive provider rejection
with a retry hint requeues automatically. Reconciliation requires the exact
attempt and independent operator evidence; changed/disabled authority cannot
reuse a pending reply. This avoids claiming exactly-once external delivery where
Telegram provides no such transaction with local SQLite.

Secrets use the explicit selected OS vault; no plaintext fallback. Token rotation
writes a new immutable vault reference, then compare-and-swaps the paused
configuration before retiring its prior reference. A stale writer can remove only
its own new secret. Disconnect leaves audit/history while clearing its authority.
Snapshot restoration disconnects every channel from source vault references,
cancels pending messages/replies and retains in-flight sends as uncertain. It
never deletes a source-profile credential or resumes old channel work on activation.

The first UI lives under Apps & AI → Telegram, with explicit sender discovery,
paused save, start review, pause, access edits, credential replacement/disconnect
and delivery review. It reuses the connection directory and 14px labels/16px
inputs/44px controls, with narrower layouts and inline errors. It does not claim
Slack, signed-webhook, group, attachment or live Telegram acceptance. Native
packaging, full-source regression, retention management and live account checks
remain release gates. See [channel setup and contracts](../channels.md).
