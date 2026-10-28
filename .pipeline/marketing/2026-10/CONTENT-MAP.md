# CONTENT MAP — Hutch — 2026-10-28 (session 3, Phase 2)

> No CONTENT-MAP.md template exists in the pack; structure derived from 03-PHASE-2-STRATEGY.md §3 (audience/intent/page ownership) + §6 (content plan). Assumption recorded in DECISION.md (P2-03).
> Source-of-truth order (D-05): repo README/docs → site FAQ (canonical public summary) → llms.txt (derived). Machine files never originate claims.

## 1. Current surfaces (all 6 + gaps)

| Surface | Role | Audience intent | Owner | Claims carried | Gaps / defects | Verdict |
|---|---|---|---|---|---|---|
| `/` (index.html, one-pager) | definition + decision + transaction + answers + trust | informational / commercial / transactional / answers | campaign | C-01..C-14, C-18..C-26 | F-04 (no og:image/twitter cards), F-08 (description 198 ch), F-10 (H1 category — D-01), F-12 (trust words below fold), F-03/F-02 (canonical/sitemap — B-01) | KEEP; small repairs in S-b/S-c; hero per D-01 |
| `/robots.txt` | machine | crawler policy | campaign | C-20 | D-04 training-bot decision pending; sitemap directive impossible pre-domain (F-02) | KEEP; finalize after D-04 |
| `/llms.txt` | derived agent-navigation file (D-02: never an SEO claim) | answers | campaign | C-15..C-17 (stale), C-26 | F-01 (S1 contradiction: "private preview / source not public"), F-06 (no GitHub link) | REWRITE — slice S-a, P0 |
| `/downloads.json` | release manifest (rel=alternate index.html:8) | machine | **desktop release pipeline** (B-06 answered 2026-10-28, DECISION P2-04) | C-21 | F-07 (platform list readable as support; no status field) | KEEP untouched by campaign; status-field change = request to that workstream |
| `/THIRD_PARTY_NOTICES.txt` | legal/trust | trust | campaign | — | none measured | KEEP |
| README (GitHub) — off-site entity surface | answers + transaction (only public entity) | informational | maintainers | all (canonical source) | none measured (RECON §6: no contradictions vs site) | KEEP as canonical; not edited by this campaign |
| `/sitemap.xml` | machine | discovery | — | — | ABSENT (F-02) — cannot exist without domain | NEW, domain-gated (S-d) |
| `/security.txt` | trust | vulnerability reporting | — | — | ABSENT (F-11); needs human contact address + domain | NEW, domain-gated (deferred) |
| og:image + social meta | social citation | commercial | campaign | mirrors C-01..C-05 | F-04: shares render bare | NEW asset, slice S-c (domain-independent part only) |

Orphan/redirect/duplicate audit (RECON §3): none — 1 indexable URL, 10/10 anchors resolve, 0 duplicate metadata. Nothing to merge or redirect at current scale.

## 2. Ranked slices (after Phase 2 sign-off; one slice per session)

### S-a — llms.txt entity-surface repair (P0) — content-only
- Scope: apply the CLAIM-REGISTER F-01 wording (llms.txt:3, :9) + add the GitHub repository line (F-06). File touched: `website/llms.txt` only.
- Why first: F-01 is an S1 measured contradiction that makes AI agents answer "source is private" — false on the one fact every evaluator needs.
- AC: (1) `grep -in "private preview" website/llms.txt` → 0 hits; (2) llms.txt states source public + MIT + GitHub URL; (3) every fact in llms.txt matches README:5,16-22 and index.html:793,780 (spot-check C-05, C-11, C-12); (4) `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0 with `llms_txt.mentions_github=true`; (5) no other file changed (`git status` scoped).
- Rollback: `git revert` of the single commit (content-only, no build artifact).
- Dependency: CLAIM-REGISTER sign-off only. NOT blocked by B-06 (manifest untouched).

### S-b — on-page metadata trim (P1) — content-only
- Scope: meta description 198→~155 ch keeping "Development preview." intact (F-08); per D-01 outcome: either trust-row addition (Option A) or hero wording change (B/C). File: `website/index.html` head + (if approved) hero block.
- AC: description ≤160 ch, no mid-sentence cut, JSON-LD description parity unaffected (schema description is separate text, index.html:23); if hero changed: full visual gate (Phase 3) + audit_site.py green + FAQ parity 20/20 + `dateModified` updated (C-24 trigger).
- Rollback: `git revert`; screenshots in EVIDENCE.md allow pixel comparison.
- Dependency: D-01 sign-off (question asked this session).

### S-c — social cards (P2) — content + one new asset
- Scope: og:image asset (rendered from existing brand tokens/mascot — a new static asset, NOT a layout change), og:url/og:site_name + twitter:* tags (F-04). og:url requires the canonical domain → that half waits for S-d if B-01 unresolved.
- AC: image ≥1200×630, under 300 KB, references only committed assets; tags added without third-party requests (input.css:5 contract); audit_site.py head inventory shows new tags; visual capture of the asset itself inspected.
- Rollback: revert commit; asset removal is file deletion.
- Dependency: none for the asset; domain for og:url.

### S-d — domain-gated technical slice (blocked on B-01) — config + content
- Scope (only after human chooses domain + host): sitemap.xml + Sitemap directive in robots.txt (F-02), canonical link tag (F-03), GSC + Bing Webmaster verification (F-09/B-03), IndexNow readiness, deploy-host header checks (Content-Type/caching — P1-01 caveat), security.txt (F-11, needs contact address), AI-answer baseline run (RESEARCH §5 prompt set), CWV lab measurement (RECON §7 limitation).
- AC: canonical + sitemap live and mutually consistent; verification green in both consoles; baseline prompt set run ≥2 times across days with dated records; no regression in audit_site.py (re-run from live origin).
- Rollback: revert deploy commit; console properties remain (harmless).
- Dependency: B-01 (human domain/host), B-03 (human properties). D-04 answered 2026-10-28 (allow-all) — no robots.txt policy change needed at S-d. B-06 answered (desktop pipeline owns manifest) — downloads.json stays out of campaign scope.

### Deferred / not planned
- New content pages (blog, comparison pages, docs site): NOT planned — D-06 (no unique-value + earn-links plan yet), anti-patterns (scaled content abuse).
- downloads.json status field: B-06 answered 2026-10-28 — desktop release pipeline owns the manifest; a status-field change (F-07) is a REQUEST to that workstream, never a campaign edit.
- Training-crawler robots policy: RESOLVED 2026-10-28 (D-04 allow-all, status quo) — no slice needed.
- README edits: campaign does not edit README (maintainer surface; no contradictions found in RECON §6).

## 3. Internal-link and intent continuity (measured)
- All intents resolve within `/` anchored sections (RECON §3): no orphan pages exist, so no link debt to repay.
- Post-S-a: llms.txt → GitHub README link closes the AI-citation path (F-06).
- Post-S-d: canonical + sitemap create the first engine-submittable URL set.
