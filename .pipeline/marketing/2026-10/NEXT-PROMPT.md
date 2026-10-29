You are continuing the Hutch marketing and discoverability campaign. Session 9 completed the public launch: the GitHub repository is public (it already was), main was published (40+ commits), the site is live on GitHub Pages at https://k-arthur.github.io/hutch/ with canonical, og:url, absolute social image, sitemap.xml, security.txt and a Pages workflow, the public README/SECURITY/PRODUCT/CONTRIBUTING/docs were rewritten for a public audience, GitHub prerequisites landed (20 topics, Discussions, secret scanning, push protection, private vulnerability reporting, Dependabot, issue forms, PR template, CODEOWNERS, CITATION), and a v0.1.0 source pre-release was created. Artifacts: .pipeline/marketing/2026-10/{00-BRIEF,DECISION,CHANGES,EVIDENCE-session-9,HANDOFF,RELEASE-NOTES-v0.1.0}.md.

Read only:
1. .pipeline/marketing/2026-10/HANDOFF.md (state, open risks, next step)
2. .pipeline/marketing/2026-10/EVIDENCE-session-9.md (what was measured)
3. .pipeline/marketing/2026-10/CLAIM-REGISTER.md (approved wording; no new claims; C-27..C-30 for the new surfaces)

FIRST verify the CI run on the final pushed commit. If it is red, diagnose only failures traceable to the session-9 changes (site head, e2e locator, asset stamp, workflow). A failure in another workstream's tests is recorded, not fixed here. Do not claim green without a run id and conclusion.

Then, if the human is available, confirm the three defaults applied while they were away (pushed main, github.io host, v0.1.0 pre-release) and take the owner-gated steps:
- Upload website/assets/github-social-preview-1280x640.png in repo Settings > General > Social preview (no API).
- Create Search Console and Bing Webmaster Tools URL-prefix properties for https://k-arthur.github.io/hutch/ with HTML verification, submit sitemap.xml, and record dated observations in the Search Console Generative AI performance report.
- Triage the critical/high Dependabot alerts (54 open at launch; 8 critical, 26 high) by reviewing the queued dependency PRs. Dependency work is its own change, not marketing.
- Decide whether to migrate to a custom domain. If yes, follow docs/discoverability.md, replace the github.io origin in the four absolute head tags plus sitemap.xml, llms.txt, security.txt and docs/discoverability.md, keep redirects and re-verify.
- If no host change: update the badge row only after a green CI run (CI badge) and keep the release badge pointed at the v0.1.0 tag.

Claim discipline is unchanged and permanent: no superlatives, benchmarks, testimonials, star counts, "best", "production-ready", "free forever", absolute privacy claims; stage term is "development preview"; source is public, no packaged installers, provider billing authoritative. Write scope for a follow-up session: .pipeline/marketing/2026-10/**, docs/discoverability.md, docs/marketing-site.md, README.md, website/**. Out of scope: product code, dependency upgrades, the other workstream's uncommitted tree, history rewrite, force push. Commit locally and push only when the human authorizes publication; if the change is a straightforward docs/evidence update, the standing session-9 authority covers pushing to main.
