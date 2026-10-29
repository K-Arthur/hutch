# EVIDENCE - session 9 (public-repo launch, GitHub discoverability, Pages hosting) - 2026-10-28

Pre-push facts were measured in the working tree; push, first deployment, release and CI state are recorded at the end and in the session report.

## Acceptance criteria to evidence

| # | Acceptance criterion (00-BRIEF session 9) | Result | Evidence |
|---|---|---|---|
| 1 | Public repo state verified; no visibility flip fabricated | PASS | `curl -s -o /dev/null -w '%{http_code}' https://api.github.com/repos/K-Arthur/hutch` = 200; API body: visibility public, private false, created 2026-10-07. Local main was 38 commits ahead before session; origin/main b5fee054. |
| 2 | Private-preview vocabulary removed from forward-facing docs | PASS | README, SECURITY, PRODUCT, CONTRIBUTING (2 hunks), docs/marketing-site no longer say repo/source is private or "not public". Stale term sweep except the feature-specific Gmail "private preview" rows. CONTRIBUTING staged by index-only blob; other workstream's appended section left unstaged. |
| 3 | GitHub prerequisites applied | PASS | 20 topics (agents, ai, ai-agents, ai-assistant, automation, desktop-app, developer-tools, fastapi, linux, llm, local-first, local-llm, multi-agent, personal-ai, personal-assistant, privacy, python, self-hosted, sqlite, tauri); new description; Discussions enabled; secret scanning + push protection + Dependabot security updates + private vulnerability reporting enabled; delete-branch-on-merge and auto-merge enabled; issue forms, PR template, CODEOWNERS, CITATION, Dependabot config committed; "dependencies" label exists. |
| 4 | Site live on a real URL with full discovery metadata | PASS | Pages enabled via API (build_type workflow, public true). Live https://k-arthur.github.io/hutch/ returned 200 on third poll; live HTML contained canonical + og:url + absolute og:image; sitemap.xml 200, .well-known/security.txt 200, llms.txt 200, robots.txt 200. |
| 5 | Site audit green | PASS | `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0, stderr 0 B: canonical true, 9 og keys (includes og:url), 4 twitter keys, sitemap.xml 200, security.txt 200, FAQ parity 20/20, description_len 157, anchors 10/10, six crawler user-agents identical 99,015 bytes. |
| 6 | Website e2e green after fixes | PASS | `pytest -q tests/e2e/test_website.py` -> 42 passed in 68.79s. Two failures found and fixed first: (a) sitemap link violated the local asset cache-key contract, tag removed; (b) workflow availability locator matched two rows, replaced with unique "Owner-started saved workflows" text in one line; (c) pre-existing stale tokens.css cache key restamped with `node scripts/stamp_site_assets.mjs`. |
| 7 | Repo gates | PASS with pre-existing exception | `scripts/check_repo_hygiene.py` staged check passed; `scripts/audit_emoji.py` clean (2762 files); `npm run check:agent` FAIL with ONE pre-existing violation: tests/test_commit_attribution.py 419 lines (B-07, other workstream). No new violation: tests/e2e/test_website.py remained 1449 lines after the fix. |
| 8 | Secret scan before publishing | PASS | `gitleaks git --log-opts="origin/main..HEAD" --redact=100 --no-banner` -> 40 commits scanned, no leaks. Staged-blob scans for both commits -> no leaks. |
| 9 | Public docs updated and internally consistent | PASS | README rebuilt (badges, tagline, status, screenshot, shallow-clone quickstart, 5 capability bullets, link row, TOC, availability table, 6 common questions, docs map). SECURITY rewritten for public private-vulnerability reporting. PRODUCT stale instruction fixed. docs/README new. docs/brand-assets identity section plus social preview. docs/marketing-site claim rules updated with live URL, JSON-LD, robots caveat, hosting section. docs/discoverability new runbook. CoC added. |
| 10 | Brand asset | PASS | website/assets/github-social-preview-1280x640.png: 1280x640 PNG, 133,259 bytes, sha256 cc1a0b08fdacd14ea2680386313f087b17a0ee19cae4a2f1948675c2ae6fed7c; deterministic renderer + evidence note under evidence/brand/; image inspected at full res and at 320 px width; 112 px safe inset. |
| 11 | Push and release | PASS (release step follows this commit) | Push `b5fee054..b44e62fd main -> main` succeeded (40 commits). v0.1.0 source tag and pre-release notes prepared; the tag and release are created immediately after the record commit is pushed. No binaries. |
| 12 | CI on the final commit | PENDING at commit time | The CI run is triggered by the final push (three Python versions, full pytest). Watch Actions and record the run before the next session; do not claim green without it. |

## New risks measured this session

| ID | Finding | Impact | Owner | Next action |
|---|---|---|---|---|
| R9-D1 | 54 open Dependabot alerts (8 critical, 26 high, 19 medium, 1 low; 53 pip, 1 rust) surfaced when alerts were enabled | Supply-chain exposure on a public repo; update PRs will appear | dependency/maintainer | Triage critical/high first; the five queued update jobs will open grouped PRs. Not fixed in this marketing slice. |
| R9-D2 | Repository is about 1.37 GB (local .git 1.7 GB; docs/realignment about 385 MB of trace.zip evidence) | Clone friction; GitHub size guidance | maintainer | Shallow clone documented in README. A history/LFS migration is a separate, coordinated decision. |
| R9-D3 | Social preview cannot be uploaded by API | Repo shares may show GitHub's generated card | maintainer | Upload website/assets/github-social-preview-1280x640.png in Settings > General > Social preview. |
| R9-D4 | github.io origin root is not controlled by this repository, so robots.txt and /.well-known/security.txt are not read at the origin root | Crawler policy and security.txt are only advisory until a custom domain | maintainer | Documented in docs/discoverability.md; migrate with a custom domain. |
| R9-D5 | CI/benchmarks on the final pushed commit are unverified at commit time | A red CI badge on the public repo would undercut launch | maintainer | Watch the Actions run; fix only failures traceable to this session's changes. |
| R9-D6 | CONTRIBUTING.md still carries another workstream's unstaged "Repository hygiene" section | The public commit omits their section by design; their work stays local | other workstream | Commit their section in their own change; do not stage it here. |
| R9-D7 | Dependabot update jobs started immediately after the config landed | Grouped dependency PRs will appear in the public repo | maintainer | Review them as dependency PRs, not marketing changes. |

## Manual and deferred steps

- Search Console and Bing Webmaster Tools URL-prefix properties for https://k-arthur.github.io/hutch/ (HTML verification), then submit sitemap.xml and review the Search Console Generative AI performance report.
- Social preview upload (D3).
- Custom domain migration: CNAME, DNS, HTTPS, redirects, replace the github.io origin in the four head tags, sitemap.xml, llms.txt, security.txt and docs/discoverability.md; re-verify both consoles.
- Dependabot triage (D1).
- CI confirmation (D5).
