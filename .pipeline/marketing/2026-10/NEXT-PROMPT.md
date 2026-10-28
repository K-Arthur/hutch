You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md (decisions D-01..D-08, blockers B-01..B-06, next slice)
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/RECON.md (§6 content/claims inventory, §4 machine layer)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/FINDINGS.md (F-01 is the wording you must draft a fix for)
4. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/DECISION.md (resolved assumptions + P1-01..P1-06)
5. RESEARCH.md sections: §6 entity facts sheet, §7 decision memos (D-01 positioning + D-06 off-site need your sign-off packet), §8 forbidden claims (the claim register must enforce these)
6. Templates: 03-PHASE-2-STRATEGY.md and templates/{STRATEGY.md,CLAIM-REGISTER.md,CONTENT-MAP.md} in /home/kevina/Downloads/Telegram Desktop/marketing-seo-aeo-geo-prompt-pack/

Session type: Phase 2 strategy. Produce STRATEGY.md + CLAIM-REGISTER.md + CONTENT-MAP.md. NO product edits, NO copy shipped to the site.

Write scope: /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/** only.
Out of scope: any file under website/, src/, docs/, app/, README.md; other agents' uncommitted work (src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — use `git show HEAD:<file>` for committed-state reads).

What to do:
- Positioning: turn D-01 ("governed local-first AI assistants") into a concrete message hierarchy for the one-pager, honoring the measured hero state (category eyebrow above human-tone H1, F-10; trust words below fold, F-12). Offer the human 2-3 alternatives with tradeoffs; do not silently pick.
- Claim register: every public factual claim from RECON §6 + JSON-LD fields (incl. softwareVersion 0.1.0, dateModified, featureList x6, FAQ answers) gets exact wording → evidence pointer (file:line / test / HEAD state) → owner → refresh trigger → status. Enforce RESEARCH §8 forbidden-claims table. Draft the F-01 llms.txt replacement wording here (fix lands in slice S-a AFTER sign-off).
- Content map: page/intent/claim map for the single route + machine files; note gaps (og:image asset S-c, social cards F-04) and the domain-gated queue (F-02/F-03/F-09 → slice S-d). Rank the post-sign-off slices: S-a (llms.txt repair), S-b (metadata trim), S-c (social cards), S-d (domain-gated technical) — each with acceptance criteria + rollback.
- Surface the human decisions explicitly: D-01 sign-off, D-04 training-crawler policy, B-06 downloads.json owner. Use the question tool for these; a written BLOCKER is a valid outcome.
- Do not ship any wording to website/ this session. Do not create new pages without unique-value justification + earn-links plan (D-06).

Acceptance (all must be true, with evidence paths):
- STRATEGY.md follows templates/STRATEGY.md structure; positioning options each have references to RECON measurements.
- CLAIM-REGISTER.md covers every claim in RECON §6 with evidence pointers that exist (no invented file:line).
- CONTENT-MAP.md lists all 6 current surfaces (/, robots.txt, llms.txt, downloads.json, THIRD_PARTY_NOTICES.txt, README-as-entity) with intents + gaps + ranked slices with AC/rollback.
- Human sign-off recorded in DECISION.md (or BLOCKER written).
- No product files modified (git status shows only .pipeline/ changes from this campaign).
- Commit locally: `marketing(phase-2): strategy, claim register, content map` staging ONLY .pipeline/marketing/. Do not push.
