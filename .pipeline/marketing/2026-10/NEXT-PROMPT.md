You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md (decisions incl. S-b-01..06; B-07 repo-gate red is pre-existing/other-workstream; next slice = S-c domain-independent part)
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/DECISION.md (front-end necessity note: even a new static asset is gated; S-b-05 shows the research+approval pattern to repeat; S-b-03 stale-impeccable-context note)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CONTENT-MAP.md §2 slice S-c (acceptance criteria + rollback)
4. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CLAIM-REGISTER.md (approved wording usable on the card; prohibited-claims table — NO star counts, benchmarks, "best", testimonials)
5. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/FINDINGS.md (F-04 og:image/social meta gap)

Session type: slice S-c — IMPLEMENTATION (Phase 5), but it MUST OPEN with the Phase 3 front-end gate because it adds a rendered asset + head meta (og/twitter tags).

Before any asset creation or HTML edit:
(a) answer the five Phase 3 questions in DECISION.md (S-b-01 records the reconstructed question set — reuse it);
(b) run the standing design-workflow research requirement: web research with >=3 concrete INSPECTED examples from >=2 sources (Figma Community scouting via web search + image reading; the Figma MCP is 403 — do not ask the user to re-auth; direct figma.com fetches were CloudFront-blocked for automated clients, so use accessible live interfaces/creator previews and DISCLOSE anything blocked). Inspect real social-card/og-image patterns (e.g., how dev tools render their 1200x630 cards — text card vs product shot vs mascot);
(c) present 3-4 scope-sized route options (composition style of the card + which approved strings it carries) with a recommendation and WAIT for human route approval (question tool) before writing any file. If approval does not arrive, hand off without creating the asset.

Write scope: /home/kevina/CodingProjects/hutch/website/index.html + ONE new file under /home/kevina/CodingProjects/hutch/website/assets/ + .pipeline/marketing/2026-10/** only.
Out of scope: every other file — especially website CSS sources/generated CSS (no new classes; ship styling INSIDE the SVG if needed), llms.txt (approved state), downloads.json (P2-04), robots.txt (D-04), README.md, src/**, app/**, and the other agent's uncommitted/untracked files (never stage; use `git show HEAD:<file>` for reads).

What to do:
- Create the og:image asset per the approved route: >=1200x630, <300 KB, references ONLY committed assets (no external URLs, no third-party fonts — input.css:5 contract; embed fonts as paths or use the committed woff2 via the site only, since SVG-in-og-image cannot load web fonts reliably: prefer system/standalone vector text or a raster export).
- Add head tags in website/index.html: og:image, og:image:alt, og:image:width/height, og:site_name, twitter:card (summary_large_image), twitter:title, twitter:description, twitter:image. DO NOT add og:url or twitter:url (domain-gated, B-01). og:title/og:description/og:type already exist (index.html:10-12) — do not duplicate or reword them without a register reason.
- If the change is a visible-copy change per C-24, refresh JSON-LD dateModified (index.html:37) — currently 2026-10-28; same-day edits keep the same value.
- Verify like an adversary: file size + dimensions of the asset (identify/wc), audit_site.py exit 0 with head inventory showing new tags, FAQ parity 20/20, UA parity 6/6; render the SVG/PNG in the browser at 1440 and 390 and LOOK at the capture; check the file references zero external URLs (grep for https:// in the asset).
- Run `npm run check:agent` and report honestly: currently RED for B-07 (pre-existing, other workstream: tests/test_commit_attribution.py 419 lines from bee491d5) — report the violation, do NOT fix those files.
- Commit locally (one commit): `seo(slice-s-c): add og:image asset + social meta tags`. Stage website/index.html + the one new asset + .pipeline/marketing/ only. Do not push.
- Update EVIDENCE.md (AC -> evidence incl. inspected captures), CHANGES.md, HANDOFF.md, NEXT-PROMPT.md (next slice: S-d remains domain-gated — if B-01 still unresolved, the next session should be a review/handoff session or the human's domain decision), CLAIM-REGISTER.md (review-log entry; any card strings must come from approved rows).

Do NOT start S-d. Do not add og:url/canonical/sitemap (would need a fake URL — prohibited). Do not flip the H1. Do not add any claim not in the register. Do not push/deploy/merge.

Acceptance (all must be true, with evidence paths):
- Asset >=1200x630, <300 KB, zero external URL references; card text = approved register wording only.
- Head inventory in s-b/s-c crawl shows og:image + twitter:* tags; og:url absent; audit_site.py exit 0; FAQ parity 20/20.
- Asset render captured AND inspected (observations recorded in EVIDENCE.md).
- git show of the commit contains only website/index.html + website/assets/<one-file> + .pipeline/marketing/2026-10/**.
- EVIDENCE.md maps each AC to its evidence; HANDOFF.md updated; not pushed.
