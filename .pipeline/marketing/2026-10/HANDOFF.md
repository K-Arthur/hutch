# HANDOFF - Hutch - 2026-10-30 - session 11 (CI flakiness check + CI badge)

## State
- Repo/branch: `/home/kevina/CodingProjects/hutch` · local `main` is the product workstream's branch: 15 commits ahead of `origin/main` at first check, 118 at the last check (it committed continuously; `f0551b8b` was one mid-session tip), and dirty (153 paths at session start). Its HEAD moved mid-session (`cb8ca349` -> `f0551b8b`), confirming active work. After this session's pushes it is far ahead (118 at the last check) / 4 behind `origin/main`; the product workstream must rebase before its next push. Do not reset, clean, merge or stage it.
- Origin/main: `adddfbfd` + this session's docs commits (badge commit `3980a03b`, a post-push evidence/count follow-up, and a review-correction follow-up; find the tip with `git log -1 origin/main` after `git fetch`). Campaign work was done in detached worktree `.worktrees/marketing-s11` at origin/main; the worktree is left in place for reading.
- Site: LIVE at https://k-arthur.github.io/hutch/ on the github.io host. No `website/**` change this session, so the Pages deployment is unchanged.
- Release: v0.1.0 source pre-release; release badge unchanged and still points at the tag.
- CI: latest run `41099288093` on `8db7f28e` is **RED** (completed 2026-10-30T18:14:09Z): 3.13 and 3.11 failed, 3.12 passed; benchmarks and attribution passed. 3.13: `test_assistant_settings_header_groups_secondary_actions` (tests/e2e/test_design_system.py:281 - after clicking "Assistant options", the "Open chat" menuitem is not visible). 3.11 additionally: `test_virtual_passkey_pairs_locks_and_unlocks_over_https` (10 s response timeout) and `test_conversation_open_has_pending_controls_and_route_ownership[controls]` (`#conversation-switcher` remains disabled/inert). The README badge truthfully shows `ci - failing`. The public run is on product code identical to `577e1154`; the product workstream's 118 local commits are unpushed, so their fixes (if any) are not in it. Earlier run `40838063314` on `adddfbfd` was green; run `40837883068` was cancelled.
- Campaign phase machine: Phases 0-7 complete; maintenance/measure mode. Open work is owner-gated.
- Other workstream: over 100 unpushed commits (118 at the last check) + dirty tree (src, app, tests, package files, AGENTS.md, .gitignore, CONTRIBUTING.md, website/brand assets) untouched. PR #11 open (theirs).

## What changed this session
- README badge row gains the CI workflow badge as the first badge (`README.md:7`), linking to `https://github.com/K-Arthur/hutch/actions/workflows/ci.yml`. The v0.1.0 release badge is unchanged (`README.md:13`).
- Campaign artifacts: `00-BRIEF.md` (session 11), `EVIDENCE-session-11.md`, `DECISION.md` R11-01..R11-07, this entry in `CHANGES.md`, `HANDOFF.md`, `NEXT-PROMPT.md`; evidence under `evidence/ci/run-40837883068/`, `evidence/ci/run-40838063314/`, `evidence/ci/run-41099288093/` and `evidence/badge/`.
- Recorded the post-badge red run `41099288093` (3.11/3.13 failures) and routed it to product/Studio; the badge is left in place as truthful status.
- Nothing else public: no site, docs, llms.txt, downloads.json or claim-register change.

## Decisions
See `DECISION.md` "Session 11 decisions". Key: the cancelled run is not evidence; run `40838063314` was green on identical product code, but the post-badge run `41099288093` failed on 3.11/3.13, so the design-system and UI tests are intermittent/brittle rather than proven deterministic or fully flaky; the badge is left red as truthful status; campaign work was isolated in a worktree; Search Console was deferred, social preview and Bing are owner-side.

## Evidence map
- Acceptance table: `EVIDENCE-session-11.md`.
- CI: `evidence/ci/run-40838063314/{run.json,jobs.json,summaries.txt}`; `evidence/ci/run-40837883068/{run.json,jobs.json}`; `evidence/ci/run-41099288093/{run.json,jobs.json,failures.txt}` (red run: 3.13 `1 failed, 4161 passed`; 3.11 `3 failed, 4159 passed`; 3.12 `4162 passed`).
- Badge: `evidence/badge/{ci-badge-before.svg,badge-headers-before.txt}` (HTTP 200, `image/svg+xml`, `<title>ci - passing</title>`).
- Post-push: `evidence/badge/{readme-badge-excerpt.html,ci-badge-after.svg}` - GitHub-rendered README contains the badge pair. Runs `41098154819` and `41098384979` were cancelled by the next docs push (workflow concurrency), so the badge briefly showed `ci - failing` as a cancellation artifact. Run `41099288093` then failed for real on 3.11/3.13, so the badge now shows `ci - failing` truthfully. The badge condition was run `40838063314` (green); the current red is the latest run, not a cancellation.
- README diff: one added line at `README.md:7`; release badge line unchanged.

## Owner-gated steps (status 2026-10-30)
1. Social preview: selected by the human this session; completion NOT confirmed. github.com/K-Arthur/hutch -> Settings -> General -> Social preview -> Upload `website/assets/github-social-preview-1280x640.png` (1280x640, 133 KB) -> Save. No API exists (R9-D3). Record the date when done.
2. Search Console: DEFERRED by the human 2026-10-29 (chose "Defer to next session"). search.google.com/search-console -> Add property -> URL prefix `https://k-arthur.github.io/hutch/` -> verification method HTML tag -> paste the meta tag into `website/index.html` via a campaign commit -> deploy -> Verify -> Submit sitemap `https://k-arthur.github.io/hutch/sitemap.xml` -> record dated observations from the Generative AI performance report (B-03). A meta tag is a rendered change: run `audit_site.py` + the 42-test website e2e. A head-only tag does not require a JSON-LD `dateModified` change unless visible copy changes (C-24).
3. Bing Webmaster Tools: selected by the human this session; completion NOT confirmed. bing.com/webmasters -> Add property (import from Search Console is fastest) -> verify -> submit sitemap -> record observations (B-03).
4. Dependabot triage: 54 open alerts (8 critical, 26 high as of 2026-10-29; unchanged); 10 open update PRs. Dependency work is its own change (R9-D1), not marketing.
5. CI badge: DONE this session, conditioned on run `40838063314` (green on `adddfbfd`). The latest run `41099288093` failed on 3.11/3.13, so the badge is now red; leave it (truthful status) and route the failures to the product workstream.

## Open risks / blockers
| ID | Risk | Impact | Owner | Next action | Trigger |
|---|---|---|---|---|---|
| R10-D1 | Product e2e/UI failures recur: run `41099288093` failed 3.11/3.13 on design-system header groups (both), passkey response timeout (3.11) and conversation switcher disabled/inert (3.11); 3.12 green | Public badge is red; Actions shows failures | product/Studio workstream | triage the design-system header-groups test and the conversation/passkey timeouts; the public run is on old product code (118 local commits unpushed) | now |
| R11-D1 | Product workstream's local `main` is far ahead (118 at the last check) / 4 behind `origin/main` after this session | Their next push will be rejected until they rebase; dirty tree may complicate it | product/Studio workstream | fetch + rebase onto origin/main before pushing | their next push |
| R9-D1 | 54 open Dependabot alerts (8 critical, 26 high) + 10 update PRs | Supply-chain risk on a public repo | maintainer | triage critical/high; review queued PRs | now |
| B-03 | No Search Console/Bing properties | AI-performance and index measurement not started | maintainer | steps 2-3 above | now |
| R9-D3 | Social preview not uploaded | Weaker repo unfurls | maintainer | step 1 above | now |
| R9-D2 | Repo about 1.37 GB | Clone friction | maintainer | shallow clone documented; history/LFS later | before growth |
| R9-D4 | github.io origin root not controlled; robots.txt/security.txt advisory only | Full crawler policy + RFC 9116 location await a custom domain (human chose to stay) | maintainer | docs/discoverability.md migration plan | domain chosen |
| B-06 | downloads.json lists 4 platforms, 0 artifacts, no status field | Machine readers can misread availability | desktop workstream | add status fields when that pipeline is touched | pipeline activity |
| B-07 | Local `npm run check:agent` red: tests/test_commit_attribution.py 419 lines (as of 2026-10-29) | Local repo gate red; not CI (CI attribution job green) | git-attribution workstream | split the file | their next session |

## Next step (one only)
- The latest run is red: record it and route the 3.11/3.13 failures to product/Studio. Do not fix product tests here. Check whether the product workstream has pushed/rebase the 118 local commits; if so, re-check CI on the new main. Then, with the human, do the deferred Search Console tag slice if they provide the tag, or record social/Bing completion.

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
