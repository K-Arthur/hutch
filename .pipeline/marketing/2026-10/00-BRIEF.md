# 00 — CAMPAIGN BRIEF (session 3: Phase 2 strategy)

- Product / one-liner: Hutch — local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. GitHub https://github.com/K-Arthur/hutch is the only public entity surface (no live domain, B-01).
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · `44d66918` (phase-1 artifacts landed; other agent still dirty in src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never staged).
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: strategy (Phase 2) — mandate from NEXT-PROMPT.md (session 2). Output: STRATEGY.md + CLAIM-REGISTER.md + CONTENT-MAP.md, ending in HUMAN sign-off.
- Today / owner: 2026-10-28 / human owner (Claude research lead).
- Audience(s) in scope: developers/technical builders evaluating a self-hosted multi-agent tool; privacy/local-first advocates; operators wanting repeatable scheduled work on their own machine.
- Surfaces in scope: website/ (read-only this session), README as entity surface, machine files (robots.txt, llms.txt, downloads.json). NO product edits, NO copy shipped to website/ this session.
- Explicit non-goals: NO implementation (S-a..S-d land after sign-off); NO new pages without unique-value justification; NO sitemap/canonical/domain work (B-01); NO training-crawler robots change without human decision (D-04); NO downloads.json edit (B-06).
- Authority: commit locally only (.pipeline/marketing/ staging); never push/deploy/merge.
- Budget: ~15 files read; 1 session wall time; zero product diff.
- Success criteria (from NEXT-PROMPT acceptance):
  1. STRATEGY.md follows templates/STRATEGY.md structure; positioning options each reference RECON measurements; human offered 2-3 alternatives with tradeoffs (D-01), not silently picked.
  2. CLAIM-REGISTER.md covers every public factual claim from RECON §6 + JSON-LD fields (softwareVersion, dateModified, featureList x6, FAQ answers) with evidence pointers that exist; enforces RESEARCH §8 forbidden claims; drafts F-01 llms.txt replacement wording (fix lands in S-a after approval).
  3. CONTENT-MAP.md lists all 6 current surfaces (/ , robots.txt, llms.txt, downloads.json, THIRD_PARTY_NOTICES.txt, README-as-entity) with intents + gaps + ranked slices S-a..S-d, each with AC + rollback.
  4. Human decisions surfaced via question tool: D-01 sign-off, D-04 training-crawler policy, B-06 downloads.json owner; recorded in DECISION.md (BLOCKER is a valid outcome).
  5. Commit `marketing(phase-2): strategy, claim register, content map` staged to .pipeline/marketing/ only, not pushed.
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 2, Phase 1 audit — complete, committed `44d66918`).
