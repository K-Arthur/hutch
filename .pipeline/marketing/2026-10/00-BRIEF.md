# 00 — CAMPAIGN BRIEF (session 6: slice S-c, Phase 5 implementation + Phase 3 gate)

- Product / one-liner: Hutch — local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. GitHub https://github.com/K-Arthur/hutch is the only public entity surface (no live domain, B-01).
- Repo / branch / commit: /home/kevina/CodingProjects/hutch · main · `0ccad1e1` (slice S-b landed; other agent still dirty in src/hutch/server/**, app/**, tests/**, package*.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore + untracked .ai/, .codex/, .githooks/ etc. — never staged; website/ + .pipeline/ confirmed clean in my scope via `git status --porcelain`).
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: slice S-c — IMPLEMENTATION (Phase 5) — mandate from NEXT-PROMPT.md (session 5). MUST OPEN with the Phase 3 front-end gate (new rendered asset + head meta) + standing design-workflow research + human route approval BEFORE any asset creation or HTML edit.
- Today / owner: 2026-10-28 / human owner (Claude research lead).
- Write scope: `website/index.html` + ONE new file under `website/assets/` + `.pipeline/marketing/2026-10/**` ONLY. NO CSS-source edits (card styling must live inside the asset render, e.g. an SVG/inline-HTML render — not new site classes).
- Explicit non-goals: NO og:url / twitter:url / canonical / sitemap (domain-gated, B-01 — fake URL prohibited); NO H1 flip; NO edits to llms.txt, downloads.json, robots.txt, README.md, src/**, app/**, tests/**; NO claims beyond CLAIM-REGISTER (card strings from approved rows only: og:title text, "MIT-licensed · open source · Linux" (P2-01), "Development preview." (C-05)); NO push/deploy/merge; do NOT start S-d.
- Authority: commit locally only; never push/deploy/merge without explicit human instruction (standing, confirmed 2026-10-28).
- Budget: ~10 files read (target: pipeline docs already read + index.html head/hero regions only); one product file changed + one new asset; wall time moderate (research step required before routes).
- Success criteria (from CONTENT-MAP §2 S-c AC + NEXT-PROMPT session 5):
  1. Asset ≥1200×630, <300 KB, zero external URL references; card text = approved register wording only.
  2. Head tags added: og:image, og:image:alt, og:image:width/height, og:site_name, twitter:card (summary_large_image), twitter:title, twitter:description, twitter:image. og:title/og:description/og:type (index.html:10-12) NOT duplicated/reworded. og:url ABSENT.
  3. audit_site.py exit 0 with head inventory showing the new tags; FAQ parity 20/20; UA parity 6/6.
  4. Asset rendered capture taken AND inspected (observations recorded in EVIDENCE.md); render at 1440 and 390 checked.
  5. `npm run check:agent` run + reported honestly (expected RED for B-07, pre-existing, other workstream — do not fix).
  6. Commit `seo(slice-s-c): add og:image asset + social meta tags` locally, containing website/index.html + website/assets/<one-file> + .pipeline/marketing/2026-10/** only; NOT pushed.
  7. EVIDENCE.md maps each AC to evidence; CHANGES.md, HANDOFF.md, NEXT-PROMPT.md, CLAIM-REGISTER.md review log updated.
- Gate sequence this session: (a) Phase 3 five questions → DECISION.md; (b) web research ≥3 inspected social-card examples from ≥2 sources (Figma Community attempted via web; disclose blocks); (c) 3-4 route options via question tool → WAIT for human approval. No approval ⇒ hand off without creating the asset.
- Previous handoff: .pipeline/marketing/2026-10/HANDOFF.md (session 5, slice S-b — complete, commit `0ccad1e1`).
