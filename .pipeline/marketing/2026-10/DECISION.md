# DECISION — assumptions & front-end gate

## Assumptions (Phase 0 → resolved in Phase 1, 2026-10-28)
- A-01: RESOLVED — `website/` is the only deployed public marketing surface. `docs/` is repo-internal markdown (no docs deploy in `.github/workflows/`: ci.yml, desktop-linux.yml, native-platform.yml only). The GitHub README (https://github.com/K-Arthur/hutch) is the de facto off-site entity page. (RECON §1, §3)
- A-02: RESOLVED — no analytics installed anywhere on the site. `website/site.js` read in full (zero tracking code); `index.html` head/body contain no third-party scripts; `website/src/input.css:5` states the "no-external-request surface" contract; crawl found 0 third-party requests. (F-09)
- A-03: RESOLVED — no sitemap.xml exists (404 measured; absent from website/ listing). robots.txt:1-2 documents the reason (no absolute URL without a domain). (F-02)
- A-04: RESOLVED as far as the repo can tell — still no deploy target. Confirmed the three workflows are CI/desktop only; nothing builds or deploys `website/`. Deployment host + pipeline remain a human input (stays open, coupled to B-01).
- A-05: RESOLVED — English only (`lang="en"` index.html:2; no i18n files or locale switches).
- A-06: STILL ACTIVE — the other agent's uncommitted files remain `M` in git status (src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore). This campaign never stages/modifies them. Committed-state reads used `git show HEAD:<file>`.

## Research decisions (Phase 0, 2026-10-28)
D-01..D-08 recorded with evidence and falsifiers in `RESEARCH.md §7`. Summary: governed-local-first positioning (pending human sign-off in Phase 2); llms.txt kept as agent affordance only; FAQPage markup kept with zero rich-result expectation; robots allow-all for search/user bots with training bots as a human call; entity source order README → site FAQ → llms.txt; no mention-chasing; measurement via GSC + Bing AI Performance + dated prompt set; BLOCKER D-08 public domain unknown.

## Phase 1 audit decisions (2026-10-28)
- P1-01: Local serve baseline = `python -m http.server -d website` (works; adapter SERVE_CMD resolved). Caveat: it sends no Content-Type header on `/` — audit artifact only; real-host header checks go on the deploy-phase verification list, not against the site source.
- P1-02: Visual/a11y gates for this campaign = the committed evidence scripts (`evidence/audit/capture_site.py`, `audit_site.py`) re-runnable via `uv run --frozen --no-sync`. The repo has no site e2e/a11y gate; none is added in audit phase.
- P1-03: Site is dark-only BY DESIGN (`website/src/input.css:8` "one dark theme" brand contract, `color-scheme: dark` :26). Light-mode captures are N/A; the visual gate records dark at 4 viewports + reduced-motion instead of light/dark pairs.
- P1-04: `downloads.json` is treated as possibly owned by the desktop release pipeline (channel "preview", contract_version 1). No campaign edit to it until the owner confirms the contract (F-07, needs-human).
- P1-05: Full-page screenshot opacity-0 sections (shots/desktop-full.png) classified as capture-timing artifact, not a content-hiding defect: site.js:41 failsafe verified by the post-failsafe capture (desktop-full-failsafe.png) and by 0 sub-1.0-opacity elements under prefers-reduced-motion (focus-trace.txt). No-JS readability per site.js:1-5 contract + noscript block index.html:208-210.
- P1-06: Focus-ring rendering on a named control was not captured (trace started mid-page after scripted clicks). Accepted limitation for audit phase; a Phase 5+ rendered-change slice must capture real focus states per the mandatory visual gate.

## Post-session inputs
- 2026-10-28 (human): site has no live domain yet. B-01 resolved as pre-launch status; slices must stay domain-independent until a domain/host is chosen. GitHub repo is the sole public entity surface; treat README as the primary off-site discovery asset.
- 2026-10-28 (Phase 1 measurements): version triangulation passed (pyproject HEAD 0.1.0 = JSON-LD index.html:26 = footer index.html:955); GitHub-URL triangulation passed (downloads.json:5 = index.html:774/775/976, #quickstart anchor valid at README:41). Entity facts sheet §6 of RESEARCH gains these confirmations; llms.txt remains the one contradicting surface (F-01).

## Front-end necessity gate (Phase 3 — deferred)
Not run this session (audit only; no UI work planned or approved). Note for Phase 3: the user's standing design-workflow gate requires online UI/UX research + route approval before any rendered change; public Figma previews via web research are the sanctioned path since the Figma MCP is unavailable. The only render-adjacent candidate so far is an og:image asset (S-c), which is a new static asset, not a layout change — still gated.

## Authority
- Commit locally only. No push/deploy/merge without explicit human instruction (confirmed by user 2026-10-28).
