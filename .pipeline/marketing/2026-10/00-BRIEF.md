# 00 — CAMPAIGN BRIEF (session 7: CAMPAIGN REVIEW, Phase 7 — read-only on product)

- Product / one-liner: Hutch — local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. GitHub https://github.com/K-Arthur/hutch is the only public entity surface (no live domain, B-01, owner-confirmed 2026-10-28).
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · `f152b9b6` (slice S-c landed; other agent still dirty in src/hutch/server/**, app/**, tests/**, package*.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .githooks/, docs/*.md etc. — never staged; website/ + .pipeline/ clean via `git status --porcelain`).
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: CAMPAIGN REVIEW (Phase 7) — read-only review of slices S-a..S-c as shipped, per NEXT-PROMPT.md (session 6). NOT an implementation slice: S-d is blocked on B-01 (human domain decision) and no other domain-independent slice exists.
- Today / owner: 2026-10-28 / human owner (Claude research lead).
- Write scope: `.pipeline/marketing/2026-10/**` ONLY. If the review finds a product defect: record it in FINDINGS.md with severity and STOP (fix = a future slice with its own gate).
- Explicit non-goals: NO product-file edits (website/**, src/**, app/**, tests/**, README.md, llms.txt, downloads.json, robots.txt, docs/**); NO og:url/canonical/sitemap (would need a fake URL — prohibited); NO card re-render (asset present — instructed skip); NO new claims; NO push/deploy/merge; do NOT touch/stage the other agent's files.
- Authority: commit locally only; never push/deploy/merge without explicit human instruction (standing, confirmed 2026-10-28).
- Budget: ~8-10 files read beyond pipeline docs (index.html head/hero regions, llms.txt, audit outputs); one review commit max; wall time moderate.
- Success criteria (from NEXT-PROMPT session 6):
  1. audit_site.py re-run exit 0 recorded (FAQ 20/20, UA 6/6, 8 og + 4 twitter tags, canonical=false) → evidence/review/ outputs.
  2. Claim-parity spot-checks: card + head meta + llms.txt strings mapped to CLAIM-REGISTER rows (C-01/C-02/C-03/C-05/C-15..C-17 at minimum), listed with row IDs.
  3. Prohibited-claims grep across website/ = 0 hits, recorded.
  4. FINDINGS.md verdict table updated as a review record: F-01/F-04/F-06/F-08/F-12 closed-with-evidence; remaining OPEN list with reasons (expected: F-02/F-03/F-07/F-09/F-10-partial/F-11 — domain-gated or other-owner).
  5. EVIDENCE.md gains a review appendix (or REVIEW.md) mapping review checks → outputs.
  6. `npm run check:agent` run + reported honestly (expected RED: B-07 + B-07b, both other workstreams — do NOT fix).
  7. git status shows no product file touched; commit (if any) contains .pipeline/marketing/2026-10/** only; NOT pushed.
  8. HANDOFF.md + NEXT-PROMPT.md updated; NEXT-PROMPT points at the human domain decision (S-d) as the only remaining step.
- Gate sequence this session: (a) audit re-run on built site; (b) adversarial claim parity + prohibited grep; (c) findings verdict reconciliation vs EVIDENCE.md/CHANGES.md; (d) review-appendix artifacts; (e) commit + handoff.
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 6, slice S-c — complete, commit `f152b9b6`).
