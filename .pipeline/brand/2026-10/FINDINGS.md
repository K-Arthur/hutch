# FINDINGS.md - Run 1 findings (lead synthesis)

Date: 2026-10-28 · Lead: DSH session "lead" · Evidence base: RESEARCH.md, APP-BRAND-AUDIT.md,
ASSET-INVENTORY.md (all reviewed and spot-checked by the lead against sources; spot-check
commands listed in section 7). Plan under review: docs/brand/00-PLAN.md on branch brand/plan.
No legal clearance, distinctiveness or non-infringement is claimed anywhere in this run.

## 1. Evidence-base state

- A Phase 0 brand program already exists (commits efc43c3e-45849dea, PR #11, "complete pending
  maintainer review") with a 32-item gap register and 26 explicit unknowns. Run 1 was executed,
  on human decision, as a REVIEW AND GAP-FILL of that program rather than a parallel build
  (DECISION.md D03).
- The brand/phase-1 session was reported stale/abandoned by the human; its capture evidence
  (docs/brand/evidence/research/README.md describes it) is NOT committed and lives in a worktree
  this pipeline must not read. All Phase 1 capture claims are therefore unavailable here (B3).

## 2. Phase 0 plan section A: 8 claims REFUTED against main (577e1154)

| # | Plan claim | Reality on main | Evidence |
|---|---|---|---|
| R-1 | base.html links 9 stylesheets | 10 | src/hutch/server/templates/base.html:10-25 (lead recount: 10) |
| R-2 | Studio shell loads 18 stylesheets | 15 | src/hutch/server/static/index.html:12-34 (lead recount: 15) |
| R-3 | tokens.css tiers = 31 primitives / 10 spaces / 8 motion | 28 / 12 / 7 (107 total is correct; plan's own breakdown sums to 109) | website/tokens.css counts, APP-BRAND-AUDIT 4 |
| R-4 | No image property in SoftwareApplication JSON-LD | "screenshot" image URL exists | website/index.html:43 (added for the 2026-10-28 launch) |
| R-5 | --fs-*/--s-* scale defined in hutch-tokens.css | defined in style.css:113,118; hutch-tokens.css has none | APP-BRAND-AUDIT 4 |
| R-6 | var(--color-semantic-brand) used in visible headers | marketing only; base.html uses --accent, Studio uses --brand | hutch.css:35 alias, APP-BRAND-AUDIT 4 |
| R-7 | Mascot has no usage rules | rules exist | docs/brand-assets.md:74-76, docs/marketing-site.md:207-209,239-247 |
| R-8 | Social card not generated from source artwork | reproducible token-driven renderer exists | .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py |

Named plan claims CONFIRMED: "hutch - hutch" title (base.html:7); exactly 6 inline hexagon
marks at the stated sizes; wordmark casing drift (hutch./hutch/Hutch, "(c) 2026 hutch");
daisyUI drift (app/src/input.css says v6, package.json pins ^5.7.47); tauri bundle.active=false;
brand-tokens.css byte-identical to tokens.css; hex-literal counts reproduced; all A.8 byte sizes
and A.9 absences verified. Consequence: the Phase 0 plan needs these corrections recorded in its
PR #11 review (B2).

## 3. Document conflicts surfaced for human decision (U01/U26 closed as "surfaced", not reconciled)

- Three "source of truth" documents define three different neutral ramps: design-system.md:84-89
  blue-tinted (#05070a/#080c12/#10161f/#171f2b/#f0f4f9) vs tokens.json (#09090b family) vs
  DESIGN.md (panel #101013, raised #17171b). No doc names a governing one.
- border-strong: 0.12 (DESIGN.md:16, design-system.md:93) vs 0.14 (design-system.md:63-64,
  tokens.json:53).
- Wordmark spec differs three ways: DESIGN.md:250 (1.125rem, weight 650) vs brand-assets.md:49
  ("extrabold") vs shipped markup (font-extrabold text-xl) vs social renderer (weight 620,
  capital-H "Hutch").
- Lockup: brand-assets.md:50 says 22px standard lockup; marketing header mark is 26px
  (website/index.html:234, lead-verified).
- docs/marketing-site.md contradicts itself on control radii ("8px" :256 vs "0px" :296); code
  matches the 8px wording.
- docs/research/icon-and-chat-interface-references-2026-10-10.md is STALE: claims Archivo type
  and that Outlook/Gmail/Calendar marks are not bundled - contradicted by brand-assets.md (Geist
  replaced Archivo), three later docs, and the shipped brands/ directory (11 files).
- website/tokens.json:2 asserts a "Primitive -> semantic -> component" tier that does not exist
  anywhere (U02 closed; the plan's suspicion confirmed).
- The plan itself reuses gap label C13 for two different gaps.

## 4. Asset provenance and licence-record gaps (ASSET-INVENTORY, lead-verified)

1. desktop/icons/icon.svg (295 B): same logomark concept, but stroke #28cd9d (documented accent
   is #34d399; #28cd9d appears in NO tracked doc), background #0f151e, different hex path,
   stroke-width 2.2 vs 2.5. Only provenance line: docs/realignment/desktop-production-2026-10-26.md:83.
   Author/date/tool/licence UNKNOWN. U07 closed as "mismatch at source".
2. ms-symbollockup_signin_dark.svg ships and renders in 4 app.js places (9863/9879/9899/9914)
   but has no row in docs/brand-assets.md - no source URL, retrieval date or use boundary.
3. website/THIRD_PARTY_NOTICES.txt:104 still lists removed Archivo files; no Geist entry - the
   shipped notices do not describe the shipped fonts (bears on plan C01).
4. Mascot provenance improved (original Blender render via scripts/render_hutch_agent.py, and
   hutch-agent.webp is byte-identical to frame f3-p1), but licence terms/copyright holder/usage
   rules remain unstated (C27 open). A byte-identical second 21-frame copy ships under
   src/hutch/server/static/agent/ (884,208 B), undocumented and apparently unreferenced on main.
5. Dashboard icon families (Jinja macro 34 glyphs, app.js map from :1370, inline shell glyphs)
   have no upstream attribution recorded anywhere (Lucide-like, UNVERIFIED - plan C19-adjacent).
6. Confirmed absent repo-wide: favicon files, apple-touch-icon, PWA manifest (C05/C06/C07
   unchanged). Favicon is an inline data-URI SVG, byte-identical across all three HTML roots.

## 5. Research verification (RESEARCH.md, 26 fetches total dated 2026-10-28)

- CONFIRMED from source (7): ogp.me (no pixel sizes in OGP, og:image:alt recommended), maskable
  40%-radius safe zone (C06), OFL FAQ items 1.1/1.12/1.13 (C01), Geist licence no-RFN, WIPO Nice
  13-2026 (with new 13-2027 edition listed), Python + Go trademark-separation model (C21),
  OpenRouter usage rules verbatim (brand-assets.md:14).
- Rust leg of C21 closed by lead retry: rustfoundation.org/policies/logo-policy-and-media-guide/
  live 200, Rust/Cargo logos CC-BY owned by the Foundation - use this canonical URL.
- Still OPEN: Anthropic press-kit URL (brand-assets.md:13) - redirect target and /press both 404,
  no press-kit reference on the live /news page; X/Facebook card dimensions (U17) unreachable
  (docs.x.com paths 404); parameter-level 5-second-test source (U23) unreachable (method page
  /videos/ is live - use it, not the 404 /articles/ URL).
- 6 citations returned HTTP 200 with client-rendered/truncated bodies and stay UNVERIFIED at
  execution time (Google favicon, GitHub social preview, Facebook sharing, Apple HIG app-icons,
  Android Play icons, USPTO fees): their plan rows are sourced only as of Phase 0 until
  re-checked with a rendering browser.

## 6. Unknowns closed or moved this run

- CLOSED: U01 (six docs read; conflicts surfaced in section 3), U02 (tokens.json full map),
  U06 (route map: 241 decorators across pages.py + pages_models.py:18 + pages_usage.py:20),
  U26 (no doc defines a different mark; the mismatch is the desktop icon variant, section 4.1).
- PARTIAL: U07 (depicted, hashed, mismatch quantified; authorship/licence still unknown), U23
  (method source live; parameters source missing), U17 (OGP protocol level confirmed; X/Facebook
  platform dimensions still unreachable).
- UNCHANGED / still human-or-counsel-bound: U09-U15, U18, U21-U25 (name search, territories,
  budget, counsel, PWA scope, tooling choices - see plan D and blockers B4).
- New facts the plan missed: website/downloads.json release manifest (all artifact lists empty),
  website/assets/captures/ set, routes split across three modules, light-theme variant
  hutch-theme-overrides.css shipped (U05 still open - no light contrast evidence), two daisyUI
  themes both named "hutch" differ, PRODUCT.md user-set quality gates never inventoried.

## 7. Lead spot-checks (independent verification of worker claims)

- git grep 28cd9d: present in desktop/icons/icon.svg twice; zero occurrences in docs/website/
  templates; #34d399 absent from icon.svg. (Worker C claim verified.)
- grep -c ms-symbollockup docs/brand-assets.md -> 0; 4 hits in app.js. (Verified.)
- THIRD_PARTY_NOTICES.txt:104 Archivo line present, no Geist line. (Verified.)
- link[rel=stylesheet] counts: base.html 10, static/index.html 15; tokens.json:2 asserts the
  component tier. (Worker B refutations verified.)
- website/index.html:234 header mark is size-[26px]. (Verified.)
- file(1): og-card 1200x630, github preview 1280x640, hutch-agent.webp 620x880. (Verified.)
- Plan title drift and prior-artifact reading done via git show/git log only; .worktrees/ untouched.

## 8. What Run 1 does NOT establish

No rendered/visual validation of anything (no browser capability - B1); no licence-compliance or
clearance conclusions; no claim that the plan's refuted rows were corrected in the plan itself
(corrections are recorded HERE and must be applied to PR #11 by its owner); no evidence about the
stale phase-1 session's uncommitted captures; external sources are point-in-time fetcher snapshots.

## 9. Gate 1 status

Artifacts required by the run machine (RESEARCH, APP-BRAND-AUDIT, ASSET-INVENTORY, FINDINGS) are
complete and reviewed. Gate 1 now requires HUMAN SIGN-OFF on this evidence base before Run 2,
plus a decision on which neutral-ramp document governs (section 3) and whether the Phase 0 plan
receives the section-2 corrections in PR #11.
