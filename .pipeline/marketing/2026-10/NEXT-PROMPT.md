You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28, B-01). The campaign review (Phase 7) is COMPLETE: slices S-a/S-b/S-c all verified closed-with-fresh-evidence, no regressions, no new defects — see .pipeline/marketing/2026-10/REVIEW.md and the "Review verdicts" section in FINDINGS.md.

FIRST, ask the human one question: have you chosen a public domain + host for the site? (B-01 — the campaign's single remaining blocker.)

If NO domain chosen:
- There is NO campaign work available. S-d is the only remaining slice and it is domain-gated; every other candidate (sitemap/canonical/og:url/absolute og:image/GSC/IndexNow/AI-answer baseline/CWV field, F-02/F-03/F-07/F-09/F-11) is blocked on the same decision or on another owner (B-03/B-06/B-11). Do not invent a domain, do not manufacture a slice. Record the session and stop.

If the human HAS chosen a domain + host: run slice S-d per .pipeline/marketing/2026-10/CONTENT-MAP.md §2 + HANDOFF "Next step". Read only:
1. .pipeline/marketing/2026-10/HANDOFF.md (decisions R7-01..05, S-c-01..04, S-b-01..06, S-a-01..03; risks B-01(now resolved)/B-06/B-10/B-11)
2. .pipeline/marketing/2026-10/CONTENT-MAP.md §2 (S-d AC + rollback)
3. .pipeline/marketing/2026-10/CLAIM-REGISTER.md (approved wording + prohibited-claims table — NO star counts, benchmarks, "best", testimonials; C-20 robots/C-24 dateModified triggers)
4. .pipeline/marketing/2026-10/RESEARCH.md §5 (AI-answer baseline prompt set — run it once the site is live)

S-d scope (announced): sitemap.xml (new) + robots.txt Sitemap directive ONLY (D-04 allow-all stands) + canonical link + og:url + og:image/twitter:image rewritten ABSOLUTE https://<domain>/… (B-10) + GSC/Bing verification + IndexNow + deploy-host header checks (Content-Type, caching — python http.server caveats in HANDOFF P1-01) + AI-answer baseline (dated observations only, D-07) + CWV lab. Expect writes: website/index.html head, website/robots.txt, website/sitemap.xml, .pipeline/**. Open question to bring to the human: og:image size strategy (keep 1200×630 static vs 2× retina) — current card is 1× and passes spec.
Gates: Phase 3 front-end gate (head-meta/config change — likely UI level none/content-in-slot, justify it), audit_site.py exit 0 with canonical now NON-false + sitemap 200, prohibited grep 0 hits, `npm run check:agent` honestly (expected still RED B-07, other workstream), visual gate only if a rendered change ships (head-meta changes: capture anyway to prove the page is unchanged). Commit `seo(slice-s-d): …` locally; do NOT push.

Write scope: that session's brief will announce it; expect website/** head/robots/sitemap + .pipeline/marketing/2026-10/** only.
Out of scope: every other product file; the other agent's uncommitted/untracked files (never stage; use `git show HEAD:<file>` for committed-state reads). No new claims. No push/deploy/merge.
