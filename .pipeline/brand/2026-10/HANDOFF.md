# HANDOFF.md — Session-End Handoff (Run 6: Clean-Sheet Mark Design, Human Pick & Complete Identity Package)

- **Pipeline root:** `.pipeline/brand/2026-10/`
- **Date:** `2026-10-29`
- **Run completed:** Run 6 — Clean-sheet mark design from the triad brief (`Grokbot` + `Pac-Man ghost` + `meaning of hutch`), human pick recorded (`D54` — Direction B `"Visor Hutch"`), production asset package (`assets/production/`), press kit (`assets/press-kit/`), production WOFF2 subset + verbatim OFL 1.1 licence (`assets/concepts/fonts/`), `BRAND-GUIDELINES.md`, `VALIDATION-MATRIX.md`, `PROVENANCE-REGISTER.md`, and `IP-CLEARANCE.md` updates
- **Write scope enforced:** `.pipeline/brand/2026-10/**` only. Zero files written outside `.pipeline/brand/2026-10/`; zero pushes or deploys.

---

## 1. Headline Summary for the Maintainer

1. **Name (`DECIDED`, D38):** **`Hutch`** retained by the maintainer on `2026-10-29` with full visibility into the confirmed UK Class 9/42 registration (`UK00003711474`). Pre-screen only; nothing is clearance.
2. **Wordmark (`DECIDED`, D42):** Lowercase **`hutch`** + emerald period (`.`), set in **Bricolage Grotesque** (`weight 800`, `-0.03em` tracking, optical ink-trap joins). Production WOFF2 subset (`bricolage-grotesque-latin-800.woff2`, `24,040 B`, sha256 `493fdff834574e538d2a9d31691383180c0d39179d95511092dd80e469601162`) and verbatim upstream OFL 1.1 licence (`OFL-bricolage-grotesque.txt`, `4,403 B`, sha256 `4b5a7d8f37f56026fe2ffefab5bbbf0efdc0fb2553a1481fe3c0958dedaa292b`) are staged in `.pipeline/brand/2026-10/assets/production/fonts/` and `.pipeline/brand/2026-10/assets/press-kit/fonts/`. Outlined `<path>` wordmark and horizontal lockup SVGs (`zero <text> dependency`) plus `@2x` PNGs are generated.
3. **Colour system (`DECIDED`, D43 / `COLOUR-SYSTEM.md`):** Measured contrast table complete (`#34d399` on `#0a0a0c` = `10.35:1` PASS; `#34d399` on `#f8fafc` = `1.65:1` FAIL -> light surfaces use `#047857` at `5.32:1` on `#f8fafc` / `4.69:1` on `#eef2f6`). Semantic collision between `--brand` (`#34d399`) and `--ok`/`--success` (`#34d399`) is documented with non-colour redundant cue requirements (`R10`).
4. **Mark (`DECIDED`, D53/D54 — `2026-10-29`):**
   - Following the human's Run 5 rejection of all Rounds 1–12 marks (`D51`/`D52`, archived as non-candidates) and the human's Run 6 creative brief (*"Take inspiration from grokbot, the ghost from pacman and the maining of the word hutch"* [sic], `D53`), two clean-sheet directions were constructed to `PRINCIPLES.md` (`R1–R11`) with full coordinate sheets, redrawn Master (`>=32px`) and Small (`16–24px`) tiers, a real-surface test matrix, and a pre-recommendation `R1–R11` self-critique (`MARK-DIRECTIONS-RUN6.md`).
   - On `2026-10-29`, the maintainer reviewed both directions and **picked Direction B — "Visor Hutch"** (`D54`):
     - **Outer container:** `1:1` optical square balance (`24.0u x 24.6u` Master; `26.0u x 26.4u` Small) combining a sheltered ghost-dome roof (`R = 11.6u` Master, `R = 12.6u` Small) with a **tangent-continuous 3-post / 2-burrow-arch base** (`3 x 4.40u` grounded feet + `2 x 5.40u` semicircular burrow arches = `24.0u`). Placing a solid post at `x = 16.0` eliminates any central-mouth pareidolia while reading unmistakably as both a classic arcade ghost skirt and a multi-bay hutch frame on legs.
     - **Interior move:** A single recessed **hutch-loft / Grokbot visor cutout** (`x = 6.80..25.20, y = 8.60..18.40` Master) housing **two positive-space inward-tilted (`-8 deg` left, `+8 deg` right) gleaming oval bot eyes** (`rx = 2.05, ry = 2.65` Master; `rx = 2.45, ry = 3.05` Small) with a `+0.30u` upward right-eye gaze toward the wordmark—visually uniting the 2D mark with Hutch's in-app bot avatars (`src/hutch/server/static/app.js:1452-1507` `ID_FACES`) and 3D marketing hero mascot (`website/assets/hutch-agent.webp`).
5. **Deliverables Owed (`COMPLETED`, D55/D56):**
   - `BRAND-GUIDELINES.md`: Complete 13-section canonical manual covering foundation, the picked "Visor Hutch" mark system (Master & Small redrawn coordinates, clear space, minimum sizes, misuse rules), wordmark, colour, typography, iconography, motion, surface applications, accessibility (`R10`), governance, legal/attribution, asset inventory, and changelog.
   - `assets/production/` & `assets/press-kit/`: **78 production and press-kit files** generated deterministically by `assets/build_production_package.py` and indexed with full SHA-256 checksums in `assets/production/PACKAGE-MANIFEST.json` (favicons `16/32/48` + multi-res `.ico` + `.svg`, `apple-touch-icon.png` `180x180`, PWA `192/512` `any`/`maskable`/`monochrome`, `site.webmanifest`, `og-card-1200x630.png`, `github-social-preview-1280x640.png`, `<path>`-outlined wordmarks and lockups across emerald/obsidian/paper/mono, `@2x` PNG renders, and `assets/press-kit/README.md`).
   - `VALIDATION-MATRIX.md` + `assets/production/validation-sheet.png`: 8-panel composite validation matrix inspected visually via `read_file` across dark/light themes, `16px–512px` zoom, maskable `r = 40%` safe zone, Brettel/Viénot CVD simulation (protanopia, deuteranopia, tritanopia), and ITU-R BT.709 grayscale print proxy, with honest limitations documented in Section 4.
   - `PROVENANCE-REGISTER.md` (Appendices C & D) & `IP-CLEARANCE.md` (Section 13): Dated `2026-10-29` screen rows (`R6-01`..`R6-05`), WIPO Vienna Tenth Edition candidate divisions (`04.05`, `07.01`, `26.01`, `26.04`), unresolved flags (`UF-R6-01`..`UF-R6-04`), and unchanged counsel escalation protocol. Nothing is claimed as cleared.

---

## 2. Complete Artifact Table (`.pipeline/brand/2026-10/`)

| File / Directory | Status | Purpose |
| :--- | :--- | :--- |
| `STRATEGY.md` | Complete (Run 4) | Brand strategy, positioning, audience, voice, architecture, naming evaluation, IP pre-screen scope |
| `APP-BRAND-AUDIT.md` | Complete (Run 2) | Audit of website (`website/`) and product dashboard (`src/hutch/server/`) surfaces and divergences |
| `ASSET-INVENTORY.md` | Complete (Run 2) | SHA-256 inventory of all existing brand/icon/font assets in the repository |
| `RESEARCH.md` | Complete (Run 4) | Competitor visual landscape and typography specimen comparison |
| `PRINCIPLES.md` | Complete (Run 5) | Researched logo/mark design methodology and the Hutch `R1–R11` design rulebook |
| `COLOUR-SYSTEM.md` | Complete (Run 4) | OKLCH + hex palette, measured WCAG AA/AAA contrast tables, CVD simulation, semantic vs brand token separation, print approximations |
| `MARK-DIRECTIONS-RUN6.md` | **Complete (Run 6)** | Two clean-sheet Run 6 directions (`A: Ghost-Post Hutch`, `B: Visor Hutch`), 1-page rationales tied to product truth and surfaces, coordinate construction tables (`>=32px` Master & `16–24px` Small), test matrix, pre-recommendation `R1–R11` self-critique, recommendation, and dated human pick (`D54`, `2026-10-29`) |
| `BRAND-GUIDELINES.md` | **Complete (Run 6)** | Canonical 13-section Brand & Identity Guidelines manual for the decided `"Hutch"` name (`D38`), lowercase `"hutch."` Bricolage Grotesque 800 wordmark (`D42`), colour system (`D43`), and picked `"Visor Hutch"` mark (`D54`) |
| `VALIDATION-MATRIX.md` | **Complete (Run 6)** | Surface-by-surface validation matrix, platform specification verification table (`2026-10-29` URLs), visual inspection checklist across all 12 rendered PNGs, and honest limitations log |
| `CONCEPT-LOG.md` | **Updated (Run 6)** | Sections `6.6–6.8` preserve the Rounds 1–12 post-mortem; Section `6.9` logs the Run 6 clean-sheet synthesis and human pick of Direction B (`D53–D55`) |
| `DECISION.md` | **Updated (Run 6)** | Decisions `D1–D56` and active blockers `B6–B10` (with `B6` resolved for mark selection on `2026-10-29` and remaining active only as the product/site/desktop integration gate) |
| `IP-CLEARANCE.md` | **Updated (Run 6)** | Sections `1–12` (wordmark/name screen) + Section `13` (dated `2026-10-29` figurative screen `R6-01`..`R6-05`, Vienna classification candidates, unresolved flags `UF-R6-01`..`UF-R6-04`) |
| `PROVENANCE-REGISTER.md` | **Updated (Run 6)** | First-party provenance and SHA-256 hashes for all Run 6 concept scripts/sheets (Appendix C) and the 78-file production/press-kit package + OFL licence text (Appendix D) |
| `HANDOFF.md` | **Updated (Run 6)** | This session-end handoff document |
| `NEXT-PROMPT.md` | **Updated (Run 6)** | Paste-ready prompt for Run 7 (product/site/docs/desktop integration slice, gated on explicit dated human authorisation) |
| `assets/concepts/render_run6_directions.py` | **Complete (Run 6)** | Deterministic generator for Run 6 construction sheets and real-surface test matrix |
| `assets/concepts/sheets/run6-*.png` | **Complete (Run 6)** | `run6-direction-a-construction.png`, `run6-direction-b-construction.png`, and `run6-test-matrix.png` |
| `assets/build_production_package.py` | **Complete (Run 6)** | Deterministic generator for the 78-file production & press-kit package (`assets/production/`, `assets/press-kit/`, `PACKAGE-MANIFEST.json`) |
| `assets/production/` | **Complete (Run 6)** | Platform icon pack (`favicon.ico`, `favicon.svg`, `favicon-16/32/48.png`, `apple-touch-icon.png`, `icon-192/512` `any`/`maskable`/`monochrome`, `site.webmanifest`), social cards (`og-card-1200x630.png`, `github-social-preview-1280x640.png`), `validation-sheet.png`, `mark/`, `wordmark/`, `lockup/`, `fonts/`, and `PACKAGE-MANIFEST.json` |
| `assets/press-kit/` | **Complete (Run 6)** | Self-contained press kit (`README.md`, `mark/`, `wordmark/`, `lockup/`, `social/`, `fonts/`) |
| `assets/archive/rejected-marks-2026-10-29/` | Frozen Archive (Run 5) | **NON-CANDIDATE ARCHIVE (`D51`/`D52`).** Rejected Rounds 1–12 marks. Never reuse. |

---

## 3. Active Blockers (`DECISION.md`)

| ID | Blocker | Status | Required Action |
| :--- | :--- | :--- | :--- |
| **B6** | **Product/site/docs/desktop integration gate** (mark pick portion resolved `2026-10-29` via `D54`) | **Active for integration only** | Integrating `.pipeline/brand/2026-10/assets/production/` into `website/`, `src/hutch/server/`, `docs/`, or `desktop/icons/` requires its own explicit dated human instruction (Run 7). |
| **B7** | **Confirmed UK Class 9/42 registration (`UK00003711474`) on the retained word `"Hutch"`** | **Active (owner-accepted risk, D38)** | Nothing in `.pipeline/brand/2026-10/` is trademark clearance. Any commercial filing, paid hosting, or indemnification representation requires qualified trademark counsel review (`IP-CLEARANCE.md` Section 7). |
| **B8** | **Official registry image-similarity search for the picked "Visor Hutch" figurative mark** | **Active (`IP-CLEARANCE.md` Section 13)** | Web discovery pre-screen (`R6-01`..`R6-05`) and Vienna classification candidates (`04.05`, `07.01`, `26.01`, `26.04`) are recorded; formal figurative image clearance across USPTO, EUIPO eSearch plus, UKIPO, CIPO, and WIPO Global Brand Database remains an unexecuted manual/counsel step. |
| **B9** | **`THIRD_PARTY_NOTICES.txt` font attribution drift (`Inter`/`JetBrains Mono` vs shipped `Geist`/`Bricolage Grotesque`)** | **Active (integration debt)** | Reconcile in Run 7 when integrating `bricolage-grotesque-latin-800.woff2` and `OFL-bricolage-grotesque.txt` into repository paths. |
| **B10** | **Cross-surface title/provenance drift (`"Hutch — Operator Console"` vs `"Hutch — Personal Assistant Control Plane"`, unreferenced `desktop/icons/`, `website/tokens.json` `zinc-950` drift)** | **Active (integration debt)** | Reconcile in Run 7 alongside asset deployment. |

---

## 4. Exact Regeneration & Verification Commands

```bash
# 1. Regenerate Run 6 concept construction sheets + test matrix (.pipeline/brand/2026-10/assets/concepts/sheets/)
uv run --frozen --no-sync python .pipeline/brand/2026-10/assets/concepts/render_run6_directions.py

# 2. Regenerate the 78-file production package, press kit, validation sheet & PACKAGE-MANIFEST.json
uv run --frozen --no-sync python .pipeline/brand/2026-10/assets/build_production_package.py

# 3. Run repository emoji & hygiene audit
uv run --frozen --no-sync python scripts/audit_emoji.py
```

---

## 5. Do Not Do (Standing Rules for Run 7+)

1. **Do NOT claim any name, wordmark, or figurative mark is "cleared", "safe", "trademarkable", or "non-infringing".** Maintain strict pre-screen legal language at all times.
2. **Do NOT touch `website/`, `src/`, `docs/`, or `desktop/` without an explicit dated human instruction authorising Run 7 integration.**
3. **Do NOT revive, present, or reuse anything from `.pipeline/brand/2026-10/assets/archive/rejected-marks-2026-10-29/`.**
4. **Do NOT scale the Master mark (`>=32px`) down to `16px–24px` without switching to the redrawn Small tier (`hutch-mark-small-*.svg`).**
5. **Do NOT use `#34d399` (`emerald-400`) as text or small-icon foreground on light surfaces (`#f8fafc` / `#eef2f6`);** always use `#047857` (`emerald-700`, `4.69:1–5.32:1` contrast).
