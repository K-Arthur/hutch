# Hutch memory implementation: new-session prompt

Implement and verify the backend continuity improvements below in `/home/kevina/CodingProjects/hutch`. Complete the agreed A1–A5 acceptance, one active vertical slice at a time; do not stop after producing another plan. Start with **A1**, using existing SQLite authority, admission-context and receipt paths. New persistent migrations are justified only where existing state cannot represent the contract. Do not build a second memory database or global transcript.

## Establish current authority

First run `git status --short --branch` and `git rev-parse HEAD`. The static audit baseline is `main@f29b299b58b865053d48f4baa71601e191edb5cd`, inspected 2026-10-23; tests were not run. Revalidate affected code drift rather than treating this as today’s checkout. Preserve unrelated dirty/untracked work, research outputs and stale worktrees. Old commit, merge, push and cleanup instructions in historical records are not authorization.

Read `AGENTS.md`, `PRODUCT.md`, `docs/realignment/ledger.md`, relevant current entries in `docs/realignment/tests.md`, and these authorities:

- `docs/adr/0003-durable-state-and-honest-outcomes.md`
- `docs/adr/0007-external-runtimes.md`
- `docs/adr/0008-memory-and-bounded-collaboration.md`
- `docs/adr/0011-shared-usage-reservations.md`
- `docs/adr/0013-recoverable-transcript-files.md`
- `docs/adr/0017-governed-mcp-integration-plane-and-context-scaffolding.md`
- `docs/adr/0019-cost-guardrails-context-continuity-and-routing.md`

Read [the synthesis](Reliable%20memory%20across%20Hutch%20agents.md), at `/home/kevina/CodingProjects/hutch/reports/Reliable memory across Hutch agents.md`, and all four evidence files under `/home/kevina/CodingProjects/hutch/research_notes/Reliable memory across Hutch agents/`: [current code audit](../research_notes/Reliable%20memory%20across%20Hutch%20agents/hutch-current-state.md), [product references](../research_notes/Reliable%20memory%20across%20Hutch%20agents/product-references.md), [assistant applications](../research_notes/Reliable%20memory%20across%20Hutch%20agents/assistant-applications.md), and [frameworks](../research_notes/Reliable%20memory%20across%20Hutch%20agents/memory-frameworks.md). Research is complete: revalidate drift/relevant APIs, not every comparison. Historical ADR descriptions are not verified current implementation.

Use `feature-dev` and its `references/long-tasks.md`. Checkpoint meaningful milestones in the existing realignment authority: constraints/decisions and authoritative pointers separately from progress, acceptance evidence, blockers and next action. Reread checkpoints and revalidate affected evidence after resuming.

## Starting code and test map

Under `src/hutch/`, `store.py` owns admission, context snapshots, history/FTS, event projection, facts/shares and continuations; `models.py` owns Run contracts; `fact_memory.py` and `tools/memory.py` own reviewed references; `tools/__init__.py` owns registration. Under `src/hutch/runtime/`, inspect `builtin.py`, `opencode.py`, `opencode_server.py`, `opencode_protocol.py`, `fitloop.py` and `steps.py`; `src/hutch/engine.py` owns execution/recovery. Reuse existing server authorization paths if a bridge needs transport.

Relevant tests: `tests/test_conversations.py`, `test_fact_memory.py`, `test_runtime_builtin.py`, `test_runtime_opencode.py`, `test_runtime_compaction.py`, `test_store_events.py`, `test_transcript_mirror.py`, `test_delegated_wait.py`, `test_delegation.py`, and `test_workflow_effect_receipts.py` (all under `tests/`).

The audit found OpenCode ignores `run.conversation_context` and Hutch Tool objects, bootstraps from the first 60 messages, removes input by string matching, and reuses native sessions without a synchronization cursor after Builtin turns. Message projection drops incomplete metadata. Within-run summaries do not supply ordinary next-run task continuity. These are static findings requiring regression evidence, not reproduced live bugs. Preserve existing parked delegation, workflow continuations and narrow no-effect fresh attempts.

## Non-negotiable boundaries

Preserve immutable proposals/revisions, exact-content review, explicit bot-wide promotion and cross-bot grants. Human proposals also require review; newer pending revisions retain existing suppression of older approved values. No raw transcript auto-promotion, global writable memory, pooled cross-bot transcripts, automatic workspace sharing or inferred approval. Facts remain untrusted reference data, never system instructions. Summaries cannot grant permissions or prove effects. Store observable commitments/decisions/results, never private chain-of-thought.

Carry IDs, scope, exact revision/hash, source range/high-watermark and incomplete/truncated status where applicable. Distinguish frozen task snapshots from reusable revocable grants. Recheck cancellation, lease/fence, applicable memory-off settings and grants on each retrieval/call. Preserve memory-off semantics, tool-free modes and child exclusions. When revocation requires excluding cached material from future native requests, invalidate/rebind/rebuild; do not rewrite frozen evidence or promise erasure of already-disclosed text/provider contexts.

OpenCode native tools run with user OS authority. A run-bound API does not sandbox native filesystem access. Do not relabel existing approval/tool-receipt/accounting gaps solved by memory changes or claim universally gated, budgeted or exactly-once effects. No new frameworks/services, dependencies, paid inference, provider access, broadened capabilities, agents, commits, merges, pushes or cleanup without explicit authorization. Defer Graphiti and embeddings. No UI redesign is requested.

## Implement these ordered slices

**A1 — Shared bounded context and partial-state fidelity.** Extend admission/projection contracts; both adapters consume the same authorized selection with provenance and status. Select newest canonical history, deduplicate by message identity, preserve explicit references and reconstruct deterministically after restart. Keep canonical originals authoritative.

**A2 — Durable bindings and reconciliation.** Persist bot/conversation/route/workspace/policy affinity, synchronization cursor and send identity/state in existing authority. Reconcile or rebuild missing/stale native sessions. Distinguish acceptance from dispatch/acknowledgement. Retain uncertain submission/usage state when acceptance cannot be established; never blindly retry uncertain non-idempotent effects.

**A3 — Supported scoped memory/history access.** Load the OpenCode skill and relevant current V2 documentation before choosing a supported bridge. Use existing Hutch operations through narrowly authenticated server-side bot/conversation/run/fence bindings, not model-selected authority, direct SQLite access or broad admin endpoints. Builtin and OpenCode must genuinely exercise the supported path. If blocked, mark A3 and overall parity incomplete with the exact missing API/contract; no fake stubs or invented support.

**A4 — Ordinary-chat durable task state and bounded history.** Persist goals, constraints, decisions, pending questions and artifact references with canonical source anchors, revision compare-and-swap and explicit supersession. Separate commitments from receipt-backed results. Reuse existing FTS5/history; distinguish transcript evidence from reviewed facts. Preserve originals on failed/nonshrinking summaries and failed checkpoint writes; unknown/small windows must retain explicit limitations.

**A5 — Recovery, delivery, sharing evidence and docs.** Extend existing receipts/continuations rather than arbitrary model-loop replay. Prove result delivery separately from execution, preserve migrations and old user state, and document support/retention limits. Finish all acceptance or name exact remaining blockers.

## Immutable acceptance IDs

Keep these IDs stable in tests/checkpoints; subcases may be added without weakening them.

| ID | Required evidence |
|---|---|
| A1 | >60-message history/latest correction; repeated user strings delivered once per distinct ID; selected fact/reply/artifact/specialist references; incomplete/empty/truncated output preserved; unrelated scope excluded. |
| A2 | OpenCode → Builtin → OpenCode; route A → B → A; missing/corrupt binding and deleted native session; restart before acceptance and after dispatch/before ack; no blind uncertain-effect retransmission. |
| A3 | Memory-off and stale tools; no-grant Bot B probes; source update/revoke; cancelled/stale fences and leases; concurrent review/edit; hostile reference values; exact revision/provenance. |
| A4 | Obligations/corrections older than 12 turns; repeated compaction; smaller/unknown windows; failed/nonshrinking summaries and checkpoint writes preserve originals. |
| A5 | Restart after result commit/before parent consumption produces one logical delivery; old child late reply never resumes cancelled parent; child memory exclusion/selected specialist snapshots; stale worker rejection; existing history/receipts/user bots preserved. |

## Verification and completion

Use existing environments, isolated synthetic data and `/tmp/opencode` for temporary data/TMPDIR. Check available storage and account for database/index/artifact growth; never modify real user state or delete unrelated files to free space. Do not install dependencies implicitly.

Run focused tests first, initially `uv run pytest -q tests/test_conversations.py tests/test_runtime_opencode.py`; add affected files from the map per slice. Then run `uv run pytest --ignore=tests/e2e` and any applicable current repository-required checks. Report exact commands/results and unrun checks. Browser checks are required if browser behavior changes; impeccable’s mandatory research/route approval applies only if later scope genuinely includes UI design decisions.

Separate deterministic adapter/process-failure evidence from live-model response-quality evaluation. Authorized live credentials were unavailable to the research: report that gap, do not purchase/access inference. Compare prompt tokens, p50/p95 selection latency, labeled retrieval correctness/provenance, stale/leak results and storage against the same baseline/corpus/routes/budgets/hardware; invent no numeric target. Storage cannot eliminate hallucinations, process-crash tests do not certify power loss, and an outbox does not guarantee exactly-once network effects.

Self-review implementation and final diff against every ID, authority boundary, compatibility requirement and preserved work. Record completed/blocked acceptance, checks, limitations and next action in existing authority. Deliver working implementation and evidence, not another research plan.
