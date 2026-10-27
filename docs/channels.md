# Telegram channels

Telegram private text is an implementation preview. Slack Socket Mode and signed
webhooks remain unavailable. Transport/vault tests are synthetic; a live Telegram
bot and target-native packaged acceptance have not been verified.

Open **Apps & AI → Telegram**. Create a dedicated bot with
[Telegram's BotFather](https://t.me/BotFather), enter its token and choose an
assistant that asks before changes. Use an assistant whose model is configured.
Do not share one bot with another polling application.

Send the bot a private hello, then choose **Find my Telegram account**. Select
only accounts you trust with that assistant's knowledge and permitted tools.
Numeric user IDs can also be entered explicitly; usernames cannot authorize
access. Discovery returns sender identity without message text, acknowledges no
messages and starts no agent work.

**Save connection** stores the token in the selected OS credential store and
leaves the connection paused. **Start receiving and replying** is a separate,
reviewed choice. Messages and generated replies reach Telegram and the model
service chosen for that assistant; connected tools retain their own grants and
approval rules. This is not a Telegram or model-provider privacy guarantee.

## Conversations and control

Only private human text messages from selected IDs enter the ordinary Hutch run
engine. Groups, bot senders, slash commands, edits and attachments are ignored.
Channel input cannot resolve approvals, change grants or learn an owner
preference automatically. Review consequential actions in Hutch's Needs you view.
Auto-mode assistants cannot receive channel work.

Each sender and assigned assistant has a separate durable conversation. Main-chat
history is not copied, and channel conversations cannot be adopted as the main
chat. The assistant can still use its already-approved knowledge and tools: a
separate conversation is not a new permission boundary around the Bot's entire
workspace. Choose allowed people accordingly. Switching assistants while paused
starts a separate conversation; old history remains attached to its original Bot.

An explicit start accepts messages dated from that start second onward. Telegram
timestamps have one-second precision, so a message in the same second can also
be included. Older paused backlog is ignored. Restart and sleep do not change
this boundary: the committed cursor resumes after the application returns.
Telegram's own retention limits still apply during long offline periods.

One task at a time and up to 20 new tasks per hour are admitted per connection,
in addition to Hutch's global/Bot/provider limits. A full 100-message pending
inbox applies backpressure without advancing the acknowledged cursor. These
are admission limits, not provider invoice guarantees or a complete storage
retention policy.

**Pause** revokes pending admission, asks active channel runs to stop, and cancels
unsent replies. A send already in progress may still arrive. Access changes and
token replacement require a paused connection and its current revision. They do
not silently broaden the assistant's permissions. **Disconnect and remove token**
removes the referenced credential while preserving connection/delivery/history
records. Reconnect that same Telegram bot with a replacement token before
starting it again. Removing a Bot disables its channel; the channel can then be
disconnected or deliberately assigned to another assistant.

Hutch must remain running and the computer awake to receive and reply. The native
window's background/quit behavior is separate from the connection's paused state.

## Delivery and recovery

The inbox commits each update and its cursor before the next poll acknowledges
it. A unique transport identity and canonical message idempotency prevent
duplicate tasks if admission is interrupted. A channel lease coordinates multiple
gateway instances. Unknown/reused conflicting update identities fail visibly.

Completed canonical replies enter an independent durable outbox. Text is sent as
plain text, with link previews disabled and Telegram content protection requested.
These flags are not a guarantee against a recipient retaining information. Long
answers are explicitly shortened, with the full answer and artifacts in Hutch.
Telegram acceptance is not proof of receipt or reading.

A timeout, server failure, redirect, malformed success or lost sender outcome
leaves **Delivery unconfirmed**. Hutch does not automatically resend it. Open
**Review deliveries → Review outcome**, independently check the actual Telegram
conversation, and record whether the reply is present or confirmed absent. A
confirmed absence permits a retry only under the same still-active revision;
otherwise it is cancelled. Stale/duplicate reconciliation is refused.

An explicit rate-limit rejection schedules a bounded backoff using Telegram's
retry hint. Definitive client errors remain failed; they are not reported as sent.
Retrying definitively failed old replies after credential/access changes is not
implemented. A restored database is held, disconnected from source vault
references and stripped of pending delivery authority; activation alone never
resumes its old channel work or sends. Source credentials are not deleted.

## API v1

These routes are local-owner only, under the existing authentication, origin and
CSRF boundaries. Paired-phone permissions do not expose channel tokens/settings.
No anonymous webhook ingress or public server exposure is enabled.

| Method and route | Result |
| --- | --- |
| `GET /api/v1/channels` | Contract version 1, safe connection state, secure-store availability, unsupported transports |
| `POST /api/v1/channels/telegram/senders` | Explicit bot-token validation and bounded sender discovery without acknowledgment |
| `POST /api/v1/channels/telegram` | Validate supplied bot, save credential, create paused connection |
| `PUT /api/v1/channels/{id}/enabled` | Start/pause using `expected_revision`; start requires a stored token |
| `PUT /api/v1/channels/{id}/configuration` | Change name/assistant/senders while paused, with `expected_revision` |
| `PUT /api/v1/channels/{id}/token` | Replace a paused bot's token, binding its stable Telegram bot identity |
| `DELETE /api/v1/channels/{id}?expected_revision=N` | Disconnect, remove referenced secret, retain evidence |
| `GET /api/v1/channels/{id}/deliveries` | Latest 50 content-free delivery summaries; no reply bodies or credentials |
| `POST /api/v1/channels/{id}/deliveries/{delivery}/reconcile` | Exact uncertain delivery, attempt count, checked outcome and evidence |

Connection resources include `contract_version: 1`, identity, assistant, allowed
senders, paused/enabled state, revision and safe error; never the token or vault
reference. `has_token` records a saved credential reference, not ongoing remote
validity. Delivery states are `pending`, `sending`, `sent`, `uncertain`, `failed`
and `cancelled`. The event identity and selected policy revision persist with the
canonical run, independently from delivery outcomes and tool-action receipts.

Upstream contracts: [Telegram Bot API](https://core.telegram.org/bots/api),
[update acknowledgment](https://core.telegram.org/bots/faq#how-do-i-get-updates).
The implementation uses the official HTTPS API and Python standard library; no
upstream agent source or third-party Telegram SDK was copied.
