# 00 — CAMPAIGN BRIEF (session 5: slice S-b, Phase 5 implementation + Phase 3 gate)

- Product / one-liner: Hutch — local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. GitHub https://github.com/K-Arthur/hutch is the only public entity surface (no live domain, B-01).
- Repo / branch /commit: /home/kevina/CodingProjects/hutch · main · `4a307b88` (slice S-a landed; other agent still dirty in src/hutch/server/**, app/**, tests/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/ etc. — never staged; website/ + .pipeline/ confirmed clean in my scope via `git status --porcelain`).
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: slice S-b — IMPLEMENTATION (Phase 5) — mandate from NEXT-PROMPT.md (session 4). MUST OPEN the rendered half with the Phase 3 front-end gate + standing design-workflow research.
- Today / owner: 2026-10-28 / human owner (Claude research lead).
- Write scope: `website/index.html` + `.pipeline/marketing/2026-10/**` ONLY.
- Explicit non-goals: NO start of S-c (social cards); NO H1 flip (P2-01 Option A keeps "A little help with what's next."); NO edits to llms.txt (approved state), downloads.json (P2-04), robots.txt (D-04), README.md, src/**, app/**, tests/**; NO claims beyond CLAIM-REGISTER; NO push/deploy/merge.
- Authority: commit locally only; never push/deploy/merge without explicit human instruction (standing, confirmed 2026-10-28).
- Budget: ~10 files read; one product file changed (index.html, ~3 small regions); pipeline docs updated; wall time moderate (research step included for Step 2).
- Two-step slice (per NEXT-PROMPT):
  1. Step 1 (copy-only): meta description index.html:7 198→≤160 ch, "Development preview." intact, no mid-sentence cut; JSON-LD description (:23) untouched; JSON-LD dateModified (:37) 2026-10-26→2026-10-28 per C-24 trigger.
  2. Step 2 (rendered): "MIT-licensed · open source · Linux" trust row above the fold (F-12, P2-01 Option A). Gate: five Phase 3 questions answered in DECISION.md; online UI/UX research (>=3 inspected examples, >=2 sources; Figma Community via web since Figma MCP 403); 3-4 route options + recommendation; HUMAN route approval via question tool BEFORE any HTML edit. No approval => ship Step 1 only.
- Success criteria (from CONTENT-MAP S-b AC + NEXT-PROMPT acceptance):
  1. Description <=160 ch, "Development preview." intact, no mid-sentence cut; JSON-LD description byte-unchanged.
  2. dateModified = 2026-10-28 (C-24 refresh executed).
  3. If Step 2 approved: trust row visible above fold on desktop AND mobile captures; screenshots captured AND inspected (observations recorded in EVIDENCE.md incl. real focus-state capture per P1-06); audit_site.py exit 0 (FAQ parity 20/20, UA parity 6/6).
  4. `npm run check:agent` run + reported honestly (expected RED for B-07, pre-existing, other workstream — do not fix).
  5. Commit `seo(slice-s-b): …` locally, containing website/index.html + .pipeline/marketing/2026-10/** only; NOT pushed.
  6. EVIDENCE.md maps each AC to evidence; CLAIM-REGISTER C-24 row refreshed; HANDOFF.md + NEXT-PROMPT.md point at S-c (domain-independent part: og:image asset).
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 4, slice S-a — complete, commit `4a307b88`).
