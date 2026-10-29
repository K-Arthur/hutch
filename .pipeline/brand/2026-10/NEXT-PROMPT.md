# NEXT-PROMPT.md - paste-ready continuation: Run 6 (mark design + the identity deliverables still owed)

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
                      ("Your bots. Your machine. Your rules."), MIT code, development preview, Linux-first
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (marketing site), src/hutch/server/ (dashboard)
DOCS_PATH:            docs/
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md,
                      website/tokens.json, docs/brand/03-CLEARANCE-PROTOCOL.md
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                <YYYY-MM-DD>
RUN:                  6
HUMAN_AUTHORITY:      local commits only; never push/deploy/merge without explicit instruction;
                      no integration into website/, docs/, src/ or desktop/ without its own dated
                      authorisation
CONCURRENCY:          write scope .pipeline/brand/** only; never read .worktrees/; stage only files
                      this session wrote
JURISDICTIONS:        US + EU + UK + Canada; Nice classes 9 and 42 (D13)
LICENCE_POSTURE:      open source (MIT code, OFL fonts), zero external spend (D15); IP risk owned by
                      the maintainer in writing (D20/D23/D28/D38); no funded counsel
BUDGET:               <=15 files read per pass; <=20 external fetches; one session
```

## Decided - do not reopen

1. Name RETAINED: "Hutch" (D38, 2026-10-29), decided with the confirmed UK class 9/42 overlap in
   front of the maintainer. Pre-screen only; nothing is clearance.
2. Wordmark DECIDED: lowercase "hutch" + emerald period, set in Bricolage Grotesque at weight 800
   (D42). Geist remains the product UI font. OFL 1.1 from google/fonts; production subset and licence
   file still owed.
3. Colour DECIDED (measured): COLOUR-SYSTEM.md. Emerald-400 on ink is the brand signal (10.35:1);
   emerald-400 on paper fails at 1.65:1, so light surfaces use emerald-700 (4.69:1). brand = success
   token collision flagged; CVD simulated; print approximations listed.
4. Mark NOT decided, and no earlier mark work may be reused. On 2026-10-29 the human rejected every
   concept from rounds 1-12 ("these are all horrible") and required the work archived as NON-candidates
   (D51, D52). The archive is .pipeline/brand/2026-10/assets/archive/rejected-marks-2026-10-29/
   (manifest inside). Do not present, revive, rename or lightly modify anything from it; it exists so
   you do not repeat rejected vocabulary.

## Read first, in this order

1. .pipeline/brand/2026-10/PRINCIPLES.md - the researched method and the R1-R11 rulebook
2. CONCEPT-LOG.md sections 6.6-6.8 - what was tried, why it failed, the rejected-vocabulary table
3. STRATEGY.md sections 6-7 - positioning and the IP pre-screen scope
4. COLOUR-SYSTEM.md sections 3-5 - findings, proposed system, what is undecided
5. DECISION.md - D38-D52 and blockers B6-B10
6. APP-BRAND-AUDIT.md section 6 and ASSET-INVENTORY.md - the real surfaces and what exists today

## Task A (priority): design the mark from a clean sheet

Hard requirements:
- Original by construction: no tracing, no stock, no AI image generation; provenance recorded per asset.
- Ground the mark in the subject before drawing any shape (PRINCIPLES R1). Subject: a hutch is a timber
  home for animals; product truth: local-first, multi-bot, governed autonomy, quiet chrome, a builder
  audience, one machine that holds the colony.
- Exactly one bold, memorable move (R2). Everything else quiet.
- Grid discipline and optical corrections documented in a construction sheet (R3-R5): coordinates,
  radii, gaps, overshoots; designed counterform.
- Two size tiers, redrawn not scaled: master >=32px and small 16-24px (R6).
- Test matrix: 16px light/dark and DPR2, 32/48, 512px icon, maskable crop, mono, lockup with the
  decided wordmark, grayscale print proxy (R7-R9).
- Present AT MOST TWO directions. For each: a one-page rationale tied to product truth and the surface
  list (favicon, dashboard header, desktop icon, PWA, Open Graph, README/terminal, press); the
  construction sheet; the test matrix; a self-critique against R1-R11 written BEFORE the
  recommendation. Then recommend one and record the human's pick with a date.
- Do not decide for the human. Do not produce production assets for a mark that has not been picked.

## Task B: the identity deliverables this run still owes

- BRAND-GUIDELINES.md: foundation, mark system (after the pick), wordmark, colour, typography,
  iconography, motion, applications, accessibility, governance, legal/attribution, assets/downloads,
  changelog.
- Press kit and production wordmark: Bricolage subset (woff2) with the OFL text shipped, outlined
  lockup SVG plus 2x PNGs.
- Platform icon package for the picked mark: favicon 16/32 + ICO, apple-touch 180, PWA 192/512
  (any, maskable, monochrome), Open Graph 1200x630, GitHub social 1280x640. Re-verify the per-platform
  numbers at execution time and record the source URL plus date.
- Validation matrix across real surfaces and both themes, zoom, CVD and print proxy; open and inspect
  every image; record limitations honestly.
- IP-CLEARANCE updates: dated screen rows for the picked shape (exact queries, sources, what was not
  found), unresolved flags, counsel escalation unchanged. Never claim clearance.
- HANDOFF.md and NEXT-PROMPT.md (Run 7); one coherent local commit with the docs(brand): prefix.

## Hard rules

- Legal voice: "screened", "found", "not found in the sources searched", "unresolved", "counsel/owner
  decision required", "not legal advice". Never: safe, cleared, trademarkable, non-infringing.
- No assets outside .pipeline/brand/**; no product, site, docs or desktop integration; no push.
- No emoji; do not read .worktrees/; do not stage other workstreams' uncommitted files.
- Stop rules: missing human pick for the mark, a newly confirmed core-class hit, an unresolved no-ship
  legal or cultural risk, a capability gap, or conflicting work -> record a blocker in DECISION.md and
  stop instead of proceeding on inference.

## Success criteria for Run 6

1. At most two mark directions built to PRINCIPLES, with construction sheets and test matrices; the
   human has picked one (or asked for a specific refinement, recorded).
2. BRAND-GUIDELINES.md and the press kit exist for the decided elements, and for the mark if picked.
3. Platform icon package and validation sheet for the picked mark; limitations recorded.
4. PROVENANCE-REGISTER and IP-CLEARANCE updated with the new assets; nothing claimed as cleared.
5. HANDOFF + NEXT-PROMPT (Run 7) written; one local commit; no integration, no push.
