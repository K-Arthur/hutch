# HANDOFF - Hutch - 2026-10-28 - session 9 (public launch: Pages hosting, public docs, GitHub prerequisites)

## State
- Repo/branch: /home/kevina/CodingProjects/hutch · main. The GitHub repository is PUBLIC (has been since 2026-10-07).
- Session start: local main `f6bb3f22`, origin/main `b5fee054`, 38 local commits unpublished.
- Published this session: `b5fee054..b44e62fd` (40 commits) plus the session-9 fix and record commits. See CHANGES.md session 9 and EVIDENCE-session-9.md for exact hashes and results.
- Site: LIVE at https://k-arthur.github.io/hutch/ via GitHub Pages (Actions artifact deploy from `website/`).
- Release: v0.1.0 source tag + GitHub pre-release (no binaries, no hosted sign-up). Tag and release are created right after the record commit is pushed.
- Campaign phase machine: Phases 0-7 complete (prior sessions); the domain-gated slice S-d is now effectively unblocked by the github.io origin, with a custom domain still deferred. Session 9 is a new public-launch workstream on top of the site campaign.
- Other workstream: its uncommitted tree (src, app, tests, package files, pyproject, AGENTS.md, .gitignore, untracked .ai/, docs workflow files) remains untouched. Only the two public-wording hunks of CONTRIBUTING.md were staged (index-only).

## What changed this session
- Site: canonical, og:url, absolute og:image and twitter:image, sitemap.xml, robots Sitemap directive, .well-known/security.txt (plus root convenience copy), .nojekyll, JSON-LD url/sameAs/author/screenshot, llms.txt site fact, Pages deploy workflow, 1280x640 GitHub social preview asset.
- Docs: README rebuilt for discoverability and answer engines; SECURITY rewritten for public private-vulnerability reporting; PRODUCT stale instruction fixed; CONTRIBUTING public wording; CODE_OF_CONDUCT; docs/README; docs/brand-assets identity section; docs/marketing-site claim rules + hosting section; new docs/discoverability runbook.
- GitHub: 20 topics, new description, Discussions, secret scanning, push protection, private vulnerability reporting, Dependabot security updates, delete-branch-on-merge, auto-merge; issue forms, PR template, CODEOWNERS, CITATION, Dependabot config; "dependencies" label.
- Site fixes found by the browser gate: removed a sitemap link that broke the asset-hash contract, made the workflow availability locator unique, restamped a stale tokens.css cache key.

## Decisions
See DECISION.md "Session 9 decisions" (R9-01..R9-14). Key ones: repo was already public; owner unavailable, reversible defaults applied; github.io origin chosen; exactly two JSON-LD blocks kept; CONTRIBUTING index-only staging; dependency upgrades out of scope; repository size accepted.

## Evidence map
- Session acceptance table: EVIDENCE-session-9.md.
- Live checks: https://k-arthur.github.io/hutch/ 200; canonical, og:url, absolute og:image present; sitemap.xml, .well-known/security.txt, llms.txt, robots.txt all 200.
- Site audit: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0, stderr 0 B (canonical true, 9 og, 4 twitter, FAQ 20/20, 6 UAs identical).
- Website e2e: 42 passed.
- Secret scan: gitleaks 40 commits + staged blobs, no leaks.
- Repo gates: hygiene pass, emoji clean, `npm run check:agent` red only for pre-existing B-07.
- Brand: evidence/brand/README.md (dimensions, bytes, sha256, safe zone, contrast, deterministic command).
- Release notes: RELEASE-NOTES-v0.1.0.md.

## Open risks / blockers
| ID | Risk | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| B-07 | `npm run check:agent` red: tests/test_commit_attribution.py 419 lines | Local repo gate stays red; not CI | git-attribution workstream | split the file | their next session |
| R9-D1 | 54 open Dependabot alerts (8 critical, 26 high) | supply-chain risk on public repo | maintainer | triage critical/high; review queued update PRs | now |
| R9-D2 | repo about 1.37 GB | clone friction | maintainer | shallow clone documented; history/LFS decision later | before growth |
| R9-D3 | social preview manual upload | weaker repo unfurls | maintainer | Settings > General > Social preview | now |
| R9-D4 | github.io origin root not controlled; robots.txt/security.txt advisory only | full crawler policy and RFC 9116 location await custom domain | maintainer | custom-domain migration per docs/discoverability.md | domain chosen |
| R9-D5 | CI on final pushed commit not yet confirmed | red badge risk | maintainer | watch Actions; fix only session-caused failures | next hour |
| B-03 | No Search Console/Bing properties | evidence and AI-performance measurement not started | maintainer | create URL-prefix properties, verify HTML, submit sitemap | now |
| B-06 | downloads.json owned by desktop pipeline (data lists 4 platforms, 0 artifacts) | machine readers can misread availability | desktop workstream | add status fields when that pipeline is next touched | pipeline activity |
| B-09 | RESOLVED this session: PRODUCT.md stale private-source instruction fixed | none | campaign | - | - |
| B-10 | RESOLVED for github.io: social image URLs are absolute | none | campaign | replace origin at custom-domain time | domain change |
| B-11 | RESOLVED for github.io: security.txt served; origin-root placement still caveated | none for now | campaign | custom domain | domain change |

## Next step (one only)
- Confirm the CI run on the final pushed commit and the first Pages deployment of the record commit; then start the owner-gated discovery steps: upload the social preview, create Search Console/Bing URL-prefix properties and submit the sitemap, and triage the critical/high Dependabot alerts.

## Environment facts
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899).
- Website e2e: `uv run --frozen --no-sync pytest -q tests/e2e/test_website.py` (42 tests, about 70 s).
- Social card render: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py --thumbnail`.
- Release notes: `.pipeline/marketing/2026-10/RELEASE-NOTES-v0.1.0.md`.
- Expected environment quirk: in this sandbox set `UV_CACHE_DIR=/tmp/uv-cache` because the default cache is read-only.
- Pre-commit hook .githooks/pre-commit exists but is NOT active (core.hooksPath unset, other workstream's file); do not enable.
- Other workstream still holds uncommitted work; never stage it.

## Do not do
- Do not invent a custom domain or claim a custom domain exists.
- Do not edit llms.txt claims, downloads.json, or the claim register wording without evidence.
- Do not add claims beyond the register; no star counts, benchmarks, testimonials, "best", "production-ready", "free forever", absolute privacy claims.
- Do not push dependency upgrades as part of a marketing change; Dependabot PRs are their own review.
- Do not force-push or rewrite history.
- Do not stage the other workstream's files (including their CONTRIBUTING append) to make a commit tidy.
