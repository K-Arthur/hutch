# RECON — Hutch — 2026-10-28 (session 2, Phase 1 audit)

## 1. Pre-flight
- Commit/branch/worktree: `e8d2fa1c` · main · no worktree (single-tree convention; research/audit only)
- Working tree state / other agents' changes: dirty with ANOTHER agent's uncommitted work in `src/hutch/server/**`, `app/**`, `package-lock.json`, `package.json`, `pyproject.toml`, `AGENTS.md`, `CONTRIBUTING.md`, `.gitignore` (all `M` in git status 2026-10-28). Never staged, never modified. This campaign writes `.pipeline/marketing/2026-10/**` only.
- Commands used (all re-runnable):
  - `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` → crawl report JSON (serves `website/` on :8899 via `python -m http.server`, fetches with 6 crawler UAs, validates links/anchors/JSON-LD/FAQ parity/downloads manifest)
  - `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/capture_site.py` → 14 screenshots (Playwright chromium, :8898)
  - one-off Playwright full-page re-capture past the site.js:41 3s reveal failsafe → `desktop-full-failsafe.png` (:8897)
  - `git show HEAD:pyproject.toml | grep version` → `version = "0.1.0"` (committed state, immune to the other agent's dirty tree)
  - `git show HEAD:package.json | grep -A3 scripts` → build commands
  - `grep -n -i quickstart README.md` → README:41 `## Quickstart` (GitHub anchor `#quickstart` valid)
  - `ls .github/workflows/` → ci.yml, desktop-linux.yml, native-platform.yml (no site deploy)
  - `git tag` → 3 dev tags (skills-lifecycle-prerebase*), no v0.1.x release tag
- SERVE_CMD (adapter UNKNOWN, resolved): `python -m http.server -d website` works (all fetches 200; note: this server sends no Content-Type on `/` — audit artifact, not a site defect; real host config is a deploy-phase check).
- E2E/VISUAL/A11Y (adapter UNKNOWN, resolved): repo e2e = python playwright under `tests/e2e/` (needs `uv` env; chromium cached in ~/.cache/ms-playwright). No site-specific e2e, no axe dependency, no a11y gate exists. Visual capture performed ad hoc via the scripts above (committed to evidence/, not a repo gate).
- Artifact/evidence paths: `.pipeline/marketing/2026-10/evidence/audit/{audit_site.py,capture_site.py,crawl-report.json,focus-trace.txt,shots/*.png}`

## 2. Stack and rendering model
- Framework / rendering / base path / routing: hand-written static HTML, single route `/`; no framework, no bundler, no router. CSS = Tailwind v4 + daisyUI v5 built once and committed (`website/src/input.css:1-5` states the "static, no-build, no-external-request surface" contract).
- Where primary content is rendered: fully in `website/index.html` (991 lines, 97,639 bytes). No hydration.
- JS dependency for content/nav: NONE for content. `website/site.js` is enhancement-only by its own contract (site.js:1-5): reveals, mobile drawer, tabs, pointer-reactive mascot. noscript fallback shows center nav (index.html:208-210). Content is crawlable and readable with JS disabled.
- Deploy target + bot/CDN configuration: UNKNOWN — no site deploy workflow exists (`.github/workflows/` = ci.yml, desktop-linux.yml, native-platform.yml). No live domain (owner-confirmed 2026-10-28; robots.txt:1-2). Crawler-UA parity measured against the local static server only: Googlebot/Bingbot/OAI-SearchBot/ClaudeBot/PerplexityBot all got 200 + identical 97,639 bytes (crawl-report.json `ua_parity`) — no bot-specific behavior anywhere in the source.
- Theming: intentionally dark-only single theme ("one dark theme" brand contract, `website/src/input.css:8`; `color-scheme: dark` at :26). No light scheme exists by design — light-mode capture is N/A, not missing.

## 3. Route and page inventory
| Route | Role | Template | Indexable | Canonical | Last meaningful update | Owner | Notes |
|---|---|---|---|---|---|---|---|
| `/` (index.html) | definition+discovery+decision+transaction+answers+trust (one-pager) | single bespoke | yes (no robots meta; robots.txt Allow) | absent (F-03) | 2026-10-26 (JSON-LD dateModified matches file mtime) | campaign | all six page roles served by anchored sections (#proof #receipts #workflow #runs #control #cases #get #faq) |
| `/robots.txt` | machine | — | n/a | — | 2026-10-24 | campaign | Allow-all; documents missing sitemap (robots.txt:1-2) |
| `/llms.txt` | machine (agent affordance, D-02) | — | n/a | — | 2026-10-24 | campaign | STALE vs product (F-01) |
| `/downloads.json` | machine (release manifest, linked via rel=alternate index.html:8) | — | n/a | — | stamped `?v=34dc6a4b` | desktop pipeline? | 4 platforms, 0 artifacts (F-07) |
| `/THIRD_PARTY_NOTICES.txt` | trust/legal | — | n/a | — | 2026-10-26 | campaign | linked footer index.html:979 |
| `/sitemap.xml` | machine | — | — | — | — | — | ABSENT (404; F-02) |
| `/security.txt` | trust | — | — | — | — | — | ABSENT (404; F-11) |
| docs/ (repo) | answers | markdown | repo-internal | — | active | maintainers | NOT deployed anywhere (A-01); README on GitHub is the off-site entity surface |

Indexable URL count today: 1. Orphans/redirects/404s: none internal — all 10 fragment anchors resolve (crawl `anchors_missing: []`), every fetched internal asset 200 (21 agent frames, 4 captures, fonts, css, js, notices).

## 4. Metadata and machine layer (measured on built output; crawl-report.json)
| Metric | Value | Detail/issue |
|---|---|---|
| Indexable URLs | 1 | single-page site |
| Duplicate titles/descriptions | 0 | one page |
| Missing/overlong metadata | title 57 ch ✓; description 198 ch | description over common ~155-160 ch snippet display (F-08) |
| Canonical conflicts | canonical ABSENT | expected pre-domain; add when domain exists (F-03, B-01) |
| Robots/sitemap consistency | robots Allow:/ ; sitemap 404 | documented blocker robots.txt:1-2 (F-02) |
| JSON-LD blocks/types/errors | 2 blocks, both parse clean | SoftwareApplication + FAQPage; FAQ parity 20/20 questions AND 20/20 answers byte-equal to visible `<details>` content after entity/whitespace normalization — zero mismatches |
| OG/Twitter issues | og:title/description/type only | NO og:image, og:url, og:site_name; NO twitter:* at all (F-04) |
| llms.txt/feeds/security.txt | llms.txt 200 but STALE (F-01); no feeds; security.txt 404 (F-11) | llms.txt never links github.com/K-Arthur/hutch (F-06) |
| H1 count / lang | 1 / `lang="en"` | both correct |
| Third-party requests | 0 | self-hosted font (Geist var woff2, preload), self-hosted JS only |

## 5. Schema inventory
| Type | Pages | Visible-content parity | Required props | Issues |
|---|---|---|---|---|
| SoftwareApplication | `/` (index.html:18-39) | name/OS/version/license/features all visible: OS "Linux" ↔ footer "Linux computer required today" (index.html:977); version 0.1.0 ↔ footer badge (index.html:955) ↔ committed pyproject `version = "0.1.0"`; license MIT ↔ footer (index.html:983); 6 featureList items all present in visible copy | name, description, applicationCategory, operatingSystem present | `dateModified` 2026-10-26 matches file mtime; refresh trigger must be registered in Phase 2 claim register (manual field today) |
| FAQPage | `/` (index.html:40-207) | EXACT: 20/20 Q+A match the visible FAQ `<details>` (index.html:842-921) | mainEntity complete | FAQ rich results were REMOVED by Google May 2026 (Phase 0 D-03): zero rich-result expectation; markup kept only while FAQ is visible; deprecation documented → claim register (F-05) |

## 6. Content and claims inventory
| Page | Intent | H1 | Key claims | Evidence pointer | Contradictions | Gap |
|---|---|---|---|---|---|---|
| `/` hero | "what is this / does it fit me" (developer, privacy-conscious) | "A little help with what's next." (index.html:278) | local-first, own machine, approvals before important actions, you choose models/apps | index.html:277-288; capture `desktop-top.png` | none | H1 carries no category words; they sit in eyebrow (index.html:277) + title tag (F-10) |
| `/` proof | credibility via real app capture | h2 (index.html:313) | "Real application", captured 2026-10-23, no provider call made | index.html:316-335 | none | — |
| `/` #runs | models/data/privacy decision content | h2 (index.html:495) | hosted providers receive prompts; state stays local; bubblewrap "not a VM" | index.html:496, 523-537 | none (honest limits match RESEARCH §8 forbidden-claims table) | — |
| `/` #get | transaction intent (get the software) | h2 (index.html:771) | "source is open"; no installers; Linux preview; availability table | index.html:771-827; capture `desktop-availability-open.png` | downloads.json lists mac/windows platforms, 0 artifacts (F-07) vs "macOS/Windows executors unavailable" (index.html:811) | manifest lacks per-platform status field |
| `/` #faq | answers intent | h2 (index.html:838) | 20 Q&As incl. comparison to Open WebUI/OpenClaw (index.html:852) — factual contrast per RESEARCH §8 replacement wording | index.html:842-921 | none internal | comparison facts need claim-register refresh triggers (Phase 2) |
| footer | trust | — | "Development preview", "v0.1.0", "MIT-licensed source" | index.html:954-955, 983 | none | — |
| llms.txt | agent answers | — | "private preview: source not public" | llms.txt:3, 9 | **CONTRADICTS** README:5 (public MIT-licensed) + index.html:793 ("public on GitHub") → F-01 S1 | also missing GitHub URL (F-06) |
| README (GitHub) | off-site entity page | — | development preview, Linux first, no PyPI, MIT | README:5, 16-22, 224-226 | none found vs site | — |

Version triangulation passed: pyproject (HEAD) 0.1.0 = JSON-LD softwareVersion (index.html:26) = footer badge (index.html:955). GitHub entity links triangulation passed: downloads.json `source.repository` = `https://github.com/K-Arthur/hutch` = the three HTML links (index.html:774, 775, 976); `#quickstart` anchor valid (README:41).

## 7. Technical baseline
| Metric | Home (`/`) | Notes |
|---|---|---|
| Initial HTML | 97,639 B uncompressed | single document contains all copy incl. 20-Q FAQ — extraction-friendly, but 97 KB HTML is chunky for a "hero page" (context for Phase 2; not a defect) |
| CSS | tokens.css 4,348 + app.css 43,509 + styles.min.css 38,706 = ~86.6 KB | minified+committed; 3 requests |
| JS | site.js 7,287 B, defer, self-hosted | enhancement-only contract (site.js:1-5) |
| Fonts | Geist latin var woff2 ~92 KB dir total, preload + `font-display` via system fallback stack | self-hosted, no external font requests |
| Images | hero mascot 40,300 B (560x680 webp, fetchpriority=high); captures 11-39 KB lazy; agent frame set 21×~42 KB = 912 KB loaded ONLY on fine pointers, on demand (site.js:93-158) | well-engineered; frame set never loads on touch/mobile |
| Approx cold-load (fast 3G-ish view) | ~320 KB across ~7 requests before lazy images | no third-party anything; lab CWV not run (no field origin; lab Lighthouse deferred to first live deploy — record as limitation) |
| Search index payload | n/a (no client search) | — |

## 8. Accessibility baseline
- From code + captures (axe NOT run — no axe dependency in repo; manual audit only; recorded as limitation):
  - Skip link first in DOM (index.html:213); landmarks header/main/footer present; one h1; section h2s orderly; dialog drawer labelled (index.html:245-256); tab pattern correct incl. arrow/Home/End keys (site.js:68-91).
  - Images: content images have meaningful alt (index.html:326, 449); decorative mascot `alt=""` (index.html:298, 930); SVG diagrams titled/desc'd (index.html:575-577).
  - Keyboard: focus trace through #get→#faq in DOM order, no traps (focus-trace.txt; note the trace was taken mid-page after scripted clicks, not from page top — limitation).
  - Motion: prefers-reduced-motion honored — 0 elements below opacity 0.99 in reduce context (focus-trace.txt last line); reveal failsafe at load+3s (site.js:41); bfcache/pageshow restore (site.js:42-44).
  - Text zoom: 320px viewport + 32px root font (≈200% proxy) — no clipping/overlap/overflow observed (`narrow-text-200.png`).
  - Contrast spot-check: body text #ededf0 / secondary #a3a3ae on #09090b and emerald #34d399 on near-black are comfortably AA+ (tokens.css:34, 56-57, 40).
  - Screen-reader spot-check: not run (limitation; no SR tooling in env).

## 9. Visual baseline
| Capture | Path | Observations (inspected 2026-10-28) |
|---|---|---|
| desktop 1440 top | shots/desktop-top.png | Hero: category eyebrow directly above H1, both CTAs above fold, mascot right. Trust words (MIT/open source) NOT visible above fold — appear at #get + footer (F-12). Clean hierarchy, no clipping. |
| desktop full (pre-failsafe) | shots/desktop-full.png | Reveal-gated sections captured at opacity 0 — capture-timing artifact, NOT a defect (script waited 1.2 s < 3 s failsafe). Kept as evidence of the reveal mechanism. |
| desktop full (post-failsafe) | shots/desktop-full-failsafe.png | Complete page renders: proof capture, benefit cards, workflow steps, response-style samples, models/app cards, approval flow, use cases, availability table, 20-item FAQ, CTA, footer. Density high but scannable; honesty banners prominent. |
| desktop FAQ open | shots/desktop-faq-open.png | Two-column FAQ, first answer open; full honest answer text readable incl. "public MIT-licensed source". |
| desktop availability open | shots/desktop-availability-open.png | Decision surface strong: "The source is open." + GitHub CTAs + preview banner + availability table ("Public source — Available"). |
| focus trace shot | shots/desktop-focus-nav.png | Filename misleading (capture landed on #get section after scripted tabbing; focus was inside opened details). Focus-ring rendering on a named control NOT captured — limitation. |
| tablet 768 | shots/tablet-top.png | Hero stacks cleanly, promises wrap to 2-col, no overflow. |
| mobile 390 top/full | shots/mobile-top.png, mobile-full.png | Header = logo + CTA + hamburger; hero stacks; CTAs full-width; promises list; mascot below fold. No clipping. |
| mobile drawer open | shots/mobile-drawer-open.png | Full-screen modal drawer, all 8 section links + "Check availability" CTA, Close button; page dimmed behind. |
| narrow 320 + 200% text | shots/narrow-zoom-proxy-top.png, narrow-text-200.png | No horizontal overflow; buttons stack; text readable. |
| reduced motion | shots/desktop-reduced-motion.png + trace | Content fully visible; 0 elements with opacity < 0.99. |

## 10. Measurement baseline
- GSC/Bing/analytics access: NONE exists (F-09). No verification files, no analytics script (site.js fully read — zero tracking; input.css:5 "no-external-request" contract). B-03 stays open: human must create properties when a domain exists.
- Conversion events: none instrumented. On-page conversion proxy = GitHub outbound clicks (index.html:774/775/936/976) — currently unmeasurable.
- AI answer samples: BLOCKED — site not live (B-01); prompt set v1 frozen in RESEARCH §5; capture deferred to first-live-deploy session.
- Server-log/bot observations: none (no deploy). Local UA-parity probe recorded in §2.

## 11. Concurrency and risk notes
- Worktrees/claims: none created; this campaign claims `.pipeline/marketing/2026-10/**` + (future slices, pending) `website/**`. Other agent's dirty files listed in §1 — do not stage.
- Recent changes touching these surfaces: last site commits `e8d2fa1c`/`c7645624` (marketing phase 0, artifacts only). `website/` untouched since 2026-10-26 (file mtimes).
- Risks for this campaign: (1) F-07 downloads.json may be generated/owned by the desktop release pipeline — change needs owner confirmation before any manifest edit; (2) the other agent's work touches server templates only, no overlap with `website/`; (3) everything canonical/sitemap/GSC remains domain-gated (B-01).
