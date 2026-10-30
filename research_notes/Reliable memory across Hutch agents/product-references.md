# Grok Bot and Meta Muse: reliable memory and conversation continuity

Research/access date: **2026-10-23** for every linked source below. Public-document research only: no account access, hands-on product trial, proprietary-code inspection, or Hutch implementation audit. **B** denotes vendor-documented user behavior; **M**, vendor-described mechanism; **R**, an external report; recommendations are explicitly inferences. Documentation establishes what vendors say, not independently measured reliability.

## 1. What does Grok Bot persist, and how does continuity work?

### Takeaway

Grok Bot distinguishes conversations, learned memory, shared computer state, and handoffs. Its latest release makes memory continuity across one personal Bot’s chats explicit; this is not permission for every Bot to read every conversation. [Overview](https://docs.x.ai/grok-bot/overview), [October 22 changelog](https://x.ai/changelog/bot#v0.75.2).

### Cited Findings

- **B — Conversation versus long-term memory.** A Bot retains “stable working preferences, important facts, and summaries,” without replaying every message. Its description holds standing rules; chat holds task-specific instructions. The overview says conversations and learned context “stay separate per Bot.” History is searchable, although search availability varies. [Bots](https://docs.x.ai/grok-bot/bots), [overview](https://docs.x.ai/grok-bot/overview), [collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration).
- **B — Current cross-chat behavior.** The latest listed release was **v0.75.2, October 22**, bundling several intervening versions: “What a personal Bot saves to memory in one chat is remembered in all your chats with it, and only you can change it.” Earlier voice calls and recent chat can inform voice calls. This supersedes the repository’s October 7 latest-version reference. [Changelog](https://x.ai/changelog/bot#v0.75.2). The separate API release notes announce Grok Bot in August and an API compaction capability in May; neither establishes that Grok Bot implements that compaction API. [API release notes](https://docs.x.ai/developers/release-notes).
- **B/M — Shared project files are a different boundary.** Personal Bots share the account’s cloud computer, `/workspace`, browser sessions, command-line credentials, and account-wide connectors. Separate screens are explicitly “not separate security boundaries.” Files, browser state, and supported sign-ins are intended to survive normal updates/recovery; temporary directories and uncommitted application state are replaceable. [Computer and apps](https://docs.x.ai/grok-bot/computer-and-apps).
- **B — Team memory is selective, not shared transcripts.** A Team Bot has private chats and person-specific notes, plus team memory read by every teammate’s conversation. It saves a team fact “only when someone says the whole team should have it,” and announces the save. Users can ask what it saved and request correction/removal. Team files and skills are shared setup; routines remain personal. This is not Hutch-style owner approval for every shared fact: the documented trigger can come from a teammate. [Team Bots](https://docs.x.ai/grok-bot/team-bots#memory).
- **B — Freshness and copying.** Duplicating a personal Bot copies configuration but not conversation history, learned memory, or attachments. A teammate’s Team Bot chat starts without other teammates’ conversations, while retaining applicable team memory and private notes. Publishing a personal Bot as a Team Bot has copy/start-fresh and memory-selection controls. These are distinct operations, not a universal “new chat forgets everything” rule. [Bots](https://docs.x.ai/grok-bot/bots), [Team Bots](https://docs.x.ai/grok-bot/team-bots).
- **B — Handoffs.** Bots send asynchronous messages; recipients wake, handle requests, and reply later. Groups preserve visible handoffs and the docs recommend one owner per stage. Bot-to-group handoffs are text-only; sensitive approval/login requests are excluded from groups. [Collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration). October 22 notes fix routine results being lost when the user messages during handoff: execution and result delivery evidently require separate attention, but the implementation is undisclosed. [Changelog](https://x.ai/changelog/bot#v0.75.2).
- **B — Stopping and interruption.** Closing the app/laptop does not stop cloud work; hiding a Bot does not pause routines. A direct “Stop now” ends work without undoing completed actions. September 17 notes say Stop propagates to handed-off Bots/Cloud Agents; October 14 extends this to background subagents, preventing their results from waking the Bot and expiring pending approvals. These are release claims, not universal cancellation guarantees. [Overview](https://docs.x.ai/grok-bot/overview), [Bots](https://docs.x.ai/grok-bot/bots), [collaboration](https://docs.x.ai/grok-bot/chat-and-collaboration), [changelog](https://x.ai/changelog/bot#v0.71.2).
- **B — Failure/recovery.** October 14 says a working Bot reconnects after its computer updates and continues. Troubleshooting distinguishes waiting for questions/approvals/logins from failure. Recover/Update preserve durable files and logins; Reset restores a snapshot and can lose recent unsynced work. An unreachable computer does not necessarily mean saved conversations are lost. [Changelog](https://x.ai/changelog/bot#v0.71.2), [troubleshooting](https://docs.x.ai/grok-bot/troubleshooting).
- **B — Correction, forgetting, retention.** The Bot guide directs users to correct stale assumptions and reopen authoritative sources. September 25 notes claim save/forget reliability fixes. October 22 says deletion permanently erases conversations, memory, routines, and attachments; the standing guide still says backend retention follows Cursor terms and shared-computer files/sign-ins can remain. Do not collapse these into a verified total-erasure guarantee. [Bots](https://docs.x.ai/grok-bot/bots), [changelog](https://x.ai/changelog/bot), [privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy).

### Inferences

The useful pattern is durable, scoped continuity with visible ownership and current-source checks. Neither a large transcript nor a persistent computer alone establishes reliable completion. Grok’s release history particularly motivates separate acceptance tests for saving messages, performing work, delivering results, and honoring Stop.

### Gaps

The inspected sources do not disclose memory schemas, summarization triggers, retrieval ranking, transactional handoff guarantees, deduplication, backup cadence, or exact crash-resumption semantics. “Continues after update” does not prove process-level replay safety. Exact retention and erasure across snapshots/backups remain unverified.

## 2. Is “Meta Muse” the exact product, and what is actually documented?

### Takeaway

**Yes.** Meta’s official September 8 announcement names its personal agent Muse and links the Muse design/security sites. This is not an unrelated Muse app or merely a model name. Official sources document persistent chats, editable file-based memories, durable application storage, and background work, but not a user-managed fleet with Grok-style per-Bot/team-memory rules. [Meta announcement](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/).

### Cited Findings

- **B — Conversations and context.** Main chat and deletable side chats coexist; Muse “stays aware across the main chat and side chats.” Users can send follow-ups without waiting for the previous response. Finished artifacts are saved in the Library workspace and shared in conversation. A side chat organizes topics; it is not documented as an isolation boundary. [Getting started](https://www.meta.com/help/superintelligence/1331373868832401/).
- **B/M — Personal facts and files.** Customizations persist between conversations. Memory draws on direct statements, observed preferences/patterns, connected-service context, and a “file-based memory system.” Users can inspect/edit memory and import previous assistants’ conversation exports. [Customization](https://www.meta.com/help/superintelligence/995796179982326/). Data controls separately enumerate interactions, connector information, goals, artifacts, system files, scheduled tasks, and Memory/Soul/Identity files. [Manage data](https://www.meta.com/help/superintelligence/2225571704857152/).
- **M — Storage architecture actually disclosed.** Meta’s launch engineering account calls the dedicated cloud VM the “system of record.” The agent/workspace operates in an isolated runtime cell, while “All durable application state is stored in a postgres database separate from the runtime cell and from the credential store.” VM data is “backed up continuously.” Inference/telemetry can leave the VM. This supports distinct application, workspace, and credential state—not a claim that memory is only Markdown. [Safety architecture](https://security.muse.ai/).
- **B/M — Background tasks and handoffs.** The design account describes scheduled/event-driven work and surfacing results only when meaningfully new or requiring input. The engineering account describes concurrent subagents/crons and a specialized browser subagent. It does not specify a public handoff message schema, exactly-once delivery, or cancellation/restart protocol. [Design](https://introducing.muse.ai/), [architecture](https://security.muse.ai/).
- **B — Business context is not verified team memory.** Muse for Small Business is described as “new skills and connectors inside Muse,” including business records and collaboration services. The inspected announcement does not establish shared transcripts, per-employee private notes, independently persistent named Bots, or shared-fact approval semantics. [September 29 announcement, updated October 8](https://about.fb.com/news/2026/09/introducing-muse-small-business/).
- **B — Corrections and forgetting have explicit limits.** Users can edit/delete Memory.md and request personality reversions. Crucially, deleting a message/side chat/file can leave learned information remembered. The forget skill searches memories/supporting files and removes information “to the best of its ability.” Reset permanently deletes information, chat history, files, and active tasks and cannot be undone. Thus delete-chat, forget-topic, and reset are different contracts. [Manage data](https://www.meta.com/help/superintelligence/2225571704857152/), [customization](https://www.meta.com/help/superintelligence/995796179982326/).
- **B — Stopping is not rollback.** Users can ask to stop/undo some actions; sent email cannot be reversed. Permissions and activity logs are inspectable. Closing the app still permits background work. [Guidance and approval](https://www.meta.com/help/superintelligence/1385290430137537/), [announcement](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/).
- **M — Authority is separate from memory.** Meta describes Sentinel as host-side permission authority; approvals are “strict capabilities, not conversational suggestions,” bound to action scope. Its launch account explicitly says ordinary Secure VM does not prevent Meta operational access; Confidential VM is prospective in that account. Training use is enabled initially, with opt-out controls. These are vendor claims/settings, not independent security verification. [Architecture](https://security.muse.ai/), [data controls](https://www.meta.com/help/superintelligence/2225571704857152/).
- **R — Reported internals, not verified architecture.** Peter James’s September 22 filesystem-export account describes Markdown daily/curated memory, hourly evidence reconciliation, message/claim IDs, PostgreSQL indexes/embeddings, superseding claims, nightly “dreams,” and retraction/index rebuilds. The author says the archive and session logs are not published; this research read the article, not those files. Its stronger forgetting description does not override Meta’s best-effort contract. The author’s site markets an agent product; treat this as a bounded external technical report, not neutral certification or prevalence evidence. [Original report](https://mouse.dev/blog/muse-runtime-export/).

### Inferences

Muse provides stronger primary-source evidence for inspectable memory files plus separate durable application storage than the repository’s earlier unverified Muse comparisons suggested. Its cross-chat awareness is useful within one authorized personal scope, but cannot justify automatic cross-Bot sharing in Hutch.

### Gaps

No hands-on behavior was observed. Official sources reviewed do not establish summary construction, context budgets, evidence-reconciliation schedules, per-subagent memory isolation, recovery point/time objectives, or whether pending actions resume after reboot. Continuous backup is not an exactly-once execution guarantee. The engineering article explicitly describes launch architecture, not a separately audited October deployment.

The search integration returned HTTP 429; Google yielded no usable results, and `ai.meta.com/muse/` returned no extractable content. Bing located the official announcement/help pages, which were read directly. Search snippets were not used as product evidence. The earlier repository privacy allegations were not re-established by this review.

## 3. What should Hutch implement or deliberately avoid?

### Takeaway

**Recommendation: Hutch should own durable local conversation and task-continuity records, plus separately scoped curated memory.** First inventory and reuse existing storage; this research does not establish that Hutch lacks it. Add shared facts only through the owner-approved sharing model, rather than a universally readable chat pool.

### Cited Findings

The relevant precedents are selective team facts with private chats ([Grok Team Bots](https://docs.x.ai/grok-bot/team-bots)), continuity/result-delivery fixes ([Grok changelog](https://x.ai/changelog/bot)), inspectable memory plus durable application state ([Muse architecture](https://security.muse.ai/)), and explicit differences between deletion and forgetting ([Muse data controls](https://www.meta.com/help/superintelligence/2225571704857152/)). None demonstrates that more injected history improves Hutch’s reliability.

### Inferences

Recommended behavioral contract, subject to the separate Hutch code audit:

1. **Separate records by purpose.** Preserve local, scoped chat/event history for provenance; task checkpoints for objectives, ownership, completed/pending steps, blockers and artifact references; curated facts for durable preferences; and an execution/result-delivery ledger. A summary is a derived aid, not approval or proof an effect happened.
2. **Resume with bounded context.** Supply current instructions, relevant approved facts, recent turns, a versioned checkpoint, and source references. Reopen changing sources. Offer a fresh task/session without silently erasing durable facts or importing unrelated conversations. Measure outcomes, latency, and token use before adding broader retrieval.
3. **Make cross-Bot transfer explicit.** Share a bounded brief, authorized facts/artifacts, source IDs, recipient scope, and ownership. Record the owner’s promotion/revocation decision. Do not copy Grok’s shared credentials/computer or treat Muse side chats as separate Bot security domains.
4. **Persist interruption semantics.** Distinguish waiting, failed, canceled, completed, and delivery-pending. Retry delivery without repeating completed external actions. Record Stop durably across descendants; late replies must not restart canceled work. After crashes, reconcile uncertain actions before retrying. A local sleeping/stopped host cannot promise cloud-style continued execution.
5. **Make memory correctable.** Retain provenance, timestamps and supersession/retraction links. Define how deletion/forgetting affects derived summaries, indexes, queued context and backups, including limits. Prevent forgotten facts from being silently reconstructed from retained sources. Scope this separately from immutable execution receipts and necessary audit metadata.
6. **Preserve authority and locality.** Memory text must never grant permissions. Do not adopt cloud persistence, default telemetry/training, unreviewed proactive access, or auto-promotion of personal facts as incidental “memory improvements.” PostgreSQL, embeddings and nightly reflection are not requirements established by this evidence.

### Gaps

Prioritization requires current Hutch code and failure evidence. Proposed acceptance cases: restart after acceptance; crash after an external effect but before result delivery; fresh-session continuation; stale-fact correction; forget then reindex; unauthorized cross-Bot retrieval; and Stop followed by a late child result. These checks were not run.

### Copy-ready prompt for a new implementation session

> Work in `/home/kevina/CodingProjects/hutch`. Read repository instructions, current architectural authorities, and `research_notes/Reliable memory across Hutch agents/product-references.md`. First trace existing conversation persistence, context assembly, memories, task checkpoints, handoffs, cancellation, recovery, and result delivery with code/test references. Identify the actual missing continuity behavior before proposing another store.
>
> Implement the smallest justified backend slice using existing local storage and interfaces. Keep per-Bot isolation, explicit owner-approved fact/artifact sharing, and action-bound approvals. Separate transcript, derived summary, curated fact, execution state, and delivery state. Do not replay external effects merely because a reply was lost; do not let late child results restart canceled work. Bound resumed context and preserve provenance/correction/forgetting semantics.
>
> Define acceptance evidence first, then run focused tests and repository-required checks. Report remaining gaps and unrun checks. Do not redesign UI, add dependencies, broaden permissions, upload private code, or spawn agents without authorization. Product references are behavioral inspiration, not proof of internal architecture or guaranteed performance.

### Final source/claim table

All accessed **2026-10-23**; extracts are short vendor/report quotations, not observed product behavior.

| Source | Precise evidence extract | Supports / limitation |
|---|---|---|
| [Grok Bot guide](https://docs.x.ai/grok-bot/bots) | “important facts, and summaries” | Learned memory distinct from transcript; algorithm unknown. |
| [Grok v0.75.2, Oct 22](https://x.ai/changelog/bot#v0.75.2) | “remembered in all your chats with it” | Personal-Bot continuity; not cross-Bot access. |
| [Grok Team Bots](https://docs.x.ai/grok-bot/team-bots#memory) | “only when someone says the whole team should have it” | Selective shared facts; not owner-only promotion. |
| [Grok recovery](https://docs.x.ai/grok-bot/troubleshooting) | “can lose recent or unsynced work” | Snapshot recovery limit; no zero-loss guarantee. |
| [Muse getting started](https://www.meta.com/help/superintelligence/1331373868832401/) | “stays aware across the main chat and side chats” | Continuity within one Muse; no isolation promise. |
| [Muse architecture, Sep 8](https://security.muse.ai/) | “All durable application state is stored in a postgres database” | Official mechanism; not inspected service code. |
| [Muse data controls](https://www.meta.com/help/superintelligence/2225571704857152/) | “to the best of its ability” | Forgetting is best effort; deletion can retain learned facts. |
| [James report, Sep 22](https://mouse.dev/blog/muse-runtime-export/) | “I’m not publishing the archive, keys, or session logs” | Reported internals remain externally unverified. |
