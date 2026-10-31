# 00 - BRIEF: external research for the personal-operations initiative

Dated: 2026-10-31 (America/Vancouver). Owner: researcher (delegated). Access date for every
external source in this directory: 2026-10-31.
Status: orientation. Evidence lives in RESEARCH.md, COMPETITIVE-ANALYSIS.md and
FAILURE-ANALYSIS.md. This is research input for the Lead's implementation, not a repo audit (the
auditor owns current-state evidence).

## Mission

Produce dated, evidence-graded external research on what a dependable, local-first platform must
do for personal operations, family/shared workflows, coding orchestration, shipped deliverables
and persistent automations. The initiative's implementation contract already exists in
`DECISIONS.md` and `ARCHITECTURE.md` (commitments, shared spaces, deterministic Today,
proposed-vs-confirmed capture, reported-vs-verified completion, IANA fail-closed). This research
tests those choices against what the market shipped and where it broke, rather than restating them.

## Scope

In: OpenClaw's showcase and six named X posts; competitors current in late October 2026
(OpenClaw, n8n, Zapier, Make, Lindy, Reclaim AI, Motion, Notion AI, Google Workspace AI,
Microsoft Copilot/Power Automate, Claude Code, OpenAI Codex, OpenCode, Pi, Hermes, multi-agent
coding orchestrators); documented failures from complaints, docs, issues and advisories.

Out: feature-parity checklists, marketing claims treated as fact, repo capability auditing, and any
prediction presented as a finding.

## Method

Prefer primary sources (docs, release notes, pricing pages, GitHub issues, CVE/GHSA, papers); use
user reports as complaint evidence, never as measured incidence; cross-check load-bearing claims
where possible and say when only one source type exists; record URL, publication/observed date,
access date (2026-10-31) and tag for every source; record inaccessible sources and the substitute
used. Nothing in this directory is invented.

## Evidence tags

| Tag | Meaning | Typical use |
|---|---|---|
| VERIFIED | Primary doc, issue, advisory, release note or official pricing page | Feature contracts, known issues, CVEs |
| OBSERVED | Page fetched this pass; claim is what it shows | Showcase claims, vendor positioning, third-party reviews |
| COMPLAINT | User report; not independently reproduced | X posts, HN/Reddit threads, incident blogs |
| HYPOTHESIS | Our inference or recommendation | Unexplained failure modes, Hutch implications |

## Source-quality caveats

- **Future-dated and volatile.** Today is 2026-10-30/31; several sources are October 2026 and
  competitor pricing moves. Re-verify prices before external use.
- **X/Twitter extraction.** All six required posts were readable from `x.com` status pages on
  2026-10-31 via the page's embedded tweet JSON. That is fragile; one payload (danpeguine) is
  truncated at source and is not completed. Likes/counts in posts are user-stated, not audited.
- **Vendor self-report.** Showcase likes, "verified X threads", stars and integration counts are
  marketing surfaces (OBSERVED at best); they evidence claims and patterns, not reliability.
- **Third-party bias.** AI Agent Index reviews are affiliate-linked; the OpenChamber study is by a
  competitor (it says so). Used for dated pricing/limitation facts and complaint shape only.
- **Reddit-derived aggregates.** OpenChamber's counts are a labelled corpus, not a census; the
  article documents exclusions and a 1.38x instrument-density inflation factor.
- **Issue volume is not incidence.** 62,196 OpenClaw issues exist in total (GitHub search API query
  recorded as S37 in FAILURE-ANALYSIS.md). Cite specific issues, never totals, as failure rates.
- **Pricing gaps.** Google Workspace AI, Microsoft 365 Copilot, OpenAI Codex, Claude Code official
  costs and Make's own page were not verifiable this pass (JS-only, 403, redirect stub). Those
  cells say "not verified" instead of guessing.
- **Hutch claims.** Anything about Hutch here is a design implication labelled HYPOTHESIS.

## Reading order

1. RESEARCH.md - what the showcase demonstrates, the six-post matrix, reusable patterns.
2. COMPETITIVE-ANALYSIS.md - market map, comparison table, what not to copy, differentiation.
3. FAILURE-ANALYSIS.md - failure-class table (evidence, root cause, countermeasure) and the
   cross-cutting primitive model: authority, idempotency, reconciliation, approval binding, run
   receipts, scoped visibility, truthful completion, budgets, catch-up, timezone contract.

## Headline findings

1. The valuable workflows are persistent human-owned operating loops; reliability beats capability.
2. The showcase sells itself with the same flows that fail in public: a WhatsApp loop that messaged
   a stranger, wrong reminder times, lost subagent results, false completion.
3. The market already names the countermeasures: idempotency and uncertain-delivery reconciliation,
   approval binding, decision receipts, metadata-only audit ledgers, staged calendar previews,
   fail-closed timezones.
4. Local-first is not the moat by itself; truthful state and explicit trust/sharing boundaries are.
5. Demand is real but narrow and cost-sensitive ("just handy", ~$100/month not worth it): the win
   is cheap, inspectable, boringly reliable recurring personal operations.

## Related material (read-only; not duplicated here)

`DECISIONS.md` and `ARCHITECTURE.md` in this directory; `docs/research/complaints.md` and
`docs/research/offerings-and-failures.md` in the repository.
