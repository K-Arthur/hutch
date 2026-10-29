# HANDOFF - Hutch - 2026-10-29 - session 10 (post-launch CI/deploy verification; CI red on record commit, attributed to product workstream)

## State
- Repo/branch: /home/kevina/CodingProjects/hutch · main. GitHub repository PUBLIC. Local main = origin/main = `577e1154` (session-9 record commit). Nothing new pushed except this session's docs/evidence commit.
- Site: LIVE at https://k-arthur.github.io/hutch/ — Pages run `40813421201` on the record commit SUCCEEDED; live HTML verified to serve the record commit (canonical, og:url, locator marker, `tokens.css?v=7e5b0d00` byte-matches `git show 577e1154:website/index.html`).
- Release: v0.1.0 source pre-release live (prerelease=true, 0 assets). Human confirmed it plus pushed main and the github.io host (DECISION R10-01).
- CI on the record commit: RED. Run `40813421173`: benchmarks/attribution/3.11 green; 3.12 failed 1 test, 3.13 failed 3 different tests — all in product-UI e2e (test_workflow_route_card, test_browser, test_design_system), none traceable to session-9 (EVIDENCE-session-10 AC1a). Recorded, not fixed.
- Campaign phase machine: Phases 0-7 complete; launch done; this session was verification. Marketing work is in maintenance/measure mode; the open work is owner-gated or belongs to other workstreams.
- Other workstream: uncommitted tree (src, app, tests, package files, AGENTS.md, .gitignore, CONTRIBUTING.md) still present and untouched; brand PR #11 open (theirs).

## What changed this session
- Nothing on any public surface. Campaign artifacts only: 00-BRIEF (session 10), EVIDENCE-session-10, DECISION R10-01..R10-05, CHANGES entry, this HANDOFF, NEXT-PROMPT, and evidence/ci/run-40813421173/ log excerpts.
- README badge row deliberately unchanged: the adapter gates the CI badge on a green run, and CI is red (R10-04).

## Decisions
See DECISION.md "Session 10 decisions" (R10-01..R10-05). Key ones: three defaults confirmed by the human; host stays github.io; CI failures attributed to the product workstream (recorded, not fixed); no CI badge while red; owner-gated steps deferred by the human with exact steps recorded below.

## Evidence map
- Session acceptance table: EVIDENCE-session-10.md.
- CI: run 40813421173 (jobs.json + both failure excerpts under evidence/ci/run-40813421173/). 3.12: 1 failed/4161 passed; 3.13: 3 failed/4159 passed; 3.11 green.
- Pages/deploy: run 40813421201 success; live marker checks (canonical, og:url, locator, asset stamp) recorded in EVIDENCE-session-10 AC2.
- Repo/release/API re-verification: EVIDENCE-session-10 AC3.

## Owner-gated steps (deferred by human 2026-10-29; exact paths)
1. Social preview: github.com/K-Arthur/hutch → Settings → General → Social preview → Upload an image → website/assets/github-social-preview-1280x640.png (from a local checkout) → Save. No API exists (R9-D3).
2. Search Console: search.google.com/search-console → Add property → URL prefix `https://k-arthur.github.io/hutch/` → verification method HTML tag (paste the meta tag into website/index.html via a campaign commit, or use domain-verification if preferred) → after verification, Submit sitemap `https://k-arthur.github.io/hutch/sitemap.xml` → record dated observations from the Generative AI performance report (B-03).
3. Bing Webmaster Tools: bing.com/webmasters → Add property (URL prefix or import from Search Console) → verify → submit sitemap → record observations (B-03).
4. Dependabot triage: 54 open alerts still (8 critical, 26 high at launch; unchanged 2026-10-29); 10 open update PRs (#1-#10). Dependency work is its own change (R9-D1) — not marketing.
5. CI badge: once a green CI run exists on main (after the product workstream fixes/red-flakes the e2e failures), add to README badge row: `[![CI](https://github.com/K-Arthur/hutch/actions/workflows/ci.yml/badge.svg)](https://github.com/K-Arthur/hutch/actions/workflows/ci.yml)` and keep the release badge on the v0.1.0 tag. Then it is a straightforward docs commit under standing authority.

## Open risks / blockers
| ID | Risk | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| R10-D1 | CI red on main's record commit: 4 distinct product e2e failures (3.12: workflow route card forced-colors; 3.13: 2 browser timeouts + 1 design-system assert) | Red Actions tab on a public repo; badge withheld; flakiness possible but the forced-colors/design-system asserts look deterministic (inference) | product/Studio workstream | triage the four tests; re-run CI; then campaign adds the CI badge | their next session |
| R9-D1 | 54 open Dependabot alerts (8 critical, 26 high) + 10 open update PRs | supply-chain risk on public repo | maintainer | triage critical/high; review queued PRs | now |
| B-03 | No Search Console/Bing properties | AI-performance and index measurement not started | maintainer | steps 2-3 above | now |
| R9-D3 | social preview not uploaded | weaker repo unfurls | maintainer | step 1 above | now |
| R9-D2 | repo about 1.37 GB | clone friction | maintainer | shallow clone documented; history/LFS later | before growth |
| R9-D4 | github.io origin root not controlled; robots.txt/security.txt advisory only | full crawler policy + RFC 9116 location await custom domain (human chose to stay, 2026-10-29) | maintainer | docs/discoverability.md migration plan | domain chosen |
| B-06 | downloads.json lists 4 platforms, 0 artifacts, no status field | machine readers can misread availability | desktop workstream | add status fields when that pipeline is touched | pipeline activity |
| B-07 | local `npm run check:agent` red: tests/test_commit_attribution.py 419 lines | local repo gate red; not CI (CI attribution job green) | git-attribution workstream | split the file | their next session |

## Next step (one only)
- Check CI run `40837883068` (triggered by this session's record commit `fe263eef`, same product code as `577e1154`): if the four product e2e tests pass, that is dated flakiness evidence for the product workstream; if they fail identically, the failures are deterministic. Either way the product/Studio workstream owns the fix; the campaign adds the CI badge only after a green run on main (step 5), while the human works the owner-gated steps 1-4.

## Environment facts
- CI checks: `gh api repos/K-Arthur/hutch/actions/runs/<id>` and `gh api repos/K-Arthur/hutch/actions/jobs/<id>/logs` (gh authenticated as K-Arthur).
- Serve/crawl: `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves website/ on :8899).
- Website e2e: `uv run --frozen --no-sync pytest -q tests/e2e/test_website.py` (42 tests, about 70 s).
- Expected sandbox quirk: set `UV_CACHE_DIR=/tmp/uv-cache` (default cache read-only).
- Pre-commit hook .githooks/pre-commit exists but is NOT active; do not enable.
- Other workstream still holds uncommitted work; never stage it.

## Do not do
- Do not add the CI badge before a green CI run on main.
- Do not fix the product e2e failures from a marketing session; record and route them.
- Do not invent a custom domain; do not edit llms.txt claims, downloads.json, or claim-register wording without evidence.
- Do not add claims beyond the register; no superlatives, benchmarks, testimonials, star counts, "production-ready", "free forever", absolute privacy claims.
- Do not push dependency upgrades as marketing; do not force-push or rewrite history.
- Do not stage the other workstream's files (including their CONTRIBUTING append and PR #11).
