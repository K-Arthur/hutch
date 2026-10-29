You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28, B-01).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md (decisions S-a-01..03, S-b-01..06, S-c-01..04; B-07/B-07b repo-gate red is pre-existing/other-workstream; S-d remains domain-gated)
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/EVIDENCE.md (what each landed slice proved)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CHANGES.md (S-a..S-c entries — the campaign's change log)
4. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CLAIM-REGISTER.md (approved wording + prohibited-claims table — NO star counts, benchmarks, "best", testimonials)
5. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CONTENT-MAP.md §2 (S-d AC — only if the human has since chosen a domain)

Session type: CAMPAIGN REVIEW (Phase 7) — read-only review of slices S-a..S-c as shipped, NOT an implementation slice. Rationale: S-d is blocked on B-01 (human domain decision) and no other domain-independent slice is planned; a review is the one valuable session available without new inputs.

If instead the human opens this session having CHOSEN a domain + host: skip the review and run slice S-d per CONTENT-MAP §2 + HANDOFF "Next slice" (sitemap.xml + robots Sitemap directive + canonical + og:url + ABSOLUTE og:image/twitter:image (B-10) + GSC/Bing verification + AI-answer baseline with RESEARCH §5 prompt set + CWV lab). Ask for the domain string first; never invent one.

What to do (review session):
- Re-verify the shipped state on the BUILT site: run `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (expect exit 0, FAQ 20/20, UA 6/6, 8 og + 4 twitter tags, canonical=false); re-run `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/s_c_render_card.py` ONLY if the asset is missing — do not re-render or touch the card otherwise.
- Adversarially re-check claim parity: every string on the card + in the head meta + in llms.txt must still map to a CLAIM-REGISTER row (spot-check C-01/C-02/C-03/C-05/C-15..C-17). Grep the prohibited list against website/ (expect 0 hits).
- Review FINDINGS.md: confirm F-01, F-04, F-06, F-08, F-12 are closed with evidence; list which findings remain OPEN and why (expected: F-02/F-03/F-07/F-09/F-10-partial/F-11 — all domain-gated or other-owner).
- Write scope: .pipeline/marketing/2026-10/** ONLY (a review changes no product file; if the review finds a product defect, record it in FINDINGS.md with severity and stop — fix = next slice with its own gate).
- `npm run check:agent` — report honestly (expected RED: B-07 tests/test_commit_attribution.py + B-07b hutch-composer.css; do NOT fix other workstreams' files).
- Commit review artifacts locally if anything under .pipeline changed: `marketing(review): …`. Do not push.
- Update HANDOFF.md + NEXT-PROMPT.md at the end (next step after review = human domain decision for S-d; there is no further domain-independent slice).

Write scope: .pipeline/marketing/2026-10/** only.
Out of scope: every product file — website/**, src/**, app/**, tests/**, README.md, llms.txt, downloads.json, robots.txt, docs/** — plus the other agent's uncommitted/untracked files (never stage; use `git show HEAD:<file>` for committed-state reads). No og:url/canonical/sitemap (would need a fake URL — prohibited). No new claims. No push/deploy/merge.

Acceptance (all must be true, with evidence paths):
- audit re-run exit 0 recorded; claim-parity spot-checks listed with register row IDs; prohibited-claims grep = 0 hits recorded.
- FINDINGS.md verdict table updated (closed vs open with reasons) — as a review record, not silent edits.
- EVIDENCE.md gains a short review-appendix section (or a REVIEW.md alongside it) mapping the review checks to their output.
- git status shows no product file touched; commit (if any) contains .pipeline/marketing/2026-10/** only; not pushed.
- HANDOFF.md + NEXT-PROMPT.md updated; NEXT-PROMPT points at the human domain decision (S-d) as the only remaining step.
