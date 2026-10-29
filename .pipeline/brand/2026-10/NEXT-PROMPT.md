# NEXT-PROMPT.md - paste-ready continuation: Run 4

## Session input block

```
PROJECT:              Hutch - local-first, open-source multi-bot agent platform
REPO_ROOT:            /home/kevina/CodingProjects/hutch
SITE_APP_PATH:        website/ (marketing), src/hutch/server/ (dashboard)
DOCS_PATH:            docs/
NATIVE_TARGETS:       desktop (Tauri) + web
EXISTING_BRAND_DOCS:  docs/brand-assets.md, docs/design-system.md, DESIGN.md, PRODUCT.md,
                      docs/marketing-site.md, docs/brand/03-CLEARANCE-PROTOCOL.md
ARTIFACT_DIR:         .pipeline/brand/2026-10
TODAY:                <YYYY-MM-DD>
RUN:                  4
HUMAN_AUTHORITY:      local commits only; never push/deploy/merge without explicit instruction
CONCURRENCY:          write scope .pipeline/brand/** only; docs/brand/** needs a fresh explicit
                      assignment; never read .worktrees/; stage only files this session wrote
JURISDICTIONS:        CONFIRMED 2026-10-28 (D13): US + EU + UK + Canada; Nice classes 9 and 42 only
LICENCE_POSTURE:      open source (MIT code, OFL fonts, vendor marks per docs/brand-assets.md);
                      zero external spend (D15); IP risk owned by the maintainer in writing
                      (D20/D23/D28); no funded counsel until re-decided
BUDGET:               <=15 files read per pass; <=~30 min wall; <=15 external fetches
```

## Run 4 = capability + free checks, then text elaboration of D3/D4 and refinement of D1/D2;
## no asset files and no renders without a new dated human decision

Preconditions (read, do not assume):
1. DECISION.md shows D19 (direction), D22 (protocol signed and adopted), D24 (browser approved),
   D28 (stop condition accepted as a recorded risk; class check owed later), D29 (D3+D4 join the
   shortlist). If any is absent, re-read Run 3 first.
2. Read in this order: DECISION.md, CONCEPTS-D1-D2.md, IP-CLEARANCE.md (sections 0 and 10),
   CLEARANCE-PROTOCOL.md (sections 3-5 and 9), PROVENANCE-REGISTER.md, then STRATEGY.md 7.
3. No asset file, render, master SVG, favicon or manifest icon is produced this run unless the human
   gives a new explicit instruction. Text and specifications only.

## Step list

1. Capability step (first): run `uv sync --extra browser` (approved, D24) and verify the Playwright
   Chromium revision works. If it fails, record the exact error as B1 and continue text-only.
2. U21 free checks (D26): RDAP for hutch.com, hutch.app, hutch.ai, hutch.dev; GitHub org/user
   K-Arthur and repo name "hutch"; npm and PyPI package names; social handles (X, LinkedIn, YouTube,
   Bluesky). Record every result with URL + date in IP-CLEARANCE.md; a blocked check is unreachable,
   never clear.
3. Vienna codes: if the browser works, open the WIPO Vienna browser, record the edition number and the
   codes for a polygon outline and a centred dot with verbatim definitions; if blocked, record
   "unreachable" and carry it. Do not cite any code before this.
4. Class check (still valuable, no longer blocking text work): if the browser can reach the records,
   try USPTO serials 99695333 and 87196849 and UKIPO UK00003791602, UK00902129492, UK00915655715;
   record holder, status, classes, goods/services, dates, URL. If CAPTCHA blocks, record
   "unreachable - maintainer check owed (B7)". Do not state or imply clearance.
5. Elaborate D3 "Quiet Chrome" and D4 "Character Tiering" in text as CONCEPTS-D3-D4.md: D3 =
   colour-absent contexts (monochrome-first favicon, maskable/monochrome PWA layers, forced-colours,
   terminal/README), colour-job reservation rules; D4 = two-tier imagery doctrine (3D character in
   marketing, simple 2D identity in product), written usage rules, duplicate-copy resolution,
   provenance/licence position (C27 marketing-only per D25). Described, not drawn.
6. Refine CONCEPTS-D1-D2.md with anything learned: wordmark weight, small-size rule, lockup numbers,
   title/copy fixes, alias collapse. Keep it text-only.
7. Selection aid: a short written rubric (legibility, monochrome adaptability, category distinction,
   accessibility, migration cost, risk) comparing D1-D4 on the evidence, no scores invented -
   so the human can choose the Run 5 direction. No asset work.
8. Close-out: update DECISION.md; rewrite HANDOFF.md and NEXT-PROMPT.md (Run 5); commit one coherent
   unit, docs(brand): prefix, local only.

## Rules for this run

- No clearance, distinctiveness or non-infringement claims. "Pre-screen, not clearance"; "risk
  rated"; anything stronger only for what is documented.
- No asset generation, no renders, no product/source changes. Text only; any asset file needs a new
  dated human decision.
- Evidence convention: URL + retrieval date per source; every hit, miss and unreachable recorded
  with the exact query. A bot-blocked source is "unreachable", never "clear".
- No emoji. No docs/brand/** writes without a fresh assignment. Never read .worktrees/.
- Stop rules: missing human decision, a newly confirmed core-class hit, or a capability gap ->
  blocker in DECISION.md; a blocker is a valid outcome. A confirmed class 9/42 overlap still means
  escalate and reconsider before any asset work.

Deliverables: CONCEPTS-D3-D4.md; updated CONCEPTS-D1-D2.md; updated IP-CLEARANCE.md with the date
checks; updated DECISION.md (D30+, blockers); updated HANDOFF.md and NEXT-PROMPT.md (Run 5).
