# Memory frameworks and durable execution for Hutch

Research date: **2026-10-23**. Research only; no frameworks installed, benchmarks run, or product changes made. Hutch working-tree sources were inspected with HEAD `f29b299b58b865053d48f4baa71601e191edb5cd`. Evidence below distinguishes documented contracts, pinned implementation details, and proposed Hutch adaptations; documentation is not evidence of benchmark gains.

## 1. What do the frameworks actually persist, expose, and coordinate?

### Takeaway

Borrow the separation of thread state from cross-thread knowledge, explicit memory ownership, and replayable task results. **Letta has materially changed:** its repository now directs active development to `letta-code`; the V1 server and memory-block APIs are historical, not the recommended foundation for new work. [Repository migration notice](https://github.com/letta-ai/letta/blob/8816d3a8516893bfdc0fa14bfb1235226012e295/README.md)

### Cited Findings

**Version/license evidence.** These are the exact inspected snapshots, not a claim that floating documentation describes every tagged release. Package licenses do not establish licenses for hosted services or transitive dependencies.

| Code inspected | Exact version/snapshot | Primary license evidence |
|---|---|---|
| Retired Letta V1 | [0.16.8, commit `1131535716e8`](https://github.com/letta-ai/letta/blob/1131535716e8a31c9a437f8695e25ac98f203a24/pyproject.toml); [release published 2026-05-14](https://github.com/letta-ai/letta/releases/tag/0.16.8) | [Apache-2.0](https://github.com/letta-ai/letta/blob/1131535716e8a31c9a437f8695e25ac98f203a24/LICENSE) |
| Current Letta harness | [0.34.23, `6c8b08fedfb6`](https://github.com/letta-ai/letta-code/blob/6c8b08fedfb6f3fb437163ede8320a387151693f/package.json) | [Apache-2.0](https://github.com/letta-ai/letta-code/blob/6c8b08fedfb6f3fb437163ede8320a387151693f/LICENSE) |
| LangGraph | [1.2.16, `9d68e5b3eb1a`](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/langgraph/pyproject.toml); [SQLite checkpointer 3.1.2](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint-sqlite/pyproject.toml) | [Core MIT](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/LICENSE); [SQLite MIT](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint-sqlite/LICENSE) |
| Graphiti | [0.31.2, `345e73161a61`](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/pyproject.toml) | [Apache-2.0 at this snapshot](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/LICENSE), not an assumed historical MIT license |

**Mechanism comparison**

| Mechanism | Concrete operation and persistence | Scope, conflicts, and limitations |
|---|---|---|
| Letta agent messages/current conversations | `createSession(agentId)` creates a conversation; `resumeSession(conversationId)` reopens one; `client.conversations.listMessages()` retrieves retained history. Compaction summarizes older messages while history remains searchable. | Conversations have separate message contexts but share their agent's long-term memory. Disconnected SDK streams do not replay missed events; fetch history/snapshots. A failed connection after `send()` is not permission to resend blindly. [Conversations](https://docs.letta.com/concepts/conversations/index.md), [session guarantees](https://docs.letta.com/agent-sdk/sessions/index.md) |
| Letta V1 blocks/shared blocks | `client.blocks.create(label, value, limit)`; attach the same ID through `block_ids` or `agents.blocks.attach`. Stored block contents are rendered into the prompt; `blocks.update(value=...)` replaces the whole value. | Always-visible memory consumes context. `read_only` applies to the whole block, not individual attached agents. This is shared mutable content, not Hutch-style reviewed snapshots. [Blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks/index.md), [sharing](https://docs.letta.com/v1-sdk/memory/shared-memory/index.md) |
| Letta V1 archives | Agent tools `archival_memory_insert/search`; SDK `client.agents.passages.insert/search` and management endpoints. An SQLAlchemy archive contains embedding configuration/vector-provider metadata and agent associations. | Retrieved on demand, not pinned context. Archives can be shared between agents; agents normally insert/search while developers can update/delete. Semantic retrieval does not establish factual correctness or review. [API](https://docs.letta.com/v1-sdk/memory/archival-memory/index.md), [archive ORM](https://github.com/letta-ai/letta/blob/1131535716e8a31c9a437f8695e25ac98f203a24/letta/orm/archive.py) |
| Current Letta MemFS | Agent-owned Git repository; root memory files enter every-turn context, nested indexed directories are read on demand. Local state lives under `~/.letta/lc-local-backend`. | Local agents need no Letta account. Shared repositories currently require cloud-hosted agents and explicit commit/push/pull synchronization. Git history supports inspection, not semantic truth or effect deduplication. No vector index by default; local transcript search is full-text. [MemFS](https://docs.letta.com/concepts/memfs/index.md), [self-hosting](https://docs.letta.com/self-hosting/index.md), [sharing](https://docs.letta.com/concepts/shared-memory/index.md) |
| LangGraph checkpointer | `builder.compile(checkpointer=...)`; invoke with `configurable.thread_id`. Saves graph state at super-step boundaries plus completed task writes. SQLite stores separate `checkpoints` and `writes` tables. | Scoped by thread/checkpoint namespace. `InMemorySaver` loses state on process restart; persistent backends are separate choices. Stored task results can prevent repeating completed work, not guarantee remote exactly-once effects. [Contract](https://docs.langchain.com/oss/python/langgraph/checkpointers), [SQLite implementation](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py) |
| LangGraph cross-thread Store | `store.put((user_id, "memories"), key, value)`; `get/search/delete`; optional embedding index. Store is supplied separately from the checkpointer. | Namespace tuples organize JSON records; prefix searches can include descendant namespaces. They are not themselves access-control grants. `InMemoryStore` is not restart-persistent. [Stores](https://docs.langchain.com/oss/python/langgraph/stores), [API source](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint/langgraph/store/base/__init__.py) |
| Graphiti, optional temporal graph | `add_episode(name, episode_body, source_description, reference_time, group_id, ...)`; `search(query, group_ids=...)`. Derived relationship edges link source episode IDs and temporal fields. | Adds relationship traversal and temporal validity beyond flat facts. Requires a graph backend, LLM, and embedder; callers supply authorization. The reference servers do not authenticate callers. [API source](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/graphiti.py), [deployment boundaries](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/README.md) |

**Update conflicts matter.** Letta's legacy guide recommends append-style `memory_insert`, describes targeted replacement as conditional on the old string, and warns full `memory_rethink` rewrites are last-writer-wins. Its ORM additionally has SQLAlchemy optimistic version checks; the manager updates records then rebuilds attached agents' prompts. These mechanisms do not establish semantic merging of independently drafted replacements. Current MemFS exposes dirty/conflict/push-failed states, with Git fast-forward/rebase paths. [Legacy guidance](https://docs.letta.com/v1-sdk/memory/shared-memory/index.md), [versioned ORM](https://github.com/letta-ai/letta/blob/1131535716e8a31c9a437f8695e25ac98f203a24/letta/orm/block.py), [manager](https://github.com/letta-ai/letta/blob/1131535716e8a31c9a437f8695e25ac98f203a24/letta/services/block_manager.py), [current Git implementation](https://github.com/letta-ai/letta-code/blob/6c8b08fedfb6f3fb437163ede8320a387151693f/src/agent/memory-git.ts)

LangGraph's ordinary `put` has no expected-revision argument. Postgres implements `ON CONFLICT (prefix,key) DO UPDATE SET value=EXCLUDED.value`: application-level read/modify/write needs its own conflict policy. Graph-state reducers do not supply that policy for Store records. [Store API](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint/langgraph/store/base/__init__.py), [Postgres SQL](https://github.com/langchain-ai/langgraph/blob/9d68e5b3eb1a63027b05e9f0152149ea0284dcdb/libs/checkpoint-postgres/langgraph/store/postgres/base.py)

Graphiti distinguishes `valid_at`/`invalid_at` from recording/invalidation metadata such as `expired_at`, retaining episode provenance. Its automatic extraction and invalidation are model-mediated interpretations, not reviewed truth. This is useful for “who owned this project at that time?”, less compelling for ordinary preferences. [Edge schema](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/edges.py), [extraction pipeline](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/graphiti.py)

### Inferences

Hutch should copy the **ownership and indexing distinctions**, not adopt globally writable profile blocks. Existing reviewed fact revisions are a better fit than either unrestricted Store upserts or automatic graph invalidation. A temporal validity field can be added to SQLite without adopting a graph service. [Hutch fact model](../../src/hutch/fact_memory.py)

### Gaps

No framework was crash-tested here. Current docs are unversioned; legacy guides explicitly identify themselves as legacy. Cross-process graph-ingestion conflict/retry behavior and complete Letta tool-effect recovery were not established by this inspection. No source establishes universal recall or latency gains for Hutch.

## 2. Which memory layers improve relevance, and which prevent duplicate actions?

### Takeaway

Continuity is useful context selection plus preserved evidence. Reliable execution additionally needs transactional ownership, immutable intent, stable effect identity, receipts, and explicit uncertainty; summaries cannot substitute for these. [Hutch ADR-0003](../../docs/adr/0003-durable-state-and-honest-outcomes.md), [LangGraph idempotency](https://docs.langchain.com/oss/python/langgraph/functional-api#idempotency)

### Cited Findings

| Layer | Authority and practical contribution |
|---|---|
| Conversation transcript | Evidence of what was said, not whether an assertion or claimed action was true. Hutch retains canonical messages separately from reference facts. |
| Model context window | A bounded, disposable projection of selected messages, tools, references, and instructions. Persisted history can be much larger. |
| Summary | Lossy context compression. Keep source boundaries, exact task anchors, and provenance; do not promote summary claims into reviewed facts. |
| Execution checkpoint | Structured continuation state and completed outputs; can support restart at defined boundaries. A prose “next steps” summary is not one. |
| Reviewed semantic fact | Scoped, versioned reference data; review is neither verified truth nor permission. Primarily improves relevance and constraint recall. |
| Task/effect state | Authority for pending work, ownership, approvals, external-effect uncertainty, and completion receipts. Primarily improves operational reliability. |

These distinctions are supported by [Hutch ADR-0008](../../docs/adr/0008-memory-and-bounded-collaboration.md), [compaction ADR-0019](../../docs/adr/0019-cost-guardrails-context-continuity-and-routing.md), [Letta context/history separation](https://docs.letta.com/concepts/conversations/index.md), and [LangGraph checkpoints](https://docs.langchain.com/oss/python/langgraph/checkpointers).

LangGraph's `durability="sync"` writes a checkpoint before the next step; `async` overlaps persistence with subsequent execution and can lose recent progress on a crash; `exit` does not protect intermediate progress from process death. Successful sibling-node writes can survive another node's failure. These guarantees require an appropriate persistent saver. [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)

With the Functional API, replay begins at the entrypoint and restores persisted `@task` results. A task that started but did not finish may execute again. Plain graph nodes restart their function, and time-travel replay re-executes subsequent API calls. Put separate effects/nondeterminism in separate tasks, but still make effects idempotent; task-result checkpointing leaves a crash gap between remote success and local recording. [Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api#determinism), [replay](https://docs.langchain.com/oss/python/langgraph/checkpointers#replay)

Hutch already brackets effects through `ctx.begin_effect()` and `finish_action()`. Workflow identities include revision/site/instance/slot; completed receipts reuse stored results, while unresolved effects block dispatch. This is more specific than merely hashing arguments. Older ADR wording about limited continuation should not erase these newer workflow capabilities in source. [Receipt boundary](../../src/hutch/runtime/steps.py#L160)

### Inferences

**What actually prevents replay after a crash:** preserve Hutch's existing receipt guard and extend only deliberately:

1. Persist logical operation identity, reviewed arguments, owner fence, and intent **before dispatch**; refuse dispatch if that commit fails.
2. Atomically claim the operation under current ownership. Reuse a completed receipt; never treat a matching prose summary as a receipt.
3. Where the destination supports it, send the same persisted idempotency key on retry and retain its remote object ID. The destination must actually honor that contract; a locally invented key alone changes nothing remotely.
4. If remote success occurred but the local receipt is missing, reconcile by authoritative destination lookup or retain `outcome_unknown`. Without remote deduplication/verification, block automatic replay.
5. For effects entirely inside the same SQLite database, consider one transaction for mutation plus receipt. For network effects, an outbox provides durable delivery attempts, not exactly-once delivery by itself.

This is an implementation recommendation derived from [Hutch's intent/uncertainty contract](../../docs/adr/0003-durable-state-and-honest-outcomes.md) and [LangGraph's explicit idempotency requirement](https://docs.langchain.com/oss/python/langgraph/functional-api#idempotency). Tradeoff: honest uncertainty sometimes needs human reconciliation instead of seamless automatic recovery.

### Gaps

Destination-specific idempotency contracts need separate adapter research. Hutch documents process-crash evidence, not power-loss certification. A successful executor status is not independently verified task completion. [ADR-0003](../../docs/adr/0003-durable-state-and-honest-outcomes.md)

## 3. What should Hutch adopt, measure, and hand off?

### Takeaway

Keep SQLite and reviewed facts authoritative. Prioritize measurable retrieval/provenance improvements, then narrowly scoped durable continuation; add embeddings or a graph only for demonstrated residual failures.

### Cited Findings

Hutch already has immutable fact content/revisions, hash-bound review, scope filtering, FTS5, and explicitly granted cross-bot snapshots. Runtime recall returns at most 20 records within 6,000 serialized reference characters. Replacing a source revision, revoking its share, or disabling either bot's memory excludes that shared snapshot from new recall; it does not retract previously sent context. [Fact queries](../../src/hutch/fact_memory.py), [share/recall operations](../../src/hutch/store.py#L9137), [runtime tool](../../src/hutch/tools/memory.py), [retention limits](../../docs/adr/0008-memory-and-bounded-collaboration.md)

Two concrete improvement candidates emerge from code: fact search ANDs at most ten literal terms; `recall_fact_page()` merges and re-sorts results by recency after the own-fact query used FTS rank. Also, runtime serialization omits the fact ID/content hash that storage already exposes. These are evaluation targets, not demonstrated defects. A new proposed revision suppresses the previous revision through `CURRENT`, even before approval; regression expectations must preserve or explicitly reconsider that behavior. [Queries/current predicate](../../src/hutch/fact_memory.py#L117), [merge](../../src/hutch/store.py#L9137), [serialization](../../src/hutch/tools/memory.py#L60)

### Inferences

**Prioritized implementation patterns**

1. **P0 — Establish evidence and lineage.** Add synthetic recall/provenance fixtures and crash schedules around existing receipts. Carry stable fact IDs, revisions, and source references through bounded recall output; keep review and sharing authority unchanged. Start with the existing [fact](../../tests/test_fact_memory.py) and [effect-receipt tests](../../tests/test_workflow_effect_receipts.py).
2. **P1 — Improve FTS5 before infrastructure.** Compare current ranking with preserved relevance ordering, controlled keyword selection, and bounded literal fallback queries. Filter scope/current status before limits. Separate “what was said?” transcript retrieval from “what is currently reviewed?” fact retrieval. Never turn archive search into implicit cross-bot sharing. [Existing layer contract](../../docs/adr/0008-memory-and-bounded-collaboration.md)
3. **P2 — Bounded continuity manifest.** Extend existing compaction/task state with source-message range/high-watermark, exact anchors, unresolved questions, artifact references, reviewed-fact revision references, and receipt IDs. Keep derived summary text untrusted; revalidate mutable references before use. Store under a revision check in the existing transaction/event path rather than adding an independent memory database. [Existing compaction provenance](../../docs/adr/0019-cost-guardrails-context-continuity-and-routing.md)
4. **P3 — One resumable execution boundary.** Borrow LangGraph's persisted-output pattern for one tool-free or already-receipted stage. Bind continuation to workflow revision, capability snapshot, owner fence, and logical effect identity; define rejection on incompatibility. Do not introduce arbitrary replay of conversational tool calls. [LangGraph task semantics](https://docs.langchain.com/oss/python/langgraph/functional-api), [Hutch receipt boundary](../../src/hutch/runtime/steps.py#L160)
5. **Defer dependencies.** Letta adds another agent harness/memory authority; LangGraph adds another execution/persistence model. Graphiti additionally requires graph operations and model-based extraction. Reconsider embeddings only after paraphrase misses remain material; reconsider graphs only after measured temporal/multi-hop failures justify them. Keep any future index rebuildable from authorized canonical data. [Letta architecture](https://docs.letta.com/self-hosting/index.md), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Graphiti requirements](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/README.md)

**Proposed behavioral evaluation — measurements, not claimed gains**

| Scenario | Measure and acceptance evidence |
|---|---|
| Preference recall after a long thread/restart; exact wording and paraphrases | Retrieval recall@k and precision@k against labeled authorized facts; answer correctness separately; provenance links resolving to the right revision/message. |
| Bot A private fact; Bot B probes it; then explicit share/revoke | Count unauthorized result records and answer disclosures. Require zero in the fixture, including stale caches and reconnects; distinguish already-submitted context from fresh retrieval. |
| “Moved to London” supersedes “Paris”; older timestamps and pending reviews | Stale-fact answer rate, correct abstentions, valid revision selected, and source attribution. Exercise current pending-revision suppression. |
| Two writers propose conflicting values; review races with replacement | Silent-overwrite count, detected conflicts, deterministic exact-retry results, retained decision provenance. |
| Kill before intent, after intent, after remote success, after receipt, before checkpoint | Destination-side effect count, attempted dispatches, receipt reuse, unresolved-state accuracy, and restart status. Require no automatic redispatch of unresolved non-idempotent effects. |
| Long task compacted, interrupted, resumed under changed capabilities | Exact-constraint retention, correct next stage, duplicate LLM/tool calls, rejection of stale authority, and preserved original history. |
| Scale authorized facts and conversations on representative local hardware | p50/p95 retrieval and end-to-end latency, prompt tokens, extraction/embedding calls, database/index size, cold-start time, restart recovery duration. Compare identical models/budgets/corpora. |

Use deterministic fake destinations for fault injection and a separately labeled live-model answer set. Report denominators, failures, and uncertainty; do not substitute framework marketing benchmarks for Hutch measurements. These scenarios derive from the [existing fact boundary](../../docs/adr/0008-memory-and-bounded-collaboration.md), [compaction contract](../../docs/adr/0019-cost-guardrails-context-continuity-and-routing.md), and [receipt contract](../../docs/adr/0003-durable-state-and-honest-outcomes.md).

**Coding-session handoff prompt**

> Read this note and current AGENTS.md, ADR-0003/0008/0019, `fact_memory.py`, `tools/memory.py`, `Store.recall_fact_page`, and `runtime/steps.py`. Revalidate the current checkout; some older ADR continuation descriptions lag workflow source. Implement one backend slice: provenance-preserving, scope-safe recall with meaningful behavioral evidence. Begin with failing scenarios for missing provenance, ranking displacement, stale revisions, and cross-bot leakage; preserve owner review, memory-off, current-revision filtering, and bounded output. Establish the FTS5 baseline before selecting a ranking change. Keep transcripts, summaries, facts, and effect receipts separate. Add no framework, embedding service, provider, or automatic sharing. Then propose a separate bounded continuation slice, accounting for existing workflow receipt replay and unknown outcomes. Run focused tests and `uv run pytest --ignore=tests/e2e` as repository instructions require; report exact failures/unrun checks. No UI work, commits, deployment, or account changes are authorized by this handoff.

### Gaps

No measured Hutch recall/latency baseline or independently verified “Grokbot/Muse-like” behavior was supplied. Treat that phrase as desired continuity, not an equivalence claim. Permanent deletion, cross-device synchronization, and provider-side retention need separate requirements; this note does not establish them. No tests were executed during this research.
