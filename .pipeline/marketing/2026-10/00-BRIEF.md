# 00 - CAMPAIGN BRIEF (session 9: public-repo launch, GitHub discoverability, Pages hosting)

- Product / one-liner: Hutch - local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. Repo: https://github.com/K-Arthur/hutch · site: https://k-arthur.github.io/hutch/
- Repo / branch / commit at session start: /home/kevina/CodingProjects/hutch · main · `f6bb3f22`; origin/main `b5fee054`; the GitHub repository was already PUBLIC (verified with an unauthenticated API call, HTTP 200, visibility public), with 38 committed local commits not yet pushed.
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: public-launch implementation. Extends the campaign from the static site to repository and GitHub surfaces (repo settings, community profile files, Pages hosting, release).
- Human request this session: make the repo public; do marketing, branding, SEO, AEO and GEO; add GitHub prerequisites and tags; update all forward-facing docs; account for edge cases and gaps.
- Owner input: the three blocking decisions (push main, choose public site host, create v0.1.0 pre-release) were asked twice through the question tool; both attempts timed out with no answer. Recommended, reversible defaults were applied and recorded in DECISION.md R9-01..R9-12.
- Host decision: GitHub Pages project site `https://k-arthur.github.io/hutch/` (B-01 resolved for now; a custom domain remains a later migration).
- Write scope: README.md, SECURITY.md, PRODUCT.md, CONTRIBUTING.md (public-wording hunks only), CODE_OF_CONDUCT.md, docs/** (README, brand-assets, marketing-site, discoverability), website/**, .github community files + pages workflow, CITATION.cff, .pipeline/**.
- Explicit non-goals: no new product claims; no dependency upgrades; no history rewrite or repository-size reduction; no custom domain, analytics or tracking; no changes to another workstream's uncommitted files.
- Success criteria:
  1. Repo public state verified; private-preview vocabulary removed from forward-facing docs; CONTRIBUTING corrected without staging the other workstream's section.
  2. GitHub prerequisites added: issue forms, PR template, CODEOWNERS, CITATION, Dependabot, Discussions, secret scanning, push protection, private vulnerability reporting, 20 topics, description.
  3. Site live on a real URL with canonical, og:url, absolute og:image, sitemap, security.txt and a Pages deploy workflow.
  4. Company docs updated: discoverability runbook, marketing claim rules, brand assets, docs index.
  5. Evidence: site audit exit 0, full website e2e green, focused tests, secret scans, and recorded manual/deferred steps.
  6. Pushed main; v0.1.0 source tag and pre-release notes; no binaries.