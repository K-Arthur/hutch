# EVIDENCE — slice S-b (meta description trim + above-fold trust row) — 2026-10-28

Phase 6 proof per acceptance criterion. Slice scope: `website/index.html` (head description :7, JSON-LD dateModified :37, hero trust line :281) + this artifact dir.

## AC → evidence map

| # | Acceptance criterion (CONTENT-MAP §2 S-b / NEXT-PROMPT session 4) | Result | Evidence |
|---|---|---|---|
| 1 | Meta description ≤160 ch, "Development preview." intact, no mid-sentence cut | PASS (157 ch) | python length check this session (`desc_len: 157`, ends `'. Development preview.'`); independent confirmation from the adversarial crawl: `s-b-audit-stdout.txt` → `head.description_len = 157` |
| 2 | JSON-LD description (index.html:23) byte-unchanged | PASS | python regex check (`jsonld_desc_unchanged: True`); both JSON-LD blocks still parse (json.loads on both, this session + crawl `jsonld [list len 2]`) |
| 3 | dateModified updated per C-24 trigger (visible-copy change) | PASS (2026-10-28) | index.html:37 = "2026-10-28"; trigger = head description is SERP/share-visible copy + hero trust line added (decision S-b-04, DECISION.md) |
| 4 | Trust row added in human-approved Route A wording verbatim | PASS | index.html:281 `<p class="w-full text-xs text-ink-3">MIT-licensed · open source · Linux</p>` — first child of `section.hero .hero-actions`; wording matches P2-01 exactly; H1 (:278) and eyebrow (:277) untouched (git diff) |
| 5 | Trust row visible above the fold on desktop AND mobile captures; images LOOKED AT | PASS | `evidence/audit/shots/desktop-top.png` (1440×900: trust line at ~y620, buttons fully visible) and `shots/mobile-top.png` (390×844: single line at ~y438, both stacked buttons fully visible) — inspected this session; observations recorded below |
| 6 | Full visual gate incl. real focus-state capture (P1-06) + narrow/zoom states | PASS | `shots/s-b-focus-hero.png` — keyboard Tab (10 presses) to the hero "See the app" control shows a clear focus ring (white outline + brand-tint offset); `shots/narrow-zoom-proxy-top.png` (320 px: single line, no wrap); `shots/narrow-text-200.png` (200 % text: wraps to 2 lines, no clipping/overlap); `shots/s-b-hero-actions-clip-{desktop,mobile}.png` (2× close-ups: ~32 px above / ~12 px flex-gap below, no collision) — all inspected this session |
| 7 | audit_site.py exit 0; FAQ parity 20/20; UA parity 6/6 | PASS | exit 0 (shell); full report `evidence/audit/s-b-audit-stdout.txt` (stderr empty): ua_parity 6/6 UAs 200 with identical 97686 bytes (grew +47 B vs S-a's 97639 — the two copy edits); faq_parity 20/20, 0 mismatches; anchors_missing 0; only known 404s remain domain-gated sitemap.xml + security.txt (F-02/F-11) |
| 8 | `npm run check:agent` run + reported honestly | FAIL — pre-existing B-07, NOT caused by this slice | run this session: context hygiene names 1 violation, `tests/test_commit_attribution.py` (419 lines, committed in `bee491d5`, not in this diff); chain stops there (tool-contracts/constitution/agent-map not reached this run; S-a session recorded those separately). Same violation, same file as B-07. Owner: git-attribution/agent-map workstream |
| 9 | Commit touches website/index.html + .pipeline/marketing/2026-10/** only | PASS | see CHANGES.md S-b entry: `git show --stat` of the S-b commit lists 1 product file + pipeline artifacts; the other agent's dirty files (incl. .gitignore, AGENTS.md, src/hutch/server/**, app/**, tests/**) never staged |

## Visual inspection observations (recorded 2026-10-28, images read at full res)

- desktop-top.png: trust line renders as a quiet single-line qualifier directly above the CTA pair; spacing balanced (larger gap above from .hero-sub margin, tighter to buttons from the flex row-gap); muted tertiary gray reads as an honest footnote, not a badge — consistent with the site's no-hype tone. H1/eyebrow/buttons unchanged vs Phase-1 baseline shots.
- mobile-top.png: line stays unbroken at 390 px; both stacked full-width buttons remain comfortably above the 844 px fold.
- narrow-zoom-proxy-top.png (320×568): trust line still single-line and above the fold; the second stacked button's lower edge extends past 568 px — pre-existing consequence of `flex-direction: column` stacking at small widths (styles.css:260-261), marginally (~19 px) extended by the added line; primary CTA fully visible. No overlap or clipping.
- narrow-text-200.png: at 200 % root text the line wraps to two lines ("MIT-licensed · open / source · Linux") with no clipping, no overlap, no horizontal scroll — acceptable degradation.
- s-b-focus-hero.png: `:focus-visible` ring on the hero primary CTA is clearly visible (2 px focus-ring outline, offset per styles.css:34). Closes the P1-06 capture gap on a named control inside the changed region.
- Clips: text baseline clean; no collision with buttons; letterforms crisp at 2× DPR.

## Research/step notes
- Step 1 (copy-only) and Step 2 (rendered) split per NEXT-PROMPT session 4; Step 2 gated by Phase 3 answers (DECISION.md S-b-01..03) + human route approval (S-b-05, Route A, question tool 2026-10-28).
- No CSS rebuild needed: all three utility classes used (`w-full`, `text-xs`, `text-ink-3`) verified already present in the committed `website/app.css` (grep, this session); `npm run build:css:site` not run — no source CSS touched.
- Research captures for the route decision (posthog/ghost/supabase + blocked Figma Community attempt) live in scratch `/tmp/opencode/s-b-research/` — intentionally NOT committed (third-party screenshots are research material, not repo artifacts); sources + observations recorded in DECISION.md S-b-05.
- Real-query/AI-answer check: still deferred to S-d (B-01, no live domain). No invented queries used.
