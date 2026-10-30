# HANDOFF - Hutch - 2026-10-30 - session 11 (CI flakiness check + CI badge)

## State
- Repo/branch: `/home/kevina/CodingProjects/hutch` · local `main` is the product workstream's branch: 15 commits ahead of `origin/main` at first check, 108 at the last check (it committed continuously; `f0551b8b` was one mid-session tip), and dirty (153 paths at session start). Its HEAD moved mid-session (`cb8ca349` -> `f0551b8b`), confirming active work. After this session's pushes it is far ahead (108 at the last check) / 2 behind `origin/main`; the product workstream must rebase before its next push. Do not reset, clean, merge or stage it.
- Origin/main: `adddfbfd` + this session's docs commits (badge commit `3980a03b`, a post-push evidence/count follow-up, and a review-correction follow-up; find the tip with `git log -1 origin/main` after `git fetch`). Campaign work was done in detached worktree `.worktrees/marketing-s11` at origin/main; the worktree is left in place for reading.
- Site: LIVE at https://k-arthur.github.io/hutch/ on the github.io host. No `website/**` change this session, so the Pages deployment is unchanged.
- Release: v0.1.0 source pre-release; release badge unchanged and still points at the tag.
- CI: run `40838063314` on `adddfbfd` is GREEN (5/5 jobs; 4162 passed on each Python 3.11/3.12/3.13). Run `40837883068` on `fe263eef` was CANCELLED (superseded 101 s later), not a result. The badge commit starts a fresh run (workflow triggers on every push, no paths filter); its conclusion is not awaited here.
- Campaign phase machine: Phases 0-7 complete; maintenance/measure mode. Open work is owner-gated.
- Other workstream: over 100 unpushed commits (108 at the last check) + dirty tree (src, app, tests, package files, AGENTS.md, .gitignore, CONTRIBUTING.md, website/brand assets) untouched. PR #11 open (theirs).

## What changed this session
- README badge row gains the CI workflow badge as the first badge (`README.md:7`), linking to `https://github.com/K-Arthur/hutch/actions/workflows/ci.yml`. The v0.1.0 release badge is unchanged (`README.md:13`).
- Campaign artifacts: `00-BRIEF.md` (session 11), `EVIDENCE-session-11.md`, `DECISION.md` R11-01..R11-06, this entry in `CHANGES.md`, `HANDOFF.md`, `NEXT-PROMPT.md`; evidence under `evidence/ci/run-40837883068/`, `evidence/ci/run-40838063314/` and `evidence/badge/`.
- Nothing else public: no site, docs, llms.txt, downloads.json or claim-register change.

## Decisions
See `DECISION.md` "Session 11 decisions". Key: the cancelled run is not evidence; run `40838063314` is green on identical product code, so the four red-run e2e failures are dated flakiness evidence; the badge was added with the release badge kept; campaign work was isolated in a worktree; Search Console was deferred, social preview and Bing are owner-side.

## Evidence map
- Acceptance table: `EVIDENCE-session-11.md`.
- CI: `evidence/ci/run-40838063314/{run.json,jobs.json,summaries.txt}`; `evidence/ci/run-40837883068/{run.json,jobs.json}`.
- Badge: `evidence/badge/{ci-badge-before.svg,badge-headers-before.txt}` (HTTP 200, `image/svg+xml`, `<title>ci - passing</title>`).
- Post-push: `evidence/badge/{readme-badge-excerpt.html,ci-badge-after.svg}` - GitHub-rendered README contains the badge pair. The badge commit's run `41098154819` was cancelled by the post-push follow-up (workflow concurrency), so the GitHub Actions badge temporarily showed `ci - failing` even though the only completed test-bearing run, `40838063314`, was green. Run `41098384979` (post-push follow-up) was in progress when this review-correction commit was pushed, so it was superseded too. The badge reflects the latest run; check the final run's conclusion, not just the badge color. This is a cancellation artifact, not evidence of a test failure.
- README diff: one added line at `README.md:7`; release badge line unchanged.

## Owner-gated steps (status 2026-10-30)
1. Social preview: selected by the human this session; completion NOT confirmed. github.com/K-Arthur/hutch -> Settings -> General -> Social preview -> Upload `website/assets/github-social-preview-1280x640.png` (1280x640, 133 KB) -> Save. No API exists (R9-D3). Record the date when done.
2. Search Console: DEFERRED by the human 2026-10-29 (chose "Defer to next session"). search.google.com/search-console -> Add property -> URL prefix `https://k-arthur.github.io/hutch/` -> verification method HTML tag -> paste the meta tag into `website/index.html` via a campaign commit -> deploy -> Verify -> Submit sitemap `https://k-arthur.github.io/hutch/sitemap.xml` -> record dated observations from the Generative AI performance report (B-03). A meta tag is a rendered change: run `audit_site.py` + the 42-test website e2e. A head-only tag does not require a JSON-LD `dateModified` change unless visible copy changes (C-24).
3. Bing Webmaster Tools: selected by the human this session; completion NOT confirmed. bing.com/webmasters -> Add property (import from Search Console is fastest) -> verify -> submit sitemap -> record observations (B-03).
4. Dependabot triage: 54 open alerts (8 critical, 26 high as of 2026-10-29; unchanged); 10 open update PRs. Dependency work is its own change (R9-D1), not marketing.
5. CI badge: DONE this session, conditioned on run `40838063314` (green on `adddfbfd`). If a later run goes red on the same flaky e2e tests, leave the badge (it reports the truth) and route the failure to the product workstream.

## Open risks / blockers
| ID | Risk | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| R10-D1 | Four product e2e failures (workflow route-card forced colors; 2 browser timeouts; design-system assert) | Badge can flip red; public Actions tab shows failures | product/Studio workstream | triage recurrence; the 2026-10-29 green run on identical code makes flakiness the working explanation | next red run |
| R11-D1 | Product workstream's local `main` is far ahead (108 at the last check) / 2 behind `origin/main` after this session | Their next push will be rejected until they rebase; dirty tree may complicate it | product/Studio workstream | fetch + rebase onto origin/main before pushing | their next push |
| R9-D1 | 54 open Dependabot alerts (8 critical, 26 high) + 10 update PRs | Supply-chain risk on a public repo | maintainer | triage critical/high; review queued PRs | now |
| B-03 | No Search Console/Bing properties | AI-performance and index measurement not started | maintainer | steps 2-3 above | now |
| R9-D3 | Social preview not uploaded | Weaker repo unfurls | maintainer | step 1 above | now |
| R9-D2 | Repo about 1.37 GB | Clone friction | maintainer | shallow clone documented; history/LFS later | before growth |
| R9-D4 | github.io origin root not controlled; robots.txt/security.txt advisory only | Full crawler policy + RFC 9116 location await a custom domain (human chose to stay) | maintainer | docs/discoverability.md migration plan | domain chosen |
| B-06 | downloads.json lists 4 platforms, 0 artifacts, no status field | Machine readers can misread availability | desktop workstream | add status fields when that pipeline is touched | pipeline activity |
| B-07 | Local `npm run check:agent` red: tests/test_commit_attribution.py 419 lines (as of 2026-10-29) | Local repo gate red; not CI (CI attribution job green) | git-attribution workstream | split the file | their next session |

## Next step (one only)
- Fetch `origin/main`, then check the latest `ci` run on main (earlier docs-commit runs were superseded by the next push; compare the run's conclusion, not just the badge color, because a cancelled run renders as failing). Green = the badge is backed by two consecutive green runs; red on the same four e2e tests = recurrence evidence for the product workstream. Do not fix product tests from a marketing session. Then, with the human, do the deferred Search Console tag slice if they provide the tag, or record social/Bing completion.

## Environment facts
- Campaign worktree: `/home/kevina/CodingProjects/hutch/.worktrees/marketing-s11` (detached at `adddfbfd` + this session's docs commits; gitignored). Reuse it or recreate from `origin/main`.
- Main checkout is the product workstream's: do not reset/clean/stage it.
- CI checks: `gh api repos/K-Arthur/hutch/actions/runs/<id>` and `.../jobs`; list with `gh api "repos/K-Arthur/hutch/actions/runs?branch=main&per_page=10"`.
- Badge: `https://github.com/K-Arthur/hutch/actions/workflows/ci.yml/badge.svg`.
- Serve/crawl: `UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` (self-serves `website/` on :8899).
- Website e2e: `UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q tests/e2e/test_website.py` (42 tests, about 70 s).
- Pre-commit hook `.githooks/pre-commit` exists but is NOT active; do not enable.

## Do not do
- Do not add the GSC verification tag without the full rendered-change gate (audit_site.py + 42 website e2e + head-state evidence).
- Do not fix the product e2e failures from a marketing session; record and route them.
- Do not push, merge, reset or clean the product workstream's far-ahead unpushed commits or dirty tree; never force-push or rewrite history.
- Do not claim the badge means permanent green; it reports the latest run.
- Do not add claims beyond the register; no superlatives, benchmarks, testimonials, star counts, "production-ready", "free forever", absolute privacy claims.
- Do not edit llms.txt claims, downloads.json or claim-register wording without evidence.
