---
name: outlook-mail-digest
description: Digest recent Outlook mail into a short brief with senders, subjects and what needs a reply. Use when the user asks what arrived in their inbox or wants a morning mail digest. Requires the Bot to have an Outlook Mail connection granted.
license: MIT
compatibility: Requires an Outlook Mail connection granted to this Bot. Read-only.
metadata:
  hutch.version: "1.0"
  hutch.requires-connections: "outlook-mail"
---

# Outlook mail digest

Produce a short, honest digest of recent mail using only the granted Outlook Mail search. This
skill reads; it cannot send, delete or move anything.

## Prerequisites

The Bot must have an Outlook Mail connection granted by the operator. If `outlook_mail_search`
is unavailable, say exactly which connection and grant is missing and stop — do not attempt to
reach the mailbox any other way.

## Steps

1. Search recent mail with a bounded query (for example the last 10 messages; the tool caps
   results and returns previews, not full bodies).
2. Group the results into: **Needs a reply**, **FYI**, and **Likely noise** (newsletters,
   notifications). Base the grouping only on sender, subject and the returned preview.
3. Keep the digest to the point: no more than 10 bullets total, one line each.
4. Never quote more than a short phrase from a preview, and never repeat anything that looks
   like a credential, one-time code or private identifier.

## Output format

- **Inbox, last check**: one line with the query and how many messages were returned.
- **Needs a reply**: sender — subject — why (one short clause).
- **FYI**: sender — subject.
- **Noise**: a count with one example, not a full list.
- **Not covered**: state plainly that only previews were read and older mail was not searched.

## Edge cases

- An empty result is a valid answer: report "no matching mail" rather than padding the digest.
- If the connection is present but the search fails, report the tool's error text and stop;
  do not retry more than once.
