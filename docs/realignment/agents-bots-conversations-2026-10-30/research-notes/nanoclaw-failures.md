# NanoClaw and OpenClaw failure research (agents, bots, conversations)

Captured 2026-10-30. Read-only research; this note is the only artifact written.

Evidence classes: [DOC] vendor documentation fact from docs.nanoclaw.dev; [GH] issue-tracker fact as returned by `gh api repos/openclaw/openclaw`; [ANEC] anecdote (one report, unconfirmed, or second-hand). "Reading:" marks my interpretation. Timestamps are reproduced verbatim from the API (UTC); absent fields are called out rather than filled.

Reachability: all four NanoClaw guide pages returned HTTP 200 (274116, 243558, 237198, 279066 bytes); the first-agent page footer read "Last modified on September 4, 2026". All five named issues and comment pages returned successfully, and fetched comment counts matched each issue's `comments` field (2, 2, 2, 5, 1). No `gh` call failed; core rate limit was 4971/5000 remaining.
Repo metadata: created 2025-11-24, 7919 open issues, 393500 stars, not archived. Reddit was blocked: `r/openclaw/about.json` returned HTTP 403 and `search.json` returned HTML, not JSON, so no Reddit evidence is used. HN Algolia returned HTTP 200 for every query.
Every page and API response used below was fetched during this session; nothing is cited from memory.

---

## A. NanoClaw documentation

Pages read: `/guides/first-agent`, `/guides/customize-an-agent`, `/guides/scheduled-tasks`, `/guides/multi-agent-swarm`. A "Migrate from v1 or OpenClaw" page appears in navigation but was not fetched, so the OpenClaw lineage is established only as a migration path the vendor names.

### A1. Agent lifecycle
- An agent is an "agent group" (central DB row plus `groups/<folder>/`), a "messaging group" (one chat on one platform, unique `(channel_type, platform_id)`), and a "wiring" (routing rule). [DOC]
- `ncl groups create` inserts the row and runs `initGroupFilesystem()` inline, so folder and container-config row exist before any message; re-running with the same `--folder` returns the existing row, and a directory with no owning row is refused rather than adopted. [DOC]
- A never-messaged agent costs nothing: "no container runs for it". First contact is a cold start, "expect 30-60 seconds"; the session persists server-side so context carries across invocations. [DOC]
- The two pages describe idle exit differently: first-agent says "the runner never exits just for being idle", customize-an-agent says "containers exit after idling". Reading: reconcilable but never stated as one rule - the runner does not self-exit, the host sweep terminates it - and neither page gives the idle threshold. [DOC]
- `ncl sessions list` exposes `status=active` and `container_status=running`; `ncl groups restart --id <id> [--rebuild]` forces a fresh container. [DOC]

### A2. Workspace ownership
- Three surfaces: personality in `groups/<folder>/instructions.prepend.md`, "brain" (model, effort) in the `container_configs` row, capabilities (packages, MCP servers) behind admin approval. [DOC]
- `groups/<folder>/CLAUDE.md` is host-generated on every spawn and re-mounted read-only; whatever is written there "gets clobbered". It is one flat file with no `@`-imports, pinned by a test. [DOC]
- `instructions.prepend.md` is inlined verbatim as the first section (`# Persona`) and "is never dropped, even when the document hits its size cap"; durable facts live in `memory/`. [DOC]
- Ownership splits by mechanism: persona is co-owned by operator and agent (the `self-customize` skill edits it with no approval), while capabilities require approval because they change what the agent can do. [DOC]
- Documented doc-rot: the `/customize` skill text "still points persona edits at the composed `groups/<folder>/CLAUDE.md`", which the tutorial contradicts. [DOC]

### A3. Scheduling
- "v2 has no scheduler service." A task is a row in an isolated per-task session's `messages_in` table with `kind='task'` and `process_after`, swept by the same host sweep as chat messages. [DOC]
- The sweep waits 60 seconds after the prior tick drains; message writes and container-exit can trigger earlier checks. Timing is explicitly approximate: "the roughly one-minute resync is not a strict latency bound; do not schedule anything that needs second-level timing." [DOC]
- "Recurring tasks are clones, not loops": on completion, reconciliation computes the next run with cron-parser, inserts a fresh pending row with the same `series_id`, and clears `recurrence` on the completed row so it is not re-cloned. A series with no live occurrence and a stopped container has its per-task session closed; history remains until explicitly deleted. [DOC]
- Recurrences over 4 fires per day are refused unless the task carries a `--script` gate or `--dangerously-override-recurrence-limit`. [DOC]
- `--script` runs in-container before the agent: 30-second timeout, 1 MB output cap, process-group SIGTERM then SIGKILL after 2 seconds, last stdout line must be JSON `{wakeAgent, data}`. Failure marks the occurrence failed, backs off exponentially, and auto-pauses after 8 consecutive script failures. [DOC]
- The docs state the limit plainly: "the container still wakes on every firing (the sweep can't know the script's verdict in advance)". The script gates the agent call, not the spawn. Task rows live in `data/v2-sessions/<agent_group_id>/<task_session_id>/inbound.db`; template-stamped tasks are created paused. [DOC]

### A4. Swarm delegation
- "There is no swarm engine." Agent groups are fully isolated (own container, workspace, memory); "agents never share state - they can only message each other". [DOC]
- Agent-to-agent messages are queue rows through the same SQLite inbox/outbox as a WhatsApp message, only `channel_type` differs (`agent`). [DOC]
- Destinations are permission edges: a row in `agent_destinations` means "agent A may send to target B, and calls it `local-name`"; "No row, no delivery." Each direction is a separate row, and channels and agents share one namespace. [DOC]
- `create_agent` is fire-and-forget: host inserts the row, scaffolds the folder, seeds instructions, adds a container config inheriting the creator's provider, inserts two destination rows (creator to child, child to creator as `parent`), projects into the parent's running container, and notifies it. No child container starts until its first message. [DOC]
- Authorization depends on the caller's `cli_scope`: the wizard's first agent is trusted (`global`) and creates directly; other groups default to `group` scope and "is a potential prompt-injection victim", so approval is queued. Approver order is group admins, global admins, owners; with no reachable approver "the request fails and the agent is told why". [DOC]
- Destination names are local: a child knows its creator only as `parent`. Sibling and cross-level edges do not exist by default and are added by hand, one direction per `ncl destinations add`; a per-edge `message policy` can hold every message for human approval. [DOC]

### A5. Context transfer
- Between agents the payload is message text plus any `send_file` attachments copied from sender outbox to receiver inbox; memory, workspace and tools are not shared. [DOC]
- "Every routed a2a message is stamped with the sender's `source_session_id`", and a reply goes to "which parent session started the exchange - not to whichever parent session happens to be newest". [DOC]
- "Sibling sessions in the same conversation can still receive non-triggering background context through cross-session echoes"; on server channels `--session-mode per-thread` is forced. Reading: routing identity for replies is defined, but no durable delegation record (who asked, what returned, whether delivered) is described. [DOC]

### A6. Process isolation
- One container per active agent, spawned on first message, ended by the host sweep when idle or by restart; container names start with `ncl-` and derive from install and session ids, enumerated via `docker ps --filter label=nanoclaw-install`. [DOC]
- Isolation is per agent group, not per task: the private per-task session DB is described, but not a separate container per scheduled task. The "Isolation levels" page was outside this brief and was not read, so per-level guarantees are not asserted here. [DOC]

### A7. Documented limits
- "No general loop protection. There is no throttle, hop limit, or cycle detection on agent-to-agent messages - two agents told to 'always reply' will ping-pong indefinitely, burning API calls." The one broken loop is failure notices. [DOC]
- "No broadcast" (one destination per message) and "No concurrency cap": `MAX_CONCURRENT_CONTAINERS` was "removed from the code entirely". [DOC]
- Destination edits made outside `ncl` do not propagate live; a running container serves a projection refreshed on wake and by ncl commands. [DOC]
- `ncl groups delete` cascades central-DB rows and stops the container within about a minute, but "does not delete `groups/<folder>/` and `data/v2-sessions/<group-id>/`"; a later bare create refuses to reuse a leftover folder without an owning row. [DOC]
- Routing fails open: "an invalid pattern fails open (the agent responds to everything)". Wiring is fan-out, so a catch-all plus a named wiring means "a message starting with 'scout' engages both agents and you'll get two replies". [DOC]

---

## B. Named issues (openclaw/openclaw)

Fetched with `gh api repos/openclaw/openclaw/issues/<n>` and `/comments?per_page=100`.

| Issue | State (reason) | Closed by |
| --- | --- | --- |
| 72604 | closed (completed) | clawsweeper[bot] |
| 62872 | closed (not_planned) | clawsweeper[bot] |
| 21104 | closed (completed) | BooRy95 (reporter) |
| 72176 | closed (not_planned) | clawsweeper[bot] |
| 67619 | closed (not_planned) | steipete (maintainer) |

### B1. 72604 - duplicate messages after session replay/restart
- "Session history replay creates duplicate messages in web UI after session restart/migration". Closed, created 2026-04-27T05:08:32Z, closed 2026-04-30T18:45:41Z, labels none, 2 comments, reporter GenieWeenie; version 2026.4.24, macOS 15.6, Node v25.9.0. [GH]
- Symptom: after context overflow, auto-compaction and session restart (new sessionId, same sessionKey), the gateway replays old history into the new session and every reconnect replays again - "35 messages dumped into the session in a single second" at 04:31:15, 12 at 04:15:20, one duplicate 152 ms after its twin. [GH]
- Repro: active webchat session, force context overflow so the session restarts, reconnect repeatedly. [GH]
- Stated root cause (reporter source reading): `createTranscriptUpdateBroadcastHandler` in `server.impl-CtLS1ywt.js` unions `sessionEventSubscribers` with `sessionMessageSubscribers` per sessionKey, so each transcript write during replay fans out to every subscriber. [GH]
- Comment 1 (reporter, 2026-04-27) links 72227, 72356, 72341 (open), 72536 (open), 72538 (open) and three fix PRs: 72290 gateway dedupe, 72325 WebChat reload reconciliation, 72512 Enter-to-send guard; it attributes duplicates to retry paths minting a new idempotencyKey per attempt, user messages carrying no idempotencyKey, and a renderer that does not reset its text accumulator between tool blocks. [GH]
- Comment 2 (clawsweeper[bot], 2026-04-30) closes as "already implemented": replay and reseed context separated from transcript writes, compacted transcripts rotated from summary plus unsummarized tail, WebChat reload no longer duplicating optimistic tails, "present in the shipped v2026.4.27 tag". [GH]
- My checks: PR 72325 merged 2026-04-27T19:52:39Z; PR 72290 closed 2026-04-30T23:21:01Z with null `merged_at`; PR 72512 closed 2026-04-28T03:52:17Z with null `merged_at`; release `v2026.4.27` exists, published 2026-04-29T22:12:19Z. [GH]
- Resolved? Partially and only on the bot's account: the renderer/reload fix merged and the named release exists, but both gateway-dedupe changes went unmerged and no human confirmed the fix in-thread. Reading: renderer layer fixed, admission/idempotency layer unproven.

### B2. 62872 - sessions_send A2A ping-pong duplicates
- "sessions_send A2A flow ping-pong causes duplicate messages in persistent sessions". Closed, created 2026-04-08T03:10:52Z, closed 2026-05-19T15:20:38Z, labels P1, impact:session-state, impact:message-loss, 2 comments, reporter tonyhth. [GH]
- Symptom: A sends via `sessions_send` to B; B replies inline (expected), then the framework injects an "Agent-to-agent announce step" whose reply is marked `sourceTool: "sessions_send"`, routed back to A and also delivered to B's external channels - three duplicate messages. [GH]
- Repro: persistent (non-subagent) sessions, one `sessions_send`, observe the announce turn. Reporter states no effective workaround: "the ping-pong cannot be disabled". Mechanism: `maxPingPongTurns = 5` default, injected messages persist and are delivered as new user messages. [GH]
- Comment 1 (clawsweeper[bot], 2026-04-27) closes as duplicate of 39476 and 44309 while stating "current main and the latest release still show the A2A ping-pong/announce behavior" and that tests assert it. Comment 2 (2026-04-29) says "keeping this open" and gives acceptance criteria plus test paths because the tool has no per-call ping-pong disable. It was closed 2026-05-19 as `not_planned` with no comment on that date. [GH]
- Follow-up state I verified: 39476 open (13 comments), 44309 open, PR 91161 closed 2026-07-21 and PR 112326 closed 2026-09-13T03:39:12Z, both with null `merged_at`; 39476's last comment (2026-09-23) reports a fresh production trace where "both sides treated bodyless/duplicate inter-session envelopes as turns". [GH]
- Resolved? No. Closed as a duplicate of a still-open bug, and both named fix PRs closed unmerged. Reading: duplicate a2a delivery has been open since 2026-03-08 with no merged fix as of 2026-10-30.

### B3. 21104 - history orphaned when named agents added
- "Session history orphaned when named agents added to config (agent:main to agent:<name> routing change)". Closed, created 2026-02-19T17:23:27Z, closed 2026-02-27T05:16:40Z, labels ["stale"], 2 comments, reporter BooRy95; version 2026.2.17 (4134875), macOS, Telegram (~16 topics) plus Discord (~17 channels), running since 2026-01-30. [GH]
- Symptom: adding named agents and setting a new default changed the default id from `main` to `xavier`; new messages routed to `agent:xavier:*` while 474 session files and 840 MB stayed under `agent:main:*`. "The user experiences sudden, complete amnesia across every channel", with no warning or migration. [GH]
- Repro: set a non-`main` id as default in `agents.list`, restart, message any channel. [GH]
- Stated root cause, confirmed by the reporter's own fix: "`name` is cosmetic, `id` selects the session store". [GH]
- Fix applied: revert the id to `main` with `default: true` and a cosmetic name, move other agents' channel bindings to the top-level `bindings` array (they had been under `channels.discord.bindings`, an invalid key), restart, verify with `openclaw agents list --bindings`. [GH]
- Additional fallout: `session_status(model=...)` overrides applied to the wrong session so model switching "silently failed - the agent confidently reported being on Opus while actually running Sonnet"; cron jobs still referenced `agentId: "xavier"`; the invalid bindings key blocked `config.patch`. [GH]
- Resolved? No product fix. The reporter posted the workaround and left the issue open because the UX gap "is still valid"; openclaw-barnacle[bot] marked it stale on 2026-02-27 and the reporter closed it that day. Reading: an identity-key change is silent and can also silently mis-target model overrides.

### B4. 72176 - intermittent duplicate delivery
- "[Bug]: Intermittent duplicate message delivery in 2026.4.24 across all channels". Closed, created 2026-04-26T13:09:40Z, closed 2026-09-19T03:39:27Z, labels bug, regression, P2, impact:session-state, impact:message-loss, 5 comments, reporter bmdf; 2026.4.24 (cbcfdf6), regression from 2026.4.23, WSL2, npm global, bailian/qwen3.6-plus and nvidia-nim/glm4.7. [GH]
- Symptom: identical user messages delivered twice with the same timestamp but different `__openclaw.id` and sequential seq numbers (2703 and 2705); the assistant answers both (2704 and 2706, same responseId), duplicating in webchat and WeChat. Intermittent, not every message. [GH]
- Repro: run 2026.4.24, send one message, read `sessions_history`; duplicate pairs show identical timestamps. [GH]
- Stated root cause: none established. The closing sweep says "the report never demonstrates that missing message IDs caused these duplicates". [GH]
- Comments: a sweep comment (dated 2026-04-29) closes "pending a current-version reproduction"; xilopaint on 2026-05-03 reports "still an issue in v2026.5.2"; schiles67 on 2026-05-15 reports "still present in v2026.5.12" with "23% of all assistant text messages duplicated in the session transcript - one entry with short 8-char ID, one with full UUID", both delivered to Telegram. Stale notices on 2026-06-04 and 2026-09-19 preceded closure. [GH]
- Data caveat: the sweep comment's `created_at` precedes the May comments it describes, so it was evidently edited after posting; dates are reported as returned.
- Resolved? No. Two independent human confirmations across two later versions, then closed `not_planned` with no fix or version named.

### B5. 67619 - context lost after switching sessions
- "[Bug]: Agent response context lost after switching between chat sessions without explicit save". Closed, created 2026-04-16T10:25:20Z, closed 2026-04-25T18:13:59Z, labels bug, regression, 1 comment, reporter Vansh1811; 2026.2.17, Windows 11, npm global, anthropic/claude-sonnet-4.5. [GH]
- Symptom: with two or more active sessions, clicking A to B and back to A leaves A's messages and agent context "completely wiped", with no recovery option. [GH]
- Repro: five steps - two sessions, converse deeply in A, click B without saving A, return to A, observe loss. [GH]
- Stated cause: the reporter attributes it to state depending on unsaved browser-local state; no root cause was accepted by maintainers. [GH]
- Named fix: maintainer steipete closed "as not reproducible on current `main` after Codex review", citing `switchChatSession()` resetting the view and calling `loadChatHistory(state)` (`ui/src/ui/app-render.helpers.ts:509`) and `loadChatHistory()` versioning requests via `chatHistoryRequestVersions` so a response applies only when latest and `state.sessionKey` still matches (`ui/src/ui/controllers/chat.ts:19`), at commit 7e52223d3275, with a regression test for stale history responses. No version number named. [GH]
- Resolved? Probably, for the shipped UI path: code-level non-reproducibility rather than dismissal, but it remains a single anecdote with no reporter repro, and the cited fix postdates 2026.2.17.

---

## C. Independent failure evidence

### C0. GitHub issue search
Queries run as `gh api -X GET search/issues -f q='... repo:openclaw/openclaw'`. Totals are loose-query `total_count` values including unrelated work: "duplicate messages after restart" 6921, "lost conversation history" 2360, "wrong conversation delivered" 894, "agent loop infinite" 1031, "duplicate subagent delegation" 544, "subagent continues after parent completes" 172, "cannot stop agent run" 31294, "session identity bot confusion" 240. Title-scoped (`in:title`): duplicate 2318, orphan 717, "wrong session" 82, subagent 2664, "session lost" 82.
Those totals span open and closed issues alike. I did not sample-verify these, so they are reported as API values only, not incidence.

Each entry below was opened individually; symptom and version come from the issue body.

1. 39476 - "A2A sessions_send: target agent can call sessions_send back, causing duplicate messages". Open, created 2026-03-08T04:47:13Z, 13 comments, P1, impact:session-state, impact:message-loss. https://github.com/openclaw/openclaw/issues/39476
   A calls `sessions_send` to B; B replies through the tool return value, then calls back with its own report, and A posts both. Reached from 62872 as canonical tracker; production traces as recent as 2026-09-23; both canonical PRs unmerged. Reproducibility: multiple independent reports plus source-level repro. Relevance: Hutch's delegation is one-way dispatch with a final-text return, which structurally avoids this. Measure: no reverse-send channel from a child to its requester, or a hop budget with cycle detection if one is ever added.

2. 44925 - "Subagent completion silently lost - no retry, no notification, no auto-restart on timeout". Open, created 2026-03-13T09:29:37Z, 31 comments, P1. https://github.com/openclaw/openclaw/issues/44925
   On 2026.3.11 Telegram forum mode: announce-back fails after a successful child ("at least 9 times in production"), a timeout leaves the child dead with no retry or notice, and a child claims a file exists that is not on disk. Reproducibility: single reporter, repeated production occurrences with log lines. Relevance: a child finishing is not the same as the parent learning it finished. Measure: a durable completion record written in the child's terminal transaction and retried until the parent observes it.

3. 164972 - "claude-cli multi-agent teams: end-to-end matrix under visibility agent/tree/all (clarification, follow-up and parent context all break; failures look like success)". Open, created 2026-10-04T15:07:54Z, 10 comments, P2. https://github.com/openclaw/openclaw/issues/164972
   On 2026.9.7 and 2026.9.8 only "a parent hands a fully specified task to a child and gets one result back" works; clarification, follow-up and parent-context handoff break and present as success. A 2026-10-15 update says some rows work on 2026.10.3 and one needs 2026.10.5. Reproducibility: systematic matrix over three visibility modes, one author, linked per-mechanism issues. Relevance: Hutch's specialist handoff has a real clarification path (question card, `needs_input`), which is the row this matrix says breaks. Measure: a typed child outcome (completed, failed, needs_input, cancelled) the parent must consume.

4. 145908 - "Session continues after chat timeout - unbounded loop requiring Gateway restart". Open, created 2026-09-12T10:54:06Z, 2 comments, P1. https://github.com/openclaw/openclaw/issues/145908
   On 2026.7.1-2 a session kept running after "chat run timed out", re-entered by 11 heartbeat polls with an identical timestamp, aborted settle timed out (`timeoutMs=2000`), and ran 37+ user turns until restart. Reproducibility: single report with transcript line numbers, no minimal repro. Relevance: Hutch parks a waiting parent and exits its worker, so the inverse risk is a run outliving its own timeout. Measure: timeout terminates the run and is verified by process death, not a status flag.

5. 119313 - "agents: embedded run loop never returns and keeps dispatching billed model calls when mid-turn precheck has nothing to truncate". Open, created 2026-08-04T19:04:52Z, 3 comments, P1, labelled `clawsweeper:bulk-filed`. https://github.com/openclaw/openclaw/issues/119313
   With `midTurnPrecheck.enabled: true` a tool-heavy session loops with zero backoff; "the loop's own retry cap (32 to 160 attempts) is never reached because the attempt that consumes budget also refunds it". Only a user abort stops it; the flag is opt-in. Reproducibility: source-level repro at a named commit. Relevance: a retry budget that can be refunded is not a budget. Measure: monotonic per-run step and spend counters no retry path can decrement.

6. 135117 - "2026.8.1 heartbeat replays delivered async results into the wrong Discord channel". Open, created 2026-09-01T10:37:01Z, 7 comments, P1, impact:security. https://github.com/openclaw/openclaw/issues/135117
   An already-delivered isolated cron result was replayed about nine minutes later into a long-lived `heartbeat-main` session with unrelated stale completions; the session used "a sticky Discord route acquired from an earlier, unrelated workstream" and posted into the wrong channel, described as "a live cross-channel reproduction" of the gap in 69492. Reproducibility: single report with a timed trace. Relevance: Hutch routes per run and channel; "sticky last route" is the mechanism to avoid. Measure: delivery target stored on the producing run, never resolved from session or connection state at send time.

7. 158156 - "Chat: assistant response occasionally rendered/duplicated twice in full, verbatim, within a single turn". Open, created 2026-09-25T14:26:48Z, 5 comments, P2. https://github.com/openclaw/openclaw/issues/158156
   Two occurrences in one session on 2026-09-25, one partial and one byte-for-byte duplicate of a two-paragraph answer within what the UI called a single turn; `sessions_history` showed two stored assistant entries, "not a UI rendering artifact". Reproducibility: single reporter, transcript-level evidence. Relevance: duplicate rendering can be a storage defect, not a paint bug. Measure: one canonical assistant message per (run, attempt, segment), enforced by a uniqueness constraint rather than renderer dedupe.

8. 177498 - "2026.10.5 Dashboard sidebar session filter default view causes historical conversations to appear missing". Open, created 2026-10-19T16:49:38Z, 2 comments, P2. https://github.com/openclaw/openclaw/issues/177498
   After upgrading, the sidebar showed 8 of 30 sessions because the default filter was `includeGlobal+includeUnknown+configuredAgentsOnly+agentId+archived`; "Data is intact; the filter is simply restricting display", but users read it as lost history. Reproducibility: UX report with filter values. Relevance: absent-from-view is indistinguishable from deleted for a local-first user. Measure: permissive defaults plus a visible "showing N of M" and clear-filter affordance.

9. 170030 - "[2026.9.8] Control UI loses recent conversation from rendered history". Open, created 2026-10-12T17:08:18Z, 3 comments, P2. https://github.com/openclaw/openclaw/issues/170030
   The UI showed 1-3 recent exchanges followed by messages 20-36 hours old while `/readyz` passed; a separate `chat.history` read at limit 1000 returned recent records (500 assistant, 487 toolResult, 13 user) with `hasMore=true`; one "Show earlier" did not restore contiguous history. Reproducibility: single report with API cross-check. Relevance: the store held the data and the view did not. Measure: paging tested against a store that provably holds the rows, asserting contiguity after one page-back.

10. 103067 - "Centralize chat-session naming; define subagent session lifetime and cross-channel persistence". Open, created 2026-07-09T18:33:15Z, 6 comments, P2. https://github.com/openclaw/openclaw/issues/103067
    ACP/Copilot sessions lack meaningful titles; "the lifetime of agent-created subagent sessions is undefined - when they should live, persist, or be cleaned up is unclear"; no defined model for agent identity across channels and sessions. A design gap, not a code defect. Relevance: Hutch keeps bot, conversation, run and specialist task as separate objects with separate ids; this is what happens when they collapse. Measure: publish a lifetime table (bot, conversation, run, delegated child) with owner, terminal state and retention rule for each.

### C1. Hacker News (fetched, thin)
- Story search returned 2926 hits for "openclaw" and 501 for "nanoclaw"; top stories concern billing policy, security, popularity and renaming, not orchestration defects, e.g. 47963204 (2026-04-30), 47628608 (2026-04-03), 46850205 (2026-02-01, NanoClaw Show HN).
- The one dated failure anecdote: HN story 47150122, 2026-02-25, "OpenClaw deletes Summer Yue's emails", 10 points, 2 comments, linking the reporter's own post. A later comment (47269231, 2026-03-06) describes the same incident as an agent "deleting 200+ emails while ignoring her stop commands", claiming "context window compaction dropping" the constraint as root cause. [ANEC] Reproducibility: single incident, second-hand in the comment, no version pinned. Relevance: work that continues after a stop instruction. Measure: stop cancels the run tree and is enforced at the tool layer, not by messaging the model.
- Comment searches for "openclaw duplicate messages" and "nanoclaw duplicate" returned zero hits; I found no HN evidence for duplicate delivery, orphaned history, wrong-conversation delivery, or parent-before-child completion.

### C2. Reddit (blocked)
`https://www.reddit.com/r/openclaw/about.json` returned HTTP 403 and `search.json` returned HTML instead of JSON. No Reddit evidence is included; this is a reachability gap, not a null result.

### C3. Sample bias
- The tracker is machine-triaged: many closures here come from `clawsweeper[bot]` with `not_planned` or `completed`, and some carry `clawsweeper:bulk-filed` (119313). Closure reason says little about whether behavior changed.
- Issue authors are the population that files issues; silent users and fixed-in-config cases are absent. 21104 is a config mistake, not a code defect, and would not appear in a code-only review.
- Several entries are single-reporter (145908, 135117, 158156, 170030, 67619), which bounds their weight. Only 39476 has multiple independent reports plus a source-level repro plus a production trace.
- Vendor docs state intended behavior, including intended absence of loop protection; they cannot show whether the implementation matches the document.

---

## Failure modes Hutch must design against (ranked)

1. Duplicate delivery from replay or retry (72604, 72176, 39476, 158156). The same content enters the transcript twice under different ids. Measure: stable inbound idempotency key plus a uniqueness constraint on (conversation, source message id); replay never writes transcript rows.
2. Bidirectional agent-to-agent reply loops (62872, 39476, 44309; NanoClaw documents "no general loop protection"). Measure: one-way delegation only, or hop budget, cycle detection and a per-edge human gate.
3. Silent orphaning when an identity or routing key changes (21104, 103067). Measure: immutable store keys, mutable display names, an explicit migration on key change, and a warning when the default identity changes.
4. Completion reported before child work durably settles (44925, 164972). Measure: the parent's terminal state is written from the child's durable terminal record in one transaction with the result.
5. Lost child completion (44925; 164972's "failures look like success"). Measure: outbox with retry and an operator-visible "delivery unconfirmed" state.
6. Unbounded or unkillable runs (145908, 119313; HN 47150122 for the instruction-level version). Measure: monotonic step and spend budgets, timeout verified by process death, cancellation of the whole child tree.
7. Wrong-conversation delivery (135117; same shape in 153543 and 148274, seen in search listings but not opened). Measure: delivery target is a field on the run, resolved once at admission.
8. Stale response applied to the current session (67619). Measure: versioned history requests pinned to the session key, as the maintainer's fix describes.
9. History present but invisible (177498, 170030). Measure: permissive default filters, "showing N of M", and a contiguity test that pages back through a known store.
10. Identity ambiguity between bot, agent, session, conversation and channel (103067). Measure: one id per object, one lifetime table, and an operator-visible label on every transcript row naming the object that produced it.
11. Fan-out duplicates that are configuration, not defects (NanoClaw wiring fan-out; pattern failing open on invalid regex). Measure: validate wiring at write time, fail closed on invalid patterns, and preview which agents a message would engage before saving.
12. Deletion that leaves the durable half behind (NanoClaw `groups delete` keeps `groups/<folder>/` and `data/v2-sessions/<group-id>/`; Hutch's own bot-deletion plan). Measure: tombstone plus an explicit verified workspace purge, and refuse recreate-into-leftovers.

---

## Open questions

1. Does Hutch persist an idempotency key on inbound channel messages today, and is it stable across channel retries - the exact gap 72604 attributes to 2026.4.24?
2. Is there any bot-to-bot send in Hutch, or only one-way specialist dispatch and same-bot `delegate_task`? If the latter, modes 1 and 2 collapse into the channel and provider paths.
3. When a delegated child finishes, is the parent requeue driven by a durable child terminal record or by an in-memory notification?
4. Does Hutch's Stop verify process death for the whole child tree, and what is the bound between Stop and a provably dead tree?
5. Are bot ids immutable across rename, and does any config key select a store the way OpenClaw's default agent id did in 21104?
6. Do Hutch history views default to showing all conversations, and is there a contiguity test equivalent to the one missing in 170030?
7. What is the retention and cleanup rule for delegated child transcripts once the parent conversation is archived?
8. Do Hutch scheduled tasks have clone-versus-loop semantics like NanoClaw's (stable series id, one live occurrence), and what happens if a clone insert is retried?
9. Which isolation guarantees apply per bot versus per run? NanoClaw's isolation-levels page was outside this brief and was not read.
10. Can the "replay/reseed context is runtime-only" property claimed in 72604 be verified in code, or is it only a bot's assertion?
